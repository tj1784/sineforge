"""API routes for managed Storyboard Phase 1 reference / planning media assets."""

from __future__ import annotations

import tempfile
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.assets import (
    AssetArchiveRequest,
    AssetDeleteRequest,
    AssetKind,
    AssetListResponse,
    AssetUploadResponse,
    CharacterReferenceLinkCreate,
    CharacterReferenceLinkRead,
    PlanningMediaAssetRead,
    StartingImageApprovalUpdate,
)
from backend.app.services import reference_assets as service


router = APIRouter(prefix="/assets", tags=["assets"])


def _http_for(error: Exception) -> HTTPException:
    if isinstance(error, service.ReferenceAssetNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, service.ReferenceAssetConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, service.ReferenceAssetError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error))


def _to_read(asset, *, is_duplicate: bool = False) -> PlanningMediaAssetRead:
    return PlanningMediaAssetRead.model_validate(
        service.to_public_dict(asset, is_duplicate=is_duplicate)
    )


@router.post(
    "/projects/{project_id}/upload",
    response_model=AssetUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_planning_asset(
    project_id: UUID,
    request: Request,
    http_response: Response,
    kind: AssetKind = Query(...),
    original_filename: str | None = Query(None, max_length=240),
    consent_confirmed: bool = Query(False),
    source_type: str = Query("user_upload", min_length=1, max_length=48),
    db: Session = Depends(get_db),
) -> AssetUploadResponse:
    """Bounded raw-body upload; returns IDs only and requires no multipart runtime."""
    if kind == AssetKind.video_source:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Use /video/phase-7/projects/{project_id}/sources/upload for "
                "bounded streaming video ingest."
            ),
        )
    max_bytes = int(service.KIND_POLICY[kind.value]["max_bytes"])
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise service.ReferenceAssetError(
                    f"Upload exceeds the {max_bytes}-byte limit for {kind.value}."
                )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header.",
            ) from error

    temporary = tempfile.SpooledTemporaryFile(max_size=min(max_bytes, 1024 * 1024), mode="w+b")
    try:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > max_bytes:
                raise service.ReferenceAssetError(
                    f"Upload exceeds the {max_bytes}-byte limit for {kind.value}."
                )
            temporary.write(chunk)
        temporary.seek(0)
        asset, created = service.upload_asset_from_fileobj(
            db,
            project_id=project_id,
            kind=kind.value,
            fileobj=temporary,
            original_filename=original_filename,
            content_type=request.headers.get("content-type"),
            source_type=source_type,
            consent_confirmed=consent_confirmed if kind == AssetKind.voice_source else None,
        )
    except (service.ReferenceAssetError, service.ReferenceAssetNotFoundError) as error:
        raise _http_for(error) from error
    finally:
        temporary.close()

    # Duplicate reuse is still a successful response; created=false signals no clone.
    http_response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response_payload = AssetUploadResponse(
        asset=_to_read(asset, is_duplicate=not created),
        created=created,
        duplicate_of_existing=not created,
    )
    return response_payload


@router.get(
    "/projects/{project_id}",
    response_model=AssetListResponse,
)
def list_planning_assets(
    project_id: UUID,
    kind: AssetKind | None = None,
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
) -> AssetListResponse:
    try:
        rows = service.list_assets(
            db,
            project_id,
            kind=kind.value if kind else None,
            include_archived=include_archived,
        )
    except (service.ReferenceAssetError, service.ReferenceAssetNotFoundError) as error:
        raise _http_for(error) from error
    items = [_to_read(row) for row in rows]
    return AssetListResponse(items=items, total=len(items))


@router.get(
    "/{asset_id}",
    response_model=PlanningMediaAssetRead,
)
def get_planning_asset(
    asset_id: UUID,
    include_archived: bool = Query(True),
    db: Session = Depends(get_db),
) -> PlanningMediaAssetRead:
    try:
        asset = service.get_asset(db, asset_id, include_archived=include_archived)
    except service.ReferenceAssetNotFoundError as error:
        raise _http_for(error) from error
    return _to_read(asset)


@router.patch(
    "/{asset_id}/starting-image-approval",
    response_model=PlanningMediaAssetRead,
)
def update_starting_image_approval(
    asset_id: UUID,
    payload: StartingImageApprovalUpdate,
    db: Session = Depends(get_db),
) -> PlanningMediaAssetRead:
    """Explicitly persist review state for one active managed starting image."""
    try:
        asset = service.transition_starting_image_approval(
            db,
            asset_id,
            approval_state=payload.approval_state.value,
            expected_approval_state=payload.expected_approval_state.value,
            reason=payload.reason,
            changed_by=payload.changed_by,
        )
    except (
        service.ReferenceAssetError,
        service.ReferenceAssetNotFoundError,
        service.ReferenceAssetConflictError,
    ) as error:
        raise _http_for(error) from error
    return _to_read(asset)


@router.get("/{asset_id}/content")
def stream_planning_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Controlled stream by asset ID. Clients never supply filesystem paths."""
    try:
        asset, path = service.open_asset_for_stream(db, asset_id)
    except (service.ReferenceAssetError, service.ReferenceAssetNotFoundError) as error:
        raise _http_for(error) from error

    filename = asset.original_filename or path.name
    return FileResponse(
        path=path,
        media_type=asset.mime_type or "application/octet-stream",
        filename=filename,
        content_disposition_type="inline",
    )


@router.post(
    "/{asset_id}/archive",
    response_model=PlanningMediaAssetRead,
)
def archive_planning_asset(
    asset_id: UUID,
    payload: AssetArchiveRequest | None = None,
    db: Session = Depends(get_db),
) -> PlanningMediaAssetRead:
    try:
        asset = service.archive_asset(
            db,
            asset_id,
            reason=(payload.reason if payload else None),
        )
    except (service.ReferenceAssetError, service.ReferenceAssetNotFoundError) as error:
        raise _http_for(error) from error
    return _to_read(asset)


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_planning_asset(
    asset_id: UUID,
    force: bool = Query(False),
    reason: str | None = Query(None),
    db: Session = Depends(get_db),
) -> None:
    try:
        service.delete_asset(db, asset_id, reason=reason, force=force)
    except (service.ReferenceAssetError, service.ReferenceAssetNotFoundError) as error:
        raise _http_for(error) from error


@router.post(
    "/characters/{character_id}/references",
    response_model=CharacterReferenceLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def link_character_reference(
    character_id: UUID,
    payload: CharacterReferenceLinkCreate,
    db: Session = Depends(get_db),
) -> CharacterReferenceLinkRead:
    try:
        link = service.link_character_reference(
            db,
            character_id=character_id,
            asset_id=payload.asset_id,
            reference_role=payload.reference_role.value,
            approved=payload.approved,
            order_index=payload.order_index,
        )
        asset = service.get_asset(db, link.asset_id)
    except (
        service.ReferenceAssetError,
        service.ReferenceAssetNotFoundError,
        service.ReferenceAssetConflictError,
    ) as error:
        raise _http_for(error) from error
    return CharacterReferenceLinkRead(
        id=link.id,
        character_id=link.character_id,
        asset_id=link.asset_id,
        reference_role=link.reference_role,
        approved=link.approved,
        order_index=link.order_index,
        created_at=link.created_at,
        updated_at=link.updated_at,
        asset=_to_read(asset),
    )


@router.get(
    "/characters/{character_id}/references",
    response_model=list[CharacterReferenceLinkRead],
)
def list_character_references(
    character_id: UUID,
    db: Session = Depends(get_db),
) -> list[CharacterReferenceLinkRead]:
    try:
        links = service.list_character_references(db, character_id)
    except service.ReferenceAssetNotFoundError as error:
        raise _http_for(error) from error
    results: list[CharacterReferenceLinkRead] = []
    for link in links:
        try:
            asset = service.get_asset(db, link.asset_id, include_archived=True)
            asset_read = _to_read(asset)
        except service.ReferenceAssetNotFoundError:
            asset_read = None
        results.append(
            CharacterReferenceLinkRead(
                id=link.id,
                character_id=link.character_id,
                asset_id=link.asset_id,
                reference_role=link.reference_role,
                approved=link.approved,
                order_index=link.order_index,
                created_at=link.created_at,
                updated_at=link.updated_at,
                asset=asset_read,
            )
        )
    return results


@router.delete(
    "/character-references/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unlink_character_reference(
    link_id: UUID,
    db: Session = Depends(get_db),
) -> None:
    try:
        service.unlink_character_reference(db, link_id)
    except service.ReferenceAssetNotFoundError as error:
        raise _http_for(error) from error


# Silence unused import warning for AssetDeleteRequest (reserved for body-form deletes).
_ = AssetDeleteRequest
