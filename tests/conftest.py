from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import BinaryIO

# Add the project root to Python path so tests can import app
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.deps import get_asset_repository, get_blob_store, get_settings
from app.main import create_app
from app.storage.repository import SqlAssetRepository

ADMIN_KEY = "test-key"
ADMIN_OPERATOR = "test-operator"

INIT_SQL = Path(__file__).resolve().parents[1] / "init.sql"
DB_URL = os.environ.get("SCAR_DATABASE_URL")


class FakeBlobStore:
    """
    Mock a blob store in memory, no need for MinIO/boto3 in tests

    Record every put so tests can assert what was written, returns a
    deterministic fake presigned URL
    """

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: BinaryIO, content_length: int, content_type: str) -> None:
        self.objects[key] = data.read()

    def presign_get(self, key: str) -> str:
        return f"https://blobstore.test/{key}"


"""
DB Fixtures
"""


def _ensure_schema(engine) -> None:
    with engine.begin() as conn:
        if conn.execute(text("SELECT to_regclass('public.asset_versions')")).scalar():
            return
        no_comments = "\n".join(
            line.split("--", 1)[0] for line in INIT_SQL.read_text().splitlines()
        )
        """
        psycopg can't run a multi-statement script in one execute call,
        so we split on `;`
        also strip line comments starting with `--` 
        """
        for statement in (s.strip() for s in no_comments.split(";")):
            if statement:
                conn.exec_driver_sql(statement)


@pytest.fixture
def db_engine():
    if not DB_URL:
        pytest.skip("SCAR_DATABASE_URL not set, skipping DB tests")
    engine = create_engine(DB_URL, future=True)
    _ensure_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """
    fresh session per test

    truncation runs in its own committed transaction, so the yielded session
    starts with on open transactiopn (the repository's `apply_plan`
    opens iws own with `session.begin()`)
    """

    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE asset_versions RESTART IDENTITY"))
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def repo(db_session):
    return SqlAssetRepository(db_session)


"""
API Fixtures
"""


@pytest.fixture
def fake_blobstore() -> FakeBlobStore:
    return FakeBlobStore()


@pytest.fixture
def client(db_session, fake_blobstore):
    app = create_app()
    test_settings = Settings(
        database_url=DB_URL,
        admin_api_keys=f"{ADMIN_KEY}:{ADMIN_OPERATOR}",
    )

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_blob_store] = lambda: fake_blobstore
    # overriding to reuse `db_session` means the HTTP layer reads and writes
    # the same transaction-isolated  table the test set up
    app.dependency_overrides[get_asset_repository] = lambda: SqlAssetRepository(db_session)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
