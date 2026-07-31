"""Atomic apply for stored Storyboard Phase 1 proposals.

Single transaction:
- PostgreSQL row locks on story (+ base version when present)
- stale base version id + content hash checks
- non-committing mutations only
- one new immutable draft StoryboardVersion
- flush before active pointer update
- one audit event
- no external calls / no commit-per-entity helpers
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import AIProposalRecord, AuditLog, Story, StoryboardVersion
from backend.app.schemas.proposals import ProposalApplyRequest, ProposalApplyResult
from backend.app.services.ai_orchestration.schemas import STORYBOARD_PROPOSAL_TYPES, ProposalType
from backend.app.services.ai_orchestration.validator import ProposalValidator, content_hash_for
from backend.app.services.ai_orchestration.schemas import AIProposal
from backend.app.services import storyboard_mutations as mutations
from backend.app.services import storyboard_snapshot as snapshot_service
from backend.app.services.proposal_service import (
    ProposalNotFoundError,
    ProposalServiceError,
    ProposalStateError,
    _load_reference_catalogs,
    validate_storyboard_proposal_ownership,
)


def _now() -> datetime:
    return datetime.utcnow()


def _lock_story(db: Session, story_id: UUID) -> Story:
    story = db.scalar(select(Story).where(Story.id == story_id).with_for_update())
    if story is None:
        raise ProposalServiceError("Story not found.")
    return story


def _lock_version(db: Session, version_id: UUID) -> StoryboardVersion:
    version = db.scalar(
        select(StoryboardVersion).where(StoryboardVersion.id == version_id).with_for_update()
    )
    if version is None:
        raise ProposalServiceError("Base storyboard version not found.")
    return version


def apply_proposal(db: Session, proposal_id: UUID, request: ProposalApplyRequest) -> ProposalApplyResult:
    record = db.scalar(
        select(AIProposalRecord).where(AIProposalRecord.id == proposal_id).with_for_update()
    )
    if record is None:
        raise ProposalNotFoundError("Proposal not found.")

    if record.status == "applied":
        if record.applied_storyboard_version_id is None:
            raise ProposalStateError("Applied proposal is missing its storyboard version link.")
        applied_version = db.get(StoryboardVersion, record.applied_storyboard_version_id)
        if applied_version is None:
            raise ProposalStateError("Applied proposal storyboard version was not found.")
        return ProposalApplyResult(
            proposal_id=record.id,
            story_id=applied_version.story_id,
            new_storyboard_version_id=applied_version.id,
            version_number=applied_version.version_number,
            content_hash=applied_version.content_hash,
            status=record.status,
        )
    if record.status in {"rejected", "superseded"}:
        raise ProposalStateError(f"Cannot apply proposal in status '{record.status}'.")
    if record.validation_status == "invalid" or record.validation_errors:
        raise ProposalStateError("Cannot apply proposal with validation errors.")
    if record.status in {"generating", "validating", "applying"}:
        raise ProposalStateError(f"Cannot apply proposal in status '{record.status}'.")

    try:
        proposal_type = ProposalType(record.proposal_type)
    except ValueError as exc:
        raise ProposalServiceError(f"Unknown proposal_type: {record.proposal_type}") from exc
    if proposal_type not in STORYBOARD_PROPOSAL_TYPES:
        raise ProposalServiceError("Only storyboard Phase 1 proposals can be applied here.")

    payload = record.payload if isinstance(record.payload, dict) else {}
    computed_payload_hash = content_hash_for(payload)
    stored_payload_hash = record.payload_hash or record.content_hash
    if stored_payload_hash and stored_payload_hash != computed_payload_hash:
        raise ProposalStateError("Stored proposal payload hash does not match its immutable payload.")
    if record.story_id is None:
        raise ProposalServiceError("Proposal is missing its persisted story binding.")
    story = _lock_story(db, record.story_id)
    bound_story, _ = validate_storyboard_proposal_ownership(
        db,
        payload=payload,
        story_id=record.story_id,
        base_storyboard_version_id=record.base_storyboard_version_id,
        orchestration_run_id=record.orchestration_run_id,
    )
    if bound_story.id != story.id:  # defensive; helper already enforces this
        raise ProposalStateError("Proposal ownership changed while acquiring the story lock.")

    base_version_id = record.base_storyboard_version_id
    expected_base_id = request.expected_base_version_id or base_version_id
    base_version: StoryboardVersion | None = None
    base_snapshot = None
    base_hash = None

    if expected_base_id is not None:
        base_version = _lock_version(db, expected_base_id)
        if base_version.story_id != story.id:
            raise ProposalStateError("Base storyboard version does not belong to the proposal story.")
        base_snapshot = base_version.snapshot_json
        base_hash = base_version.content_hash

        # Stale base ID check against active pointer when one exists.
        if story.active_storyboard_version_id != expected_base_id:
            raise ProposalStateError(
                "Stale base storyboard version: active version id does not match proposal base."
            )

        expected_hash = (
            request.expected_base_content_hash
            or record.base_content_hash
            or payload.get("base_content_hash")
        )
        if expected_hash and base_hash and expected_hash != base_hash:
            raise ProposalStateError(
                "Stale base content hash: base storyboard content changed since proposal creation."
            )
        if expected_hash and base_hash is None:
            # Compute from snapshot when historical row lacks hash.
            computed = content_hash_for(base_snapshot or {})
            if expected_hash != computed:
                raise ProposalStateError(
                    "Stale base content hash: base storyboard content changed since proposal creation."
                )
            base_hash = computed

    if base_version_id is not None and expected_base_id is not None and base_version_id != expected_base_id:
        raise ProposalStateError("expected_base_version_id does not match proposal base_storyboard_version_id.")

    expected_live_hash = (
        request.expected_base_content_hash
        or record.base_content_hash
        or payload.get("base_content_hash")
    )
    if expected_live_hash:
        _, live_hash = snapshot_service.build_snapshot_with_hash(db, story.id)
        if live_hash != expected_live_hash:
            raise ProposalStateError(
                "Stale base content hash: live storyboard content changed since proposal creation."
            )

    catalogs = _load_reference_catalogs(db, story.project_id)
    ai_proposal = AIProposal(
        proposal_type=proposal_type,
        summary=f"apply:{record.id}",
        payload=payload,
        schema_name=record.schema_name,
        story_id=str(story.id),
        base_storyboard_version_id=str(base_version.id) if base_version else None,
        base_content_hash=base_hash,
    )
    validation = ProposalValidator().validate(
        ai_proposal,
        base_snapshot=base_snapshot,
        known_model_variant_ids=catalogs["model_variant_ids"],
        known_workflow_template_ids=catalogs["workflow_template_ids"],
        known_provider_profile_ids=catalogs["provider_profile_ids"],
        known_asset_ids=catalogs["asset_ids"],
    )
    if not validation.accepted or validation.errors:
        record.validation_errors = list(validation.errors)
        record.validation_status = "invalid"
        record.warnings_json = list(validation.warnings)
        record.validation_report_json = validation.report or {}
        db.add(
            AuditLog(
                entity_type="ai_proposal_record",
                entity_id=record.id,
                action="proposal_apply_rejected_invalid",
                details={"errors": validation.errors},
            )
        )
        db.commit()
        raise ProposalStateError("; ".join(validation.errors) or "Proposal revalidation failed.")

    story_payload = payload.get("story") or {}
    try:
        mutations.upsert_story_fields(story, story_payload)
        voices = mutations.upsert_voices(db, story.id, story_payload.get("voices") or [])
        characters = mutations.upsert_characters(
            db, story.id, story_payload.get("characters") or [], voices
        )
        shots = mutations.upsert_hierarchy(
            db,
            story.id,
            story_payload.get("chapters") or [],
            characters,
            voices,
            replace_identities=proposal_type == ProposalType.storyboard_full_plan,
        )
        mutations.build_snapshot(story, voices, characters, shots, payload)
        # Applying creates an editable draft.  Set lifecycle state before the
        # immutable draft snapshot is captured so it never embeds "approved".
        story.approval_state = "draft"
        story.updated_at = _now()
        db.flush()
        snapshot, snapshot_hash = snapshot_service.build_snapshot_with_hash(db, story.id)
    except mutations.MutationError as exc:
        db.rollback()
        raise ProposalStateError(str(exc)) from exc

    current_number = db.scalar(
        select(StoryboardVersion.version_number)
        .where(StoryboardVersion.story_id == story.id)
        .order_by(StoryboardVersion.version_number.desc())
        .limit(1)
    ) or 0

    new_version = StoryboardVersion(
        id=uuid4(),
        story_id=story.id,
        version_number=int(current_number) + 1,
        status="draft",
        snapshot_json=snapshot,
        source_proposal_id=record.id,
        created_by=request.applied_by,
        base_version_id=base_version.id if base_version else story.active_storyboard_version_id,
        content_hash=snapshot_hash,
    )
    db.add(new_version)
    # Flush-before-pointer: version row must exist before active pointer assignment.
    db.flush()

    # Proposal apply creates the next editable draft.  Preserve the most recent
    # approved immutable version as the valid approved baseline until this
    # draft is explicitly approved; approval owns the supersession transition.
    story.active_storyboard_version_id = new_version.id
    story.updated_at = _now()

    record.status = "applied"
    record.applied_at = _now()
    record.applied_storyboard_version_id = new_version.id
    record.reviewed_by = record.reviewed_by or request.applied_by
    record.reviewed_at = record.reviewed_at or record.applied_at
    record.content_hash = record.content_hash or content_hash_for(payload)
    record.validation_status = validation.validation_status
    record.validation_report_json = validation.report or {}
    record.warnings_json = list(validation.warnings)
    record.validation_errors = []

    # Exactly one audit/event for successful apply.
    db.add(
        AuditLog(
            entity_type="ai_proposal_record",
            entity_id=record.id,
            action="proposal_applied",
            details={
                "applied_by": request.applied_by,
                "story_id": str(story.id),
                "new_storyboard_version_id": str(new_version.id),
                "version_number": new_version.version_number,
                "base_storyboard_version_id": str(base_version.id) if base_version else None,
                "content_hash": snapshot_hash,
            },
        )
    )

    db.commit()
    db.refresh(record)
    db.refresh(new_version)

    return ProposalApplyResult(
        proposal_id=record.id,
        story_id=story.id,
        new_storyboard_version_id=new_version.id,
        version_number=new_version.version_number,
        content_hash=snapshot_hash,
        status=record.status,
    )
