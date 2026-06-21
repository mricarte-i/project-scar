import hashlib
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.deps import get_asset_repository, get_blob_store, require_admin
from app.domain.assets import AssetType, is_frame, media_type_for
from app.domain.versioning import plan_retire, plan_supersede
from app.domain.window import Window
from app.schemas import FrameUploadIn, JsonUploadIn, RetireIn, RetireOut, SupersededOut, UploadOut
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
    request: Request,
    operator: str = Depends(require_admin),
    repo: AssetRepository = Depends(get_asset_repository),
    blobs: BlobStore = Depends(get_blob_store),
):
    """
    Two transports share this route, keyed on asset_type: frames arrive as
    multipart file uploads (the .npy file streams in), JSON assets as an application/json
    body.
    FastAPI can't declare both Form and a JSON body on one route, so we
    read the raw request and parse it ourselves, if anything goes wrong we raise a RequestValidationError
    as a 422 error, just like a declared body would.
    """

    if is_frame(asset_type):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="frame upload requires a file ",
            )
        try:
            metadata = FrameUploadIn.model_validate(
                {
                    "valid_from": form.get("valid_from"),
                    "valid_to": form.get("valid_to"),
                    "allow_historical_overwrite": form.get("allow_historical_overwrite", False),
                }
            )
        except ValidationError as e:
            raise RequestValidationError(errors=e.errors()) from e
        body = await upload.read()
        ext = ".npy"
        window = Window(metadata.valid_from, metadata.valid_to)
        allow_historical_overwrite = metadata.allow_historical_overwrite
    else:
        try:
            json_body = JsonUploadIn.model_validate_json(await request.body())
        except ValidationError as e:
            raise RequestValidationError(errors=e.errors()) from e
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
