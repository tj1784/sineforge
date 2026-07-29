"""Read-only production-profile catalog routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.production_profiles import (
    ProductionProfileCatalogRead,
    ProductionProfileRead,
)
from backend.app.services.production_profiles import (
    DEFAULT_PRODUCTION_PROFILE_REF,
    ProductionProfileError,
    list_production_profiles,
    resolve_production_profile,
)


router = APIRouter(prefix="/production-profiles", tags=["production-profiles"])


@router.get("", response_model=ProductionProfileCatalogRead)
def get_production_profile_catalog() -> ProductionProfileCatalogRead:
    return ProductionProfileCatalogRead(
        default_profile_ref=DEFAULT_PRODUCTION_PROFILE_REF,
        profiles=[
            ProductionProfileRead.from_domain(profile)
            for profile in list_production_profiles(include_unqualified=True)
        ],
    )


@router.get("/{profile_ref}", response_model=ProductionProfileRead)
def get_production_profile(profile_ref: str) -> ProductionProfileRead:
    try:
        profile = resolve_production_profile(profile_ref)
    except ProductionProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return ProductionProfileRead.from_domain(profile)
