from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.services.comfy.engine import ComfyEngineManager


LOCAL_LOOPBACK_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"


def create_app(settings=None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Attach exactly one lifecycle owner for the bundled ComfyUI engine."""

        manager = ComfyEngineManager(settings)
        app.state.comfy_engine = manager
        manager.start_in_background()
        try:
            yield
        finally:
            await manager.shutdown()

    configure_logging(settings.log_level)
    local_private_cors = settings.env == "local" and settings.cors_allowed_origins == ["*"]
    app = FastAPI(
        title="CineForge Backend",
        version="0.1.0",
        description="Deterministic local AI video orchestration backend.",
        lifespan=lifespan,
    )
    app.state.settings = settings
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

