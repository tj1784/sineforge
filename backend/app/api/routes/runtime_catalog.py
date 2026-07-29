"""Read-only factual runtime model/workflow catalog API.

Database-backed catalog endpoints never infer installation state. The explicit
``local-model-inventory`` endpoint is a separate read-only filename probe
against the configured ComfyUI instance so operators can see what ComfyUI
currently exposes without changing the evidence registry.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.runtime_catalog import (
    LocalModelInventoryResponse,
    LoraCatalogItem,
    ModelCatalogItem,
    ModelVariantCatalogItem,
    QuantizationCatalogItem,
    RuntimeCatalogResponse,
    RuntimeCatalogSummary,
    WorkflowCandidateRegistryResponse,
    WorkflowTemplateCatalogItem,
)
from backend.app.core.config import get_settings
from backend.app.services import runtime_catalog as service
from backend.app.services.comfy.client import ComfyUIClient
from backend.app.services.workflows import candidate_catalog as workflow_candidates


router = APIRouter(prefix="/runtime-catalog", tags=["runtime-catalog"])

LOCAL_MODEL_FOLDERS = (
    "checkpoints",
    "diffusion_models",
    "loras",
    "vae",
    "text_encoders",
    "latent_upscale_models",
    "frame_interpolation",
    "upscale_models",
    "controlnet",
    "embeddings",
    "sams",
    "ultralytics",
)


@router.get("", response_model=RuntimeCatalogResponse)
def get_full_catalog(db: Session = Depends(get_db)) -> RuntimeCatalogResponse:
    payload = service.full_catalog(db)
    return RuntimeCatalogResponse(
        summary=RuntimeCatalogSummary.model_validate(payload["summary"]),
        models=[ModelCatalogItem.model_validate(item) for item in payload["models"]],
        model_variants=[
            ModelVariantCatalogItem.model_validate(item) for item in payload["model_variants"]
        ],
        workflow_templates=[
            WorkflowTemplateCatalogItem.model_validate(item)
            for item in payload["workflow_templates"]
        ],
        quantizations=[
            QuantizationCatalogItem.model_validate(item) for item in payload["quantizations"]
        ],
        loras=[LoraCatalogItem.model_validate(item) for item in payload["loras"]],
    )


@router.get("/summary", response_model=RuntimeCatalogSummary)
def get_catalog_summary(db: Session = Depends(get_db)) -> RuntimeCatalogSummary:
    return RuntimeCatalogSummary.model_validate(service.catalog_summary(db))


@router.get("/models", response_model=list[ModelCatalogItem])
def list_models(db: Session = Depends(get_db)) -> list[ModelCatalogItem]:
    return [ModelCatalogItem.model_validate(item) for item in service.list_models(db)]


@router.get("/local-model-inventory", response_model=LocalModelInventoryResponse)
async def get_local_model_inventory() -> LocalModelInventoryResponse:
    """Return the active ComfyUI model lists without mutating either system."""

    base_url = str(get_settings().comfyui_base_url).rstrip("/")
    categories: dict[str, list[str]] = {}
    errors: dict[str, str] = {}
    async with ComfyUIClient(base_url, timeout=10.0) as client:
        for folder in LOCAL_MODEL_FOLDERS:
            try:
                categories[folder] = await client.get_model_names(folder)
            except Exception as exc:  # each folder remains independently useful
                categories[folder] = []
                errors[folder] = str(exc)

    available_categories = sum(1 for folder in LOCAL_MODEL_FOLDERS if folder not in errors)
    if available_categories == len(LOCAL_MODEL_FOLDERS):
        inventory_status = "available"
    elif available_categories:
        inventory_status = "partial"
    else:
        inventory_status = "unavailable"
    return LocalModelInventoryResponse(
        status=inventory_status,
        source_url=base_url,
        total_count=sum(len(items) for items in categories.values()),
        categories=categories,
        errors=errors,
    )


@router.get("/model-variants", response_model=list[ModelVariantCatalogItem])
def list_model_variants(
    model_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[ModelVariantCatalogItem]:
    return [
        ModelVariantCatalogItem.model_validate(item)
        for item in service.list_model_variants(db, model_id=model_id)
    ]


@router.get("/model-variants/{variant_id}", response_model=ModelVariantCatalogItem)
def get_model_variant(
    variant_id: UUID,
    db: Session = Depends(get_db),
) -> ModelVariantCatalogItem:
    item = service.get_model_variant(db, variant_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model variant not found.")
    return ModelVariantCatalogItem.model_validate(item)


@router.get("/workflow-templates", response_model=list[WorkflowTemplateCatalogItem])
def list_workflow_templates(
    db: Session = Depends(get_db),
) -> list[WorkflowTemplateCatalogItem]:
    return [
        WorkflowTemplateCatalogItem.model_validate(item)
        for item in service.list_workflow_templates(db)
    ]


@router.get(
    "/workflow-candidates",
    response_model=WorkflowCandidateRegistryResponse,
)
def get_workflow_candidate_registry() -> WorkflowCandidateRegistryResponse:
    """Return the non-executing archetype/candidate/preset planning registry."""

    return WorkflowCandidateRegistryResponse.model_validate(
        workflow_candidates.catalog_document()
    )


@router.get(
    "/workflow-templates/{template_id}",
    response_model=WorkflowTemplateCatalogItem,
)
def get_workflow_template(
    template_id: UUID,
    db: Session = Depends(get_db),
) -> WorkflowTemplateCatalogItem:
    item = service.get_workflow_template(db, template_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow template not found."
        )
    return WorkflowTemplateCatalogItem.model_validate(item)


@router.get("/quantizations", response_model=list[QuantizationCatalogItem])
def list_quantizations(db: Session = Depends(get_db)) -> list[QuantizationCatalogItem]:
    return [
        QuantizationCatalogItem.model_validate(item) for item in service.list_quantizations(db)
    ]


@router.get("/loras", response_model=list[LoraCatalogItem])
def list_loras(db: Session = Depends(get_db)) -> list[LoraCatalogItem]:
    return [LoraCatalogItem.model_validate(item) for item in service.list_loras(db)]
