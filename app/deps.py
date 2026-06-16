from functools import lru_cache
from typing import Iterator
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.storage.blobstore import BlobStore, S3BlobStore
from app.storage.repository import AssetRepository, SqlAssetRepository


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def _engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True, future=True)


@lru_cache
def _session_factory() -> sessionmaker:
    return sessionmaker(bind=_engine(), expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_asset_repository(session: Session = Depends(get_session)) -> AssetRepository:
    return SqlAssetRepository(session)


@lru_cache
def get_blob_store(settings: Settings = Depends(get_settings)) -> BlobStore:
    return S3BlobStore(settings.blob_store_url)


def require_admin(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    operator = settings.admin_api_keys.get(x_api_key or "")
    if operator is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return operator
