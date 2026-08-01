"""Contextual Operator agent API routes."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import AgentMessage
from backend.app.db.session import get_db
from backend.app.schemas.agent import (
    AgentActionReceiptRead,
    AgentMessageCreate,
    AgentMessageTurnResponse,
    AgentProviderHealth,
    AgentProviderModelsResponse,
    AgentProposalApproveRequest,
    AgentProposalRead,
    AgentProposalRejectRequest,
    AgentSessionCreate,
    AgentSessionRead,
    AgentToolsResponse,
    AgentUndoRequest,
)
from backend.app.services.agent.service import (
    AgentConflictError,
    AgentNotFoundError,
    AgentPolicyError,
    AgentService,
    AgentServiceError,
)


router = APIRouter(prefix="/agent", tags=["agent"])


def get_agent_service() -> AgentService:
    return AgentService()


def _raise_agent_error(exc: AgentServiceError) -> None:
    status_code = getattr(exc, "status_code", status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, AgentPolicyError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, AgentNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, AgentConflictError):
        status_code = status.HTTP_409_CONFLICT
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/sessions", response_model=AgentSessionRead, status_code=status.HTTP_201_CREATED)
def create_agent_session(
    payload: AgentSessionCreate,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> AgentSessionRead:
    try:
        return service.create_session(db, payload)
    except AgentServiceError as exc:
        _raise_agent_error(exc)


@router.get("/sessions/{session_id}", response_model=AgentSessionRead)
def get_agent_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> AgentSessionRead:
    try:
        return service.get_session(db, session_id)
    except AgentServiceError as exc:
        _raise_agent_error(exc)


@router.post("/sessions/{session_id}/messages", response_model=AgentMessageTurnResponse)
async def create_agent_message(
    session_id: UUID,
    payload: AgentMessageCreate,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> AgentMessageTurnResponse:
    try:
        return await service.run_message(
            db,
            session_id=session_id,
            actor_id=payload.actor_id,
            content=payload.content,
            context=payload.context,
            thinking_enabled=payload.thinking_enabled,
            idempotency_key=payload.idempotency_key,
        )
    except AgentServiceError as exc:
        _raise_agent_error(exc)


@router.get("/sessions/{session_id}/events")
def stream_agent_events(
    session_id: UUID,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    messages = db.scalars(
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at.asc())
    ).all()

    def generate():
        for message in messages:
            payload = {
                "type": "message",
                "message": {
                    "id": str(message.id),
                    "role": message.role,
                    "status": message.status,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                    "metadata": message.metadata_json,
                },
            }
            yield f"event: message\ndata: {json.dumps(payload, default=str)}\n\n"
        yield "event: done\ndata: {\"type\":\"done\"}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/runs/{run_id}/cancel")
def cancel_agent_run(run_id: UUID) -> dict[str, str]:
    return {
        "status": "not_running",
        "run_id": str(run_id),
        "message": "No long-running operator turn is active for this run.",
    }


@router.get("/providers/health", response_model=AgentProviderHealth)
async def get_agent_provider_health(
    service: AgentService = Depends(get_agent_service),
) -> AgentProviderHealth:
    return await service.provider_health()


@router.get("/providers/models", response_model=AgentProviderModelsResponse)
async def get_agent_provider_models(
    service: AgentService = Depends(get_agent_service),
) -> AgentProviderModelsResponse:
    return await service.provider_models()


@router.get("/tools", response_model=AgentToolsResponse)
def list_agent_tools(
    service: AgentService = Depends(get_agent_service),
) -> AgentToolsResponse:
    return AgentToolsResponse(tools=service.list_tools())


@router.get("/proposals/{proposal_id}", response_model=AgentProposalRead)
def get_agent_proposal(
    proposal_id: UUID,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> AgentProposalRead:
    try:
        return service.get_proposal(db, proposal_id)
    except AgentServiceError as exc:
        _raise_agent_error(exc)


@router.post("/proposals/{proposal_id}/approve", response_model=AgentActionReceiptRead)
def approve_agent_proposal(
    proposal_id: UUID,
    payload: AgentProposalApproveRequest,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> AgentActionReceiptRead:
    try:
        return service.approve_proposal(db, proposal_id, payload)
    except AgentServiceError as exc:
        _raise_agent_error(exc)


@router.post("/proposals/{proposal_id}/reject", response_model=AgentProposalRead)
def reject_agent_proposal(
    proposal_id: UUID,
    payload: AgentProposalRejectRequest,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> AgentProposalRead:
    try:
        return service.reject_proposal(db, proposal_id, payload)
    except AgentServiceError as exc:
        _raise_agent_error(exc)


@router.post("/actions/{action_id}/undo", response_model=AgentActionReceiptRead)
def undo_agent_action(
    action_id: UUID,
    payload: AgentUndoRequest,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> AgentActionReceiptRead:
    try:
        return service.undo_action(db, action_id, payload)
    except AgentServiceError as exc:
        _raise_agent_error(exc)
