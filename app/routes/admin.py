import hashlib
import io
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import AwareDatetime

from app.deps import get_asset_repository, get_blob_store, require_admin
from app.domain.assets import AssetType, is_frame, media_type_for
from app.domain.versioning import plan_retire, plan_supersede
from app.domain.window import Window
from app.schemas import RetireIn, RetireOut, SupersededOut, UploadOut
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
    file: UploadFile = File(...),
    valid_from: AwareDatetime = Form(...),
    valid_to: AwareDatetime | None = Form(default=None),
    allow_historical_overwrite: bool = Form(default=False),
    operator: str = Depends(require_admin),
    repo: AssetRepository = Depends(get_asset_repository),
    blobs: BlobStore = Depends(get_blob_store),
):
    """
    A multipart upload carrying payload as a file, plus the validity window
    as form fields. Frames (.npy) are stored as opaque bytes; JSON assets are
    parsed, re-serialized with sorted keys and no whitespace, so
    logically equivalent JSON should yield the same hash.
    """
    raw = await file.read()
    if is_frame(asset_type):
        body = raw
        ext = ".npy"
    else:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "JSON asset payload must be a valid JSON",
            ) from e
        if not isinstance(payload, dict):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "JSON asset payload must be a JSON object",
            )
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ext = ".json"

    window = Window(valid_from, valid_to)
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


@router.post(
    "/{satellite_id}/assets/{asset_type}/versions/retire",
    response_model=RetireOut,
)
def retire_version(
    satellite_id: str,
    asset_type: AssetType,
    body: RetireIn,
    operator: str = Depends(require_admin),
    repo: AssetRepository = Depends(get_asset_repository),
):
    # close the currently-open version at `effective`, by truncating it to end at `effective`
    timeline = repo.timeline(satellite_id, asset_type)
    plan = plan_retire(body.effective_from, timeline)
    repo.apply_plan(
        plan,
        satellite_id=satellite_id,
        asset_type=asset_type,
        new_payload_uri=None,
        created_by=operator,
    )
    t = plan.truncations[0]
    return RetireOut(retired=SupersededOut(version_id=t.version_id, new_valid_to=t.new_window.end))
