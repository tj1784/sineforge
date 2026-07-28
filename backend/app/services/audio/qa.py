"""Dependency-free QA for generated PCM Foley samples."""

from __future__ import annotations

import math
from collections.abc import Iterable

from .contracts import SilenceQAConfig, SilenceQAResult


def _to_dbfs(amplitude: float) -> float:
    if amplitude <= 0:
        return float("-inf")
    return 20.0 * math.log10(amplitude)


def evaluate_silence(
    samples: Iterable[float],
    *,
    expected_sample_count: int,
    config: SilenceQAConfig | None = None,
) -> SilenceQAResult:
    """Validate mono PCM floats in nominal ``[-1, 1]`` amplitude units."""

    if expected_sample_count <= 0:
        raise ValueError("expected_sample_count must be positive")
    config = config or SilenceQAConfig()
    count = 0
    sum_squares = 0.0
    peak = 0.0
    finite = True
    for value in samples:
        sample = float(value)
        count += 1
        if not math.isfinite(sample):
            finite = False
            continue
        magnitude = abs(sample)
        peak = max(peak, magnitude)
        sum_squares += sample * sample

    rms = math.sqrt(sum_squares / count) if count and finite else 0.0
    peak_dbfs = _to_dbfs(peak)
    rms_dbfs = _to_dbfs(rms)
    is_silent = (
        finite
        and peak_dbfs <= config.peak_silence_dbfs
        and rms_dbfs <= config.rms_silence_dbfs
    )
    findings: list[str] = []
    if not finite:
        findings.append("audio contains non-finite PCM samples")
    if abs(count - expected_sample_count) > config.sample_count_tolerance:
        findings.append(
            f"sample count mismatch: expected {expected_sample_count}, got {count}"
        )
    if is_silent:
        findings.append("unexpected silence detected")
    if peak > 1.0:
        findings.append("PCM peak exceeds nominal full scale")

    return SilenceQAResult(
        passed=not findings,
        is_silent=is_silent,
        finite=finite,
        expected_sample_count=expected_sample_count,
        actual_sample_count=count,
        peak_dbfs=peak_dbfs,
        rms_dbfs=rms_dbfs,
        findings=tuple(findings),
    )

