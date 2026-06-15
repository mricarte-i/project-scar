from pydantic import BaseModel, field_validator
from typing import Any, Literal
from datetime import datetime

from app.domain.assets import AssetType


def _require_aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("timestamp must include timezone offset (no naive datetimes)")
    return ts


class BlobPayload(BaseModel):
    kind: Literal["blob"] = "blob"
    url: str
    media_type: str  # tells the client how to interpret the blob, "application/json" vs "application/x-npy"
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
