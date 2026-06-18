import hashlib
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.deps import get_asset_repository, get_blob_store, require_admin
from app.domain.assets import AssetType, is_frame, media_type_for
from app.domain.versioning import plan_supersede
from app.domain.window import Window
from app.schemas import JsonUploadIn, SupersededOut, UploadOut
from app.storage.blobstore import BlobStore
from app.storage.repository import AssetRepository

router = APIRouter(prefix="/admin/v1/satellites", tags=["admin"])


def _upload_response(plan, new_id: int, asset_type: AssetType, window: Window) -> UploadOut:
    superseded = [
        SupersededOut(version_id=t.version_id, new_valid_to=t.new_window.end)
        for t in plan.truncations
    ]
    return UploadOut(
        created={
            "version_id": new_id,
            "asset_type": asset_type.value,
            "valid_from": window.start,
            "valid_to": window.end,
        },
        superseded=superseded,
    )


@router.post(
    "/{satellite_id}/assets/{asset_type}/versions",
    response_model=UploadOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_version(
    satellite_id: str,
    asset_type: AssetType,
    valid_from: datetime | None = Form(default=None),
    valid_to: datetime | None = Form(default=None),
    allow_historical_overwrite: bool = Form(default=False),
    file: UploadFile | None = File(default=None),
    json_body: JsonUploadIn | None = None,
    operator: str = Depends(require_admin),
    repo: AssetRepository = Depends(get_asset_repository),
    blobs: BlobStore = Depends(get_blob_store),
):
    # TODO: file extensions assume we only work with json and npy, just keep in mind
    if is_frame(asset_type):
        if file is None or valid_from is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="file and valid_from are required for frame assets",
            )
        body = await file.read()
        ext = ".npy"
        window = Window(valid_from, valid_to)
    else:
        if json_body is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="JSON asset requires an application/json body",
            )
        body = json.dumps(json_body.payload, sort_keys=True, separators=(",", ":")).encode()
        ext = ".json"
        window = Window(json_body.valid_from, json_body.valid_to)
        allow_historical_overwrite = json_body.allow_historical_overwrite

    sha256 = hashlib.sha256(body).hexdigest()
    media_type = media_type_for(asset_type)
    key = f"{satellite_id}/{asset_type.value}/{sha256}{ext}"
    blobs.put(key, io.BytesIO(body), len(body), media_type)
    timeline = repo.timeline(satellite_id, asset_type)
    plan = plan_supersede(
        window,
        new_payload_ref=None,
        timeline=timeline,
        allow_historical_overwrite=allow_historical_overwrite,
    )
    new_id = repo.apply_plan(
        plan,
        satellite_id=satellite_id,
        asset_type=asset_type,
        new_payload_uri=key,
        media_type=media_type,
        sha256=sha256,
        created_by=operator,
    )
    # an upload always inserts a new version (not a continuation), so apply_plan
    # should always return a new_id; None would mean a truncation-only plan (continuation)
    assert new_id is not None
    return _upload_response(plan, new_id, asset_type, window)
