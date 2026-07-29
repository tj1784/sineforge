from fastapi import APIRouter

from backend.app.api.routes import (
    api_caller,
    audio,
    assets,
    campaigns,
    health,
    jobs,
    lm_studio,
    orchestration_runs,
    projects,
    production,
    production_profiles,
    proposal_review,
    providers,
    runtime_catalog,
    storyboard,
    storyboard_crud,
    storyboard_settings,
    video,
    video_ingest,
    voices,
)


api_router = APIRouter()
api_router.include_router(api_caller.router)
api_router.include_router(lm_studio.router)
api_router.include_router(health.router)
api_router.include_router(audio.router)
api_router.include_router(storyboard_settings.router)
api_router.include_router(projects.router)
api_router.include_router(production.router)
api_router.include_router(production_profiles.router)
api_router.include_router(campaigns.router)
api_router.include_router(jobs.router)
api_router.include_router(runtime_catalog.router)
api_router.include_router(providers.router)
api_router.include_router(assets.router)
api_router.include_router(voices.router)
api_router.include_router(orchestration_runs.router)
api_router.include_router(proposal_review.router)
api_router.include_router(storyboard_crud.router)
api_router.include_router(storyboard.router)
api_router.include_router(video.router)
api_router.include_router(video_ingest.router)
