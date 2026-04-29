"""
conftest.py — Test setup for APA backend

Your models use three PostgreSQL-only types that SQLite cannot render:
  - JSONB  (users, documents, shares)
  - INET   (audit_logs.ip_address)

We patch ALL of them to SQLite-compatible equivalents before
any app module is imported. This is the complete and final fix.
"""
import os
import sys
from pathlib import Path

# ── Env vars first — use = not setdefault so they override .env file ───────
TEST_DB_PATH = Path(__file__).resolve().parent / "test_app.db"
os.environ["DATABASE_URL"]              = f"sqlite:///{TEST_DB_PATH}"
os.environ["REDIS_URL"]                 = "redis://localhost:6379/15"
os.environ["FRONTEND_URL"]             = "http://localhost:3000"
os.environ["MINIO_ENDPOINT"]           = "localhost:9000"
os.environ["MINIO_ACCESS_KEY"]         = "minio"
os.environ["MINIO_SECRET_KEY"]         = "minio123"
os.environ["SECRET_KEY"]               = "test-secret-key-for-apa-tests-only-32chars"
os.environ["MALWARE_SCANNING_ENABLED"] = "false"
os.environ["OCR_ENABLED"]              = "false"
os.environ["ENABLE_METRICS"]           = "false"
os.environ["LLM_PROVIDER"]             = "mock"

# ── Patch ALL PostgreSQL-only types → SQLite-compatible equivalents ─────────
# Must happen before any app.models.* import.
from sqlalchemy import types as _sa_types
from sqlalchemy.dialects import postgresql as _pg

# JSONB → JSON  (users, documents, shares)
_pg.JSONB = _sa_types.JSON
sys.modules["sqlalchemy.dialects.postgresql"].JSONB = _sa_types.JSON

# INET → String  (audit_logs.ip_address — stores IP strings)
_pg.INET = _sa_types.String
sys.modules["sqlalchemy.dialects.postgresql"].INET = _sa_types.String

# ── Now safe to import app modules ──────────────────────────────────────────
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """Create all tables in SQLite before any test runs."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    from app.db.base_class import Base
    import app.db.base  # noqa — registers all models with Base.metadata

    test_engine = create_engine(
        f"sqlite:///{TEST_DB_PATH}",
        connect_args={"check_same_thread": False},
    )

    # Patch app session so every endpoint uses SQLite during tests
    import app.db.session as _session
    _session.engine = test_engine
    _session.SessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False
    )

    Base.metadata.create_all(bind=test_engine)
    yield
    try:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
    except PermissionError:
        pass