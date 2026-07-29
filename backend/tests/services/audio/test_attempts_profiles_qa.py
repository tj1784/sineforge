import math

import pytest

from backend.app.services.audio import (
    DeliveryProfileName,
    FrameRate,
    PictureLock,
    PictureLockError,
    SilenceQAConfig,
    TimeBase,
    build_attempt_metadata,
    evaluate_silence,
    get_delivery_profile,
    plan_foley_windows,
)


def one_window():
    lock = PictureLock(
        content_hash="locked-picture",
        total_frames=240,
        frame_rate=FrameRate(30),
        time_base=TimeBase(1, 90_000),
    )
    window = plan_foley_windows(
        lock,
        expected_picture_lock_hash=lock.content_hash,
    )[0]
    return lock, window


def test_attempt_metadata_is_reproducible_and_retry_specific() -> None:
    lock, window = one_window()
    inputs = {
        "current_picture_lock_hash": lock.content_hash,
        "base_seed": 1234,
        "model_id": "hunyuan-video-foley-xxl",
        "model_hash": "model-sha256",
        "workflow_hash": "workflow-sha256",
        "prompt_hash": "prompt-sha256",
    }

    first = build_attempt_metadata(window, attempt_number=1, **inputs)
    repeated = build_attempt_metadata(window, attempt_number=1, **inputs)
    retry = build_attempt_metadata(window, attempt_number=2, **inputs)

    assert first == repeated
    assert first.seed >= 0
    assert first.attempt_id != retry.attempt_id
    assert first.seed != retry.seed


def test_attempt_metadata_refuses_stale_picture() -> None:
    _, window = one_window()

    with pytest.raises(PictureLockError, match="stale"):
        build_attempt_metadata(
            window,
            current_picture_lock_hash="changed-picture",
            attempt_number=1,
            base_seed=1,
            model_id="model",
            model_hash="model-hash",
            workflow_hash="workflow-hash",
            prompt_hash="prompt-hash",
        )


def test_delivery_profiles_expose_mastering_intent() -> None:
    web = get_delivery_profile("web")
    broadcast = get_delivery_profile(DeliveryProfileName.BROADCAST)
    preserve = get_delivery_profile("preserve_dynamics")

    assert web.integrated_lufs == -16.0
    assert broadcast.integrated_lufs == -23.0
    assert preserve.integrated_lufs is None
    assert preserve.maximum_true_peak_dbtp == -1.0


def test_silence_qa_rejects_wrapper_silence_fallback() -> None:
    result = evaluate_silence([0.0] * 48_000, expected_sample_count=48_000)

    assert not result.passed
    assert result.is_silent
    assert "unexpected silence detected" in result.findings
    assert result.peak_dbfs == float("-inf")


def test_silence_qa_accepts_finite_non_silent_exact_length_audio() -> None:
    samples = [0.1 if index % 2 else -0.1 for index in range(48_000)]

    result = evaluate_silence(samples, expected_sample_count=48_000)

    assert result.passed
    assert not result.is_silent
    assert result.finite
    assert math.isclose(result.peak_dbfs, -20.0)


def test_silence_qa_reports_length_nonfinite_and_full_scale_failures() -> None:
    result = evaluate_silence(
        [float("nan"), 1.1],
        expected_sample_count=4,
        config=SilenceQAConfig(sample_count_tolerance=1),
    )

    assert not result.passed
    assert not result.finite
    assert "audio contains non-finite PCM samples" in result.findings
    assert "PCM peak exceeds nominal full scale" in result.findings
    assert any("sample count mismatch" in finding for finding in result.findings)

