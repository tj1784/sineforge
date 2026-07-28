"""Non-rendering Phase 7 video-domain API routes.

This router is intentionally not registered here.  It validates and constructs
domain contracts only; it never reads local paths, executes ComfyUI/FFmpeg, or
claims that media has been rendered.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.video import (
    CompileSubsceneRequest,
    CompileSubsceneResponse,
    ConstructPictureLockRequest,
    EditDecisionRead,
    PhaseSevenCapabilitiesRead,
    PhaseSevenPolicyRead,
    PictureLockRead,
    RenderSegmentRead,
    ValidateEdlRequest,
    ValidateEdlResponse,
)
from backend.app.services.video import (
    DomainValidationError,
    EditDecision,
    EditDecisionList,
    PictureLock,
    ProviderRenderConstraints,
    Subscene,
    compile_render_segments,
)


router = APIRouter(prefix="/video/phase-7", tags=["video-phase-7"])


def _unprocessable(error: DomainValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "video_domain_validation_failed", "message": str(error)},
    )


def _to_edl(payload: ValidateEdlRequest) -> EditDecisionList:
    try:
        return EditDecisionList(
            edl_id=payload.edl_id,
            stitch_stage=payload.stitch_stage,
            fps_numerator=payload.fps_numerator,
            fps_denominator=payload.fps_denominator,
            decisions=tuple(
                EditDecision(
                    decision_id=item.decision_id,
                    asset_id=item.asset_id,
                    asset_sha256=item.asset_sha256,
                    source_start_frame=item.source_start_frame,
                    source_end_frame_exclusive=item.source_end_frame_exclusive,
                    timeline_start_frame=item.timeline_start_frame,
                    drop_leading_frames=item.drop_leading_frames,
                )
                for item in payload.decisions
            ),
        )
    except DomainValidationError as error:
        raise _unprocessable(error) from error


def _edl_response(edl: EditDecisionList) -> ValidateEdlResponse:
    return ValidateEdlResponse(
        edl_id=edl.edl_id,
        stitch_stage=edl.stitch_stage,
        fps_numerator=edl.fps_numerator,
        fps_denominator=edl.fps_denominator,
        total_frame_count=edl.total_frame_count,
        duration_sec=edl.duration_sec,
        edl_sha256=edl.sha256,
        decisions=tuple(
            EditDecisionRead(
                **item.canonical_dict(),
                source_frame_count=item.source_frame_count,
                timeline_frame_count=item.timeline_frame_count,
                timeline_end_frame_exclusive=item.timeline_end_frame_exclusive,
            )
            for item in edl.decisions
        ),
    )


@router.get("/policy", response_model=PhaseSevenPolicyRead)
def get_phase_seven_policy() -> PhaseSevenPolicyRead:
    return PhaseSevenPolicyRead()


@router.get("/capabilities", response_model=PhaseSevenCapabilitiesRead)
def get_phase_seven_capabilities() -> PhaseSevenCapabilitiesRead:
    return PhaseSevenCapabilitiesRead()


@router.post(
    "/subscenes/compile",
    response_model=CompileSubsceneResponse,
)
def compile_subscene(payload: CompileSubsceneRequest) -> CompileSubsceneResponse:
    try:
        subscene = Subscene(
            subscene_id=payload.subscene.subscene_id,
            duration_sec=payload.subscene.duration_sec,
            short_reason=payload.subscene.short_reason,
        )
        constraints = ProviderRenderConstraints(
            **payload.provider.model_dump()
        )
        plans = compile_render_segments(subscene, constraints)
    except DomainValidationError as error:
        raise _unprocessable(error) from error

    return CompileSubsceneResponse(
        subscene_id=subscene.subscene_id,
        editorial_duration_sec=subscene.duration_sec,
        short_exception=subscene.is_short_exception,
        segment_count=len(plans),
        expected_effective_frame_count=sum(
            item.effective_frame_count for item in plans
        ),
        segments=tuple(
            RenderSegmentRead(
                segment_id=item.segment_id,
                subscene_id=item.subscene_id,
                segment_index=item.segment_index,
                timeline_start_sec=item.timeline_start_sec,
                timeline_end_sec=item.timeline_end_sec,
                requested_duration_sec=item.requested_duration_sec,
                frame_count=item.frame_count,
                drop_leading_frames=item.drop_leading_frames,
                effective_frame_count=item.effective_frame_count,
                expected_output_duration_sec=item.expected_output_duration_sec,
                provider_profile_id=item.provider_profile_id,
                fps_numerator=item.fps_numerator,
                fps_denominator=item.fps_denominator,
            )
            for item in plans
        ),
    )


@router.post("/edl/validate", response_model=ValidateEdlResponse)
def validate_edl(payload: ValidateEdlRequest) -> ValidateEdlResponse:
    return _edl_response(_to_edl(payload))


@router.post("/picture-locks/construct", response_model=PictureLockRead)
def construct_picture_lock(
    payload: ConstructPictureLockRequest,
) -> PictureLockRead:
    edl = _to_edl(payload.edl)
    try:
        picture_lock = PictureLock.from_edl(
            picture_lock_id=payload.picture_lock_id,
            edl=edl,
            final_video_asset_id=payload.final_video_asset_id,
            final_video_sha256=payload.final_video_sha256,
            assembly_manifest_sha256=payload.assembly_manifest_sha256,
            width=payload.width,
            height=payload.height,
            pixel_format=payload.pixel_format,
            locked_at=payload.locked_at,
        )
    except DomainValidationError as error:
        raise _unprocessable(error) from error

    return PictureLockRead(
        picture_lock_id=picture_lock.picture_lock_id,
        edl_sha256=picture_lock.edl_sha256,
        final_video_asset_id=picture_lock.final_video_asset_id,
        final_video_sha256=picture_lock.final_video_sha256,
        assembly_manifest_sha256=picture_lock.assembly_manifest_sha256,
        frame_count=picture_lock.frame_count,
        fps_numerator=picture_lock.fps_numerator,
        fps_denominator=picture_lock.fps_denominator,
        duration_sec=picture_lock.duration_sec,
        width=picture_lock.width,
        height=picture_lock.height,
        pixel_format=picture_lock.pixel_format,
        stitch_stage=picture_lock.stitch_stage,
        selected_asset_ids=picture_lock.selected_asset_ids,
        locked_at=picture_lock.locked_at,
    )
