"""Managed, bounded video-source ingest for Phase 7."""

from __future__ import annotations

import tempfile
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.assets import AssetUploadResponse, PlanningMediaAssetRead
from backend.app.services import reference_assets as service


router = APIRouter(prefix="/video/phase-7", tags=["video-phase-7"])


def _asset_read(asset, *, duplicate: bool) -> PlanningMediaAssetRead:
    return PlanningMediaAssetRead.model_validate(
        service.to_public_dict(asset, is_duplicate=duplicate)
    )


@router.post(
    "/projects/{project_id}/sources/upload",
    response_model=AssetUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_video_source(
    project_id: UUID,
    request: Request,
    http_response: Response,
    original_filename: str = Query(min_length=1, max_length=240),
    source_type: str = Query(
        default="user_upload", min_length=1, max_length=48
    ),
    db: Session = Depends(get_db),
) -> AssetUploadResponse:
    """Preserve one uploaded video in managed storage and record ffprobe evidence."""

    max_bytes = int(service.KIND_POLICY["video_source"]["max_bytes"])
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise service.ReferenceAssetError(
                    f"Upload exceeds the {max_bytes}-byte video_source limit."
                )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header.",
            ) from error

    temporary = tempfile.SpooledTemporaryFile(
        max_size=1024 * 1024, mode="w+b"
    )
    try:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > max_bytes:
                raise service.ReferenceAssetError(
                    f"Upload exceeds the {max_bytes}-byte video_source limit."
                )
            temporary.write(chunk)
        temporary.seek(0)
        asset, created = service.upload_video_asset_from_fileobj(
            db,
            project_id=project_id,
            fileobj=temporary,
            original_filename=original_filename,
            content_type=request.headers.get("content-type"),
            source_type=source_type,
            max_read_bytes=max_bytes,
        )
    except service.ReferenceAssetNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except service.ReferenceAssetError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    finally:
        temporary.close()

    http_response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )
    return AssetUploadResponse(
        asset=_asset_read(asset, duplicate=not created),
        created=created,
        duplicate_of_existing=not created,
    )
