from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


from psycopg.types.range import Range
from sqlalchemy import select, text
from sqlalchemy.orm import Session


from app.logic.assets import AssetType
from app.logic.versioning import ExistingVersion, SupersedePlan
from app.logic.window import Window
from app.storage.models import AssetVersion


@dataclass(frozen=True)
class ResolvedVersion:
    id: int
    satellite_id: str
    asset_type: AssetType
    window: Window
    sha256: str
    payload_uri: str
    media_type: str


def window_to_range(w: Window) -> Range:
    return Range(w.valid_from, w.valid_to, bounds="[)")


def range_to_window(r: Range) -> Window:
    return Window(r.lower, r.upper)


class AssetRepository(Protocol):
    def resolve_at(
        self, satellite_id: str, asset_type: AssetType, at: datetime
    ) -> ResolvedVersion | None: ...
    def resolve_all_at(
        self, satellite_id: str, at: datetime
    ) -> dict[AssetType, ResolvedVersion | None]: ...
    def timeline(
        self, satellite_id: str, asset_type: AssetType
    ) -> list[ResolvedVersion]: ...
    def apply_plan(
        self,
        plan: SupersedePlan,
        *,
        satellite_id: str,
        asset_type: AssetType,
        new_payload_uri: str,
        media_type: str,
        sha256: str,
        created_by: str,
    ) -> int: ...


class SqlAssetRepository(AssetRepository):
    def __init__(self, session: Session):
        self._s = session

    def resolve_at(self, satellite_id, asset_type, at):
        stmt = (
            select(AssetVersion)
            .where(
                AssetVersion.satellite_id == satellite_id,
                AssetVersion.asset_type == asset_type.value,
                text("validity @> :at"),
            )
            .params(at=at)
        )
        row = self._s.execute(stmt).scalar_one_or_none()
        return self._to_resolved(row) if row else None

    def resolve_all_at(self, satellite_id, at):
        out: dict[AssetType, ResolvedVersion | None] = {t: None for t in AssetType}
        stmt = (
            select(AssetVersion)
            .where(
                AssetVersion.satellite_id == satellite_id,
                text("validity @> :at"),
            )
            .params(at=at)
        )
        for row in self._s.execute(stmt).scalars():
            out[AssetType(row.asset_type)] = self._to_resolved(row)
        return out

    def timeline(self, satellite_id, asset_type):
        stmt = (
            select(AssetVersion)
            .where(
                AssetVersion.satellite_id == satellite_id,
                AssetVersion.asset_type == asset_type.value,
            )
            .order_by(text("lower(validity)"))
        )
        return [
            ExistingVersion(
                id=row.id,
                window=range_to_window(row.validity),
                payload_ref=row.id,
                # storage clones by re-reading the row on split
            )
            for row in self._s.execute(stmt).scalars()
        ]

    def apply_plan(
        self,
        plan,
        *,
        satellite_id,
        asset_type,
        new_payload_uri,
        media_type,
        sha256,
        created_by,
    ):
        new_id: int | None = None
        with self._s.begin():  # one TRANSACTION to rule them all
            for deletion in plan.deletions:
                obj = self._s.get(AssetVersion, deletion.version_id)
                if obj:
                    self._s.delete(obj)

            for trunc in plan.truncations:
                obj = self._s.get(AssetVersion, trunc.version_id)
                obj.validity = window_to_range(trunc.new_window)

            for insert in plan.inserts:
                if insert.lineage_version_id is None:
                    row = AssetVersion(
                        satellite_id=satellite_id,
                        asset_type=asset_type.value,
                        validity=window_to_range(insert.window),
                        payload_uri=new_payload_uri,
                        media_type=media_type,
                        sha256=sha256,
                        created_by=created_by,
                    )
                else:
                    # lineage_version_id is set when this row is a continuation of an existing version
                    row = AssetVersion(
                        satellite_id=satellite_id,
                        asset_type=asset_type.value,
                        validity=window_to_range(insert.window),
                        payload_uri=new_payload_uri,
                        media_type=media_type,
                        sha256=sha256,
                        lineage_version_id=insert.lineage_version_id,
                        created_by=created_by,
                    )
                self._s.add(row)
                self._s.flush()  # to get the id populated
                if insert.lineage_version_id is None:
                    new_id = row.id
        return new_id

    @staticmethod
    def _to_resolved(row: AssetVersion) -> ResolvedVersion:
        return ResolvedVersion(
            id=row.id,
            satellite_id=row.satellite_id,
            asset_type=AssetType(row.asset_type),
            window=range_to_window(row.validity),
            sha256=row.sha256,
            payload_uri=row.payload_uri,
            media_type=row.media_type,
        )
