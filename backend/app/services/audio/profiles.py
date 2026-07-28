"""Named delivery/mastering profiles without an FFmpeg dependency."""

from __future__ import annotations

from .contracts import DeliveryProfileName, LoudnessProfile


DELIVERY_PROFILES: dict[DeliveryProfileName, LoudnessProfile] = {
    DeliveryProfileName.WEB: LoudnessProfile(
        name=DeliveryProfileName.WEB,
        integrated_lufs=-16.0,
        maximum_true_peak_dbtp=-1.0,
        loudness_range_lu=11.0,
    ),
    DeliveryProfileName.BROADCAST: LoudnessProfile(
        name=DeliveryProfileName.BROADCAST,
        integrated_lufs=-23.0,
        maximum_true_peak_dbtp=-1.0,
        loudness_range_lu=7.0,
    ),
    DeliveryProfileName.PRESERVE_DYNAMICS: LoudnessProfile(
        name=DeliveryProfileName.PRESERVE_DYNAMICS,
        integrated_lufs=None,
        maximum_true_peak_dbtp=-1.0,
        loudness_range_lu=None,
    ),
}


def get_delivery_profile(name: DeliveryProfileName | str) -> LoudnessProfile:
    try:
        profile_name = DeliveryProfileName(name)
    except ValueError as exc:
        raise ValueError(f"unknown audio delivery profile: {name}") from exc
    return DELIVERY_PROFILES[profile_name]

