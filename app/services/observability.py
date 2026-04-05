
from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

request_id_ctx: ContextVar[str] = ContextVar('request_id', default='')
logger = logging.getLogger('paperwork')

HTTP_REQUEST_COUNT = Counter(
    'paperwork_http_requests_total',
    'Total HTTP requests',
    ['method', 'path', 'status_code'],
)
HTTP_REQUEST_LATENCY = Histogram(
    'paperwork_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'path'],
)
AUTH_REFRESH_COUNT = Counter(
    'paperwork_auth_refresh_total',
    'Refresh token calls',
    ['outcome'],
)

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'request_id': getattr(record, 'request_id', request_id_ctx.get('')),
            'timestamp': self.formatTime(record, self.datefmt),
        }
        if hasattr(record, 'extra_data'):
            payload.update(record.extra_data)
        return json.dumps(payload)

class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get('')
        return True


def configure_logging(level: str = 'INFO') -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get('x-request-id') or str(uuid.uuid4())
        request_id_ctx.set(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration = time.perf_counter() - started
            HTTP_REQUEST_COUNT.labels(request.method, request.url.path, str(status_code)).inc()
            HTTP_REQUEST_LATENCY.labels(request.method, request.url.path).observe(duration)
            logger.exception('request_failed', extra={'extra_data': {'path': request.url.path, 'method': request.method}})
            raise
        duration = time.perf_counter() - started
        duration_ms = round(duration * 1000, 2)
        response.headers['x-request-id'] = request_id
        HTTP_REQUEST_COUNT.labels(request.method, request.url.path, str(status_code)).inc()
        HTTP_REQUEST_LATENCY.labels(request.method, request.url.path).observe(duration)
        logger.info(
            'request_completed',
            extra={
                'extra_data': {
                    'path': request.url.path,
                    'method': request.method,
                    'status_code': response.status_code,
                    'duration_ms': duration_ms,
                }
            },
        )
        return response


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
