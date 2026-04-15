from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.hipaa_compliance import run_hipaa_self_check
from app.db.base_class import Base
from app.db.session import engine
from app.services.observability import RequestLoggingMiddleware, configure_logging, metrics_response

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger("app.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.ENVIRONMENT)

    # Create DB tables (Alembic handles migrations in production)
    Base.metadata.create_all(bind=engine)

    # [HIPAA] Run compliance self-check at startup
    findings = run_hipaa_self_check()
    for f in findings:
        level = {"PASS": logging.INFO, "WARN": logging.WARNING,
                 "FAIL": logging.ERROR, "INFO": logging.INFO}.get(f["status"], logging.INFO)
        logger.log(level, "[HIPAA %s] %s — %s", f["status"], f["requirement"], f["detail"])

    # Fail fast if critical HIPAA checks fail in production
    if settings.is_production:
        failures = [f for f in findings if f["status"] == "FAIL"]
        if failures:
            logger.critical(
                "HIPAA compliance failures detected in production startup — refusing to start. "
                "Fix the following: %s",
                [f["requirement"] for f in failures]
            )
            raise RuntimeError("HIPAA compliance failures — see logs")

    logger.info("Startup complete. %d HIPAA checks passed.", sum(1 for f in findings if f["status"] == "PASS"))
    yield

    # ── Shutdown ───────────────────────────────────────────────────────
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "AI-powered paperwork assistant for seniors and families. "
        "Analyzes Medicare, Medicaid, medical bills, insurance EOBs, "
        "utility bills (electricity, gas, water, telecom), property taxes, "
        "rent, HOA, financial documents, and more."
    ),
    # [HIPAA] Disable API docs in production — docs expose schema details
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

# ── Middleware (outermost = first to process request) ─────────────────────

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)


@app.middleware("http")
async def request_pipeline(request: Request, call_next) -> Response:
    """
    Single middleware for:
      - Unique request ID injection
      - Response time measurement
      - [HIPAA] Security headers on every response
      - [HIPAA] HTTPS enforcement in production
    """
    # Unique request ID for tracing across services
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]

    # [HIPAA §164.312(e)] Refuse plaintext in production
    if settings.is_production and request.url.scheme != "https":
        return JSONResponse(
            status_code=400,
            content={"detail": "HTTPS required. This system handles protected health information."},
        )

    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    # [HIPAA] Security response headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration_ms}ms"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"  # [HIPAA] No PHI caching
    response.headers["Pragma"] = "no-cache"

    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    [HIPAA] Stack traces must never reach the client — they may reveal
    PHI field names, database schema, or system paths.
    """
    error_id = str(uuid.uuid4())[:8]
    logger.error("Unhandled exception [%s] %s %s: %s",
                 error_id, request.method, request.url.path, str(exc), exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred.",
            "error_id": error_id,
            "support": "Include this error_id when contacting support.",
        },
    )


# ── Routers ───────────────────────────────────────────────────────────────

app.include_router(api_router, prefix=settings.API_V1_STR)


# ── Operational endpoints ─────────────────────────────────────────────────

@app.get("/health", tags=["ops"], include_in_schema=False)
def health():
    """Liveness probe — always returns 200 if the process is alive."""
    return {"status": "ok", "service": settings.APP_NAME, "version": "1.0.0"}


@app.get("/ready", tags=["ops"], include_in_schema=False)
def ready():
    """Readiness probe — checks DB and Redis connectivity."""
    from sqlalchemy import text
    from app.db.session import SessionLocal
    import redis

    issues = []

    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as exc:
        issues.append(f"database: {exc}")

    try:
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
    except Exception as exc:
        issues.append(f"redis: {exc}")

    if issues:
        return JSONResponse(status_code=503, content={"status": "not_ready", "issues": issues})

    return {"status": "ready"}


@app.get("/metrics", tags=["ops"], include_in_schema=False)
def metrics():
    """Prometheus metrics — scraped by monitoring stack."""
    return metrics_response()


@app.get("/hipaa-status", tags=["ops"], include_in_schema=False)
def hipaa_status():
    """
    Returns HIPAA self-check results.
    [HIPAA] Restrict this endpoint in production — internal use only.
    """
    if settings.is_production:
        return JSONResponse(status_code=403, content={"detail": "Not available in production."})
    findings = run_hipaa_self_check()
    passed = sum(1 for f in findings if f["status"] == "PASS")
    failed = sum(1 for f in findings if f["status"] == "FAIL")
    warned = sum(1 for f in findings if f["status"] == "WARN")
    return {
        "summary": {"passed": passed, "failed": failed, "warned": warned},
        "findings": findings,
    }
