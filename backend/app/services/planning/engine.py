"""Durable Storyboard Phase 1 planning-run engine.

Responsibilities:
- persisted run/step state transitions
- steps, events, provider invocation hashes
- idempotent create + invoke
- cancellation
- provider-neutral strict contracts
- deterministic mock provider
- automatic / manual / hybrid routing
- Luna → Terra → Sol escalation
- bounded transport retries
- localized semantic repair within total repair/time budgets
- resume-safe checkpoints
- sanitized errors; no hidden reasoning

Planning ends at an immutable AIProposalRecord with status pending_review.
It never applies proposals and never calls ComfyUI, FFmpeg, media queues,
audio generation, installers, arbitrary CLI, or model downloads.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.base import (
    OrchestrationRun,
    OrchestrationStep,
    ProviderProfile,
    StoryboardVersion,
    TaskProviderAssignment,
)
from backend.app.schemas.orchestration import (
    ActorType,
    CheckpointState,
    CreateOrchestrationRunRequest,
    EngineBudgets,
    EventType,
    FailureCategory,
    LogicalModelProfile,
    ManualTaskRoute,
    PlanningContext,
    PlanningTaskType,
    ProviderRequestContract,
    ProviderResponseContract,
    RoutingMode,
    RunStatus,
    StepStatus,
)
from backend.app.schemas.proposals import ProposalCreateRequest
from backend.app.services.ai_orchestration.schemas import (
    STORYBOARD_PROPOSAL_SCHEMA_NAME,
    ProposalType,
)
from backend.app.services.ai_orchestration.validator import content_hash_for
from backend.app.services.planning.contracts import (
    assert_no_execution_side_effects,
    build_proposal_payload,
    build_repair_instructions,
    merge_task_outputs,
    validate_provider_response,
)
from backend.app.services.planning.errors import PlanningError, PlanningErrorCode, sanitize_message
from backend.app.services.planning.hashes import (
    invocation_idempotency_key,
    proposal_content_hash,
    request_hash,
    response_hash,
    run_input_hash,
    sha256_hex,
    step_input_hash,
)
from backend.app.services.planning.provider import (
    MockPlanningProvider,
    PlanningProvider,
    TransportError,
    get_provider,
)
from backend.app.services.planning.provider_registry import (
    build_provider_registry,
    describe_providers,
)
from backend.app.services.planning.repository import PlanningRepository
from backend.app.services.planning.routing import (
    build_routing_snapshot,
    escalate_route,
    select_route,
)
from backend.app.services.planning.state_machine import is_run_terminal, is_step_terminal, utcnow
from backend.app.services import (
    proposal_service,
    storyboard_settings as storyboard_settings_service,
    storyboard_snapshot,
)


DEFAULT_PIPELINE: tuple[PlanningTaskType, ...] = (
    PlanningTaskType.story_structure,
    PlanningTaskType.character_bible,
    PlanningTaskType.chapter_outline,
    PlanningTaskType.scene_breakdown,
    PlanningTaskType.shot_list,
    PlanningTaskType.narration_plan,
    PlanningTaskType.prompt_package,
    PlanningTaskType.continuity_plan,
    PlanningTaskType.model_recommendation,
    PlanningTaskType.production_proposal,
)


class PlanningEngine:
    def __init__(
        self,
        db: Session,
        *,
        providers: dict[str, PlanningProvider] | None = None,
        auto_commit: bool = True,
    ) -> None:
        self.repo = PlanningRepository(db)
        self._provider_registry_is_explicit = providers is not None
        self.providers: dict[str, PlanningProvider] = dict(
            providers if providers is not None else build_provider_registry()
        )
        if MockPlanningProvider.identifier not in self.providers:
            self.providers[MockPlanningProvider.identifier] = MockPlanningProvider()
        self.auto_commit = auto_commit

    def _persisted_task_routes(
        self,
        story_id: UUID,
        task_types: list[PlanningTaskType],
    ) -> tuple[list[ManualTaskRoute], dict[str, dict[str, str]]]:
        """Resolve enabled per-story assignments to provider-neutral routes.

        Provider-profile rows contain public configuration metadata only.  The
        live registry remains authoritative for actual availability; these
        records choose among those registered providers and never construct a
        provider, read credentials, or execute a connection test.
        """
        allowed_tasks = set(task_types)
        rows = self.repo.db.execute(
            select(TaskProviderAssignment, ProviderProfile)
            .join(
                ProviderProfile,
                ProviderProfile.id == TaskProviderAssignment.provider_profile_id,
            )
            .where(
                TaskProviderAssignment.story_id == story_id,
                TaskProviderAssignment.enabled.is_(True),
            )
            .order_by(
                TaskProviderAssignment.priority.desc(),
                TaskProviderAssignment.task_type,
            )
        ).all()
        routes: list[ManualTaskRoute] = []
        evidence: dict[str, dict[str, str]] = {}
        for assignment, profile in rows:
            try:
                task = PlanningTaskType(assignment.task_type)
            except ValueError as exc:
                raise PlanningError(
                    PlanningErrorCode.ROUTING_FAILED,
                    f"Stored provider assignment has unsupported task_type={assignment.task_type}",
                ) from exc
            if task not in allowed_tasks:
                continue
            if profile.execution_mode == "disabled":
                raise PlanningError(
                    PlanningErrorCode.ROUTING_FAILED,
                    f"Provider profile '{profile.display_name}' is disabled",
                    details={"provider_profile_id": str(profile.id), "task_type": task.value},
                )
            routes.append(
                ManualTaskRoute(
                    task_type=task,
                    provider_identifier=profile.provider_identifier,
                    resolved_model=profile.provider_model_id,
                    rationale=assignment.rationale
                    or f"Persisted task assignment {assignment.id}",
                )
            )
            evidence[task.value] = {
                "assignment_id": str(assignment.id),
                "provider_profile_id": str(profile.id),
            }
        return routes, evidence

    # ==================================================================
    # Public API
    # ==================================================================

    def create_run(self, request: CreateOrchestrationRunRequest) -> tuple[OrchestrationRun, bool]:
        """Create a pending run. Returns (run, created). Idempotent on client key."""
        story = self.repo.lock_story_for_run_creation(request.story_id)
        project_settings = storyboard_settings_service.get_settings(
            self.repo.db, story.project_id
        )
        if request.prefer_hosted_providers and not project_settings.prefer_hosted_providers:
            raise PlanningError(
                PlanningErrorCode.ROUTING_FAILED,
                "Hosted planning providers are disabled by project policy",
            )
        if request.prefer_local_providers and not project_settings.prefer_local_providers:
            raise PlanningError(
                PlanningErrorCode.ROUTING_FAILED,
                "Local planning providers are disabled by project policy",
            )
        if (
            request.routing_mode != RoutingMode.manual
            and not request.prefer_local_providers
            and not request.prefer_hosted_providers
        ):
            raise PlanningError(
                PlanningErrorCode.ROUTING_FAILED,
                "Automatic planning requires at least one provider class allowed by project/run policy",
            )

        _, input_context_hash = storyboard_snapshot.build_snapshot_with_hash(
            self.repo.db, story.id
        )
        base_content_hash = input_context_hash
        if request.base_storyboard_version_id is not None:
            base_version = self.repo.db.get(
                StoryboardVersion, request.base_storyboard_version_id
            )
            if base_version is None or base_version.story_id != story.id:
                raise PlanningError(
                    PlanningErrorCode.VALIDATION_FAILED,
                    "Base storyboard version does not belong to the planning story",
                )
            if story.active_storyboard_version_id != base_version.id:
                raise PlanningError(
                    PlanningErrorCode.VALIDATION_FAILED,
                    "Base storyboard version is stale relative to the active story version",
                )
            base_content_hash = (
                base_version.content_hash
                or storyboard_snapshot.content_hash_for_snapshot(base_version.snapshot_json or {})
            )
            if base_content_hash != input_context_hash:
                raise PlanningError(
                    PlanningErrorCode.VALIDATION_FAILED,
                    "Live story content does not match the declared base storyboard version",
                )

        task_types = list(request.task_types) if request.task_types else list(DEFAULT_PIPELINE)
        if not task_types:
            raise PlanningError(PlanningErrorCode.VALIDATION_FAILED, "At least one task_type is required")
        if len(task_types) > request.max_steps:
            raise PlanningError(
                PlanningErrorCode.VALIDATION_FAILED,
                "task_types length exceeds max_steps",
                details={"task_count": len(task_types), "max_steps": request.max_steps},
            )

        stored_routes, stored_route_evidence = self._persisted_task_routes(
            story.id,
            task_types,
        )
        route_by_task = {route.task_type: route for route in stored_routes}
        for route in request.manual_routes:
            if route.task_type in set(task_types):
                route_by_task[route.task_type] = route
                stored_route_evidence.pop(route.task_type.value, None)
        effective_routes = [
            route_by_task[task]
            for task in task_types
            if task in route_by_task
        ]
        effective_mode = request.routing_mode
        if effective_routes and effective_mode == RoutingMode.automatic:
            effective_mode = RoutingMode.hybrid

        descriptors = describe_providers()
        descriptor_by_id = {
            item.provider_identifier: item for item in descriptors
        }
        for manual_route in effective_routes:
            descriptor = descriptor_by_id.get(manual_route.provider_identifier)
            if descriptor is None:
                raise PlanningError(
                    PlanningErrorCode.ROUTING_FAILED,
                    f"Provider '{manual_route.provider_identifier}' is not registered for planning",
                )
            if (
                self._provider_registry_is_explicit
                and manual_route.provider_identifier not in self.providers
            ):
                raise PlanningError(
                    PlanningErrorCode.ROUTING_FAILED,
                    f"Provider '{manual_route.provider_identifier}' is not available in this planning engine",
                    details={"availability_status": "not_configured"},
                )
            if (
                not self._provider_registry_is_explicit
                and descriptor.availability_status.value != "available"
            ):
                raise PlanningError(
                    PlanningErrorCode.ROUTING_FAILED,
                    f"Provider '{manual_route.provider_identifier}' is not available for planning",
                    details={"availability_status": descriptor.availability_status.value},
                )
            if (
                descriptor.privacy_classification == "hosted"
                and (
                    not project_settings.prefer_hosted_providers
                    or not request.prefer_hosted_providers
                )
            ):
                raise PlanningError(
                    PlanningErrorCode.ROUTING_FAILED,
                    f"Hosted provider '{manual_route.provider_identifier}' is disabled by project/run policy",
                )
            if (
                descriptor.privacy_classification == "local"
                and (
                    not project_settings.prefer_local_providers
                    or not request.prefer_local_providers
                )
            ):
                raise PlanningError(
                    PlanningErrorCode.ROUTING_FAILED,
                    f"Local provider '{manual_route.provider_identifier}' is disabled by project/run policy",
                )

        if request.idempotency_key:
            existing = self.repo.find_run_by_idempotency(request.story_id, request.idempotency_key)
            if existing is not None:
                return existing, False

        active = self.repo.find_active_run(request.story_id)
        if active is not None:
            raise PlanningError(
                PlanningErrorCode.ACTIVE_RUN_EXISTS,
                "An active orchestration run already exists for this story",
                details={"run_id": str(active.id), "status": active.status},
            )

        routing_snapshot = build_routing_snapshot(
            mode=effective_mode,
            manual_routes=effective_routes,
            prefer_local_providers=request.prefer_local_providers,
            prefer_hosted_providers=request.prefer_hosted_providers,
            transport_retry_limit=request.transport_retry_limit,
            time_budget_sec=request.time_budget_sec,
            task_types=task_types,
        )
        provider_catalog: list[dict[str, Any]] = []
        for descriptor in descriptors:
            if (
                self._provider_registry_is_explicit
                and descriptor.provider_identifier not in self.providers
            ):
                continue
            entry = descriptor.as_dict()
            if self._provider_registry_is_explicit:
                # An injected registry is authoritative for this engine
                # instance. Keep routing aligned with the provider objects the
                # caller supplied instead of advertising globally configured
                # providers that would bypass deterministic test/offline use.
                entry["availability_status"] = "available"
                entry["execution_mode"] = "injected"
            provider_catalog.append(entry)
        routing_snapshot["provider_catalog"] = provider_catalog
        routing_snapshot["input_context_hash"] = input_context_hash
        routing_snapshot["base_content_hash"] = base_content_hash
        routing_snapshot["persisted_task_assignments"] = stored_route_evidence
        routing_snapshot["requested_mode"] = request.routing_mode.value
        if request.idempotency_key:
            routing_snapshot["client_idempotency_key"] = request.idempotency_key

        default_provider_snapshot = {
            "schema_name": "planning.provider_catalog.v1",
            "providers": provider_catalog,
        }

        input_hash = run_input_hash(
            story_id=story.id,
            base_storyboard_version_id=request.base_storyboard_version_id,
            input_context_hash=input_context_hash,
            target_duration_sec=float(story.target_duration_sec),
            routing_snapshot=routing_snapshot,
            task_types=[t.value for t in task_types],
        )

        try:
            run = self.repo.create_run(
                story_id=story.id,
                base_storyboard_version_id=request.base_storyboard_version_id,
                requested_by=request.requested_by,
                routing_snapshot=routing_snapshot,
                default_provider_snapshot=default_provider_snapshot,
                target_duration_sec_snapshot=float(story.target_duration_sec),
                input_hash=input_hash,
                max_steps=request.max_steps,
                repair_budget=request.repair_budget,
            )
        except IntegrityError as exc:
            self.repo.rollback()
            active = self.repo.find_active_run(request.story_id)
            if active is not None:
                raise PlanningError(
                    PlanningErrorCode.ACTIVE_RUN_EXISTS,
                    "An active orchestration run already exists for this story",
                    details={"run_id": str(active.id), "status": active.status},
                ) from exc
            raise

        # Seed pending steps as resume-safe plan.
        for index, task in enumerate(task_types):
            self.repo.create_step(
                run_id=run.id,
                sequence_index=index,
                task_type=task.value,
                provider_identifier=None,
                logical_model=None,
                resolved_model=None,
                attempt_number=1,
                input_hash=None,
                metadata_json={"planned": True},
            )

        self.repo.add_event(
            run_id=run.id,
            event_type=EventType.run_created,
            actor_type=ActorType.user if request.requested_by else ActorType.system,
            actor_reference=request.requested_by,
            details={
                "input_hash": input_hash,
                "task_types": [t.value for t in task_types],
                "routing_mode": effective_mode.value,
            },
        )
        self._commit()
        return run, True

    def claim_run(
        self,
        run_id: UUID,
        *,
        owner_id: str | None = None,
        claim_token: str | None = None,
        lease_seconds: int = 600,
    ) -> tuple[OrchestrationRun, bool]:
        """Durably claim a pending or recoverable run without executing provider work.

        Returns ``(run, newly_started)``.  A running run is intentionally
        claimable only when its previous lease is absent or expired.
        """

        run = self.repo.get_run(run_id)
        if is_run_terminal(run.status):
            raise PlanningError(
                PlanningErrorCode.ALREADY_TERMINAL,
                f"Run is already terminal with status={run.status}",
                details={"run_id": str(run.id), "status": run.status},
            )
        if owner_id is None and claim_token is None:
            if run.status == RunStatus.running.value:
                return run, False
            self.repo.transition_run(run, RunStatus.running)
            self.repo.add_event(
                run_id=run.id,
                event_type=EventType.run_started,
                actor_type=ActorType.system,
                details={"started_at": utcnow().isoformat()},
            )
            self._commit()
            return run, True

        owner = owner_id or "sync-planning-engine"
        token = claim_token or uuid4().hex
        run, newly_started, acquired = self.repo.acquire_execution_lease(
            run_id,
            owner_id=owner,
            claim_token=token,
            lease_seconds=lease_seconds,
        )
        if not acquired:
            return run, False

        if newly_started:
            self.repo.add_event(
                run_id=run.id,
                event_type=EventType.run_started,
                actor_type=ActorType.system,
                details={
                    "started_at": utcnow().isoformat(),
                    "execution_owner_id": owner[:128],
                },
            )
        else:
            self.repo.add_event(
                run_id=run.id,
                event_type=EventType.run_resumed,
                actor_type=ActorType.system,
                details={
                    "current_step": run.current_step,
                    "execution_owner_id": owner[:128],
                },
            )
        self._commit()
        return run, newly_started

    def execute_claimed_run(
        self,
        run_id: UUID,
        *,
        resumed: bool = False,
        owner_id: str | None = None,
        claim_token: str | None = None,
        lease_seconds: int = 600,
    ) -> OrchestrationRun:
        """Execute a claimed run from its latest durable checkpoint."""

        run = self.repo.get_run(run_id)
        if is_run_terminal(run.status):
            return run
        if run.status == RunStatus.pending.value:
            run, _ = self.claim_run(
                run_id,
                owner_id=owner_id,
                claim_token=claim_token,
                lease_seconds=lease_seconds,
            )
        elif resumed:
            self.repo.add_event(
                run_id=run.id,
                event_type=EventType.run_resumed,
                actor_type=ActorType.system,
                details={"current_step": run.current_step},
            )
            self._commit()
        if owner_id and claim_token and not self.repo.owns_execution_lease(
            run.id,
            owner_id=owner_id,
            claim_token=claim_token,
        ):
            raise PlanningError(
                PlanningErrorCode.ACTIVE_RUN_EXISTS,
                "Planning run is leased to another worker",
                details={"run_id": str(run.id), "status": run.status},
            )
        return self._execute(
            run,
            owner_id=owner_id,
            claim_token=claim_token,
            lease_seconds=lease_seconds,
        )

    def start_run(self, run_id: UUID) -> OrchestrationRun:
        """Synchronous compatibility entry point for service-level callers."""

        owner_id = "sync-planning-engine"
        claim_token = uuid4().hex
        run, newly_started = self.claim_run(
            run_id,
            owner_id=owner_id,
            claim_token=claim_token,
        )
        if run.execution_claim_token != claim_token:
            raise PlanningError(
                PlanningErrorCode.ACTIVE_RUN_EXISTS,
                "Planning run is already leased to another worker",
                details={"run_id": str(run.id), "status": run.status},
            )
        return self.execute_claimed_run(
            run.id,
            resumed=not newly_started,
            owner_id=owner_id,
            claim_token=claim_token,
        )

    def cancel_run(
        self,
        run_id: UUID,
        *,
        reason: str | None = None,
        requested_by: str | None = None,
    ) -> OrchestrationRun:
        run = self.repo.get_run(run_id)
        if is_run_terminal(run.status):
            raise PlanningError(
                PlanningErrorCode.ALREADY_TERMINAL,
                f"Cannot cancel terminal run status={run.status}",
                details={"run_id": str(run.id), "status": run.status},
            )

        # Mark a cancel requested flag so in-flight execute loop stops at checkpoint.
        snap = dict(run.routing_snapshot_json or {})
        snap["cancel_requested"] = True
        snap["cancel_reason"] = sanitize_message(reason or "canceled by user")
        snap["cancel_requested_by"] = requested_by
        run.routing_snapshot_json = snap
        self.repo.db.add(run)

        # Cancel pending/running steps.
        for step in self.repo.get_steps(run.id):
            if not is_step_terminal(step.status):
                target = StepStatus.canceled
                if step.status == StepStatus.pending.value:
                    self.repo.transition_step(
                        step,
                        target,
                        error_category=FailureCategory.canceled.value,
                        error_message=reason or "canceled",
                    )
                elif step.status == StepStatus.running.value:
                    self.repo.transition_step(
                        step,
                        target,
                        error_category=FailureCategory.canceled.value,
                        error_message=reason or "canceled",
                    )
                self.repo.add_event(
                    run_id=run.id,
                    step_id=step.id,
                    event_type=EventType.step_canceled,
                    actor_type=ActorType.user if requested_by else ActorType.system,
                    actor_reference=requested_by,
                    details={"reason": sanitize_message(reason or "canceled")},
                )

        self.repo.transition_run(
            run,
            RunStatus.canceled,
            failure_category=FailureCategory.canceled.value,
            failure_message=reason or "canceled by user",
        )
        self.repo.add_event(
            run_id=run.id,
            event_type=EventType.run_canceled,
            actor_type=ActorType.user if requested_by else ActorType.system,
            actor_reference=requested_by,
            details={"reason": sanitize_message(reason or "canceled by user")},
        )
        self._commit()
        return run

    def get_run(self, run_id: UUID) -> OrchestrationRun:
        return self.repo.get_run(run_id)

    def get_run_detail(self, run_id: UUID) -> dict[str, Any]:
        run = self.repo.get_run(run_id)
        return {
            "run": run,
            "steps": self.repo.get_steps(run_id),
            "events": self.repo.get_events(run_id),
            "invocations": self.repo.get_invocations(run_id),
            "proposals": self.repo.get_proposals_for_run(run_id),
        }

    def list_runs_for_story(self, story_id: UUID) -> list[OrchestrationRun]:
        from sqlalchemy import select
        from backend.app.db.base import OrchestrationRun as OR

        return list(
            self.repo.db.scalars(
                select(OR).where(OR.story_id == story_id).order_by(OR.created_at.desc())
            )
        )

    # ==================================================================
    # Execution loop
    # ==================================================================

    def _execute(
        self,
        run: OrchestrationRun,
        *,
        owner_id: str | None = None,
        claim_token: str | None = None,
        lease_seconds: int = 600,
    ) -> OrchestrationRun:
        self._renew_execution_lease(
            run,
            owner_id=owner_id,
            claim_token=claim_token,
            lease_seconds=lease_seconds,
        )
        budgets = self._budgets_from_run(run)
        budgets.started_monotonic = time.monotonic()
        context = self._build_context(run)
        _, live_context_hash = storyboard_snapshot.build_snapshot_with_hash(
            self.repo.db, run.story_id
        )
        expected_context_hash = str(
            (run.routing_snapshot_json or {}).get("input_context_hash") or ""
        )
        if not expected_context_hash or live_context_hash != expected_context_hash:
            self._fail_run(
                run,
                FailureCategory.validation,
                "Story content changed after the planning run was created; create a new run",
                details={
                    "expected_input_context_hash": expected_context_hash or None,
                    "actual_input_context_hash": live_context_hash,
                },
            )
            return self.repo.get_run(run.id)
        context_hash = sha256_hex(context.model_dump(mode="json"))
        task_outputs: dict[str, dict[str, Any]] = self._load_completed_outputs(run)

        try:
            steps = self.repo.get_steps(run.id)
            # Group by sequence; prefer latest attempt.
            by_seq: dict[int, list[OrchestrationStep]] = {}
            for step in steps:
                by_seq.setdefault(step.sequence_index, []).append(step)

            for sequence_index in sorted(by_seq.keys()):
                self.repo.db.expire_all()
                run = self.repo.get_run(run.id)
                self._renew_execution_lease(
                    run,
                    owner_id=owner_id,
                    claim_token=claim_token,
                    lease_seconds=lease_seconds,
                )
                if self._cancel_requested(run) or run.status == RunStatus.canceled.value:
                    return run

                attempts = sorted(by_seq[sequence_index], key=lambda s: s.attempt_number)
                head = attempts[-1]

                if head.status == StepStatus.completed.value:
                    # Already done — resume safety.
                    continue
                if head.status in {StepStatus.skipped.value, StepStatus.canceled.value}:
                    continue
                if head.status == StepStatus.failed.value and not self._should_retry_failed_step(run, head):
                    # Terminal failure already recorded.
                    self._fail_run(run, FailureCategory.provider, head.error_message or "step failed")
                    return run

                self.repo.set_current_step(run, sequence_index)
                self._ensure_time_budget(budgets)

                completed_payload = self._run_step(
                    run=run,
                    step=head,
                    context=context,
                    context_hash=context_hash,
                    budgets=budgets,
                    previous_outputs=task_outputs,
                    owner_id=owner_id,
                    claim_token=claim_token,
                    lease_seconds=lease_seconds,
                )
                if completed_payload is None:
                    # Failed or canceled inside _run_step (run already updated).
                    return self.repo.get_run(run.id)

                self.repo.db.expire_all()
                run = self.repo.get_run(run.id)
                if self._cancel_requested(run) or run.status == RunStatus.canceled.value:
                    return run
                task_outputs[head.task_type] = completed_payload

                # Persist checkpoint after each completed step.
                self._write_checkpoint(
                    run,
                    sequence_index=sequence_index,
                    task_type=PlanningTaskType(head.task_type),
                    attempt_number=head.attempt_number,
                    context_hash=context_hash,
                    output_hash=sha256_hex(completed_payload),
                    budgets=budgets,
                    completed_task_types=list(task_outputs.keys()),
                    partial_payload={"task_outputs_keys": list(task_outputs.keys())},
                )

            # All steps completed — emit immutable proposal from production_proposal or merge.
            self.repo.db.expire_all()
            run = self.repo.get_run(run.id)
            self._renew_execution_lease(
                run,
                owner_id=owner_id,
                claim_token=claim_token,
                lease_seconds=lease_seconds,
            )
            if run.status != RunStatus.running.value:
                return run

            proposal_payload = self._finalize_proposal(run, context, task_outputs)
            self.repo.transition_run(run, RunStatus.completed)
            self.repo.add_event(
                run_id=run.id,
                event_type=EventType.run_completed,
                actor_type=ActorType.system,
                details={
                    "proposal_content_hash": proposal_content_hash(proposal_payload),
                    "awaiting_review": True,
                    "auto_applied": False,
                },
            )
            self._commit()
            return run

        except PlanningError as err:
            run = self.repo.get_run(run.id)
            if not is_run_terminal(run.status):
                self._fail_run(run, err.category, err.message, details=err.details)
            return self.repo.get_run(run.id)
        except Exception as exc:  # noqa: BLE001 — sanitize unexpected failures
            run = self.repo.get_run(run.id)
            if not is_run_terminal(run.status):
                self._fail_run(
                    run,
                    FailureCategory.internal,
                    sanitize_message(f"Internal planning failure: {exc}"),
                )
            return self.repo.get_run(run.id)

    def _run_step(
        self,
        *,
        run: OrchestrationRun,
        step: OrchestrationStep,
        context: PlanningContext,
        context_hash: str,
        budgets: EngineBudgets,
        previous_outputs: dict[str, dict[str, Any]],
        owner_id: str | None = None,
        claim_token: str | None = None,
        lease_seconds: int = 600,
    ) -> dict[str, Any] | None:
        task_type = PlanningTaskType(step.task_type)
        routing_snapshot = dict(run.routing_snapshot_json or {})
        decision = select_route(task_type=task_type, routing_snapshot=routing_snapshot)

        # Bind routing onto step if not set.
        step.provider_identifier = decision.provider_identifier
        step.logical_model = decision.logical_model.value
        step.resolved_model = decision.resolved_model
        step.input_hash = step_input_hash(
            run_id=run.id,
            sequence_index=step.sequence_index,
            task_type=task_type.value,
            context_hash=context_hash,
            attempt_number=step.attempt_number,
            logical_model=decision.logical_model.value,
            provider_identifier=decision.provider_identifier,
        )
        self.repo.db.add(step)
        self.repo.flush()

        if step.status == StepStatus.pending.value:
            self.repo.transition_step(step, StepStatus.running)
            self.repo.add_event(
                run_id=run.id,
                step_id=step.id,
                event_type=EventType.step_started,
                actor_type=ActorType.system,
                details={
                    "task_type": task_type.value,
                    "provider_identifier": decision.provider_identifier,
                    "logical_model": decision.logical_model.value,
                },
            )
            self.repo.add_event(
                run_id=run.id,
                step_id=step.id,
                event_type=EventType.routing_selected,
                actor_type=ActorType.router,
                details=decision.model_dump(mode="json"),
            )
            self._commit()

        repair_instructions: list[str] = []
        current_decision = decision
        attempt = step.attempt_number
        active_step = step

        while True:
            self.repo.db.expire_all()
            refreshed_run = self.repo.get_run(run.id)
            self._renew_execution_lease(
                refreshed_run,
                owner_id=owner_id,
                claim_token=claim_token,
                lease_seconds=lease_seconds,
            )
            if refreshed_run.status == RunStatus.canceled.value:
                return None
            if self._cancel_requested(refreshed_run):
                self.cancel_run(run.id, reason="cancel requested during step")
                return None

            self._ensure_time_budget(budgets)

            merged_prev = merge_task_outputs(previous_outputs)
            request = ProviderRequestContract(
                task_type=task_type,
                logical_model=current_decision.logical_model,
                resolved_model=current_decision.resolved_model,
                provider_identifier=current_decision.provider_identifier,
                context=context,
                constraints=dict((run.routing_snapshot_json or {}).get("provider_constraints") or {}),
                previous_output=merged_prev if merged_prev else None,
                repair_instructions=repair_instructions,
                attempt_number=attempt,
                idempotency_key=f"req_{run.id}_{active_step.id}_{attempt}",
            )

            req_hash = request_hash(request.model_dump(mode="json"))
            inv_key = invocation_idempotency_key(
                run_id=run.id,
                step_id=active_step.id,
                provider_identifier=current_decision.provider_identifier,
                request_hash_value=req_hash,
                attempt_number=attempt,
            )

            existing_inv = self.repo.find_invocation_by_key(inv_key)
            if existing_inv and existing_inv.status == "succeeded" and existing_inv.response_hash:
                # Idempotent replay — reconstruct from step metadata if present.
                cached = (active_step.metadata_json or {}).get("result_payload")
                if isinstance(cached, dict):
                    self.repo.transition_step(
                        active_step,
                        StepStatus.completed,
                        output_hash=existing_inv.response_hash,
                        metadata_patch={"idempotent_replay": True},
                    )
                    self.repo.add_event(
                        run_id=run.id,
                        step_id=active_step.id,
                        event_type=EventType.step_completed,
                        actor_type=ActorType.system,
                        details={"idempotent_replay": True, "output_hash": existing_inv.response_hash},
                    )
                    self._commit()
                    return cached

            inv = self.repo.create_invocation(
                run_id=run.id,
                step_id=active_step.id,
                provider_identifier=current_decision.provider_identifier,
                model=current_decision.resolved_model,
                idempotency_key=inv_key,
                request_hash=req_hash,
            )
            self.repo.add_event(
                run_id=run.id,
                step_id=active_step.id,
                event_type=EventType.invocation_started,
                actor_type=ActorType.provider,
                actor_reference=current_decision.provider_identifier,
                details={"invocation_id": str(inv.id), "request_hash": req_hash},
            )
            self._commit()

            response, transport_error = self._invoke_with_transport_retries(
                run=run,
                step=active_step,
                request=request,
                budgets=budgets,
            )

            # Cancellation is committed by a separate request/session while a
            # provider may be blocked.  Refresh after the provider returns so
            # this worker cannot overwrite the durable canceled run/step.
            self.repo.db.expire_all()
            refreshed_run = self.repo.get_run(run.id)
            self._renew_execution_lease(
                refreshed_run,
                owner_id=owner_id,
                claim_token=claim_token,
                lease_seconds=lease_seconds,
            )
            if (
                refreshed_run.status == RunStatus.canceled.value
                or self._cancel_requested(refreshed_run)
            ):
                refreshed_inv = self.repo.find_invocation_by_key(inv_key)
                if refreshed_inv is not None and refreshed_inv.status == "pending":
                    self.repo.complete_invocation(
                        refreshed_inv,
                        status="canceled",
                        error_category=FailureCategory.canceled.value,
                        error_message="run canceled while provider invocation was in flight",
                    )
                    self._commit()
                return None

            if transport_error is not None:
                self.repo.complete_invocation(
                    inv,
                    status="failed",
                    error_category=FailureCategory.transport.value,
                    error_message=transport_error.message,
                )
                self.repo.transition_step(
                    active_step,
                    StepStatus.failed,
                    error_category=FailureCategory.transport.value,
                    error_message=transport_error.message,
                )
                self.repo.add_event(
                    run_id=run.id,
                    step_id=active_step.id,
                    event_type=EventType.step_failed,
                    actor_type=ActorType.system,
                    details={"category": FailureCategory.transport.value},
                )
                self._fail_run(run, FailureCategory.transport, transport_error.message)
                return None

            assert response is not None
            resp_dump = response.model_dump(mode="json")
            resp_hash = response_hash(resp_dump)
            latency_ms = int((response.usage or {}).get("latency_ms") or 0)

            if response.status == "failed":
                err_msg = response.error.message if response.error else "provider failed"
                self.repo.complete_invocation(
                    inv,
                    status="failed",
                    response_hash=resp_hash,
                    latency_ms=latency_ms,
                    usage_json=response.usage,
                    finish_category=response.finish_category,
                    error_category=(response.error.category.value if response.error else FailureCategory.provider.value),
                    error_message=err_msg,
                )
                # Try escalation / repair path below via validation errors.
                validation_errors = [err_msg]
            else:
                validation_errors = validate_provider_response(response, expected_task=task_type)
                if not validation_errors:
                    try:
                        assert_no_execution_side_effects(response.payload)
                    except PlanningError as pe:
                        validation_errors = [pe.message]

                if not validation_errors:
                    self.repo.complete_invocation(
                        inv,
                        status="succeeded",
                        response_hash=resp_hash,
                        latency_ms=latency_ms,
                        usage_json=response.usage,
                        finish_category=response.finish_category or "stop",
                    )
                    self.repo.transition_step(
                        active_step,
                        StepStatus.completed,
                        output_hash=resp_hash,
                        metadata_patch={
                            "result_payload": response.payload,
                            "logical_model": current_decision.logical_model.value,
                            "provider_identifier": current_decision.provider_identifier,
                        },
                    )
                    self.repo.add_event(
                        run_id=run.id,
                        step_id=active_step.id,
                        event_type=EventType.invocation_succeeded,
                        actor_type=ActorType.provider,
                        actor_reference=current_decision.provider_identifier,
                        details={"response_hash": resp_hash},
                    )
                    self.repo.add_event(
                        run_id=run.id,
                        step_id=active_step.id,
                        event_type=EventType.step_completed,
                        actor_type=ActorType.system,
                        details={
                            "task_type": task_type.value,
                            "output_hash": resp_hash,
                            "attempt_number": attempt,
                        },
                    )
                    self._commit()
                    return response.payload

                self.repo.complete_invocation(
                    inv,
                    status="failed",
                    response_hash=resp_hash,
                    latency_ms=latency_ms,
                    usage_json=response.usage,
                    finish_category="validation_failed",
                    error_category=FailureCategory.validation.value,
                    error_message="; ".join(validation_errors)[:500],
                )
                self.repo.add_event(
                    run_id=run.id,
                    step_id=active_step.id,
                    event_type=EventType.invocation_failed,
                    actor_type=ActorType.provider,
                    actor_reference=current_decision.provider_identifier,
                    details={"errors": validation_errors[:10]},
                )

            # --- Semantic repair and/or Luna→Terra→Sol escalation ---
            repair_instructions = build_repair_instructions(validation_errors)
            escalated = escalate_route(current_decision, routing_snapshot=routing_snapshot)

            can_repair = budgets.can_repair() and (self.repo.get_run(run.id).repair_used < run.repair_budget)
            if not can_repair and escalated is None:
                self.repo.transition_step(
                    active_step,
                    StepStatus.failed,
                    error_category=FailureCategory.budget.value,
                    error_message="; ".join(validation_errors)[:500],
                    metadata_patch={"validation_errors": validation_errors[:10]},
                )
                self.repo.add_event(
                    run_id=run.id,
                    step_id=active_step.id,
                    event_type=EventType.budget_exhausted,
                    actor_type=ActorType.system,
                    details={
                        "repair_budget": run.repair_budget,
                        "repair_used": run.repair_used,
                    },
                )
                self.repo.add_event(
                    run_id=run.id,
                    step_id=active_step.id,
                    event_type=EventType.step_failed,
                    actor_type=ActorType.system,
                    details={"errors": validation_errors[:10]},
                )
                self._fail_run(
                    run,
                    FailureCategory.budget,
                    "Repair/escalation budget exhausted",
                    details={"validation_errors": validation_errors[:10]},
                )
                return None

            # Consume repair budget for localized semantic repair attempt.
            if can_repair:
                run = self.repo.bump_repair_used(self.repo.get_run(run.id))
                budgets.repair_used = run.repair_used
                self.repo.add_event(
                    run_id=run.id,
                    step_id=active_step.id,
                    event_type=EventType.semantic_repair,
                    actor_type=ActorType.repair,
                    details={
                        "instructions": repair_instructions,
                        "repair_used": run.repair_used,
                        "repair_budget": run.repair_budget,
                    },
                )

            if escalated is not None:
                self.repo.add_event(
                    run_id=run.id,
                    step_id=active_step.id,
                    event_type=EventType.routing_escalated,
                    actor_type=ActorType.router,
                    details={
                        "from": current_decision.logical_model.value,
                        "to": escalated.logical_model.value,
                        "provider_identifier": escalated.provider_identifier,
                    },
                )
                current_decision = escalated

            # New attempt row for durable audit (unique run/seq/attempt).
            attempt += 1
            active_step = self.repo.create_step(
                run_id=run.id,
                sequence_index=step.sequence_index,
                task_type=task_type.value,
                provider_identifier=current_decision.provider_identifier,
                logical_model=current_decision.logical_model.value,
                resolved_model=current_decision.resolved_model,
                attempt_number=attempt,
                input_hash=step_input_hash(
                    run_id=run.id,
                    sequence_index=step.sequence_index,
                    task_type=task_type.value,
                    context_hash=context_hash,
                    attempt_number=attempt,
                    logical_model=current_decision.logical_model.value,
                    provider_identifier=current_decision.provider_identifier,
                    repair_instructions=repair_instructions,
                ),
                metadata_json={
                    "repair": True,
                    "repair_instructions": repair_instructions,
                    "escalated_from": decision.logical_model.value,
                },
            )
            self.repo.transition_step(active_step, StepStatus.running)
            # Mark previous attempt failed if still running.
            if not is_step_terminal(step.status) and step.id != active_step.id:
                try:
                    self.repo.transition_step(
                        step,
                        StepStatus.failed,
                        error_category=FailureCategory.validation.value,
                        error_message="; ".join(validation_errors)[:500],
                    )
                except PlanningError:
                    pass
            step = active_step
            self._commit()

    # ==================================================================
    # Helpers
    # ==================================================================

    def _invoke_with_transport_retries(
        self,
        *,
        run: OrchestrationRun,
        step: OrchestrationStep,
        request: ProviderRequestContract,
        budgets: EngineBudgets,
    ) -> tuple[ProviderResponseContract | None, TransportError | None]:
        limit = int((run.routing_snapshot_json or {}).get("transport_retry_limit", budgets.transport_retry_limit))
        provider = get_provider(request.provider_identifier, self.providers)
        last_error: TransportError | None = None

        for transport_attempt in range(limit + 1):
            self._ensure_time_budget(budgets)
            started = time.monotonic()
            try:
                response = provider.invoke(request)
                # Annotate latency without storing raw payloads.
                usage = dict(response.usage or {})
                usage.setdefault("latency_ms", int((time.monotonic() - started) * 1000))
                response = response.model_copy(update={"usage": usage})
                # Re-validate contract model (forbids hidden reasoning fields).
                return ProviderResponseContract.model_validate(response.model_dump()), None
            except TransportError as te:
                last_error = te
                if transport_attempt < limit:
                    self.repo.add_event(
                        run_id=run.id,
                        step_id=step.id,
                        event_type=EventType.transport_retry,
                        actor_type=ActorType.system,
                        details={
                            "attempt": transport_attempt + 1,
                            "limit": limit,
                            "message": te.message,
                        },
                    )
                    self._commit()
                    continue
                return None, te
            except PlanningError as pe:
                return (
                    ProviderResponseContract(
                        task_type=request.task_type,
                        status="failed",
                        payload={},
                        error=pe.to_sanitized(),
                    ),
                    None,
                )
            except Exception as exc:  # noqa: BLE001
                return (
                    ProviderResponseContract(
                        task_type=request.task_type,
                        status="failed",
                        payload={},
                        error=PlanningError(
                            PlanningErrorCode.PROVIDER_FAILED,
                            sanitize_message(str(exc)),
                        ).to_sanitized(),
                    ),
                    None,
                )

        return None, last_error or TransportError("transport failed")

    def _finalize_proposal(
        self,
        run: OrchestrationRun,
        context: PlanningContext,
        task_outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        merged = merge_task_outputs(task_outputs)
        production = task_outputs.get(PlanningTaskType.production_proposal.value)
        story = self.repo.get_story(run.story_id)
        base_content_hash = str(
            (run.routing_snapshot_json or {}).get("base_content_hash")
            or (run.routing_snapshot_json or {}).get("input_context_hash")
            or ""
        )
        contract = build_proposal_payload(
            project_id=story.project_id,
            context=context,
            base_storyboard_version_id=run.base_storyboard_version_id,
            base_content_hash=base_content_hash,
            target_duration_sec=float(run.target_duration_sec_snapshot or context.target_duration_sec),
            merged=merged,
            production_payload=production,
        )
        payload = contract.model_dump(mode="json")
        assert_no_execution_side_effects(payload)
        summary = str(
            (production or {}).get("summary")
            or f"Planning proposal for {context.title}"
        ).strip()[:2000]
        validation = proposal_service.validate_create_request(
            self.repo.db,
            ProposalCreateRequest(
                proposal_type=ProposalType.storyboard_full_plan.value,
                summary=summary,
                payload=payload,
                story_id=run.story_id,
                orchestration_run_id=run.id,
                base_storyboard_version_id=run.base_storyboard_version_id,
                schema_name=STORYBOARD_PROPOSAL_SCHEMA_NAME,
            ),
        )
        if not validation.accepted or validation.errors:
            raise PlanningError(
                PlanningErrorCode.VALIDATION_FAILED,
                "Final storyboard proposal failed Phase-1 validation",
                details={"errors": list(validation.errors)[:20]},
            )
        content_hash = validation.content_hash or proposal_content_hash(payload)

        record = self.repo.create_proposal(
            proposal_type=ProposalType.storyboard_full_plan.value,
            payload=payload,
            story_id=run.story_id,
            orchestration_run_id=run.id,
            base_storyboard_version_id=run.base_storyboard_version_id,
            schema_name=STORYBOARD_PROPOSAL_SCHEMA_NAME,
            schema_version=1,
            content_hash=content_hash,
            payload_hash=content_hash_for(payload),
            input_context_hash=str(
                (run.routing_snapshot_json or {}).get("input_context_hash") or ""
            ),
            base_content_hash=base_content_hash,
            validation_status=str(validation.validation_status),
            validation_report_json=validation.report,
            warnings_json=list(validation.warnings),
        )

        # Attach proposal id to the production_proposal step when present.
        for step in self.repo.get_steps(run.id):
            if (
                step.task_type == PlanningTaskType.production_proposal.value
                and step.status == StepStatus.completed.value
            ):
                step.proposal_id = record.id
                self.repo.db.add(step)

        self.repo.add_event(
            run_id=run.id,
            event_type=EventType.proposal_created,
            actor_type=ActorType.system,
            details={
                "proposal_id": str(record.id),
                "content_hash": content_hash,
                "status": "pending_review",
                "auto_applied": False,
            },
        )
        self._commit()
        return payload

    def _build_context(self, run: OrchestrationRun) -> PlanningContext:
        story = self.repo.get_story(run.story_id)
        characters = self.repo.list_characters(story.id)
        snapshot = storyboard_snapshot.build_canonical_snapshot(self.repo.db, story.id)
        return PlanningContext(
            story_id=story.id,
            title=story.title,
            base_story=story.base_story,
            target_duration_sec=float(story.target_duration_sec),
            logline=story.logline,
            synopsis=story.synopsis,
            audience=story.audience,
            tone=story.tone,
            genre=story.genre,
            visual_style=story.visual_style,
            point_of_view=story.point_of_view,
            production_notes=story.production_notes,
            characters=[
                {
                    "id": str(c.id),
                    "name": c.name,
                    "role": c.role,
                    "physical_description": c.physical_description,
                    "speaking_style": c.speaking_style,
                    "consistency_prompt": c.consistency_prompt,
                }
                for c in characters
            ],
            existing_structure={
                "chapters": list(snapshot.get("chapters") or []),
                "characters": list(snapshot.get("characters") or []),
                "voices": list(snapshot.get("voice_profiles") or []),
            },
        )

    def _renew_execution_lease(
        self,
        run: OrchestrationRun,
        *,
        owner_id: str | None,
        claim_token: str | None,
        lease_seconds: int,
    ) -> None:
        if not owner_id or not claim_token:
            return
        if self.repo.renew_execution_lease(
            run.id,
            owner_id=owner_id,
            claim_token=claim_token,
            lease_seconds=lease_seconds,
        ):
            self._commit()
            return
        raise PlanningError(
            PlanningErrorCode.ACTIVE_RUN_EXISTS,
            "Planning execution lease is no longer owned by this worker",
            details={"run_id": str(run.id), "status": run.status},
        )

    def _budgets_from_run(self, run: OrchestrationRun) -> EngineBudgets:
        snap = run.routing_snapshot_json or {}
        return EngineBudgets(
            repair_budget=int(run.repair_budget),
            repair_used=int(run.repair_used),
            time_budget_sec=int(snap.get("time_budget_sec") or 300),
            transport_retry_limit=int(snap.get("transport_retry_limit") or 2),
        )

    def _ensure_time_budget(self, budgets: EngineBudgets) -> None:
        if budgets.started_monotonic is None:
            return
        elapsed = time.monotonic() - budgets.started_monotonic
        if elapsed > budgets.time_budget_sec:
            raise PlanningError(
                PlanningErrorCode.TIME_BUDGET_EXCEEDED,
                f"Planning time budget of {budgets.time_budget_sec}s exceeded",
                details={"elapsed_sec": int(elapsed)},
            )

    def _cancel_requested(self, run: OrchestrationRun) -> bool:
        return bool((run.routing_snapshot_json or {}).get("cancel_requested"))

    def _should_retry_failed_step(self, run: OrchestrationRun, step: OrchestrationStep) -> bool:
        return False

    def _load_completed_outputs(self, run: OrchestrationRun) -> dict[str, dict[str, Any]]:
        outputs: dict[str, dict[str, Any]] = {}
        for step in self.repo.get_steps(run.id):
            if step.status != StepStatus.completed.value:
                continue
            payload = (step.metadata_json or {}).get("result_payload")
            if isinstance(payload, dict):
                outputs[step.task_type] = payload
        return outputs

    def _write_checkpoint(
        self,
        run: OrchestrationRun,
        *,
        sequence_index: int,
        task_type: PlanningTaskType,
        attempt_number: int,
        context_hash: str,
        output_hash: str,
        budgets: EngineBudgets,
        completed_task_types: list[str],
        partial_payload: dict[str, Any],
    ) -> None:
        checkpoint = CheckpointState(
            run_id=run.id,
            sequence_index=sequence_index,
            task_type=task_type,
            attempt_number=attempt_number,
            input_hash=context_hash,
            last_output_hash=output_hash,
            repair_used=budgets.repair_used,
            logical_model=None,
            provider_identifier=None,
            partial_payload=partial_payload,
            completed_task_types=completed_task_types,
        )
        snap = dict(run.routing_snapshot_json or {})
        snap["checkpoint"] = checkpoint.model_dump(mode="json")
        run.routing_snapshot_json = snap
        self.repo.db.add(run)
        self.repo.add_event(
            run_id=run.id,
            event_type=EventType.step_checkpoint,
            actor_type=ActorType.system,
            details={
                "sequence_index": sequence_index,
                "task_type": task_type.value,
                "output_hash": output_hash,
                "completed_task_types": completed_task_types,
            },
        )
        self._commit()

    def _fail_run(
        self,
        run: OrchestrationRun,
        category: FailureCategory | str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        run = self.repo.get_run(run.id)
        if is_run_terminal(run.status):
            return
        cat = category.value if isinstance(category, FailureCategory) else str(category)
        self.repo.transition_run(
            run,
            RunStatus.failed,
            failure_category=cat,
            failure_message=message,
        )
        self.repo.add_event(
            run_id=run.id,
            event_type=EventType.run_failed,
            actor_type=ActorType.system,
            details={"category": cat, "message": sanitize_message(message), **(details or {})},
        )
        self._commit()

    def _commit(self) -> None:
        if self.auto_commit:
            self.repo.commit()
        else:
            self.repo.flush()
