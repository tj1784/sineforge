"""Deterministic planning and fail-closed readiness for Agentless projects."""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import re
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import WorkflowTemplate
from backend.app.schemas.agentless_workflow import (
    AGENTLESS_PLAN_SCHEMA_VERSION,
    AGENTLESS_PROFILE_REF,
    AGENTLESS_REQUEST_SCHEMA_VERSION,
    BATCH_SIZE,
    DEFAULT_SEGMENT_DURATION_SEC,
    FPS,
    FRAME_MULTIPLE,
    FRAME_REMAINDER,
    MAX_ACTIVE_GPU_JOBS,
    MAX_SEED,
    AgentlessAnchorPlan,
    AgentlessDryRunRead,
    AgentlessDryRunRequest,
    AgentlessReadiness,
    AgentlessReadinessBlocker,
    AgentlessSegmentPlan,
    AgentlessStageKind,
    AgentlessStageNode,
    AgentlessTemplateRef,
    AgentlessVideoPlan,
    AgentlessWorkflowAdmission,
    AgentlessWorkflowAdmissionStatus,
    AgentlessWorkflowProfileRead,
    AgentlessWorkflowRequirementRead,
    AgentlessWorkflowRole,
    CompiledAgentlessPlan,
)


class AgentlessCompilationError(ValueError):
    """A validated Agentless request could not be compiled safely."""


_OPAQUE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$")
_OUTPUT_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

ROLE_REQUIRED_SEMANTIC_MAPPINGS: dict[
    AgentlessWorkflowRole,
    frozenset[str],
] = {
    AgentlessWorkflowRole.FLUX_ANCHOR: frozenset(
        {
            "positive_prompt",
            "image_seed",
            "character_reference_assets",
            "set_studio_reference_assets",
            "composition_reference_assets",
            "pose_reference_assets",
            "prop_reference_assets",
            "width",
            "height",
            "output_prefix",
        }
    ),
    AgentlessWorkflowRole.LTX_INGREDIENTS_I2V: frozenset(
        {
            "positive_prompt",
            "negative_prompt",
            "video_seed",
            "ingredients_reference_image",
            "scene_anchor_image",
            "width",
            "height",
            "frame_count",
            "fps",
            "ingredients_lora_strength",
            "distilled_lora_strength",
            "bypass_i2v",
            "output_prefix",
            "audio_input",
        }
    ),
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _safe_derived_id(value: str, *, field: str) -> str:
    if len(value) > 128 or not _OPAQUE_ID_PATTERN.fullmatch(value):
        raise AgentlessCompilationError(
            f"Derived {field} is not a valid bounded opaque identifier."
        )
    return value


def _safe_derived_output_prefix(value: str, *, field: str) -> str:
    if (
        len(value) > 120
        or not _OUTPUT_PREFIX_PATTERN.fullmatch(value)
        or ".." in value
        or value.endswith(".")
    ):
        raise AgentlessCompilationError(
            f"Derived {field} is not a safe bounded output basename."
        )
    return value


def _is_api_prompt(workflow: object) -> bool:
    if not isinstance(workflow, dict) or not workflow:
        return False
    return all(
        isinstance(node_id, str)
        and isinstance(node, dict)
        and isinstance(node.get("class_type"), str)
        and bool(node["class_type"].strip())
        and isinstance(node.get("inputs"), dict)
        for node_id, node in workflow.items()
    )


def _segment_durations(duration_sec: float) -> tuple[float, ...]:
    """Split a logical scene into one or two independently viable segments.

    A scene at or below ten seconds stays whole.  Longer scenes keep the first
    segment as close to ten seconds as possible while reserving at least three
    seconds for the independently anchored B segment.  This avoids creating a
    pathological sub-second tail for scenes just over ten seconds.
    """

    if duration_sec <= DEFAULT_SEGMENT_DURATION_SEC:
        return (duration_sec,)
    first = min(
        DEFAULT_SEGMENT_DURATION_SEC,
        duration_sec - 3.0,
    )
    second = duration_sec - first
    return (first, second)


def _ltx_frame_count(duration_sec: float) -> int:
    requested_frames = Fraction(str(duration_sec)) * FPS
    shifted_frames = requested_frames - FRAME_REMAINDER
    lower_frame_count = (
        shifted_frames // FRAME_MULTIPLE
    ) * FRAME_MULTIPLE + FRAME_REMAINDER
    upper_frame_count = (
        lower_frame_count
        if Fraction(lower_frame_count) == requested_frames
        else lower_frame_count + FRAME_MULTIPLE
    )
    frame_count = int(
        min(
            (lower_frame_count, upper_frame_count),
            key=lambda candidate: (
                abs(Fraction(candidate) - requested_frames),
                -candidate,
            ),
        )
    )
    if frame_count <= 1:
        raise AgentlessCompilationError(
            "LTX compilation produced no positive frame interval"
        )
    return frame_count


def _derived_seed(
    *,
    base_seed: int,
    project_id: str,
    scene_id: str,
    segment_label: str,
    channel: str,
) -> int:
    if segment_label in {"single", "A"}:
        return base_seed
    digest = hashlib.sha256(
        _canonical_json(
            {
                "contract": AGENTLESS_PLAN_SCHEMA_VERSION,
                "project_id": project_id,
                "scene_id": scene_id,
                "segment_label": segment_label,
                "channel": channel,
                "base_seed": base_seed,
            }
        ).encode("utf-8")
    ).digest()
    derived = int.from_bytes(digest[:8], "big") & MAX_SEED
    if derived == base_seed:
        derived = (derived + 1) & MAX_SEED
    return derived


def _stage_id(segment_id: str, kind: AgentlessStageKind) -> str:
    return _safe_derived_id(
        f"{segment_id}:{kind.value}",
        field=f"{kind.value} stage_id",
    )


def _positive_prompt(character_block: str, scene_prompt: str) -> str:
    """Compose the immutable identity block before shot-specific direction."""

    return f"{character_block}\n\n{scene_prompt}"


def _compile_stages(
    segment: AgentlessSegmentPlan,
) -> tuple[AgentlessStageNode, ...]:
    anchor_id = _stage_id(segment.segment_id, AgentlessStageKind.ANCHOR)
    anchor_qa_id = _stage_id(
        segment.segment_id,
        AgentlessStageKind.ANCHOR_QA,
    )
    video_id = _stage_id(segment.segment_id, AgentlessStageKind.VIDEO)
    video_qa_id = _stage_id(
        segment.segment_id,
        AgentlessStageKind.VIDEO_QA,
    )
    master_id = _stage_id(segment.segment_id, AgentlessStageKind.MASTER)
    return (
        AgentlessStageNode(
            stage_id=anchor_id,
            segment_id=segment.segment_id,
            kind=AgentlessStageKind.ANCHOR,
            workflow_role=AgentlessWorkflowRole.FLUX_ANCHOR,
            uses_gpu=True,
            max_attempts=segment.anchor.max_attempts,
            output_artifact_kind="lossless_anchor_png",
        ),
        AgentlessStageNode(
            stage_id=anchor_qa_id,
            segment_id=segment.segment_id,
            kind=AgentlessStageKind.ANCHOR_QA,
            depends_on_stage_ids=(anchor_id,),
            uses_gpu=False,
            max_attempts=1,
            output_artifact_kind="anchor_qa_report",
        ),
        AgentlessStageNode(
            stage_id=video_id,
            segment_id=segment.segment_id,
            kind=AgentlessStageKind.VIDEO,
            depends_on_stage_ids=(anchor_qa_id,),
            workflow_role=AgentlessWorkflowRole.LTX_INGREDIENTS_I2V,
            uses_gpu=True,
            max_attempts=segment.video.max_attempts,
            output_artifact_kind="video_candidate",
        ),
        AgentlessStageNode(
            stage_id=video_qa_id,
            segment_id=segment.segment_id,
            kind=AgentlessStageKind.VIDEO_QA,
            depends_on_stage_ids=(video_id,),
            uses_gpu=False,
            max_attempts=1,
            output_artifact_kind="video_qa_report",
        ),
        AgentlessStageNode(
            stage_id=master_id,
            segment_id=segment.segment_id,
            kind=AgentlessStageKind.MASTER,
            depends_on_stage_ids=(video_qa_id,),
            uses_gpu=False,
            max_attempts=1,
            output_artifact_kind="lossless_master",
        ),
    )


def _compile_agentless_plan(
    request: AgentlessDryRunRequest,
) -> CompiledAgentlessPlan:
    """Compile manifests into isolated, deterministic per-segment stage DAGs."""

    segments: list[AgentlessSegmentPlan] = []
    stages: list[AgentlessStageNode] = []
    for scene in request.scenes:
        durations = _segment_durations(scene.duration_sec)
        audio_source_offset_sec = 0.0
        for segment_index, requested_duration_sec in enumerate(durations):
            if len(durations) == 1:
                segment_label = "single"
                segment_id = _safe_derived_id(
                    scene.scene_id,
                    field="segment_id",
                )
                output_prefix = _safe_derived_output_prefix(
                    scene.output_prefix,
                    field="segment output_prefix",
                )
            else:
                segment_label = "A" if segment_index == 0 else "B"
                segment_id = _safe_derived_id(
                    f"{scene.scene_id}-{segment_label}",
                    field="segment_id",
                )
                output_prefix = _safe_derived_output_prefix(
                    f"{scene.output_prefix}-{segment_label}",
                    field="segment output_prefix",
                )
            frame_count = _ltx_frame_count(requested_duration_sec)
            playback_duration_sec = float(Fraction(frame_count, FPS))
            duration_delta_sec = (
                playback_duration_sec - requested_duration_sec
            )
            image_seed = _derived_seed(
                base_seed=scene.image_seed,
                project_id=str(request.project_id),
                scene_id=scene.scene_id,
                segment_label=segment_label,
                channel="image",
            )
            video_seed = _derived_seed(
                base_seed=scene.video_seed,
                project_id=str(request.project_id),
                scene_id=scene.scene_id,
                segment_label=segment_label,
                channel="video",
            )
            if image_seed == video_seed:
                video_seed = (video_seed + 1) & MAX_SEED

            anchor_stage_id = _stage_id(
                segment_id,
                AgentlessStageKind.ANCHOR,
            )
            anchor = AgentlessAnchorPlan(
                workflow_template=request.workflow_templates.anchor,
                image_seed=image_seed,
                character_description_block=(
                    scene.character_description_block
                ),
                scene_prompt=scene.anchor_prompt,
                prompt=_positive_prompt(
                    scene.character_description_block,
                    scene.anchor_prompt,
                ),
                visible_character_ids=scene.visible_character_ids,
                character_reference_asset_ids=(
                    scene.character_reference_asset_ids
                ),
                flux_reference_assets=scene.flux_reference_assets,
                width=scene.width,
                height=scene.height,
                output_prefix=_safe_derived_output_prefix(
                    f"{output_prefix}-anchor",
                    field="anchor output_prefix",
                ),
                max_attempts=scene.anchor_max_attempts,
            )
            video = AgentlessVideoPlan(
                workflow_template=request.workflow_templates.video,
                ingredients_reference_asset_id=(
                    scene.ingredients_reference_asset_id
                ),
                scene_anchor_stage_id=anchor_stage_id,
                video_seed=video_seed,
                character_description_block=(
                    scene.character_description_block
                ),
                scene_prompt=scene.video_prompt,
                prompt=_positive_prompt(
                    scene.character_description_block,
                    scene.video_prompt,
                ),
                negative_prompt=scene.negative_prompt,
                width=scene.width,
                height=scene.height,
                frame_count=frame_count,
                requested_duration_sec=requested_duration_sec,
                playback_duration_sec=playback_duration_sec,
                duration_delta_sec=duration_delta_sec,
                ingredients_lora_strength=(
                    scene.ingredients_lora_strength
                ),
                distilled_lora_strength=scene.distilled_lora_strength,
                audio_asset_id=scene.audio_asset_id,
                audio_source_offset_sec=audio_source_offset_sec,
                audio_segment_duration_sec=requested_duration_sec,
                output_prefix=output_prefix,
                max_attempts=scene.video_max_attempts,
            )
            segment = AgentlessSegmentPlan(
                segment_id=segment_id,
                logical_scene_id=scene.scene_id,
                segment_index=segment_index,
                segment_label=segment_label,
                requested_duration_sec=requested_duration_sec,
                playback_duration_sec=playback_duration_sec,
                duration_delta_sec=duration_delta_sec,
                frame_count=frame_count,
                output_prefix=output_prefix,
                image_seed=image_seed,
                video_seed=video_seed,
                anchor=anchor,
                video=video,
            )
            segments.append(segment)
            stages.extend(_compile_stages(segment))
            audio_source_offset_sec += requested_duration_sec

    base_payload = {
        "schema_version": AGENTLESS_PLAN_SCHEMA_VERSION,
        "source_schema_version": AGENTLESS_REQUEST_SCHEMA_VERSION,
        "project_id": request.project_id,
        "workflow_lane": "agentless",
        "profile_ref": AGENTLESS_PROFILE_REF,
        "workflow_templates": request.workflow_templates,
        "master_policy": request.master_policy,
        "logical_scene_count": len(request.scenes),
        "segment_count": len(segments),
        "segments": tuple(segments),
        "stages": tuple(stages),
        "batch_size": BATCH_SIZE,
        "max_active_gpu_jobs": MAX_ACTIVE_GPU_JOBS,
        "backend_owns_pending_queue": True,
        "previous_clip_dependency_allowed": False,
        "previous_frame_dependency_allowed": False,
        "fresh_anchor_required_per_segment": True,
        "submission_enabled": False,
    }
    hash_payload = {
        key: (
            value.model_dump(mode="json", exclude_none=True)
            if hasattr(value, "model_dump")
            else [
                item.model_dump(mode="json", exclude_none=True)
                if hasattr(item, "model_dump")
                else item
                for item in value
            ]
            if isinstance(value, tuple)
            else str(value)
            if key == "project_id"
            else value
        )
        for key, value in base_payload.items()
    }
    return CompiledAgentlessPlan(
        **base_payload,
        plan_sha256=_sha256(hash_payload),
    )


def compile_agentless_plan(
    request: AgentlessDryRunRequest,
) -> CompiledAgentlessPlan:
    """Compile a plan while normalizing internal validation failures."""

    try:
        return _compile_agentless_plan(request)
    except AgentlessCompilationError:
        raise
    except PydanticValidationError as exc:
        raise AgentlessCompilationError(
            "Compiled Agentless plan failed its invariant checks."
        ) from exc


def _validate_role_semantic_mappings(
    *,
    workflow: dict[str, Any],
    manifest: dict[str, Any],
    role: AgentlessWorkflowRole,
) -> tuple[tuple[str, ...], str | None]:
    mappings = manifest.get("nodes")
    if not isinstance(mappings, dict) or not mappings:
        return (), "Agentless workflow manifest requires non-empty semantic mappings."

    required = ROLE_REQUIRED_SEMANTIC_MAPPINGS[role]
    mapping_keys = {
        key
        for key in mappings
        if isinstance(key, str) and bool(key.strip())
    }
    missing = sorted(required - mapping_keys)
    errors: list[str] = []
    if missing:
        errors.append(
            "missing role mappings: " + ", ".join(missing)
        )

    validated: list[str] = []
    for semantic_key, mapping in sorted(
        mappings.items(),
        key=lambda item: str(item[0]),
    ):
        if not isinstance(semantic_key, str) or not semantic_key.strip():
            errors.append("semantic mapping key must be a non-blank string")
            continue
        if not isinstance(mapping, dict):
            errors.append(f"{semantic_key}: mapping must be an object")
            continue
        node_id = mapping.get("node_id")
        class_type = mapping.get("class_type")
        input_name = mapping.get("input")
        if not all(
            isinstance(value, str) and bool(value.strip())
            for value in (node_id, class_type, input_name)
        ):
            errors.append(
                f"{semantic_key}: node_id, class_type, and input are required"
            )
            continue
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            errors.append(
                f"{semantic_key}: workflow node {node_id!r} is missing"
            )
            continue
        if node.get("class_type") != class_type:
            errors.append(
                f"{semantic_key}: class_type does not match node {node_id!r}"
            )
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or input_name not in inputs:
            errors.append(
                f"{semantic_key}: input {input_name!r} is missing from "
                f"node {node_id!r}"
            )
            continue
        validated.append(semantic_key)

    if errors:
        detail = "; ".join(errors)
        if len(detail) > 950:
            detail = f"{detail[:947]}..."
        return tuple(sorted(validated)), detail
    return tuple(sorted(validated)), None


def _admission(
    db: Session,
    *,
    role: AgentlessWorkflowRole,
    template_ref: AgentlessTemplateRef,
) -> AgentlessWorkflowAdmission:
    if not template_ref.is_exact:
        return AgentlessWorkflowAdmission(
            role=role,
            template=template_ref,
            status=AgentlessWorkflowAdmissionStatus.MISSING_EXACT_PIN,
            admitted=False,
            detail=(
                "Exact workflow admission requires template_id, version, and "
                "SHA-256."
            ),
        )

    candidates = list(
        db.scalars(
            select(WorkflowTemplate).where(
                WorkflowTemplate.name == template_ref.template_id,
                WorkflowTemplate.version == template_ref.version,
                WorkflowTemplate.sha256 == template_ref.sha256,
            )
        )
    )
    if len(candidates) != 1:
        return AgentlessWorkflowAdmission(
            role=role,
            template=template_ref,
            status=AgentlessWorkflowAdmissionStatus.NOT_FOUND,
            admitted=False,
            detail=(
                "No unique WorkflowTemplate matches the exact template ID, "
                "version, and SHA-256 pin."
            ),
        )

    template = candidates[0]
    if not _is_api_prompt(template.workflow_api_json):
        return AgentlessWorkflowAdmission(
            role=role,
            template=template_ref,
            status=AgentlessWorkflowAdmissionStatus.NOT_API_FORMAT,
            admitted=False,
            template_record_id=template.id,
            detail="The pinned template is not a ComfyUI API-format prompt.",
        )
    if _sha256(template.workflow_api_json) != template.sha256:
        return AgentlessWorkflowAdmission(
            role=role,
            template=template_ref,
            status=AgentlessWorkflowAdmissionStatus.CONTENT_HASH_MISMATCH,
            admitted=False,
            template_record_id=template.id,
            detail=(
                "Stored API workflow content does not match its recorded "
                "SHA-256."
            ),
        )

    manifest = (
        template.manifest_json
        if isinstance(template.manifest_json, dict)
        else {}
    )
    if (
        manifest.get("api_format") is not True
        or manifest.get("runtime_qualified") is not True
    ):
        return AgentlessWorkflowAdmission(
            role=role,
            template=template_ref,
            status=(
                AgentlessWorkflowAdmissionStatus.NOT_RUNTIME_QUALIFIED
            ),
            admitted=False,
            template_record_id=template.id,
            detail=(
                "The exact API workflow has not passed the static runtime "
                "qualification gate."
            ),
        )
    if manifest.get("agentless_role") != role.value:
        return AgentlessWorkflowAdmission(
            role=role,
            template=template_ref,
            status=AgentlessWorkflowAdmissionStatus.ROLE_MISMATCH,
            admitted=False,
            template_record_id=template.id,
            detail=(
                "The admitted workflow manifest does not declare the required "
                f"Agentless role {role.value!r}."
            ),
        )

    validated_mappings, mapping_error = _validate_role_semantic_mappings(
        workflow=template.workflow_api_json,
        manifest=manifest,
        role=role,
    )
    if mapping_error is not None:
        return AgentlessWorkflowAdmission(
            role=role,
            template=template_ref,
            status=(
                AgentlessWorkflowAdmissionStatus.SEMANTIC_MAPPING_INVALID
            ),
            admitted=False,
            template_record_id=template.id,
            validated_semantic_mappings=validated_mappings,
            detail=mapping_error,
        )

    return AgentlessWorkflowAdmission(
        role=role,
        template=template_ref,
        status=AgentlessWorkflowAdmissionStatus.ADMITTED,
        admitted=True,
        template_record_id=template.id,
        validated_semantic_mappings=validated_mappings,
        detail="Exact API-format workflow is admitted for this semantic role.",
    )


def evaluate_agentless_readiness(
    db: Session,
    *,
    anchor_template: AgentlessTemplateRef,
    video_template: AgentlessTemplateRef,
) -> AgentlessReadiness:
    """Evaluate static workflow evidence while keeping execution fail closed."""

    admissions = (
        _admission(
            db,
            role=AgentlessWorkflowRole.FLUX_ANCHOR,
            template_ref=anchor_template,
        ),
        _admission(
            db,
            role=AgentlessWorkflowRole.LTX_INGREDIENTS_I2V,
            template_ref=video_template,
        ),
    )
    blockers = [
        AgentlessReadinessBlocker(
            code=f"{admission.role.value}_{admission.status.value}",
            workflow_role=admission.role,
            message=admission.detail,
        )
        for admission in admissions
        if not admission.admitted
    ]
    blockers.append(
        AgentlessReadinessBlocker(
            code="agentless_execution_boundary_not_implemented",
            message=(
                "This release exposes deterministic planning and dry-run only; "
                "it cannot enqueue or render Agentless jobs."
            ),
        )
    )
    return AgentlessReadiness(
        workflows_admitted=all(
            admission.admitted for admission in admissions
        ),
        admissions=admissions,
        blockers=tuple(blockers),
    )


def unpinned_agentless_readiness() -> AgentlessReadiness:
    """Return profile readiness before a request supplies exact workflow pins."""

    placeholder_anchor = AgentlessTemplateRef(
        template_id="flux2-scene-anchor",
    )
    placeholder_video = AgentlessTemplateRef(
        template_id="ltx23-ingredients-i2v-scene-reset",
    )
    admissions = (
        AgentlessWorkflowAdmission(
            role=AgentlessWorkflowRole.FLUX_ANCHOR,
            template=placeholder_anchor,
            status=AgentlessWorkflowAdmissionStatus.MISSING_EXACT_PIN,
            admitted=False,
            detail=(
                "Dry-run must pin the exact FLUX.2 API workflow version and "
                "SHA-256."
            ),
        ),
        AgentlessWorkflowAdmission(
            role=AgentlessWorkflowRole.LTX_INGREDIENTS_I2V,
            template=placeholder_video,
            status=AgentlessWorkflowAdmissionStatus.MISSING_EXACT_PIN,
            admitted=False,
            detail=(
                "Dry-run must pin the exact LTX-2.3 Ingredients + first-frame "
                "I2V API workflow version and SHA-256."
            ),
        ),
    )
    return AgentlessReadiness(
        workflows_admitted=False,
        admissions=admissions,
        blockers=(
            AgentlessReadinessBlocker(
                code="flux_anchor_missing_exact_pin",
                workflow_role=AgentlessWorkflowRole.FLUX_ANCHOR,
                message=admissions[0].detail,
            ),
            AgentlessReadinessBlocker(
                code="ltx_ingredients_i2v_missing_exact_pin",
                workflow_role=(
                    AgentlessWorkflowRole.LTX_INGREDIENTS_I2V
                ),
                message=admissions[1].detail,
            ),
            AgentlessReadinessBlocker(
                code="agentless_execution_boundary_not_implemented",
                message=(
                    "This release exposes deterministic planning and dry-run "
                    "only; it cannot enqueue or render Agentless jobs."
                ),
            ),
        ),
    )


def build_agentless_profile(
    *,
    project_id,
    selected_planning_agent: str = "qwen",
) -> AgentlessWorkflowProfileRead:
    return AgentlessWorkflowProfileRead(
        project_id=project_id,
        selected_planning_agent=selected_planning_agent,
        non_cumulative_guarantees=(
            "Every segment creates a fresh lossless FLUX.2 PNG anchor.",
            "No segment consumes a previous clip or previous final frame.",
            "LTX-2.3 always receives Ingredients conditioning and the accepted "
            "anchor as first-frame I2V conditioning.",
            "GPU generation is serialized with batch_size=1.",
        ),
        workflow_requirements=(
            AgentlessWorkflowRequirementRead(
                role=AgentlessWorkflowRole.FLUX_ANCHOR,
                model_family="FLUX.2",
                manifest_requirements=(
                    "api_format=true",
                    "runtime_qualified=true",
                    "agentless_role=flux_anchor",
                ),
                required_semantic_mappings=tuple(
                    sorted(
                        ROLE_REQUIRED_SEMANTIC_MAPPINGS[
                            AgentlessWorkflowRole.FLUX_ANCHOR
                        ]
                    )
                ),
                configuration_requirements=(
                    "multi-reference character conditioning",
                    "fresh PNG output per segment",
                    "semantic prompt/seed/dimension/output mappings",
                ),
            ),
            AgentlessWorkflowRequirementRead(
                role=AgentlessWorkflowRole.LTX_INGREDIENTS_I2V,
                model_family="LTX-2.3",
                manifest_requirements=(
                    "api_format=true",
                    "runtime_qualified=true",
                    "agentless_role=ltx_ingredients_i2v",
                ),
                required_semantic_mappings=tuple(
                    sorted(
                        ROLE_REQUIRED_SEMANTIC_MAPPINGS[
                            AgentlessWorkflowRole.LTX_INGREDIENTS_I2V
                        ]
                    )
                ),
                configuration_requirements=(
                    "Ingredients IC-LoRA reference input",
                    "first-frame I2V input",
                    "bypass_i2v=false",
                    "24fps and 8n+1 frame-count mappings",
                ),
            ),
        ),
        readiness=unpinned_agentless_readiness(),
    )


def dry_run_agentless_workflow(
    db: Session,
    request: AgentlessDryRunRequest,
) -> AgentlessDryRunRead:
    plan = compile_agentless_plan(request)
    readiness = evaluate_agentless_readiness(
        db,
        anchor_template=request.workflow_templates.anchor,
        video_template=request.workflow_templates.video,
    )
    return AgentlessDryRunRead(
        project_id=request.project_id,
        plan=plan,
        readiness=readiness,
    )
