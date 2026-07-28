"""Local Sulphur planning adapter through LM Studio's loopback API.

The model is administrator-owned configuration. Provider requests contain
planning text only and never accept executable paths, shell commands, model
downloads, or runtime mutation instructions.
"""

from __future__ import annotations

from backend.app.core.config import Settings, get_settings
from backend.app.services.planning.openai_provider import OpenAIPlanningProvider


class SulphurPlanningProvider(OpenAIPlanningProvider):
    """OpenAI-compatible adapter for the local Sulphur GGUF model."""

    identifier = "sulphur"

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
    ) -> "SulphurPlanningProvider":
        cfg = settings or get_settings()
        if not cfg.sulphur_configured:
            raise ValueError("Sulphur planning provider is not configured")
        return cls(
            api_key="lm-studio",
            base_url=cfg.sulphur_base_url,
            timeout_sec=cfg.sulphur_timeout_sec,
            wall_time_sec=cfg.sulphur_wall_time_sec,
            transport_retries=cfg.sulphur_transport_retries,
            max_response_bytes=cfg.sulphur_max_response_bytes,
            repair_instruction_limit=cfg.sulphur_repair_instruction_limit,
            model_luna=cfg.sulphur_model_id,
            model_terra=cfg.sulphur_model_id,
            model_sol=cfg.sulphur_model_id,
        )


def build_sulphur_provider_from_settings(
    settings: Settings | None = None,
) -> SulphurPlanningProvider | None:
    cfg = settings or get_settings()
    if not cfg.sulphur_configured:
        return None
    return SulphurPlanningProvider.from_settings(cfg)
