from fastapi import APIRouter

from backend.app.schemas.themes import ThemeCatalogRead
from backend.app.services.themes import theme_catalog


router = APIRouter(prefix="/themes", tags=["themes"])


@router.get("", response_model=ThemeCatalogRead)
def list_themes() -> ThemeCatalogRead:
    return theme_catalog()
