"""Local LM Studio model catalog and explicit model activation routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.schemas.lm_studio import (
    LMStudioModelActivateRequest,
    LMStudioModelActivateResponse,
    LMStudioModelCatalogResponse,
)
from backend.app.services.lm_studio_models import (
    LMStudioModelNotFoundError,
    LMStudioModelService,
    LMStudioUnavailableError,
)


router = APIRouter(prefix="/runtime/lm-studio", tags=["runtime"])


def get_lm_studio_model_service() -> LMStudioModelService:
    return LMStudioModelService()


@router.get("/models", response_model=LMStudioModelCatalogResponse)
async def list_lm_studio_models(
    service: LMStudioModelService = Depends(get_lm_studio_model_service),
) -> LMStudioModelCatalogResponse:
    return await service.catalog()


@router.put("/models/active", response_model=LMStudioModelActivateResponse)
async def activate_lm_studio_model(
    payload: LMStudioModelActivateRequest,
    service: LMStudioModelService = Depends(get_lm_studio_model_service),
) -> LMStudioModelActivateResponse:
    try:
        return await service.activate(payload.model_id)
    except LMStudioModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except LMStudioUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LM Studio could not activate that model: {exc}",
        ) from exc
