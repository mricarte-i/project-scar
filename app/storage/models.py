from datetime import datetime

from psycopg.types.range import Range
from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import TSTZRANGE, ExcludeConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AssetVersion(Base):
    __tablename__ = "asset_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    satellite_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)

    # [valid_from, valid_to): upper bound NULL/infinity = open-endeded
    validity: Mapped[Range] = mapped_column(TSTZRANGE, nullable=False)

    # payloads live in object storage, row holds a URI reference to the payload
    # we store the sha256 of the payload for integrity verification and to avoid duplicates in the blob store
    # and whenever we do a split with a continuation, it reuses the same object
    payload_uri: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)

    lineage_version_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        ExcludeConstraint(
            ("satellite_id", "="),
            ("asset_type", "="),
            ("validity", "&&"),
            name="no_overlapping_versions",
            using="gist",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_lookup", "satellite_id", "asset_type"),
    )
