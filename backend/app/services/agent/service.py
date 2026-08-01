"""Deterministic services for the CineForge contextual Operator."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import (
    AgentActionReceipt,
    AgentAuditEvent,
    AgentContextSnapshot,
    AgentMessage,
    AgentProposal,
    AgentSession,
    AgentToolCall,
    AuditLog,
    CreativeReviewNote,
)
from backend.app.schemas.agent import (
    AgentActionReceiptRead,
    AgentContextSnapshotRead,
    AgentMessageRead,
    AgentMessageTurnResponse,
    AgentProposalRead,
    AgentProviderHealth,
    AgentProviderModel,
    AgentProviderModelsResponse,
    AgentProposalApproveRequest,
    AgentProposalRejectRequest,
    AgentRiskClass,
    AgentSessionCreate,
    AgentSessionRead,
    AgentToolActivity,
    AgentUndoRequest,
    PageContextEnvelope,
)
from backend.app.services.agent.context import (
    HydratedContext,
    create_context_snapshot,
    hydrate_page_context,
    stable_hash,
    stable_json,
)
from backend.app.services.agent.provider import (
    AgentProviderError,
    OpenAICompatibleAgentProvider,
)
from backend.app.services.agent.system_instruction import (
    OPERATOR_SYSTEM_INSTRUCTION,
    OPERATOR_SYSTEM_INSTRUCTION_VERSION,
)
from backend.app.services.agent.tools import (
    ReviewAddNoteArgs,
    ToolPolicyError,
    ToolValidationError,
    execute_read_tool,
    get_tool,
    list_tool_descriptors,
    target_version,
    validate_tool_args,
)


class AgentServiceError(RuntimeError):
    status_code = 422


class AgentNotFoundError(AgentServiceError):
    status_code = 404


class AgentConflictError(AgentServiceError):
    status_code = 409


class AgentPolicyError(AgentServiceError):
    status_code = 403


def _utcnow() -> datetime:
    return datetime.utcnow()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _truncate(value: str, limit: int = 500) -> str:
    return value[:limit]


def _read_session(record: AgentSession) -> AgentSessionRead:
    return AgentSessionRead(
        id=record.id,
        actor_id=record.actor_id,
        title=record.title,
        provider=record.provider,
        model=record.model,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _read_message(record: AgentMessage) -> AgentMessageRead:
    return AgentMessageRead(
        id=record.id,
        session_id=record.session_id,
        role=record.role,
        content=record.content,
        status=record.status,
        created_at=record.created_at,
        metadata=record.metadata_json,
    )


def _read_context(record: AgentContextSnapshot) -> AgentContextSnapshotRead:
    raw = record.context_json.get("raw_envelope")
    return AgentContextSnapshotRead(
        id=record.id,
        context_hash=record.context_hash,
        context=PageContextEnvelope.model_validate(raw),
        hydrated_summary=record.hydrated_summary_json,
        source_refs=record.source_refs_json,
    )


def _read_proposal(record: AgentProposal, *, approval_token: str | None = None) -> AgentProposalRead:
    return AgentProposalRead(
        id=record.id,
        session_id=record.session_id,
        tool_name=record.tool_name,
        proposal_hash=record.proposal_hash,
        target_type=record.target_type,
        target_id=record.target_id,
        target_version=record.target_version,
        status=record.status,
        arguments=record.arguments_json,
        validation=record.validation_json,
        approval_required=record.approval_required,
        approval_token=approval_token,
        approval_expires_at=record.approval_expires_at,
        created_at=record.created_at,
    )


def _read_receipt(record: AgentActionReceipt) -> AgentActionReceiptRead:
    return AgentActionReceiptRead(
        id=record.id,
        session_id=record.session_id,
        proposal_id=record.proposal_id,
        action=record.action,
        actor_id=record.actor_id,
        target_type=record.target_type,
        target_id=record.target_id,
        target_version_before=record.target_version_before,
        target_version_after=record.target_version_after,
        result_resource_type=record.result_resource_type,
        result_resource_id=record.result_resource_id,
        status=record.status,
        undo_status=record.undo_status,
        result=record.result_json,
        undo=record.undo_json,
        created_at=record.created_at,
    )


def _audit(
    db: Session,
    *,
    session_id: UUID | None,
    actor_id: str | None,
    event_type: str,
    target_type: str | None = None,
    target_id: UUID | None = None,
    policy_decision: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AgentAuditEvent(
            session_id=session_id,
            actor_id=actor_id,
            event_type=event_type,
            target_type=target_type,
            target_id=target_id,
            policy_decision=policy_decision,
            details_json=details or {},
        )
    )


def _provider_health_response(settings: Settings, health: dict[str, Any]) -> AgentProviderHealth:
    capabilities = OpenAICompatibleAgentProvider(settings).capabilities
    return AgentProviderHealth(
        enabled=bool(health.get("enabled")),
        provider=settings.ai_provider,
        base_url=settings.ai_base_url,
        configured_model=settings.ai_model,
        reachable=bool(health.get("reachable")),
        status=str(health.get("status") or "unknown"),
        model_count=len(health.get("models") or []),
        active_model_id=health.get("active_model_id"),
        error=health.get("error"),
        capabilities={
            "streaming": capabilities.streaming,
            "structured_output": capabilities.structured_output,
            "native_tool_calling": capabilities.native_tool_calling,
        },
    )


class AgentService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        provider: OpenAICompatibleAgentProvider | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or OpenAICompatibleAgentProvider(self.settings)

    async def provider_health(self) -> AgentProviderHealth:
        return _provider_health_response(self.settings, await self.provider.health())

    async def provider_models(self) -> AgentProviderModelsResponse:
        health = await self.provider.health()
        models = [
            AgentProviderModel(
                id=str(item.get("id")),
                owned_by=(
                    str(item.get("owned_by"))
                    if isinstance(item.get("owned_by"), str)
                    else None
                ),
                created=(
                    int(item.get("created"))
                    if isinstance(item.get("created"), int)
                    else None
                ),
            )
            for item in (health.get("models") or [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        return AgentProviderModelsResponse(
            enabled=bool(health.get("enabled")),
            reachable=bool(health.get("reachable")),
            configured_model=self.settings.ai_model,
            active_model_id=health.get("active_model_id"),
            models=models,
            error=health.get("error"),
        )

    def create_session(self, db: Session, payload: AgentSessionCreate) -> AgentSessionRead:
        session = AgentSession(
            actor_id=payload.actor_id,
            title=payload.title or "CineForge Operator",
            provider=self.settings.ai_provider,
            model=self.settings.ai_model,
            status="active",
            metadata_json={"system_instruction_version": OPERATOR_SYSTEM_INSTRUCTION_VERSION},
        )
        db.add(session)
        db.flush()
        _audit(
            db,
            session_id=session.id,
            actor_id=payload.actor_id,
            event_type="agent.session.created",
            policy_decision="allowed",
        )
        db.commit()
        db.refresh(session)
        return _read_session(session)

    def get_session(self, db: Session, session_id: UUID) -> AgentSessionRead:
        session = db.get(AgentSession, session_id)
        if session is None:
            raise AgentNotFoundError("Agent session was not found")
        return _read_session(session)

    def list_tools(self, capabilities: list[str] | None = None):
        return list_tool_descriptors(capabilities)

    async def run_message(
        self,
        db: Session,
        *,
        session_id: UUID,
        actor_id: str,
        content: str,
        context: PageContextEnvelope,
        idempotency_key: str | None,
    ) -> AgentMessageTurnResponse:
        session = db.get(AgentSession, session_id)
        if session is None:
            raise AgentNotFoundError("Agent session was not found")

        hydrated = hydrate_page_context(db, context=context, actor_id=actor_id)
        snapshot = create_context_snapshot(
            db,
            session_id=session.id,
            actor_id=actor_id,
            hydrated=hydrated,
        )
        user_message = AgentMessage(
            session_id=session.id,
            context_snapshot_id=snapshot.id,
            role="user",
            content=content,
            status="complete",
            metadata_json={"context_hash": hydrated.context_hash},
        )
        db.add(user_message)
        db.flush()

        health = await self.provider_health()
        tool_activities: list[AgentToolActivity] = []
        proposals: list[AgentProposalRead] = []
        receipts: list[AgentActionReceiptRead] = []

        if not health.enabled:
            assistant_text = (
                "The CineForge Operator is installed, but AI_AGENT_ENABLED is false. "
                "I captured this page context and can show provider/tool status once enabled."
            )
        elif not health.reachable:
            assistant_text = (
                "LM Studio is not reachable from the backend right now. I captured the exact "
                "page context, but no model turn or tool request was run."
            )
        else:
            assistant_text, tool_activities, proposals = await self._run_provider_step(
                db,
                session=session,
                user_message=user_message,
                snapshot=snapshot,
                hydrated=hydrated,
                user_content=content,
                idempotency_key=idempotency_key or str(user_message.id),
            )

        assistant_message = AgentMessage(
            session_id=session.id,
            context_snapshot_id=snapshot.id,
            role="assistant",
            content=assistant_text,
            status="complete",
            metadata_json={
                "context_hash": hydrated.context_hash,
                "provider_status": health.status,
                "tool_activity_count": len(tool_activities),
            },
        )
        db.add(assistant_message)
        session.updated_at = _utcnow()
        _audit(
            db,
            session_id=session.id,
            actor_id=actor_id,
            event_type="agent.message.completed",
            target_type=context.recordType,
            target_id=UUID(context.recordId) if context.recordId and _looks_uuid(context.recordId) else None,
            policy_decision="allowed",
            details={"context_hash": hydrated.context_hash},
        )
        db.commit()
        db.refresh(session)
        db.refresh(user_message)
        db.refresh(assistant_message)
        db.refresh(snapshot)
        return AgentMessageTurnResponse(
            session=_read_session(session),
            user_message=_read_message(user_message),
            assistant_message=_read_message(assistant_message),
            context_snapshot=_read_context(snapshot),
            provider_health=health,
            tool_activities=tool_activities,
            proposals=proposals,
            receipts=receipts,
        )

    async def _run_provider_step(
        self,
        db: Session,
        *,
        session: AgentSession,
        user_message: AgentMessage,
        snapshot: AgentContextSnapshot,
        hydrated: HydratedContext,
        user_content: str,
        idempotency_key: str,
    ) -> tuple[str, list[AgentToolActivity], list[AgentProposalRead]]:
        response_schema = {
            "type": "object",
            "properties": {
                "assistant_text": {"type": "string"},
                "tool_call": {
                    "anyOf": [
                        {"type": "null"},
                        {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "arguments": {"type": "object"},
                            },
                            "required": ["name", "arguments"],
                            "additionalProperties": False,
                        },
                    ]
                },
            },
            "required": ["assistant_text", "tool_call"],
            "additionalProperties": False,
        }
        tool_descriptors = [
            item.model_dump(mode="json")
            for item in list_tool_descriptors(hydrated.verified_capabilities)
        ]
        messages = [
            {"role": "system", "content": OPERATOR_SYSTEM_INSTRUCTION},
            {
                "role": "user",
                "content": stable_json(
                    {
                        "schema": "sineforge.operator-turn-input/v1",
                        "context_hash": hydrated.context_hash,
                        "verified_context": hydrated.hydrated_summary,
                        "available_tools": tool_descriptors,
                        "user_message": user_content,
                    }
                ),
            },
        ]
        try:
            action = await self.provider.complete_action(
                messages=messages,
                response_schema=response_schema,
                idempotency_key=idempotency_key,
            )
        except AgentProviderError as exc:
            _audit(
                db,
                session_id=session.id,
                actor_id=session.actor_id,
                event_type="agent.provider.failed",
                policy_decision="blocked",
                details={"error": _truncate(str(exc))},
            )
            return (
                f"LM Studio returned a recoverable provider error: {_truncate(str(exc), 240)}",
                [],
                [],
            )

        assistant_text = str(action.get("assistant_text") or "").strip()
        tool_call = action.get("tool_call")
        if not isinstance(tool_call, dict):
            return assistant_text or "I inspected the current context and no tool was needed.", [], []

        tool_name = str(tool_call.get("name") or "")
        arguments = tool_call.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        activity, proposal = self._handle_tool_request(
            db,
            session=session,
            user_message=user_message,
            snapshot=snapshot,
            hydrated=hydrated,
            tool_name=tool_name,
            arguments=arguments,
        )
        suffix = ""
        if proposal is not None:
            suffix = (
                f"\n\nApproval required for `{proposal.tool_name}` on "
                f"{proposal.target_type}:{proposal.target_id}. The proposal card has the exact target and version."
            )
        elif activity.status == "succeeded":
            suffix = f"\n\nTool `{activity.name}` completed against the captured context."
        elif activity.error:
            suffix = f"\n\nTool `{activity.name}` was blocked: {activity.error}"
        return assistant_text + suffix, [activity], [proposal] if proposal else []

    def _handle_tool_request(
        self,
        db: Session,
        *,
        session: AgentSession,
        user_message: AgentMessage,
        snapshot: AgentContextSnapshot,
        hydrated: HydratedContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> tuple[AgentToolActivity, AgentProposalRead | None]:
        request_hash = stable_hash({"tool": tool_name, "arguments": arguments})
        try:
            spec = get_tool(tool_name)
        except ToolValidationError as exc:
            return self._record_blocked_tool(
                db,
                session=session,
                user_message=user_message,
                snapshot=snapshot,
                tool_name=tool_name or "unknown",
                request_hash=request_hash,
                arguments=arguments,
                risk_class="destructive",
                error=str(exc),
            ), None

        tool_call = AgentToolCall(
            session_id=session.id,
            message_id=user_message.id,
            context_snapshot_id=snapshot.id,
            tool_name=spec.name,
            tool_version=spec.version,
            risk_class=spec.risk_class.value,
            status="requested",
            request_json=arguments,
            request_hash=request_hash,
            result_json={},
            started_at=_utcnow(),
        )
        db.add(tool_call)
        db.flush()

        if spec.name not in hydrated.verified_capabilities and spec.risk_class != AgentRiskClass.read:
            tool_call.status = "blocked"
            tool_call.error_class = "policy"
            tool_call.error_message = "Tool is not available for the verified context"
            return AgentToolActivity(
                id=tool_call.id,
                name=spec.name,
                status="blocked",
                risk_class=spec.risk_class,
                target={},
                validation={"allowed": False},
                error=tool_call.error_message,
            ), None

        try:
            typed_args = validate_tool_args(spec.name, arguments)
        except ToolValidationError as exc:
            tool_call.status = "failed"
            tool_call.error_class = "validation"
            tool_call.error_message = str(exc)[:1000]
            return AgentToolActivity(
                id=tool_call.id,
                name=spec.name,
                status="failed",
                risk_class=spec.risk_class,
                validation={"allowed": False, "errors": [tool_call.error_message]},
                error=tool_call.error_message,
            ), None

        if spec.risk_class == AgentRiskClass.read:
            try:
                result = execute_read_tool(
                    db,
                    name=spec.name,
                    args=typed_args,
                    hydrated_summary=hydrated.hydrated_summary,
                )
            except (ToolValidationError, ToolPolicyError) as exc:
                tool_call.status = "failed"
                tool_call.error_class = exc.__class__.__name__
                tool_call.error_message = str(exc)[:1000]
                return AgentToolActivity(
                    id=tool_call.id,
                    name=spec.name,
                    status="failed",
                    risk_class=spec.risk_class,
                    validation={"allowed": False, "errors": [tool_call.error_message]},
                    error=tool_call.error_message,
                ), None
            tool_call.status = "succeeded"
            tool_call.result_json = _bounded_result(result, self.settings.ai_max_tool_result_bytes)
            tool_call.result_hash = stable_hash(tool_call.result_json)
            tool_call.finished_at = _utcnow()
            return AgentToolActivity(
                id=tool_call.id,
                name=spec.name,
                status="succeeded",
                risk_class=spec.risk_class,
                validation={"allowed": True},
                result=tool_call.result_json,
            ), None

        if spec.name == "review.add_note":
            if not isinstance(typed_args, ReviewAddNoteArgs):
                raise AssertionError("review.add_note args type mismatch")
            try:
                proposal, token = self._create_review_note_proposal(
                    db,
                    session=session,
                    tool_call=tool_call,
                    snapshot=snapshot,
                    actor_id=session.actor_id,
                    args=typed_args,
                )
            except ToolPolicyError as exc:
                tool_call.status = "blocked"
                tool_call.error_class = "policy"
                tool_call.error_message = str(exc)[:1000]
                return AgentToolActivity(
                    id=tool_call.id,
                    name=spec.name,
                    status="blocked",
                    risk_class=spec.risk_class,
                    validation={"allowed": False, "errors": [tool_call.error_message]},
                    error=tool_call.error_message,
                ), None
            tool_call.status = "approval_required"
            tool_call.result_json = {
                "status": "approval_required",
                "proposal_id": str(proposal.id),
                "proposal_hash": proposal.proposal_hash,
            }
            tool_call.result_hash = stable_hash(tool_call.result_json)
            tool_call.finished_at = _utcnow()
            return AgentToolActivity(
                id=tool_call.id,
                name=spec.name,
                status="approval_required",
                risk_class=spec.risk_class,
                target={
                    "type": proposal.target_type,
                    "id": str(proposal.target_id) if proposal.target_id else None,
                    "version": proposal.target_version,
                },
                validation=proposal.validation_json,
                result=tool_call.result_json,
            ), _read_proposal(proposal, approval_token=token)

        tool_call.status = "blocked"
        tool_call.error_class = "policy"
        tool_call.error_message = "Mutating tool has no deterministic executor"
        return AgentToolActivity(
            id=tool_call.id,
            name=spec.name,
            status="blocked",
            risk_class=spec.risk_class,
            validation={"allowed": False},
            error=tool_call.error_message,
        ), None

    def _record_blocked_tool(
        self,
        db: Session,
        *,
        session: AgentSession,
        user_message: AgentMessage,
        snapshot: AgentContextSnapshot,
        tool_name: str,
        request_hash: str,
        arguments: dict[str, Any],
        risk_class: str,
        error: str,
    ) -> AgentToolActivity:
        tool_call = AgentToolCall(
            session_id=session.id,
            message_id=user_message.id,
            context_snapshot_id=snapshot.id,
            tool_name=tool_name,
            tool_version="unknown",
            risk_class=risk_class,
            status="blocked",
            request_json=arguments,
            request_hash=request_hash,
            result_json={},
            error_class="validation",
            error_message=error,
            started_at=_utcnow(),
            finished_at=_utcnow(),
        )
        db.add(tool_call)
        db.flush()
        return AgentToolActivity(
            id=tool_call.id,
            name=tool_name,
            status="blocked",
            risk_class=AgentRiskClass(risk_class),
            validation={"allowed": False},
            error=error,
        )

    def _create_review_note_proposal(
        self,
        db: Session,
        *,
        session: AgentSession,
        tool_call: AgentToolCall,
        snapshot: AgentContextSnapshot,
        actor_id: str,
        args: ReviewAddNoteArgs,
    ) -> tuple[AgentProposal, str]:
        normalized_type = args.target_type.lower()
        if normalized_type not in {"project", "story", "shot", "character"}:
            raise ToolPolicyError("review.add_note target must be project, story, shot, or character")
        current_version = target_version(db, normalized_type, args.target_id)
        if current_version is None:
            raise ToolPolicyError("review.add_note target was not found")
        validation = {
            "allowed": True,
            "approval_required": True,
            "risk_class": "low",
            "target": {
                "type": normalized_type,
                "id": str(args.target_id),
                "version": current_version,
            },
            "checks": [
                "schema_validated",
                "target_rehydrated_from_database",
                "client_capabilities_ignored",
                "deterministic_executor_required",
            ],
        }
        proposal_payload = {
            "tool_name": "review.add_note",
            "target_type": normalized_type,
            "target_id": str(args.target_id),
            "target_version": current_version,
            "note": args.note,
            "context_hash": snapshot.context_hash,
        }
        token = secrets.token_urlsafe(32)
        proposal = AgentProposal(
            session_id=session.id,
            tool_call_id=tool_call.id,
            context_snapshot_id=snapshot.id,
            tool_name="review.add_note",
            proposal_hash=stable_hash(proposal_payload),
            actor_id=actor_id,
            target_type=normalized_type,
            target_id=args.target_id,
            target_version=current_version,
            status="pending_approval",
            arguments_json={"note": args.note},
            validation_json=validation,
            approval_required=True,
            approval_token_hash=_token_hash(token),
            approval_expires_at=_utcnow() + timedelta(minutes=10),
        )
        db.add(proposal)
        db.flush()
        _audit(
            db,
            session_id=session.id,
            actor_id=actor_id,
            event_type="agent.proposal.created",
            target_type=normalized_type,
            target_id=args.target_id,
            policy_decision="approval_required",
            details={"proposal_hash": proposal.proposal_hash},
        )
        return proposal, token

    def get_proposal(self, db: Session, proposal_id: UUID) -> AgentProposalRead:
        proposal = db.get(AgentProposal, proposal_id)
        if proposal is None:
            raise AgentNotFoundError("Agent proposal was not found")
        return _read_proposal(proposal)

    def reject_proposal(
        self,
        db: Session,
        proposal_id: UUID,
        payload: AgentProposalRejectRequest,
    ) -> AgentProposalRead:
        proposal = db.get(AgentProposal, proposal_id)
        if proposal is None:
            raise AgentNotFoundError("Agent proposal was not found")
        if proposal.status != "pending_approval":
            raise AgentConflictError("Only pending proposals can be rejected")
        proposal.status = "rejected"
        proposal.rejected_by = payload.actor_id
        proposal.rejected_at = _utcnow()
        proposal.rejection_reason = payload.reason
        _audit(
            db,
            session_id=proposal.session_id,
            actor_id=payload.actor_id,
            event_type="agent.proposal.rejected",
            target_type=proposal.target_type,
            target_id=proposal.target_id,
            policy_decision="rejected",
            details={"proposal_hash": proposal.proposal_hash},
        )
        db.commit()
        db.refresh(proposal)
        return _read_proposal(proposal)

    def approve_proposal(
        self,
        db: Session,
        proposal_id: UUID,
        payload: AgentProposalApproveRequest,
    ) -> AgentActionReceiptRead:
        proposal = db.get(AgentProposal, proposal_id)
        if proposal is None:
            raise AgentNotFoundError("Agent proposal was not found")
        if proposal.status == "executed":
            receipt = self._receipt_for_proposal(db, proposal.id, payload.idempotency_key)
            if receipt is not None:
                return _read_receipt(receipt)
            raise AgentConflictError("Proposal has already been executed")
        if proposal.status != "pending_approval":
            raise AgentConflictError("Only pending proposals can be approved")
        if proposal.approval_token_hash != _token_hash(payload.approval_token):
            _audit(
                db,
                session_id=proposal.session_id,
                actor_id=payload.actor_id,
                event_type="agent.approval.invalid_token",
                target_type=proposal.target_type,
                target_id=proposal.target_id,
                policy_decision="blocked",
                details={"proposal_hash": proposal.proposal_hash},
            )
            db.commit()
            raise AgentPolicyError("Approval token is invalid")
        if proposal.approval_expires_at and proposal.approval_expires_at < _utcnow():
            proposal.status = "canceled"
            db.commit()
            raise AgentConflictError("Approval token expired")
        current_version = target_version(db, proposal.target_type, proposal.target_id)
        if current_version != proposal.target_version:
            proposal.status = "stale"
            _audit(
                db,
                session_id=proposal.session_id,
                actor_id=payload.actor_id,
                event_type="agent.proposal.stale",
                target_type=proposal.target_type,
                target_id=proposal.target_id,
                policy_decision="blocked",
                details={
                    "proposal_hash": proposal.proposal_hash,
                    "expected_version": proposal.target_version,
                    "current_version": current_version,
                },
            )
            db.commit()
            raise AgentConflictError("Target changed after proposal creation; refresh before applying")

        receipt = self._receipt_for_proposal(db, proposal.id, payload.idempotency_key)
        if receipt is not None:
            return _read_receipt(receipt)

        if proposal.tool_name != "review.add_note":
            raise AgentPolicyError("Proposal does not have an enabled executor")

        note_text = str(proposal.arguments_json.get("note") or "").strip()
        if not note_text:
            raise AgentConflictError("Proposal note is empty")

        note = CreativeReviewNote(
            entity_type=proposal.target_type,
            entity_id=proposal.target_id,
            note=note_text,
        )
        db.add(note)
        db.flush()
        db.add(
            AuditLog(
                entity_type=proposal.target_type,
                entity_id=proposal.target_id,
                action="agent.review_note.added",
                details={
                    "agent_proposal_id": str(proposal.id),
                    "agent_proposal_hash": proposal.proposal_hash,
                    "review_note_id": str(note.id),
                    "idempotency_key": payload.idempotency_key,
                },
            )
        )
        receipt = AgentActionReceipt(
            session_id=proposal.session_id,
            proposal_id=proposal.id,
            action="review.add_note",
            actor_id=payload.actor_id,
            target_type=proposal.target_type,
            target_id=proposal.target_id,
            target_version_before=proposal.target_version,
            target_version_after=target_version(db, proposal.target_type, proposal.target_id),
            result_resource_type="creative_review_note",
            result_resource_id=note.id,
            status="succeeded",
            undo_status="available",
            result_json={
                "idempotency_key": payload.idempotency_key,
                "review_note_id": str(note.id),
                "note": note.note,
            },
            undo_json={
                "strategy": "delete_created_review_note",
                "review_note_id": str(note.id),
            },
        )
        db.add(receipt)
        proposal.status = "executed"
        proposal.approved_by = payload.actor_id
        proposal.approved_at = _utcnow()
        proposal.executed_at = _utcnow()
        _audit(
            db,
            session_id=proposal.session_id,
            actor_id=payload.actor_id,
            event_type="agent.action.executed",
            target_type=proposal.target_type,
            target_id=proposal.target_id,
            policy_decision="approved",
            details={
                "proposal_hash": proposal.proposal_hash,
                "receipt_id": str(receipt.id),
                "idempotency_key": payload.idempotency_key,
            },
        )
        db.commit()
        db.refresh(receipt)
        return _read_receipt(receipt)

    def undo_action(
        self,
        db: Session,
        action_id: UUID,
        payload: AgentUndoRequest,
    ) -> AgentActionReceiptRead:
        receipt = db.get(AgentActionReceipt, action_id)
        if receipt is None:
            raise AgentNotFoundError("Agent action receipt was not found")
        if receipt.undo_status == "completed":
            return _read_receipt(receipt)
        if receipt.undo_status != "available":
            raise AgentConflictError("This action cannot be undone")
        if receipt.action != "review.add_note" or receipt.result_resource_id is None:
            receipt.undo_status = "unavailable"
            db.commit()
            raise AgentPolicyError("No deterministic undo executor is available")
        note = db.get(CreativeReviewNote, receipt.result_resource_id)
        if note is not None:
            db.delete(note)
        receipt.undo_status = "completed"
        receipt.undo_json = {
            **receipt.undo_json,
            "undone_by": payload.actor_id,
            "undone_at": _utcnow().isoformat(),
            "reason": payload.reason,
        }
        db.add(
            AuditLog(
                entity_type=receipt.target_type,
                entity_id=receipt.target_id,
                action="agent.review_note.undone",
                details={
                    "agent_action_receipt_id": str(receipt.id),
                    "review_note_id": str(receipt.result_resource_id),
                    "reason": payload.reason,
                },
            )
        )
        _audit(
            db,
            session_id=receipt.session_id,
            actor_id=payload.actor_id,
            event_type="agent.action.undone",
            target_type=receipt.target_type,
            target_id=receipt.target_id,
            policy_decision="allowed",
            details={"receipt_id": str(receipt.id)},
        )
        db.commit()
        db.refresh(receipt)
        return _read_receipt(receipt)

    def _receipt_for_proposal(
        self,
        db: Session,
        proposal_id: UUID,
        idempotency_key: str,
    ) -> AgentActionReceipt | None:
        receipts = db.scalars(
            select(AgentActionReceipt).where(AgentActionReceipt.proposal_id == proposal_id)
        ).all()
        for receipt in receipts:
            if receipt.result_json.get("idempotency_key") == idempotency_key:
                return receipt
        return None


def _bounded_result(value: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    encoded = stable_json(value).encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return {
        "status": "truncated",
        "sha256": stable_hash(value),
        "preview": stable_json(value)[: max(0, max_bytes - 200)],
    }


def _looks_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True
