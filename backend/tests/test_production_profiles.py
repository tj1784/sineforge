import pytest

from backend.app.services import generation_model_contract
from backend.app.services.production_profiles import (
    DEFAULT_PRODUCTION_PROFILE_REF,
    LEGACY_LTX_VIDEO_MODEL,
    LTX_BASE_PROFILE,
    LTX_SEQUENCE_PROFILE,
    ProductionProfileError,
    ProductionProfileOnHold,
    ProductionProfileQualificationRequired,
    UnknownProductionProfileError,
    WAN_BASE_PROFILE,
    canonical_production_profile_ref,
    list_production_profiles,
    resolve_production_profile,
    select_production_profile,
)


def _api_workflow(class_type: str, model_name: str) -> dict:
    return {
        "1": {
            "class_type": class_type,
            "inputs": {"model_name": model_name},
        }
    }


def test_legacy_selection_resolves_to_versioned_ltx_profile() -> None:
    assert DEFAULT_PRODUCTION_PROFILE_REF == "ltx_base@1"
    assert resolve_production_profile() is LTX_BASE_PROFILE
    assert resolve_production_profile("ltx") is LTX_BASE_PROFILE
    assert resolve_production_profile("ltx_base") is LTX_BASE_PROFILE
    assert (
        resolve_production_profile(generation_model_contract.VIDEO_MODEL_KEY)
        is LTX_BASE_PROFILE
    )
    assert (
        resolve_production_profile(generation_model_contract.VIDEO_MODEL)
        is LTX_BASE_PROFILE
    )
    assert generation_model_contract.VIDEO_PRODUCTION_PROFILE == "ltx_base@1"


def test_unknown_and_blank_profile_references_fail_closed() -> None:
    with pytest.raises(UnknownProductionProfileError, match="cannot be empty"):
        canonical_production_profile_ref(" ")
    with pytest.raises(UnknownProductionProfileError, match="Unknown production profile"):
        resolve_production_profile("future_profile@9")


def test_wan_profile_is_visible_for_planning_but_not_selectable_for_execution() -> None:
    assert resolve_production_profile("wan") is WAN_BASE_PROFILE
    assert WAN_BASE_PROFILE.ref == "wan_base@1"
    assert WAN_BASE_PROFILE.model_family == "wan"
    assert WAN_BASE_PROFILE.status == "on_hold"
    assert WAN_BASE_PROFILE.hold_reason == (
        "Local WAN dry run did not complete successfully."
    )
    assert WAN_BASE_PROFILE.selectable_for_execution is False
    assert select_production_profile("wan", allow_unqualified=True) is WAN_BASE_PROFILE
    with pytest.raises(
        ProductionProfileOnHold,
        match=r"wan_base@1 is on hold and cannot execute",
    ):
        select_production_profile("wan")
    assert list_production_profiles(include_unqualified=False) == (
        LTX_BASE_PROFILE,
        LTX_SEQUENCE_PROFILE,
    )


def test_profile_scoped_model_validation_preserves_ltx_and_blocks_draft_wan() -> None:
    generation_model_contract.require_approved_video_model(
        LEGACY_LTX_VIDEO_MODEL,
        production_profile="ltx_base@1",
    )
    with pytest.raises(ProductionProfileError, match=r"under ltx_base@1 requires"):
        generation_model_contract.require_approved_video_model(
            "ltx-2.3-22b-dev.safetensors",
            production_profile="ltx_base@1",
        )
    with pytest.raises(
        ProductionProfileOnHold,
        match=r"wan_base@1 is on hold and cannot execute",
    ):
        generation_model_contract.require_approved_video_model(
            "wan2.2-unqualified.safetensors",
            production_profile="wan_base@1",
        )


def test_workflow_validation_uses_selected_profile_and_detects_wan_loader() -> None:
    ltx_workflow = _api_workflow("LTXVLoader", LEGACY_LTX_VIDEO_MODEL)
    assert generation_model_contract.validate_workflow_base_models(
        ltx_workflow,
        "video",
        production_profile="ltx_base@1",
    ) == (LEGACY_LTX_VIDEO_MODEL,)

    wan_workflow = _api_workflow(
        "WanVideoModelLoader",
        "wan2.2-unqualified.safetensors",
    )
    assert generation_model_contract.workflow_base_model_references(wan_workflow) == (
        "wan2.2-unqualified.safetensors",
    )
    with pytest.raises(ProductionProfileQualificationRequired):
        generation_model_contract.validate_workflow_base_models(
            wan_workflow,
            "video",
            production_profile="wan_base@1",
        )


def test_ltx_frame_and_duration_policy_matches_legacy_contract() -> None:
    policy = LTX_BASE_PROFILE.frame_policy
    assert policy.accepts_frame_count(81)
    assert not policy.accepts_frame_count(80)
    assert policy.nominal_segment_duration_sec == 8.0
    assert policy.min_segment_duration_sec == 6.0
    assert policy.max_segment_duration_sec == 10.0
    policy.require_subscene_duration(8.0)
    with pytest.raises(ProductionProfileError, match="require a scene-specific reason"):
        policy.require_subscene_duration(5.0)


def test_ltx_sequence_profile_is_versioned_and_runtime_qualified() -> None:
    assert resolve_production_profile("ltx_sequence") is LTX_SEQUENCE_PROFILE
    assert LTX_SEQUENCE_PROFILE.ref == "ltx_base@2"
    assert LTX_SEQUENCE_PROFILE.model_family == "ltx"
    assert LTX_SEQUENCE_PROFILE.status == "qualified"
    assert LTX_SEQUENCE_PROFILE.execution_qualified is True
    assert LTX_SEQUENCE_PROFILE.selectable_for_execution is True
    assert LTX_SEQUENCE_PROFILE.approved_video_models == frozenset(
        {"sulphur2BaseQuants_dev.safetensors"}
    )
    assert LTX_SEQUENCE_PROFILE.capabilities.native_audio == "supported"
    assert LTX_SEQUENCE_PROFILE.capabilities.external_foley is False
    assert LTX_SEQUENCE_PROFILE.frame_policy.min_segment_duration_sec == 8.0
    assert LTX_SEQUENCE_PROFILE.frame_policy.max_segment_duration_sec == 15.0
    LTX_SEQUENCE_PROFILE.frame_policy.require_subscene_duration(8.0)
    LTX_SEQUENCE_PROFILE.frame_policy.require_subscene_duration(15.0)
    with pytest.raises(ProductionProfileError, match="shorter than 8 seconds"):
        LTX_SEQUENCE_PROFILE.frame_policy.require_subscene_duration(7.999)
    with pytest.raises(ProductionProfileError, match="exceeds 15 seconds"):
        LTX_SEQUENCE_PROFILE.frame_policy.require_subscene_duration(15.001)
    assert select_production_profile("ltx_base@2") is LTX_SEQUENCE_PROFILE


def test_wan_frame_and_logical_subscene_policy_is_explicit_and_bounded() -> None:
    policy = WAN_BASE_PROFILE.frame_policy
    assert policy.accepts_frame_count(81)
    assert not policy.accepts_frame_count(82)
    assert policy.nominal_segment_duration_sec is None
    policy.require_subscene_duration(15.0)
    policy.require_subscene_duration(90.0)
    policy.require_subscene_duration(8.0, shorter_reason="A required reaction beat.")
    with pytest.raises(ProductionProfileError, match="require a scene-specific reason"):
        policy.require_subscene_duration(8.0)
    with pytest.raises(ProductionProfileError, match="exceeds 90 seconds"):
        policy.require_subscene_duration(90.1)
