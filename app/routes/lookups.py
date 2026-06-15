from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.deps import get_asset_repository, get_blob_store
from app.logic.assets import AssetType
from app.schemas import BlobPayload, BulkOut, VersionOut
from app.storage.blobstore import BlobStore
from app.storage.repository import AssetRepository, ResolvedVersion

router = APIRouter(prefix="/v1/satellites", tags=["lookups"])


def _to_version_out(rv: ResolvedVersion, blobs: BlobStore) -> VersionOut:
    return VersionOut(
        satellite_id=rv.satellite_id,
        asset_type=rv.asset_type,
        version_id=rv.version_id,
        valid_from=rv.window.start,
        valid_to=rv.window.end,
        sha256=rv.sha256,
        payload=BlobPayload(
            url=blobs.presign_get(rv.payload_uri),
            media_type=rv.media_type,
        ),
    )


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
    return _to_version_out(resolved_version, blobs)


@router.get(
    "/{satellite_id}/assets/",
    response_model=BulkOut,
)
def bulk(
    satellite_id: str,
    at: datetime | None = Query(default=None),
    repo: AssetRepository = Depends(get_asset_repository),
    blobs: BlobStore = Depends(get_blob_store),
):
    at = at or datetime.now(timezone.utc)
    resolved_assets = repo.resolve_all_at(satellite_id, at)
    assets: dict[AssetType, VersionOut | None] = {}
    for t, rv in resolved_assets.items():
        if rv is not None:
            assets[t] = _to_version_out(rv, blobs)
        else:
            assets[t] = None
    return BulkOut(satellite_id=satellite_id, at=at, assets=assets)
