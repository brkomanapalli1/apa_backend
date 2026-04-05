import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent / "test_app.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio123")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("MALWARE_SCANNING_ENABLED", "false")
os.environ.setdefault("OCR_ENABLED", "false")
os.environ.setdefault("ENABLE_METRICS", "false")
