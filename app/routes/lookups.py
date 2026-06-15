from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.deps import get_asset_repository, get_blob_store
from app.logic.assets import AssetType
from app.schemas import BlobPayload, VersionOut
from app.storage.blobstore import BlobStore
from app.storage.repository import AssetRepository

router = APIRouter(prefix="/v1/satellites", tags=["lookups"])


@router.get(
    "/{satellite_id}/assets/{asset_type}/",
    response_model=VersionOut,
)
def point_in_time(
    satellite_id: str,
    asset_type: AssetType,
    at: datetime | None = Query(default=None),
    repo: AssetRepository = Depends(get_asset_repository),
    blobs: BlobStore = Depends(get_blob_store),
):
    at = at or datetime.now(timezone.utc)
    resolved_version = repo.resolve_at(satellite_id, asset_type, at)
    if resolved_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "no_asset_valid_at_time",
                "message": f"No version of {asset_type} for satellite {satellite_id} is valid at {at.isoformat()}",
                "details": {
                    "satellite_id": satellite_id,
                    "asset_type": asset_type,
                    "at": at.isoformat(),
                },
            },
        )
    return VersionOut(
        satellite_id=satellite_id,
        asset_type=asset_type,
        version_id=resolved_version.version_id,
        valid_from=resolved_version.window.start,
        valid_to=resolved_version.window.end,
        sha256=resolved_version.sha256,
        payload=BlobPayload(
            url=blobs.presign_get(resolved_version.payload_uri),
            media_type=resolved_version.media_type,
        ),
    )
