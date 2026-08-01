import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Numeric, PrimaryKeyConstraint, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def json_type():
    return JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class QueueStatus(str, enum.Enum):
    pending = "pending"
    reserved = "reserved"
    validating = "validating"
    submitted = "submitted"
    running = "running"
    collecting_outputs = "collecting_outputs"
    complete = "complete"
    validation_failed = "validation_failed"
    comfy_rejected = "comfy_rejected"
    runtime_failed = "runtime_failed"
    timeout = "timeout"
    interrupted = "interrupted"
    oom = "oom"
    postprocess_failed = "postprocess_failed"
    canceled = "canceled"


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class HardwareProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hardware_profiles"
    name: Mapped[str] = mapped_column(Text)
    gpu_name: Mapped[str] = mapped_column(Text)
    vram_mib: Mapped[int] = mapped_column(Integer)
    ram_mib: Mapped[int] = mapped_column(Integer)
    driver_version: Mapped[str | None] = mapped_column(Text)
    cuda_version: Mapped[str | None] = mapped_column(Text)
    os: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Project(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    workflow_lane: Mapped[str] = mapped_column(
        String(32),
        default="cineforge_studio",
        server_default="cineforge_studio",
        nullable=False,
    )
    theme_id: Mapped[str] = mapped_column(
        String(32),
        default="default",
        server_default="default",
        nullable=False,
    )
    theme_version: Mapped[str] = mapped_column(
        String(32),
        default="1.0.0",
        server_default="1.0.0",
        nullable=False,
    )
    theme_context_json: Mapped[dict] = mapped_column(
        json_type(),
        default=dict,
        nullable=False,
    )
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="project")
    __table_args__ = (
        CheckConstraint(
            "workflow_lane IN ('cineforge_studio', 'agentless')",
            name="ck_projects_workflow_lane",
        ),
        CheckConstraint(
            "theme_id IN ('default', 'greek_mythology', 'biblical')",
            name="ck_projects_theme_id",
        ),
    )


class ProjectWorkspaceCreation(UUIDMixin, TimestampMixin, Base):
    """Durable replay record for atomic project workspace creation."""

    __tablename__ = "project_workspace_creations"
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    settings_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_storyboard_settings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )


class Campaign(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    target_duration_sec: Mapped[float | None] = mapped_column(Numeric)
    project: Mapped[Project] = relationship(back_populates="campaigns")


class Track(UUIDMixin, Base):
    __tablename__ = "tracks"
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class TimelineSlot(UUIDMixin, Base):
    __tablename__ = "timeline_slots"
    track_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tracks.id", ondelete="CASCADE"))
    slot_index: Mapped[int] = mapped_column(Integer)
    start_sec: Mapped[float] = mapped_column(Numeric)
    duration_sec: Mapped[float] = mapped_column(Numeric)
    continuity_source_slot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("timeline_slots.id"))
    notes: Mapped[str | None] = mapped_column(Text)


class Prompt(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "prompts"
    text: Mapped[str] = mapped_column(Text)
    prompt_hash: Mapped[str] = mapped_column(Text)


class NegativePrompt(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "negative_prompts"
    text: Mapped[str] = mapped_column(Text)
    prompt_hash: Mapped[str] = mapped_column(Text)


class Model(UUIDMixin, Base):
    __tablename__ = "models"
    family: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    evidence_level: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class ModelVariant(UUIDMixin, Base):
    __tablename__ = "model_variants"
    model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("models.id", ondelete="CASCADE"))
    variant_name: Mapped[str] = mapped_column(Text)
    params_b: Mapped[float | None] = mapped_column(Numeric)
    file_path: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(Text)
    precision: Mapped[str | None] = mapped_column(Text)
    quantization: Mapped[str | None] = mapped_column(Text)
    compatible_24gb_status: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # Storyboard Phase 1: native voice capability is a factual tri-state.
    # "unknown" must remain distinguishable from "unsupported".
    native_voice_capability: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    native_voice_capability_source: Mapped[str | None] = mapped_column(Text)
    native_voice_capability_metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict)
    native_voice_capability_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "native_voice_capability IN ('supported', 'unsupported', 'unknown')",
            name="ck_model_variants_native_voice_capability",
        ),
    )


class Quantization(UUIDMixin, Base):
    __tablename__ = "quantizations"
    name: Mapped[str] = mapped_column(Text)
    applies_to: Mapped[str] = mapped_column(Text)
    loader_node: Mapped[str | None] = mapped_column(Text)
    evidence_level: Mapped[str] = mapped_column(Text)
    recommended_24gb: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class TextEncoder(UUIDMixin, Base):
    __tablename__ = "text_encoders"
    name: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(Text)
    precision: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class VAE(UUIDMixin, Base):
    __tablename__ = "vaes"
    name: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(Text)
    precision: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Lora(UUIDMixin, Base):
    __tablename__ = "loras"
    name: Mapped[str] = mapped_column(Text)
    base_model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("models.id"))
    base_variant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("model_variants.id"))
    purpose: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    quantized_base_status: Mapped[str] = mapped_column(Text, default="unknown")
    evidence_level: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class LoraCombination(UUIDMixin, Base):
    __tablename__ = "lora_combinations"
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class LoraCombinationItem(Base):
    __tablename__ = "lora_combination_items"
    combination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lora_combinations.id", ondelete="CASCADE"))
    lora_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("loras.id"))
    order_index: Mapped[int] = mapped_column(Integer)
    strength_model: Mapped[float | None] = mapped_column(Numeric)
    strength_clip: Mapped[float | None] = mapped_column(Numeric)
    extra_params: Mapped[dict] = mapped_column(json_type(), default=dict)

    __table_args__ = (
        PrimaryKeyConstraint("combination_id", "lora_id", "order_index"),
    )


class WorkflowTemplate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workflow_templates"
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    workflow_api_json: Mapped[dict] = mapped_column(json_type())
    manifest_json: Mapped[dict] = mapped_column(json_type())
    sha256: Mapped[str] = mapped_column(Text)
    comfyui_commit: Mapped[str | None] = mapped_column(Text)
    custom_node_snapshot: Mapped[dict | None] = mapped_column(json_type())


class Clip(UUIDMixin, Base):
    __tablename__ = "clips"
    timeline_slot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("timeline_slots.id", ondelete="CASCADE"))
    title: Mapped[str | None] = mapped_column(Text)
    selected_iteration_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, default="draft")


class ClipIteration(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "clip_iterations"
    clip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"))
    iteration_index: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    frame_count: Mapped[int] = mapped_column(Integer)
    fps: Mapped[float] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(Text, default="pending")
    extra_params: Mapped[dict] = mapped_column(json_type(), default=dict)


class WorkflowRun(UUIDMixin, Base):
    __tablename__ = "workflow_runs"
    clip_iteration_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clip_iterations.id", ondelete="SET NULL"))
    workflow_template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_templates.id"))
    patched_workflow_json: Mapped[dict] = mapped_column(json_type())
    patch_payload_json: Mapped[dict] = mapped_column(json_type())
    status: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ComfyJob(UUIDMixin, Base):
    __tablename__ = "comfy_jobs"
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"))
    prompt_id: Mapped[str | None] = mapped_column(Text)
    client_id: Mapped[str | None] = mapped_column(Text)
    queue_number: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[QueueStatus] = mapped_column(Enum(QueueStatus), default=QueueStatus.pending)
    worker_id: Mapped[str | None] = mapped_column(Text)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_state_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovery_metadata: Mapped[dict] = mapped_column(json_type(), default=dict)
    node_errors: Mapped[dict | None] = mapped_column(json_type())
    websocket_events: Mapped[list] = mapped_column(json_type(), default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GeneratedAsset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "generated_assets"
    clip_iteration_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clip_iterations.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    frame_count: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Numeric)
    duration_sec: Mapped[float | None] = mapped_column(Numeric)
    probe_json: Mapped[dict | None] = mapped_column(json_type())


class FileOutput(UUIDMixin, Base):
    __tablename__ = "file_outputs"
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"))
    generated_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("generated_assets.id", ondelete="SET NULL"))
    filename_prefix: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    subfolder: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(Text)


class BenchmarkRun(UUIDMixin, Base):
    __tablename__ = "benchmark_runs"
    hardware_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hardware_profiles.id"))
    workflow_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_templates.id"))
    model_variant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("model_variants.id"))
    quantization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("quantizations.id"))
    settings: Mapped[dict] = mapped_column(json_type())
    metrics: Mapped[dict] = mapped_column(json_type())
    decision: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class FFmpegJob(UUIDMixin, Base):
    __tablename__ = "ffmpeg_jobs"
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    command_template_id: Mapped[str] = mapped_column(Text)
    input_manifest: Mapped[dict] = mapped_column(json_type())
    output_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    probe_json: Mapped[dict | None] = mapped_column(json_type())
    error_message: Mapped[str | None] = mapped_column(Text)


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(json_type(), default=dict)


class ErrorLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "error_logs"
    source: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(json_type(), default=dict)


class AIProposalRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ai_proposal_records"
    proposal_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(json_type())
    status: Mapped[str] = mapped_column(Text, default="pending_review")
    validation_errors: Mapped[list] = mapped_column(json_type(), default=list)
    # Storyboard Phase 1 additive audit / linkage fields (SET NULL for durability).
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="SET NULL"), index=True
    )
    orchestration_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "orchestration_runs.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_ai_proposal_records_orchestration_run",
        ),
        index=True,
    )
    base_storyboard_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "storyboard_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_ai_proposal_records_base_storyboard_version",
        ),
    )
    schema_name: Mapped[str | None] = mapped_column(String(128))
    schema_version: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    input_context_hash: Mapped[str | None] = mapped_column(String(64))
    payload_hash: Mapped[str | None] = mapped_column(String(64))
    base_content_hash: Mapped[str | None] = mapped_column(String(64))
    validation_status: Mapped[str | None] = mapped_column(String(32))
    validation_report_json: Mapped[dict] = mapped_column(json_type(), default=dict)
    warnings_json: Mapped[list] = mapped_column(json_type(), default=list)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_proposal_records.id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_storyboard_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "storyboard_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_ai_proposal_records_applied_storyboard_version",
        ),
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)


class AutonomyRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "autonomy_runs"
    status: Mapped[str] = mapped_column(Text)
    policy_snapshot: Mapped[dict] = mapped_column(json_type(), default=dict)


class AutonomyRunEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "autonomy_run_events"
    autonomy_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("autonomy_runs.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(json_type(), default=dict)


class AutonomyPolicy(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "autonomy_policies"
    name: Mapped[str] = mapped_column(Text)
    policy_json: Mapped[dict] = mapped_column(json_type())
    active: Mapped[bool] = mapped_column(Boolean, default=False)


class QAReport(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "qa_reports"
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    report_json: Mapped[dict] = mapped_column(json_type())


class RetryAttempt(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "retry_attempts"
    comfy_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("comfy_jobs.id"))
    attempt_index: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)


class CreativeReviewNote(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "creative_review_notes"
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str] = mapped_column(Text)


class AgentSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_sessions"
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, default="openai_compatible")
    model: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived', 'canceled')",
            name="ck_agent_sessions_status",
        ),
    )


class AgentMessage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_messages"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    context_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_context_snapshots.id", ondelete="SET NULL")
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="complete")
    metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'tool', 'system')",
            name="ck_agent_messages_role",
        ),
        CheckConstraint(
            "status IN ('pending', 'streaming', 'complete', 'failed', 'canceled')",
            name="ck_agent_messages_status",
        ),
        Index("ix_agent_messages_session_created", "session_id", "created_at"),
    )


class AgentContextSnapshot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_context_snapshots"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    context_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    hydrated_summary_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    source_refs_json: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    redaction_report_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)


class AgentToolCall(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_tool_calls"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_messages.id", ondelete="SET NULL")
    )
    context_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_context_snapshots.id", ondelete="SET NULL")
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_class: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested")
    request_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    error_class: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "risk_class IN ('read', 'low', 'medium', 'high', 'destructive')",
            name="ck_agent_tool_calls_risk_class",
        ),
        CheckConstraint(
            "status IN ('requested', 'validated', 'blocked', 'approval_required', "
            "'running', 'succeeded', 'failed', 'canceled')",
            name="ck_agent_tool_calls_status",
        ),
        Index("ix_agent_tool_calls_session_created", "session_id", "created_at"),
    )


class AgentProposal(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_proposals"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_tool_calls.id", ondelete="SET NULL")
    )
    context_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_context_snapshots.id", ondelete="SET NULL")
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    target_version: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_approval")
    arguments_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    validation_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approval_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    approval_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[str | None] = mapped_column(String(200))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'executed', "
            "'failed', 'stale', 'canceled')",
            name="ck_agent_proposals_status",
        ),
        Index("ix_agent_proposals_session_status", "session_id", "status"),
    )


class AgentActionReceipt(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_action_receipts"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_proposals.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    target_version_before: Mapped[str | None] = mapped_column(String(128))
    target_version_after: Mapped[str | None] = mapped_column(String(128))
    result_resource_type: Mapped[str | None] = mapped_column(String(80))
    result_resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="succeeded")
    undo_status: Mapped[str] = mapped_column(String(32), nullable=False, default="available")
    result_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    undo_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed', 'partial')",
            name="ck_agent_action_receipts_status",
        ),
        CheckConstraint(
            "undo_status IN ('unavailable', 'available', 'completed', 'failed')",
            name="ck_agent_action_receipts_undo_status",
        ),
    )


class AgentAuditEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_audit_events"
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="SET NULL"), index=True
    )
    actor_id: Mapped[str | None] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(80))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    policy_decision: Mapped[str | None] = mapped_column(String(64))
    details_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)


class CandidateScore(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "candidate_scores"
    clip_iteration_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clip_iterations.id"))
    score_json: Mapped[dict] = mapped_column(json_type())


# Storyboard Phase A is deliberately separate from timeline slots and clip iterations.
# It describes an editable production plan only; downstream execution entities remain
# untouched until a future, explicitly authorised production phase.
class StoryboardTimestampMixin(TimestampMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


VOICE_SETUP_MODES = (
    "placeholder",
    "manual",
    "existing_provider_voice",
    "qwen_voice_design",
    "qwen_custom_voice",
    "elevenlabs_voice_design",
    "parler_local_voice_design",
    "user_provided_consented",
)

NATIVE_VOICE_CAPABILITIES = ("supported", "unsupported", "unknown")


class Story(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "stories"
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text)
    base_story: Mapped[str] = mapped_column(Text)
    logline: Mapped[str | None] = mapped_column(Text)
    synopsis: Mapped[str | None] = mapped_column(Text)
    target_duration_sec: Mapped[float] = mapped_column(Numeric)
    audience: Mapped[str | None] = mapped_column(Text)
    tone: Mapped[str | None] = mapped_column(Text)
    genre: Mapped[str | None] = mapped_column(Text)
    visual_style: Mapped[str | None] = mapped_column(Text)
    point_of_view: Mapped[str | None] = mapped_column(Text)
    production_notes: Mapped[str | None] = mapped_column(Text)
    narrative_objectives_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    pacing_plan_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    duration_strategy_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    active_storyboard_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "storyboard_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_stories_active_storyboard_version",
        ),
    )
    default_provider_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "provider_profiles.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_stories_default_provider_profile",
        ),
    )


PRODUCTION_PHASE_LIFECYCLE_STATES = (
    "not_started",
    "drafting",
    "qa_pending",
    "needs_revision",
    "ready_for_review",
    "approved",
    "blocked",
)


class ProductionPhase(UUIDMixin, StoryboardTimestampMixin, Base):
    """Canonical eight-phase lifecycle ledger for one story.

    Completion and approval intentionally remain separate.  ``is_stale`` is
    orthogonal to lifecycle state so an upstream revision can preserve, rather
    than delete, downstream work while making its regeneration need explicit.
    """

    __tablename__ = "production_phases"
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_started"
    )
    current_version_number: Mapped[int | None] = mapped_column(Integer)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    locked_reason: Mapped[str | None] = mapped_column(Text)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    generation_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("story_id", "phase_number", name="uq_production_phase_story_number"),
        CheckConstraint(
            "phase_number >= 1 AND phase_number <= 8",
            name="ck_production_phase_number",
        ),
        CheckConstraint(
            "lifecycle_state IN ("
            "'not_started', 'drafting', 'qa_pending', 'needs_revision', "
            "'ready_for_review', 'approved', 'blocked')",
            name="ck_production_phase_lifecycle_state",
        ),
        CheckConstraint(
            "current_version_number IS NULL OR current_version_number > 0",
            name="ck_production_phase_current_version",
        ),
        Index("ix_production_phases_story_number", "story_id", "phase_number"),
    )


class ProductionPhaseVersion(UUIDMixin, StoryboardTimestampMixin, Base):
    """Immutable output snapshot for one production-phase attempt/revision.

    Rows are append-only after insert.  ``superseded_at`` is retained for
    legacy rows but is no longer written at runtime; lineage uses
    ``previous_version_id`` only.
    """

    __tablename__ = "production_phase_versions"
    production_phase_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("production_phases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    snapshot_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_snapshot_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    output_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production_phase_versions.id", ondelete="SET NULL")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "production_phase_id",
            "version_number",
            name="uq_production_phase_version",
        ),
        CheckConstraint("version_number > 0", name="ck_production_phase_version_number"),
        CheckConstraint(
            "lifecycle_state IN ("
            "'not_started', 'drafting', 'qa_pending', 'needs_revision', "
            "'ready_for_review', 'approved', 'blocked')",
            name="ck_production_phase_version_lifecycle_state",
        ),
        CheckConstraint(
            "source IN ('baseline', 'manual', 'generated', 'revision', 'imported')",
            name="ck_production_phase_version_source",
        ),
        CheckConstraint(
            "snapshot_schema_version > 0",
            name="ck_production_phase_version_snapshot_schema",
        ),
        Index(
            "ix_production_phase_versions_phase_version",
            "production_phase_id",
            "version_number",
        ),
    )


class PlanningMediaAsset(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "planning_media_assets"
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(48))
    source_type: Mapped[str] = mapped_column(String(48))
    managed_uri: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_sec: Mapped[float | None] = mapped_column(Numeric)
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict)
    original_filename: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_planning_media_assets_size_bytes"),
        Index(
            "uq_planning_media_assets_project_kind_sha256",
            "project_id",
            "kind",
            "sha256",
            unique=True,
            postgresql_where=text("sha256 IS NOT NULL"),
            sqlite_where=text("sha256 IS NOT NULL"),
        ),
    )


class VoiceProfile(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "voice_profiles"
    story_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("characters.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(48))
    provider: Mapped[str | None] = mapped_column(String(80))
    provider_voice_reference: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(32))
    accent: Mapped[str | None] = mapped_column(Text)
    presentation: Mapped[str | None] = mapped_column(Text)
    tone: Mapped[str | None] = mapped_column(Text)
    speaking_directions: Mapped[str | None] = mapped_column(Text)
    pacing: Mapped[str | None] = mapped_column(Text)
    energy: Mapped[str | None] = mapped_column(Text)
    pronunciation_notes: Mapped[str | None] = mapped_column(Text)
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("planning_media_assets.id", ondelete="SET NULL"))
    source_description: Mapped[str | None] = mapped_column(Text)
    consent_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_notes: Mapped[str | None] = mapped_column(Text)
    usage_notes: Mapped[str | None] = mapped_column(Text)
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    # Storyboard Phase 1 voice setup / design metadata (legacy columns retained).
    setup_mode: Mapped[str] = mapped_column(String(48), default="manual", nullable=False)
    provider_model_id: Mapped[str | None] = mapped_column(Text)
    recipe_name: Mapped[str | None] = mapped_column(Text)
    recipe_description: Mapped[str | None] = mapped_column(Text)
    design_description: Mapped[str | None] = mapped_column(Text)
    design_metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict)
    selected_preview_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planning_media_assets.id", ondelete="SET NULL")
    )
    preview_text: Mapped[str | None] = mapped_column(Text)
    gender_presentation: Mapped[str | None] = mapped_column(Text)
    pitch: Mapped[str | None] = mapped_column(Text)
    style: Mapped[str | None] = mapped_column(Text)
    provider_configuration_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    provider_identifier: Mapped[str | None] = mapped_column(String(80))
    provider_voice_id: Mapped[str | None] = mapped_column(Text)
    voice_recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "voice_recipes.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_voice_profiles_voice_recipe",
        ),
    )
    voice_recipe_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    voice_recipe_hash: Mapped[str | None] = mapped_column(String(64))
    voice_description: Mapped[str | None] = mapped_column(Text)
    design_model_id: Mapped[str | None] = mapped_column(Text)
    selected_preview_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "voice_previews.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_voice_profiles_selected_preview",
        ),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "setup_mode IN ("
            "'placeholder', 'manual', 'existing_provider_voice', "
            "'qwen_voice_design', 'qwen_custom_voice', "
            "'elevenlabs_voice_design', 'parler_local_voice_design', "
            "'user_provided_consented')",
            name="ck_voice_profiles_setup_mode",
        ),
    )


class Character(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "characters"
    story_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    age_range: Mapped[str | None] = mapped_column(Text)
    physical_description: Mapped[str | None] = mapped_column(Text)
    personality: Mapped[str | None] = mapped_column(Text)
    speaking_style: Mapped[str | None] = mapped_column(Text)
    wardrobe: Mapped[str | None] = mapped_column(Text)
    consistency_prompt: Mapped[str | None] = mapped_column(Text)
    negative_identity_prompt: Mapped[str | None] = mapped_column(Text)
    identity_method: Mapped[str | None] = mapped_column(String(64))
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    assigned_voice_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("voice_profiles.id", ondelete="SET NULL", use_alter=True, name="fk_characters_assigned_voice"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CharacterReferenceAsset(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "character_reference_assets"
    character_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("planning_media_assets.id", ondelete="CASCADE"))
    reference_role: Mapped[str] = mapped_column(String(32))
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint("character_id", "order_index", name="uq_character_reference_order"),)


class Chapter(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "chapters"
    story_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    narrative_purpose: Mapped[str | None] = mapped_column(Text)
    target_duration_sec: Mapped[float | None] = mapped_column(Numeric)
    dramatic_progression: Mapped[str | None] = mapped_column(Text)
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("story_id", "order_index", name="uq_chapter_story_order"),)


class Scene(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "scenes"
    chapter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    narrative_purpose: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    conflict_or_beat: Mapped[str | None] = mapped_column(Text)
    target_duration_sec: Mapped[float | None] = mapped_column(Numeric)
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("chapter_id", "order_index", name="uq_scene_chapter_order"),)


class Shot(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "shots"
    scene_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    duration_sec: Mapped[float] = mapped_column(Numeric)
    duration_override_reason: Mapped[str | None] = mapped_column(Text)
    story_purpose: Mapped[str | None] = mapped_column(Text)
    visual_description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    camera_direction: Mapped[str | None] = mapped_column(Text)
    motion_direction: Mapped[str | None] = mapped_column(Text)
    continuity_source_type: Mapped[str] = mapped_column(String(48), default="none", nullable=False)
    continuity_source_shot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("shots.id", ondelete="SET NULL"))
    starting_image_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    starting_image_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("planning_media_assets.id", ondelete="SET NULL"))
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    production_status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("scene_id", "order_index", name="uq_shot_scene_order"),
        CheckConstraint("duration_sec > 0", name="ck_shot_positive_duration"),
    )


class ShotCharacter(Base):
    __tablename__ = "shot_characters"
    shot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shots.id", ondelete="CASCADE"), primary_key=True)
    character_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    role_in_shot: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    continuity_notes: Mapped[str | None] = mapped_column(Text)


class ShotNarration(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "shot_narrations"
    shot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shots.id", ondelete="CASCADE"), unique=True)
    voice_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("voice_profiles.id", ondelete="SET NULL"))
    narration_text: Mapped[str | None] = mapped_column(Text)
    start_offset_sec: Mapped[float] = mapped_column(Numeric, default=0)
    expected_duration_sec: Mapped[float | None] = mapped_column(Numeric)
    narration_exception_reason: Mapped[str | None] = mapped_column(Text)
    pacing_notes: Mapped[str | None] = mapped_column(Text)
    pronunciation_notes: Mapped[str | None] = mapped_column(Text)
    narration_fit_status: Mapped[str | None] = mapped_column(String(32))
    narration_fit_wpm: Mapped[float | None] = mapped_column(Numeric)
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)


class ShotPromptPackage(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "shot_prompt_packages"
    shot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shots.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    image_prompt: Mapped[str | None] = mapped_column(Text)
    video_prompt: Mapped[str | None] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text)
    continuity_instructions: Mapped[str | None] = mapped_column(Text)
    style_lock_prompt: Mapped[str | None] = mapped_column(Text)
    provider_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "provider_profiles.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_shot_prompt_packages_provider_profile",
        ),
    )
    provider_model_id: Mapped[str | None] = mapped_column(Text)
    prompt_rationale: Mapped[str | None] = mapped_column(Text)
    provider_metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_proposal_records.id", ondelete="SET NULL"))
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    __table_args__ = (UniqueConstraint("shot_id", "version", name="uq_shot_prompt_version"),)


class ShotModelRecommendation(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "shot_model_recommendations"
    shot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shots.id", ondelete="CASCADE"), index=True)
    recommendation_type: Mapped[str] = mapped_column(String(24))
    generation_model_variant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("model_variants.id", ondelete="SET NULL"))
    workflow_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_templates.id", ondelete="SET NULL"))
    rationale: Mapped[str | None] = mapped_column(Text)
    availability_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    benchmark_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    risk_status: Mapped[str | None] = mapped_column(String(32))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)


class StoryboardVersion(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "storyboard_versions"
    story_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(json_type())
    source_proposal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_proposal_records.id", ondelete="SET NULL"))
    created_by: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    base_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storyboard_versions.id", ondelete="SET NULL")
    )
    content_hash: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("story_id", "version_number", name="uq_storyboard_version"),)


class ProviderProfile(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "provider_profiles"
    provider_identifier: Mapped[str] = mapped_column(String(32))
    display_name: Mapped[str] = mapped_column(Text)
    provider_model_id: Mapped[str | None] = mapped_column(Text)
    execution_mode: Mapped[str] = mapped_column(String(32), default="disabled", nullable=False)
    availability_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    privacy_classification: Mapped[str | None] = mapped_column(String(64))
    capabilities_json: Mapped[dict] = mapped_column(json_type(), default=dict)
    configuration_reference: Mapped[str | None] = mapped_column(Text)
    capabilities_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capability_source: Mapped[str | None] = mapped_column(Text)


class TaskProviderAssignment(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "task_provider_assignments"
    story_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    task_type: Mapped[str] = mapped_column(String(64))
    provider_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("provider_profiles.id", ondelete="CASCADE"))
    assignment_mode: Mapped[str] = mapped_column(String(24), default="manual", nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("story_id", "task_type", name="uq_story_task_provider"),)


# ---------------------------------------------------------------------------
# Storyboard Phase 1 durable persistence
# ---------------------------------------------------------------------------


class ProjectStoryboardSettings(UUIDMixin, StoryboardTimestampMixin, Base):
    """Per-project storyboard defaults. Story.target_duration_sec remains authoritative."""

    __tablename__ = "project_storyboard_settings"
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shot_duration_min_sec: Mapped[float] = mapped_column(Numeric, nullable=False)
    shot_duration_max_sec: Mapped[float] = mapped_column(Numeric, nullable=False)
    continuity_policy_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    prompting_policy_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    voice_policy_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    approval_policy_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    speaking_rate: Mapped[float] = mapped_column(Numeric, nullable=False, default=1.0)
    aspect_ratio: Mapped[str] = mapped_column(String(32), nullable=False, default="16:9")
    preview_width: Mapped[int] = mapped_column(Integer, nullable=False)
    preview_height: Mapped[int] = mapped_column(Integer, nullable=False)
    final_width: Mapped[int] = mapped_column(Integer, nullable=False)
    final_height: Mapped[int] = mapped_column(Integer, nullable=False)
    fps: Mapped[float] = mapped_column(Numeric, nullable=False)
    captions_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    audio_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    production_profile_key: Mapped[str] = mapped_column(
        String(128), default="ltx_base@1", nullable=False
    )
    production_profile_snapshot_json: Mapped[dict] = mapped_column(
        json_type(), default=dict, nullable=False
    )
    stitch_stage: Mapped[str] = mapped_column(
        String(32), default="phase7_before_audio", nullable=False
    )
    prefer_hosted_providers: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prefer_local_providers: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_model_download: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_rendering: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_voice_consent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    require_production_plan_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    settings_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_project_storyboard_settings_project_id"),
        CheckConstraint("shot_duration_min_sec > 0", name="ck_pss_shot_duration_min_positive"),
        CheckConstraint("shot_duration_max_sec > 0", name="ck_pss_shot_duration_max_positive"),
        CheckConstraint(
            "shot_duration_min_sec <= shot_duration_max_sec",
            name="ck_pss_shot_duration_min_le_max",
        ),
        CheckConstraint("speaking_rate > 0", name="ck_pss_speaking_rate_positive"),
        CheckConstraint("preview_width > 0", name="ck_pss_preview_width_positive"),
        CheckConstraint("preview_height > 0", name="ck_pss_preview_height_positive"),
        CheckConstraint("final_width > 0", name="ck_pss_final_width_positive"),
        CheckConstraint("final_height > 0", name="ck_pss_final_height_positive"),
        CheckConstraint("fps > 0", name="ck_pss_fps_positive"),
        CheckConstraint(
            "production_profile_key <> ''",
            name="ck_pss_production_profile_key_nonempty",
        ),
        CheckConstraint(
            "stitch_stage IN ('phase7_before_audio', 'phase8_before_foley')",
            name="ck_pss_stitch_stage",
        ),
        CheckConstraint("settings_version > 0", name="ck_pss_settings_version_positive"),
    )


class OrchestrationRun(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "orchestration_runs"
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    retry_of_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orchestration_runs.id", ondelete="SET NULL")
    )
    base_storyboard_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storyboard_versions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    requested_by: Mapped[str | None] = mapped_column(Text)
    routing_snapshot_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    default_provider_snapshot_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    target_duration_sec_snapshot: Mapped[float | None] = mapped_column(Numeric)
    input_hash: Mapped[str | None] = mapped_column(String(64))
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_steps: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    repair_budget: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repair_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    execution_owner_id: Mapped[str | None] = mapped_column(String(128))
    execution_claim_token: Mapped[str | None] = mapped_column(String(64))
    execution_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_category: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'canceled')",
            name="ck_orchestration_runs_status",
        ),
        CheckConstraint("current_step >= 0", name="ck_orchestration_runs_current_step"),
        CheckConstraint("max_steps > 0", name="ck_orchestration_runs_max_steps"),
        CheckConstraint("repair_budget >= 0", name="ck_orchestration_runs_repair_budget"),
        CheckConstraint("repair_used >= 0", name="ck_orchestration_runs_repair_used"),
        CheckConstraint("repair_used <= repair_budget", name="ck_orchestration_runs_repair_used_le_budget"),
        CheckConstraint("execution_attempt >= 0", name="ck_orchestration_runs_execution_attempt"),
        CheckConstraint(
            "(execution_claim_token IS NULL AND execution_owner_id IS NULL "
            "AND execution_lease_expires_at IS NULL AND execution_heartbeat_at IS NULL) OR "
            "(execution_claim_token IS NOT NULL AND execution_owner_id IS NOT NULL "
            "AND execution_lease_expires_at IS NOT NULL AND execution_heartbeat_at IS NOT NULL)",
            name="ck_orchestration_runs_execution_lease_complete",
        ),
        CheckConstraint(
            "target_duration_sec_snapshot IS NULL OR target_duration_sec_snapshot > 0",
            name="ck_orchestration_runs_target_duration",
        ),
        Index("ix_orchestration_runs_story_status", "story_id", "status"),
        Index(
            "ix_orchestration_runs_execution_lease",
            "status",
            "execution_lease_expires_at",
        ),
        Index(
            "uq_orchestration_runs_one_active_per_story",
            "story_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
    )


class OrchestrationStep(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "orchestration_steps"
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orchestration_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    provider_identifier: Mapped[str | None] = mapped_column(String(80))
    logical_model: Mapped[str | None] = mapped_column(Text)
    resolved_model: Mapped[str | None] = mapped_column(Text)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_hash: Mapped[str | None] = mapped_column(String(64))
    output_hash: Mapped[str | None] = mapped_column(String(64))
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_proposal_records.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_category: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_index", "attempt_number", name="uq_orchestration_step_attempt"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'skipped', 'canceled')",
            name="ck_orchestration_steps_status",
        ),
        CheckConstraint("sequence_index >= 0", name="ck_orchestration_steps_sequence_index"),
        CheckConstraint("attempt_number > 0", name="ck_orchestration_steps_attempt_number"),
        Index("ix_orchestration_steps_run_sequence", "run_id", "sequence_index"),
    )


class OrchestrationEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "orchestration_events"
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orchestration_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orchestration_steps.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_reference: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    __table_args__ = (
        Index("ix_orchestration_events_run_created", "run_id", "created_at"),
        Index("ix_orchestration_events_step_created", "step_id", "created_at"),
    )


class ProviderInvocation(UUIDMixin, TimestampMixin, Base):
    """Provider call audit trail. Never stores raw prompts, responses, credentials, or hidden reasoning."""

    __tablename__ = "provider_invocations"
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orchestration_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orchestration_steps.id", ondelete="SET NULL"), index=True
    )
    provider_identifier: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str | None] = mapped_column(String(64))
    response_hash: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    usage_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    provider_request_id: Mapped[str | None] = mapped_column(Text)
    finish_category: Mapped[str | None] = mapped_column(String(64))
    error_category: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_provider_invocations_idempotency_key"),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'canceled')",
            name="ck_provider_invocations_status",
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_provider_invocations_latency"),
        Index("ix_provider_invocations_run_created", "run_id", "created_at"),
    )


class VoiceRecipe(UUIDMixin, StoryboardTimestampMixin, Base):
    """Voice design recipe metadata only; never stores audio bytes or base64."""

    __tablename__ = "voice_recipes"
    voice_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    recipe_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    seed: Mapped[int | None] = mapped_column(Integer)
    design_metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)


class VoicePreview(UUIDMixin, StoryboardTimestampMixin, Base):
    """Managed preview reference only; never stores audio bytes or base64."""

    __tablename__ = "voice_previews"
    voice_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    voice_recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_recipes.id", ondelete="SET NULL")
    )
    planning_media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planning_media_assets.id", ondelete="SET NULL")
    )
    provider: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(Text)
    preview_text: Mapped[str | None] = mapped_column(Text)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (
        CheckConstraint("NOT (selected AND rejected)", name="ck_voice_previews_not_selected_and_rejected"),
        Index(
            "uq_voice_previews_one_selected_per_profile",
            "voice_profile_id",
            unique=True,
            postgresql_where=text("selected IS true"),
            sqlite_where=text("selected = 1"),
        ),
    )


class GpuResourceLease(UUIDMixin, TimestampMixin, Base):
    """GPU lease boundary only — not a render/media/provider queue."""

    __tablename__ = "gpu_resource_leases"
    resource_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    exclusive_group: Mapped[str | None] = mapped_column(String(128))
    workload_type: Mapped[str] = mapped_column(String(64), nullable=False)
    workload_id: Mapped[str | None] = mapped_column(String(128))
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'released', 'expired')",
            name="ck_gpu_resource_leases_status",
        ),
        Index("ix_gpu_resource_leases_status_expires", "status", "expires_at"),
        Index(
            "uq_gpu_resource_leases_one_active_per_resource",
            "resource_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index(
            "uq_gpu_resource_leases_one_active_per_group",
            "exclusive_group",
            unique=True,
            postgresql_where=text("status = 'active' AND exclusive_group IS NOT NULL"),
            sqlite_where=text("status = 'active' AND exclusive_group IS NOT NULL"),
        ),
    )


# LTX Sequence Sheet records are deliberately additive.  They preserve an
# immutable authoring revision and per-row execution ledger instead of
# repurposing the older TimelineSlot/Clip tables or the WAN evidence.
class SequencePlan(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "sequence_plans"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Kept as an application-validated pointer to avoid a DDL cycle with
    # sequence_plan_revisions on SQLite.  The revision owns the strong FK.
    active_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        nullable=False,
    )
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'validated', 'approved', 'executing', "
            "'completed', 'failed', 'canceled')",
            name="ck_sequence_plans_status",
        ),
        Index("ix_sequence_plans_project_created", "project_id", "created_at"),
    )


class SequencePlanRevision(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "sequence_plan_revisions"

    sequence_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    profile_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255))
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    canonical_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    compiled_plan_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(32),
        default="validated",
        nullable=False,
    )
    source_json: Mapped[dict] = mapped_column(
        json_type(),
        default=dict,
        nullable=False,
    )
    canonical_json: Mapped[dict] = mapped_column(
        json_type(),
        default=dict,
        nullable=False,
    )
    compiled_plan_json: Mapped[dict] = mapped_column(
        json_type(),
        default=dict,
        nullable=False,
    )
    validation_json: Mapped[dict] = mapped_column(
        json_type(),
        default=dict,
        nullable=False,
    )
    created_by: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "sequence_plan_id",
            "revision",
            name="uq_sequence_plan_revision_number",
        ),
        CheckConstraint(
            "revision > 0",
            name="ck_sequence_plan_revisions_revision_positive",
        ),
        CheckConstraint(
            "status IN ('draft', 'invalid', 'validated', 'approved', "
            "'executing', 'completed', 'failed', 'canceled')",
            name="ck_sequence_plan_revisions_status",
        ),
        Index(
            "ix_sequence_plan_revisions_plan_created",
            "sequence_plan_id",
            "created_at",
        ),
    )


class SequenceRow(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "sequence_rows"

    sequence_plan_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_plan_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_id: Mapped[str] = mapped_column(String(128), nullable=False)
    row_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    workflow_template_key: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(80), nullable=False)
    workflow_sha256: Mapped[str | None] = mapped_column(String(64))
    profile_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    generation_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    requested_duration_sec: Mapped[float] = mapped_column(Numeric, nullable=False)
    compiled_frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    compiled_duration_sec: Mapped[float] = mapped_column(Numeric, nullable=False)
    fps_numerator: Mapped[int] = mapped_column(Integer, nullable=False)
    fps_denominator: Mapped[int] = mapped_column(Integer, nullable=False)
    concrete_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    seed_origin: Mapped[str] = mapped_column(String(16), nullable=False)
    continuity_source: Mapped[str] = mapped_column(String(32), nullable=False)
    continuity_asset_id: Mapped[str | None] = mapped_column(String(128))
    continuity_row_id: Mapped[str | None] = mapped_column(String(128))
    character_ids_json: Mapped[list] = mapped_column(
        json_type(),
        default=list,
        nullable=False,
    )
    asset_ids_json: Mapped[list] = mapped_column(
        json_type(),
        default=list,
        nullable=False,
    )
    reference_asset_ids_json: Mapped[list] = mapped_column(
        json_type(),
        default=list,
        nullable=False,
    )
    output_basename: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    compiled_segment_json: Mapped[dict] = mapped_column(
        json_type(),
        default=dict,
        nullable=False,
    )
    __table_args__ = (
        UniqueConstraint(
            "sequence_plan_revision_id",
            "row_id",
            name="uq_sequence_rows_revision_row_id",
        ),
        UniqueConstraint(
            "sequence_plan_revision_id",
            "order_index",
            name="uq_sequence_rows_revision_order",
        ),
        CheckConstraint("row_revision > 0", name="ck_sequence_rows_revision_positive"),
        CheckConstraint("order_index > 0", name="ck_sequence_rows_order_positive"),
        CheckConstraint(
            "requested_duration_sec >= 8 AND requested_duration_sec <= 15",
            name="ck_sequence_rows_duration_8_15",
        ),
        CheckConstraint(
            "compiled_frame_count > 0 AND compiled_frame_count % 8 = 1",
            name="ck_sequence_rows_frame_policy",
        ),
        CheckConstraint(
            "fps_numerator > 0 AND fps_denominator > 0",
            name="ck_sequence_rows_fps_positive",
        ),
        CheckConstraint(
            "generation_mode IN ('i2v', 't2v')",
            name="ck_sequence_rows_generation_mode",
        ),
        CheckConstraint(
            "seed_origin IN ('explicit', 'derived')",
            name="ck_sequence_rows_seed_origin",
        ),
        Index(
            "ix_sequence_rows_revision_order",
            "sequence_plan_revision_id",
            "order_index",
        ),
    )


class SequenceRowDependency(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sequence_row_dependencies"

    sequence_plan_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_plan_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    predecessor_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_rows.id", ondelete="CASCADE"),
        nullable=False,
    )
    successor_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_rows.id", ondelete="CASCADE"),
        nullable=False,
    )
    dependency_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    required_artifact_kind: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint(
            "sequence_plan_revision_id",
            "predecessor_row_id",
            "successor_row_id",
            "dependency_kind",
            name="uq_sequence_row_dependencies_edge",
        ),
        CheckConstraint(
            "predecessor_row_id <> successor_row_id",
            name="ck_sequence_row_dependencies_not_self",
        ),
    )


class SequenceExecutionRun(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "sequence_execution_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_plan_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_plan_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
    )
    allow_rendering_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_sequence_execution_runs_project_idempotency",
        ),
        CheckConstraint(
            "status IN ('pending', 'blocked', 'running', 'completed', "
            "'failed', 'canceled')",
            name="ck_sequence_execution_runs_status",
        ),
        Index(
            "ix_sequence_execution_runs_revision_status",
            "sequence_plan_revision_id",
            "status",
        ),
    )


class SequenceRowExecution(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "sequence_row_executions"

    sequence_execution_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_execution_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_rows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
    )
    current_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "sequence_execution_run_id",
            "sequence_row_id",
            name="uq_sequence_row_executions_run_row",
        ),
        CheckConstraint(
            "status IN ('draft', 'invalid', 'pending', 'blocked_on_dependency', "
            "'ready', 'leased', 'submitting', 'queued', 'running', "
            "'collecting', 'validating', 'awaiting_selection', 'succeeded', "
            "'retry_wait', 'failed', 'skipped', 'canceled', 'stale')",
            name="ck_sequence_row_executions_status",
        ),
        CheckConstraint(
            "current_attempt >= 0",
            name="ck_sequence_row_executions_attempt_nonnegative",
        ),
        Index(
            "ix_sequence_row_executions_status_lease",
            "status",
            "lease_expires_at",
        ),
    )


class SequenceRowAttempt(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sequence_row_attempts"

    sequence_row_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_row_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    concrete_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    patched_workflow_sha256: Mapped[str | None] = mapped_column(String(64))
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
    )
    comfy_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("comfy_jobs.id", ondelete="SET NULL"),
    )
    input_asset_hashes_json: Mapped[list] = mapped_column(
        json_type(),
        default=list,
        nullable=False,
    )
    handoff_input_sha256: Mapped[str | None] = mapped_column(String(64))
    output_clip_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_assets.id", ondelete="SET NULL"),
    )
    output_audio_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_assets.id", ondelete="SET NULL"),
    )
    error_class: Mapped[str | None] = mapped_column(String(128))
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "sequence_row_execution_id",
            "attempt_number",
            name="uq_sequence_row_attempt_number",
        ),
        CheckConstraint(
            "attempt_number > 0",
            name="ck_sequence_row_attempts_number_positive",
        ),
    )


class ContinuityPacket(UUIDMixin, StoryboardTimestampMixin, Base):
    __tablename__ = "continuity_packets"

    sequence_execution_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_execution_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    predecessor_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_rows.id", ondelete="CASCADE"),
        nullable=False,
    )
    successor_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequence_rows.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_clip_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_clip_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    handoff_image_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    handoff_image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_pts_sec: Mapped[float] = mapped_column(Numeric, nullable=False)
    continuity_metadata_json: Mapped[dict] = mapped_column(
        json_type(),
        default=dict,
        nullable=False,
    )
    qa_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    reanchor_decision: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint(
            "sequence_execution_run_id",
            "predecessor_row_id",
            "successor_row_id",
            name="uq_continuity_packets_run_edge",
        ),
        CheckConstraint(
            "source_frame_index >= 0",
            name="ck_continuity_packets_frame_nonnegative",
        ),
        CheckConstraint(
            "source_pts_sec >= 0",
            name="ck_continuity_packets_pts_nonnegative",
        ),
    )
