"""Deterministic scene-count planning for short generated video clips."""

from __future__ import annotations

import math
from dataclasses import dataclass


NOMINAL_CLIP_DURATION_SEC = 8.0
MIN_CLIP_DURATION_SEC = 6.0
MAX_CLIP_DURATION_SEC = 10.0


@dataclass(frozen=True)
class SceneClipPlan:
    target_duration_sec: float
    planned_scene_count: int
    scene_duration_plan_sec: tuple[float, ...]

    @property
    def durations_within_generation_range(self) -> bool:
        return all(
            MIN_CLIP_DURATION_SEC <= duration <= MAX_CLIP_DURATION_SEC
            for duration in self.scene_duration_plan_sec
        )


def plan_scenes_for_duration(target_duration_sec: float) -> SceneClipPlan:
    """Plan ceil(total seconds / 8) scenes whose durations sum to the target.

    The Sulphur homepage intake requires at least 24 seconds, which guarantees
    the equalized durations produced by this rule remain inside the supported
    6–10 second generation range.
    """

    target = round(float(target_duration_sec), 3)
    if not math.isfinite(target) or target <= 0:
        raise ValueError("target_duration_sec must be a positive finite number")

    scene_count = max(1, math.ceil(target / NOMINAL_CLIP_DURATION_SEC))
    even_duration = round(target / scene_count, 3)
    durations = [even_duration for _ in range(scene_count)]
    durations[-1] = round(target - sum(durations[:-1]), 3)
    return SceneClipPlan(
        target_duration_sec=target,
        planned_scene_count=scene_count,
        scene_duration_plan_sec=tuple(durations),
    )
