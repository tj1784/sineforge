from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging


LOCAL_LOOPBACK_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    local_private_cors = settings.env == "local" and settings.cors_allowed_origins == ["*"]
    app = FastAPI(
        title="CineForge Backend",
        version="0.1.0",
        description="Deterministic local AI video orchestration backend.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[] if local_private_cors else settings.cors_allowed_origins,
        allow_origin_regex=LOCAL_LOOPBACK_ORIGIN_REGEX if local_private_cors else None,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()

