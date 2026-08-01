from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from backend.app.core.errors import CineForgeError
from backend.app.db.base import AuditLog, ComfyJob, QueueStatus, WorkflowRun
from backend.app.queue.state_machine import JobState
from backend.app.services.comfy.object_info_cache import ObjectInfoCacheService
from backend.app.services.comfy.engine import async_comfy_prompt_submission_guard
from backend.app.services.queue.service import QueueService, SubmissionReadinessResult


class ControlledSubmissionError(CineForgeError):
    pass


class PromptSubmissionAdapter(Protocol):
    async def submit_prompt(self, prompt: dict[str, Any], client_id: str) -> dict[str, Any]:
        """Submit a prompt from the approved worker/runtime path only."""


class ComfyWorkerPromptSubmissionAdapter:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout, transport=transport)

    async def __aenter__(self) -> "ComfyWorkerPromptSubmissionAdapter":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def submit_prompt(self, prompt: dict[str, Any], client_id: str) -> dict[str, Any]:
        async with async_comfy_prompt_submission_guard():
            response = await self._client.post(
                "/prompt",
                json={"prompt": prompt, "client_id": client_id},
            )
        response.raise_for_status()
        return response.json()


@dataclass(frozen=True)
class WorkerSubmissionContext:
    job_id: UUID
    worker_id: str
    client_id: str
    object_info_cache: ObjectInfoCacheService


@dataclass(frozen=True)
class ControlledSubmissionResult:
    submitted: bool
    job_id: UUID
    worker_id: str
    status: str
    code: str
    prompt_id: str | None = None
    queue_number: int | None = None
    errors: list[str] | None = None


class ControlledComfySubmissionService:
    def __init__(
        self,
        queue_service: QueueService | None = None,
        submission_adapter: PromptSubmissionAdapter | None = None,
    ) -> None:
        self.queue_service = queue_service or QueueService()
        self.submission_adapter = submission_adapter

    async def submit_reserved_job(
        self,
        db: Session,
        context: WorkerSubmissionContext,
    ) -> ControlledSubmissionResult:
        if self.submission_adapter is None:
            raise ControlledSubmissionError("Controlled submission adapter is not configured")

        readiness = self.queue_service.evaluate_submission_readiness(
            db,
            context.job_id,
            context.worker_id,
            context.object_info_cache,
        )
        if not readiness.ready:
            self._mark_validation_failed_if_worker_owned_reserved(db, readiness)
            return ControlledSubmissionResult(
                submitted=False,
                job_id=context.job_id,
                worker_id=context.worker_id,
                status="validation_failed",
                code=readiness.code,
                errors=readiness.errors,
            )

        self.queue_service.transition_job(
            db,
            context.job_id,
            JobState.validating,
            "controlled submission readiness passed",
            actor="worker",
            worker_id=context.worker_id,
        )

        job = self._require_job(db, context.job_id)
        workflow_run = self._require_workflow_run(db, job.workflow_run_id)
        try:
            response = await self.submission_adapter.submit_prompt(
                workflow_run.patched_workflow_json,
                context.client_id,
            )
        except Exception as exc:
            self._mark_submission_failure(
                db,
                job,
                QueueStatus.comfy_rejected,
                "worker_prompt_rejected",
                "controlled submission adapter rejected prompt",
                str(exc),
                context.worker_id,
            )
            return ControlledSubmissionResult(
                submitted=False,
                job_id=context.job_id,
                worker_id=context.worker_id,
                status=QueueStatus.comfy_rejected.value,
                code="comfy_rejected",
                errors=[str(exc)],
            )

        node_errors = response.get("node_errors")
        if node_errors:
            error_message = f"ComfyUI node_errors: {node_errors}"
            self._mark_submission_failure(
                db,
                job,
                QueueStatus.validation_failed,
                "worker_prompt_node_errors",
                "controlled submission returned node_errors",
                error_message,
                context.worker_id,
            )
            return ControlledSubmissionResult(
                submitted=False,
                job_id=context.job_id,
                worker_id=context.worker_id,
                status=QueueStatus.validation_failed.value,
                code="node_errors",
                errors=[error_message],
            )

        prompt_id = response.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            error_message = "Controlled submission response missing prompt_id"
            self._mark_submission_failure(
                db,
                job,
                QueueStatus.comfy_rejected,
                "worker_prompt_rejected",
                "controlled submission response missing prompt_id",
                error_message,
                context.worker_id,
            )
            return ControlledSubmissionResult(
                submitted=False,
                job_id=context.job_id,
                worker_id=context.worker_id,
                status=QueueStatus.comfy_rejected.value,
                code="missing_prompt_id",
                errors=[error_message],
            )

        queue_number = response.get("number")
        submitted_job = self._mark_submitted(
            db,
            job,
            prompt_id,
            queue_number if isinstance(queue_number, int) else None,
            context.client_id,
            context.worker_id,
        )
        return ControlledSubmissionResult(
            submitted=True,
            job_id=context.job_id,
            worker_id=context.worker_id,
            status=submitted_job.status.value,
            code="submitted",
            prompt_id=prompt_id,
            queue_number=submitted_job.queue_number,
            errors=[],
        )

    def _mark_validation_failed_if_worker_owned_reserved(
        self,
        db: Session,
        readiness: SubmissionReadinessResult,
    ) -> None:
        job = db.get(ComfyJob, readiness.job_id)
        if job is None or job.status != QueueStatus.reserved or job.worker_id != readiness.worker_id:
            return

        self.queue_service.transition_job(
            db,
            readiness.job_id,
            JobState.validating,
            "controlled submission readiness failed",
            actor="worker",
            worker_id=readiness.worker_id,
        )
        job = self._require_job(db, readiness.job_id)
        self._mark_submission_failure(
            db,
            job,
            QueueStatus.validation_failed,
            "worker_submission_readiness_failed",
            "controlled submission readiness failed",
            "; ".join(readiness.errors),
            readiness.worker_id,
        )

    def _mark_submitted(
        self,
        db: Session,
        job: ComfyJob,
        prompt_id: str,
        queue_number: int | None,
        client_id: str,
        worker_id: str,
    ) -> ComfyJob:
        now = datetime.now(UTC)
        previous_state = job.status.value
        job.status = QueueStatus.submitted
        job.prompt_id = prompt_id
        job.queue_number = queue_number
        job.client_id = client_id
        job.submitted_at = now
        job.last_state_change_at = now
        workflow_run = self._require_workflow_run(db, job.workflow_run_id)
        workflow_run.status = QueueStatus.submitted.value
        db.add(
            AuditLog(
                entity_type="comfy_job",
                entity_id=job.id,
                action="worker_prompt_submission",
                details={
                    "previous_state": previous_state,
                    "new_state": QueueStatus.submitted.value,
                    "reason": "controlled worker prompt submission",
                    "actor": "worker",
                    "worker_id": worker_id,
                    "prompt_id": prompt_id,
                    "queue_number": queue_number,
                },
            )
        )
        db.commit()
        db.refresh(job)
        return job

    def _mark_submission_failure(
        self,
        db: Session,
        job: ComfyJob,
        target_status: QueueStatus,
        action: str,
        reason: str,
        error_message: str,
        worker_id: str,
    ) -> None:
        now = datetime.now(UTC)
        previous_state = job.status.value
        job.status = target_status
        job.error_message = error_message
        job.last_state_change_at = now
        workflow_run = self._require_workflow_run(db, job.workflow_run_id)
        workflow_run.status = target_status.value
        db.add(
            AuditLog(
                entity_type="comfy_job",
                entity_id=job.id,
                action=action,
                details={
                    "previous_state": previous_state,
                    "new_state": target_status.value,
                    "reason": reason,
                    "actor": "worker",
                    "worker_id": worker_id,
                    "error_message": error_message,
                },
            )
        )
        db.commit()

    @staticmethod
    def _require_job(db: Session, job_id: UUID) -> ComfyJob:
        job = db.get(ComfyJob, job_id)
        if job is None:
            raise ControlledSubmissionError(f"ComfyJob not found: {job_id}")
        return job

    @staticmethod
    def _require_workflow_run(db: Session, workflow_run_id: UUID) -> WorkflowRun:
        workflow_run = db.get(WorkflowRun, workflow_run_id)
        if workflow_run is None:
            raise ControlledSubmissionError(f"WorkflowRun not found: {workflow_run_id}")
        return workflow_run
