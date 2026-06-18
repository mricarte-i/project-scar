from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator

from app.domain.assets import AssetType


def _require_aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("timestamp must include timezone offset (no naive datetimes)")
    return ts


class BlobPayload(BaseModel):
    kind: Literal["blob"] = "blob"
    url: str
    media_type: (
        str  # tells the client how to interpret the blob, "application/json" vs "application/x-npy"
    )
    expires_at: datetime | None = None


class VersionOut(BaseModel):
    satellite_id: str
    asset_type: AssetType
    version_id: int
    valid_from: datetime
    valid_to: datetime | None
    sha256: str
    payload: BlobPayload


class BulkOut(BaseModel):
    satellite_id: str
    at: datetime
    assets: dict[AssetType, VersionOut | None]


class JsonUploadIn(BaseModel):
    valid_from: datetime
    valid_to: datetime | None = None
    payload: dict[str, Any]
    allow_historical_overwrite: bool = False

    _v_from = field_validator("valid_from")(_require_aware)

    @field_validator("valid_to")
    @classmethod
    def _v_to(cls, v: datetime | None) -> datetime | None:
        return _require_aware(v) if v is not None else None


class SupersededOut(BaseModel):
    version_id: int
    new_valid_to: datetime | None


class UploadOut(BaseModel):
    created: dict[str, Any]
    superseded: list[SupersededOut] = []


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorOut(BaseModel):
    error: ErrorBody
