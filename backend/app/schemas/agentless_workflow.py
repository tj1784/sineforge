"""Strict contracts for the deterministic Agentless scene-reset lane.

The models in this module are intentionally planning-only.  They accept opaque
asset identifiers, never filesystem paths, and describe an isolated stage graph
for every generated segment.  The eventual executor must resolve and authorize
those identifiers within the route project before submission.  No contract in
this module authorizes ComfyUI submission or rendering.
"""

from __future__ import annotations

from enum import StrEnum
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


AGENTLESS_REQUEST_SCHEMA_VERSION = "sineforge.agentless-scene-reset-request/v1"
AGENTLESS_PLAN_SCHEMA_VERSION = "sineforge.agentless-scene-reset-plan/v1"
AGENTLESS_PROFILE_REF = "agentless-scene-reset@1"

MIN_LOGICAL_SCENE_DURATION_SEC = 3.0
MAX_LOGICAL_SCENE_DURATION_SEC = 20.0
MAX_LOGICAL_SCENES = 50
MAX_ATTEMPTS = 3
MAX_SEED = (2**63) - 1
MAX_SCENE_ID_LENGTH = 96
MAX_SCENE_OUTPUT_PREFIX_LENGTH = 100
MAX_REFERENCES_PER_CHARACTER = 8
MAX_TOTAL_CHARACTER_REFERENCE_ASSETS = 24
MAX_TOTAL_FLUX_NON_CHARACTER_REFERENCES = 16

DEFAULT_SEGMENT_DURATION_SEC = 10.0
FPS = 24
TEN_SECOND_FRAME_COUNT = 241
FRAME_MULTIPLE = 8
FRAME_REMAINDER = 1
DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 448
ALLOWED_RESOLUTIONS = frozenset({(768, 448), (960, 544)})
BATCH_SIZE = 1
MAX_ACTIVE_GPU_JOBS = 1


OpaqueId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$",
    ),
]
SceneId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_SCENE_ID_LENGTH,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$",
    ),
]
CharacterReferenceAssetIds = Annotated[
    tuple[OpaqueId, ...],
    Field(
        min_length=1,
        max_length=MAX_REFERENCES_PER_CHARACTER,
    ),
]
OptionalReferenceAssetIds = Annotated[
    tuple[OpaqueId, ...],
    Field(max_length=8),
]
TemplateVersion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$",
    ),
]
Sha256Hex = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[0-9a-fA-F]{64}$",
    ),
]


_OUTPUT_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)


class StrictAgentlessModel(BaseModel):
    # FastAPI validates an already-decoded JSON object, so container and UUID
    # coercion must remain enabled (JSON has arrays and strings, not Python
    # tuples and UUID instances).  Scalar request fields below opt into strict
    # validation individually while unknown fields remain forbidden.
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentlessWorkflowRole(StrEnum):
    FLUX_ANCHOR = "flux_anchor"
    LTX_INGREDIENTS_I2V = "ltx_ingredients_i2v"


class AgentlessStageKind(StrEnum):
    ANCHOR = "anchor"
    ANCHOR_QA = "anchor_qa"
    VIDEO = "video"
    VIDEO_QA = "video_qa"
    MASTER = "master"


class AgentlessWorkflowAdmissionStatus(StrEnum):
    MISSING_EXACT_PIN = "missing_exact_pin"
    NOT_FOUND = "not_found"
    NOT_API_FORMAT = "not_api_format"
    CONTENT_HASH_MISMATCH = "content_hash_mismatch"
    NOT_RUNTIME_QUALIFIED = "not_runtime_qualified"
    ROLE_MISMATCH = "role_mismatch"
    SEMANTIC_MAPPING_INVALID = "semantic_mapping_invalid"
    ADMITTED = "admitted"


class AgentlessIntermediateMasterCodec(StrEnum):
    PRORES_422_HQ = "prores_422_hq"
    FFV1 = "ffv1"


class AgentlessDeliveryCodec(StrEnum):
    H264 = "h264"
    H265 = "h265"


class AgentlessMasterPolicy(StrictAgentlessModel):
    """One lossless/mezzanine master followed by one delivery encode."""

    intermediate_codec: AgentlessIntermediateMasterCodec = (
        AgentlessIntermediateMasterCodec.PRORES_422_HQ
    )
    delivery_codec: AgentlessDeliveryCodec = AgentlessDeliveryCodec.H264
    delivery_encode_count: Literal[1] = 1
    intermediate_reencoding_allowed: Literal[False] = False
    anchor_format: Literal["png"] = "png"


class AgentlessFluxReferenceAssets(StrictAgentlessModel):
    """Typed non-character references used by FLUX.2 anchor generation."""

    set_studio_asset_ids: tuple[OpaqueId, ...] = Field(
        min_length=1,
        max_length=4,
    )
    composition_asset_ids: tuple[OpaqueId, ...] = Field(
        min_length=1,
        max_length=4,
    )
    pose_asset_ids: OptionalReferenceAssetIds = ()
    prop_asset_ids: OptionalReferenceAssetIds = ()

    @field_validator(
        "set_studio_asset_ids",
        "composition_asset_ids",
        "pose_asset_ids",
        "prop_asset_ids",
    )
    @classmethod
    def reject_duplicate_assets(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("FLUX reference lists must not contain duplicates")
        return value

    @model_validator(mode="after")
    def cap_total_references(self) -> "AgentlessFluxReferenceAssets":
        total = sum(
            len(asset_ids)
            for asset_ids in (
                self.set_studio_asset_ids,
                self.composition_asset_ids,
                self.pose_asset_ids,
                self.prop_asset_ids,
            )
        )
        if total > MAX_TOTAL_FLUX_NON_CHARACTER_REFERENCES:
            raise ValueError(
                "FLUX non-character references exceed the total cap of "
                f"{MAX_TOTAL_FLUX_NON_CHARACTER_REFERENCES}"
            )
        return self


class AgentlessTemplateRef(StrictAgentlessModel):
    """Semantic reference to one static workflow template.

    ``template_id`` is the public template key stored as
    ``WorkflowTemplate.name``.  Version and content hash remain optional for
    authoring, but readiness fails closed until both are pinned.
    """

    template_id: OpaqueId
    version: TemplateVersion | None = None
    sha256: Sha256Hex | None = None

    @property
    def is_exact(self) -> bool:
        return self.version is not None and self.sha256 is not None


class AgentlessWorkflowTemplateRefs(StrictAgentlessModel):
    anchor: AgentlessTemplateRef
    video: AgentlessTemplateRef

    @model_validator(mode="after")
    def require_distinct_semantic_templates(
        self,
    ) -> "AgentlessWorkflowTemplateRefs":
        if (
            self.anchor.template_id == self.video.template_id
            and self.anchor.version == self.video.version
        ):
            raise ValueError(
                "anchor and video must reference distinct semantic workflow "
                "templates"
            )
        return self


class AgentlessSceneManifest(StrictAgentlessModel):
    """One logical scene before deterministic segmentation."""

    scene_id: SceneId
    duration_sec: float = Field(
        ge=MIN_LOGICAL_SCENE_DURATION_SEC,
        le=MAX_LOGICAL_SCENE_DURATION_SEC,
        allow_inf_nan=False,
        strict=True,
    )
    visible_character_ids: tuple[OpaqueId, ...] = Field(
        min_length=1,
        max_length=8,
    )
    character_reference_asset_ids: dict[
        OpaqueId,
        CharacterReferenceAssetIds,
    ] = Field(min_length=1, max_length=8)
    flux_reference_assets: AgentlessFluxReferenceAssets
    ingredients_reference_asset_id: OpaqueId
    character_description_block: str = Field(
        min_length=1,
        max_length=8_000,
    )
    anchor_prompt: str = Field(min_length=1, max_length=16_000)
    video_prompt: str = Field(min_length=1, max_length=16_000)
    negative_prompt: str = Field(default="", max_length=8_000)
    image_seed: int = Field(ge=0, le=MAX_SEED, strict=True)
    video_seed: int = Field(ge=0, le=MAX_SEED, strict=True)
    width: int = Field(default=DEFAULT_WIDTH, strict=True)
    height: int = Field(default=DEFAULT_HEIGHT, strict=True)
    ingredients_lora_strength: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        allow_inf_nan=False,
        strict=True,
    )
    distilled_lora_strength: float = Field(
        default=0.5,
        ge=0.0,
        le=2.0,
        allow_inf_nan=False,
        strict=True,
    )
    bypass_i2v: Literal[False] = False
    output_prefix: str = Field(
        min_length=1,
        max_length=MAX_SCENE_OUTPUT_PREFIX_LENGTH,
    )
    audio_asset_id: OpaqueId | None = None
    anchor_max_attempts: int = Field(
        default=3,
        ge=1,
        le=MAX_ATTEMPTS,
        strict=True,
    )
    video_max_attempts: int = Field(
        default=3,
        ge=1,
        le=MAX_ATTEMPTS,
        strict=True,
    )

    @field_validator(
        "character_description_block",
        "anchor_prompt",
        "video_prompt",
    )
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("prompt must not be blank")
        return normalized

    @field_validator("negative_prompt")
    @classmethod
    def normalize_negative_prompt(cls, value: str) -> str:
        return value.strip()

    @field_validator("visible_character_ids")
    @classmethod
    def reject_duplicate_characters(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("visible_character_ids must not contain duplicates")
        return value

    @field_validator("character_reference_asset_ids")
    @classmethod
    def reject_duplicate_reference_assets(
        cls,
        value: dict[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        for character_id, asset_ids in value.items():
            if not asset_ids:
                raise ValueError(
                    f"character {character_id!r} requires at least one "
                    "reference asset"
                )
            if len(asset_ids) != len(set(asset_ids)):
                raise ValueError(
                    f"character {character_id!r} has duplicate reference assets"
                )
        total = sum(len(asset_ids) for asset_ids in value.values())
        if total > MAX_TOTAL_CHARACTER_REFERENCE_ASSETS:
            raise ValueError(
                "character references exceed the total cap of "
                f"{MAX_TOTAL_CHARACTER_REFERENCE_ASSETS}"
            )
        return value

    @field_validator("output_prefix")
    @classmethod
    def validate_output_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if (
            not _OUTPUT_PREFIX_PATTERN.fullmatch(normalized)
            or ".." in normalized
            or normalized.endswith(".")
        ):
            raise ValueError(
                "output_prefix must be an opaque safe prefix using only "
                "letters, digits, underscore, hyphen, or non-trailing dot"
            )
        reserved_stem = normalized.split(".", 1)[0].upper()
        if reserved_stem in _WINDOWS_RESERVED_NAMES:
            raise ValueError("output_prefix is a reserved Windows filename")
        return normalized

    @model_validator(mode="after")
    def validate_scene_bindings(self) -> "AgentlessSceneManifest":
        if self.image_seed == self.video_seed:
            raise ValueError("image_seed and video_seed must be separate values")
        if set(self.visible_character_ids) != set(
            self.character_reference_asset_ids
        ):
            raise ValueError(
                "character_reference_asset_ids must contain exactly the visible "
                "characters"
            )
        if (self.width, self.height) not in ALLOWED_RESOLUTIONS:
            allowed = ", ".join(
                f"{width}x{height}"
                for width, height in sorted(ALLOWED_RESOLUTIONS)
            )
            raise ValueError(f"resolution must be one of: {allowed}")
        return self


class AgentlessDryRunRequest(StrictAgentlessModel):
    schema_version: Literal[AGENTLESS_REQUEST_SCHEMA_VERSION] = (
        AGENTLESS_REQUEST_SCHEMA_VERSION
    )
    project_id: UUID
    workflow_templates: AgentlessWorkflowTemplateRefs
    master_policy: AgentlessMasterPolicy = Field(
        default_factory=AgentlessMasterPolicy
    )
    scenes: tuple[AgentlessSceneManifest, ...] = Field(
        min_length=1,
        max_length=MAX_LOGICAL_SCENES,
    )

    @model_validator(mode="after")
    def require_unique_scene_identity(self) -> "AgentlessDryRunRequest":
        scene_ids = [scene.scene_id for scene in self.scenes]
        output_prefixes = [
            scene.output_prefix.casefold() for scene in self.scenes
        ]
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("scene_id values must be unique")
        if len(output_prefixes) != len(set(output_prefixes)):
            raise ValueError("output_prefix values must be unique")
        return self


class AgentlessAnchorPlan(StrictAgentlessModel):
    workflow_template: AgentlessTemplateRef
    model_family: Literal["FLUX.2"] = "FLUX.2"
    generation_mode: Literal["multi_reference_image"] = "multi_reference_image"
    image_seed: int = Field(ge=0, le=MAX_SEED)
    character_description_block: str = Field(min_length=1, max_length=8_000)
    scene_prompt: str = Field(min_length=1, max_length=16_000)
    prompt: str = Field(min_length=1, max_length=24_100)
    visible_character_ids: tuple[OpaqueId, ...]
    character_reference_asset_ids: dict[
        OpaqueId,
        CharacterReferenceAssetIds,
    ]
    flux_reference_assets: AgentlessFluxReferenceAssets
    width: int
    height: int
    output_prefix: str
    anchor_format: Literal["png"] = "png"
    fresh_anchor: Literal[True] = True
    previous_clip_asset_id: Literal[None] = None
    previous_frame_asset_id: Literal[None] = None
    max_attempts: int = Field(ge=1, le=MAX_ATTEMPTS)


class AgentlessVideoPlan(StrictAgentlessModel):
    workflow_template: AgentlessTemplateRef
    model_family: Literal["LTX-2.3"] = "LTX-2.3"
    conditioning: Literal["ingredients_ic_lora+first_frame_i2v"] = (
        "ingredients_ic_lora+first_frame_i2v"
    )
    ingredients_reference_asset_id: OpaqueId
    scene_anchor_stage_id: OpaqueId
    first_frame_i2v: Literal[True] = True
    bypass_i2v: Literal[False] = False
    previous_clip_asset_id: Literal[None] = None
    previous_frame_asset_id: Literal[None] = None
    video_seed: int = Field(ge=0, le=MAX_SEED)
    character_description_block: str = Field(min_length=1, max_length=8_000)
    scene_prompt: str = Field(min_length=1, max_length=16_000)
    prompt: str = Field(min_length=1, max_length=24_100)
    negative_prompt: str = Field(max_length=8_000)
    width: int
    height: int
    fps: Literal[FPS] = FPS
    frame_count: int = Field(gt=1)
    requested_duration_sec: float = Field(gt=0, allow_inf_nan=False)
    playback_duration_sec: float = Field(gt=0, allow_inf_nan=False)
    duration_delta_sec: float = Field(allow_inf_nan=False)
    ingredients_lora_strength: float = Field(ge=0.0, le=2.0)
    distilled_lora_strength: float = Field(ge=0.0, le=2.0)
    audio_asset_id: OpaqueId | None = None
    audio_source_offset_sec: float = Field(
        ge=0,
        allow_inf_nan=False,
    )
    audio_segment_duration_sec: float = Field(
        gt=0,
        le=DEFAULT_SEGMENT_DURATION_SEC,
        allow_inf_nan=False,
    )
    output_prefix: str
    batch_size: Literal[BATCH_SIZE] = BATCH_SIZE
    max_attempts: int = Field(ge=1, le=MAX_ATTEMPTS)

    @model_validator(mode="after")
    def require_ltx_frame_policy(self) -> "AgentlessVideoPlan":
        if self.frame_count % FRAME_MULTIPLE != FRAME_REMAINDER:
            raise ValueError("LTX frame_count must satisfy 8n+1")
        if (
            self.requested_duration_sec == DEFAULT_SEGMENT_DURATION_SEC
            and self.frame_count != TEN_SECOND_FRAME_COUNT
        ):
            raise ValueError("a 10-second LTX segment must contain 241 frames")
        expected_playback = self.frame_count / self.fps
        if abs(self.playback_duration_sec - expected_playback) > 1e-9:
            raise ValueError(
                "playback_duration_sec must equal frame_count divided by fps"
            )
        if self.audio_segment_duration_sec != self.requested_duration_sec:
            raise ValueError(
                "audio segment duration must match requested segment duration"
            )
        return self


class AgentlessSegmentPlan(StrictAgentlessModel):
    segment_id: OpaqueId
    logical_scene_id: OpaqueId
    segment_index: int = Field(ge=0, le=1)
    segment_label: Literal["single", "A", "B"]
    requested_duration_sec: float = Field(gt=0, le=10, allow_inf_nan=False)
    playback_duration_sec: float = Field(gt=0, allow_inf_nan=False)
    duration_delta_sec: float = Field(allow_inf_nan=False)
    frame_count: int = Field(gt=1)
    fps: Literal[FPS] = FPS
    output_prefix: str
    image_seed: int = Field(ge=0, le=MAX_SEED)
    video_seed: int = Field(ge=0, le=MAX_SEED)
    independently_anchored: Literal[True] = True
    anchor: AgentlessAnchorPlan
    video: AgentlessVideoPlan

    @model_validator(mode="after")
    def require_matching_compiled_inputs(self) -> "AgentlessSegmentPlan":
        if self.image_seed == self.video_seed:
            raise ValueError("compiled image_seed and video_seed must differ")
        if self.anchor.image_seed != self.image_seed:
            raise ValueError("anchor image_seed does not match segment image_seed")
        if self.video.video_seed != self.video_seed:
            raise ValueError("video video_seed does not match segment video_seed")
        if self.video.frame_count != self.frame_count:
            raise ValueError("video frame_count does not match segment frame_count")
        if self.video.playback_duration_sec != self.playback_duration_sec:
            raise ValueError(
                "video playback_duration_sec does not match segment"
            )
        if self.video.output_prefix != self.output_prefix:
            raise ValueError("video output_prefix does not match segment")
        return self


class AgentlessStageNode(StrictAgentlessModel):
    stage_id: OpaqueId
    segment_id: OpaqueId
    kind: AgentlessStageKind
    depends_on_stage_ids: tuple[OpaqueId, ...] = ()
    workflow_role: AgentlessWorkflowRole | None = None
    uses_gpu: bool
    batch_size: Literal[BATCH_SIZE] = BATCH_SIZE
    max_attempts: int = Field(ge=1, le=MAX_ATTEMPTS)
    output_artifact_kind: Literal[
        "lossless_anchor_png",
        "anchor_qa_report",
        "video_candidate",
        "video_qa_report",
        "lossless_master",
    ]


class CompiledAgentlessPlan(StrictAgentlessModel):
    schema_version: Literal[AGENTLESS_PLAN_SCHEMA_VERSION] = (
        AGENTLESS_PLAN_SCHEMA_VERSION
    )
    source_schema_version: Literal[AGENTLESS_REQUEST_SCHEMA_VERSION] = (
        AGENTLESS_REQUEST_SCHEMA_VERSION
    )
    project_id: UUID
    workflow_lane: Literal["agentless"] = "agentless"
    profile_ref: Literal[AGENTLESS_PROFILE_REF] = AGENTLESS_PROFILE_REF
    workflow_templates: AgentlessWorkflowTemplateRefs
    master_policy: AgentlessMasterPolicy
    logical_scene_count: int = Field(ge=1, le=MAX_LOGICAL_SCENES)
    segment_count: int = Field(ge=1, le=MAX_LOGICAL_SCENES * 2)
    segments: tuple[AgentlessSegmentPlan, ...]
    stages: tuple[AgentlessStageNode, ...]
    batch_size: Literal[BATCH_SIZE] = BATCH_SIZE
    max_active_gpu_jobs: Literal[MAX_ACTIVE_GPU_JOBS] = MAX_ACTIVE_GPU_JOBS
    backend_owns_pending_queue: Literal[True] = True
    previous_clip_dependency_allowed: Literal[False] = False
    previous_frame_dependency_allowed: Literal[False] = False
    fresh_anchor_required_per_segment: Literal[True] = True
    submission_enabled: Literal[False] = False
    plan_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_isolated_stage_graph(self) -> "CompiledAgentlessPlan":
        if self.logical_scene_count != len(
            {segment.logical_scene_id for segment in self.segments}
        ):
            raise ValueError("logical_scene_count does not match segments")
        if self.segment_count != len(self.segments):
            raise ValueError("segment_count does not match segments")
        if len(self.stages) != self.segment_count * 5:
            raise ValueError("each segment requires exactly five stages")

        segment_ids = [segment.segment_id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("derived segment_id values must be unique")

        artifact_prefixes = [
            prefix.casefold()
            for segment in self.segments
            for prefix in (
                segment.output_prefix,
                segment.anchor.output_prefix,
            )
        ]
        if len(artifact_prefixes) != len(set(artifact_prefixes)):
            raise ValueError(
                "derived video and anchor output prefixes must be unique"
            )

        stages_by_id = {stage.stage_id: stage for stage in self.stages}
        if len(stages_by_id) != len(self.stages):
            raise ValueError("stage_id values must be unique")

        expected_dependencies = {
            AgentlessStageKind.ANCHOR: (),
            AgentlessStageKind.ANCHOR_QA: (AgentlessStageKind.ANCHOR,),
            AgentlessStageKind.VIDEO: (AgentlessStageKind.ANCHOR_QA,),
            AgentlessStageKind.VIDEO_QA: (AgentlessStageKind.VIDEO,),
            AgentlessStageKind.MASTER: (AgentlessStageKind.VIDEO_QA,),
        }
        for segment in self.segments:
            segment_stages = {
                stage.kind: stage
                for stage in self.stages
                if stage.segment_id == segment.segment_id
            }
            if set(segment_stages) != set(AgentlessStageKind):
                raise ValueError(
                    f"segment {segment.segment_id!r} does not have the exact "
                    "five-stage pipeline"
                )
            for kind, expected_kinds in expected_dependencies.items():
                stage = segment_stages[kind]
                dependencies = tuple(
                    stages_by_id[dependency_id]
                    for dependency_id in stage.depends_on_stage_ids
                    if dependency_id in stages_by_id
                )
                if len(dependencies) != len(stage.depends_on_stage_ids):
                    raise ValueError(
                        f"stage {stage.stage_id!r} references an unknown stage"
                    )
                if any(
                    dependency.segment_id != segment.segment_id
                    for dependency in dependencies
                ):
                    raise ValueError(
                        "Agentless stage dependencies cannot cross segment "
                        "boundaries"
                    )
                if tuple(dependency.kind for dependency in dependencies) != (
                    expected_kinds
                ):
                    raise ValueError(
                        f"stage {stage.stage_id!r} has invalid dependencies"
                    )
        return self


class AgentlessWorkflowAdmission(StrictAgentlessModel):
    role: AgentlessWorkflowRole
    template: AgentlessTemplateRef
    status: AgentlessWorkflowAdmissionStatus
    admitted: bool
    template_record_id: UUID | None = None
    validated_semantic_mappings: tuple[str, ...] = ()
    detail: str = Field(min_length=1, max_length=1_000)


class AgentlessReadinessBlocker(StrictAgentlessModel):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=1_000)
    workflow_role: AgentlessWorkflowRole | None = None


class AgentlessReadiness(StrictAgentlessModel):
    ready_to_execute: Literal[False] = False
    workflows_admitted: bool
    submission_supported: Literal[False] = False
    admissions: tuple[AgentlessWorkflowAdmission, ...]
    blockers: tuple[AgentlessReadinessBlocker, ...]


class AgentlessWorkflowRequirementRead(StrictAgentlessModel):
    role: AgentlessWorkflowRole
    model_family: Literal["FLUX.2", "LTX-2.3"]
    exact_template_pin_required: Literal[True] = True
    required_pin_fields: tuple[
        Literal["template_id", "version", "sha256"],
        ...,
    ] = ("template_id", "version", "sha256")
    manifest_requirements: tuple[str, ...]
    required_semantic_mappings: tuple[str, ...]
    configuration_requirements: tuple[str, ...]


class AgentlessWorkflowProfileRead(StrictAgentlessModel):
    project_id: UUID
    workflow_lane: Literal["agentless"] = "agentless"
    profile_ref: Literal[AGENTLESS_PROFILE_REF] = AGENTLESS_PROFILE_REF
    display_name: Literal["Agentless Workflow"] = "Agentless Workflow"
    agent_runtime_required: Literal[True] = True
    local_planning_agent_required: Literal[True] = True
    hosted_planning_agents_allowed: Literal[False] = False
    default_planning_agent: Literal["grok"] = "grok"
    selected_planning_agent: Literal["qwen", "sulphur", "grok"] = "grok"
    prompt_artifact_format: Literal["json"] = "json"
    prompt_artifact_extension: Literal[".json"] = ".json"
    deterministic_python_orchestrator: Literal[True] = True
    logical_scene_duration_range_sec: tuple[Literal[3], Literal[20]] = (3, 20)
    default_segment_duration_sec: Literal[10] = 10
    default_fps: Literal[FPS] = FPS
    default_ten_second_frame_count: Literal[TEN_SECOND_FRAME_COUNT] = (
        TEN_SECOND_FRAME_COUNT
    )
    default_ten_second_playback_duration_sec: float = (
        TEN_SECOND_FRAME_COUNT / FPS
    )
    ltx_frame_policy: Literal["8n+1"] = "8n+1"
    max_logical_scenes: Literal[MAX_LOGICAL_SCENES] = MAX_LOGICAL_SCENES
    allowed_resolutions: tuple[tuple[int, int], ...] = (
        (DEFAULT_WIDTH, DEFAULT_HEIGHT),
        (960, 544),
    )
    batch_size: Literal[BATCH_SIZE] = BATCH_SIZE
    max_active_gpu_jobs: Literal[MAX_ACTIVE_GPU_JOBS] = MAX_ACTIVE_GPU_JOBS
    max_attempts_per_generation_stage: Literal[MAX_ATTEMPTS] = MAX_ATTEMPTS
    default_master_policy: AgentlessMasterPolicy = Field(
        default_factory=AgentlessMasterPolicy
    )
    pipeline: tuple[
        Literal["anchor", "anchor_qa", "video", "video_qa", "master"],
        ...,
    ] = ("anchor", "anchor_qa", "video", "video_qa", "master")
    non_cumulative_guarantees: tuple[str, ...]
    workflow_requirements: tuple[AgentlessWorkflowRequirementRead, ...]
    readiness: AgentlessReadiness


class AgentlessDryRunRead(StrictAgentlessModel):
    valid: Literal[True] = True
    status: Literal["valid_with_blockers"] = "valid_with_blockers"
    project_id: UUID
    workflow_lane: Literal["agentless"] = "agentless"
    plan: CompiledAgentlessPlan
    readiness: AgentlessReadiness
