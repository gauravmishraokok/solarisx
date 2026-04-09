"""App middleware and error handlers."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from memora.core.errors import AlreadyResolvedError, MemoryNotFoundError, QuarantineNotFoundError

logger = logging.getLogger(__name__)

# Origins allowed for CORS (must match browser URL exactly, including scheme).
CORS_ALLOW_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]


def cors_headers_for_request(request: Request) -> dict[str, str]:
    """Build Access-Control-* headers when origin is allowed."""
    origin = request.headers.get("origin")
    if origin and origin in CORS_ALLOW_ORIGINS:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Log request path, status, and latency."""

    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - started) * 1000.0
        response.headers["X-Response-Time"] = f"{ms:.2f}"
        logger.info(
            "%s %s -> %s (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            ms,
        )
        return response


class UncaughtExceptionMiddleware(BaseHTTPMiddleware):
    """
    Catch exceptions that escape inner layers so the browser always gets JSON
    and CORS headers. Without this, uvicorn can emit a bare 500 with no
    Access-Control-Allow-Origin, which Chrome reports as a CORS failure.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled exception: %s", exc)
            headers = cors_headers_for_request(request)
            return JSONResponse(
                status_code=500,
                content={
                    "detail": str(exc),
                    "type": type(exc).__name__,
                },
                headers=headers,
            )


def register_middleware(app: FastAPI) -> None:
    """
    Register middleware. Starlette applies add_middleware in order: each new
    middleware wraps the previous stack, so the LAST added runs first on the
    request (outermost). Order here (inner -> outer):
    RequestTiming -> CORSMiddleware -> UncaughtException
    """
    app.add_middleware(RequestTimingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(UncaughtExceptionMiddleware)


def register_error_handlers(app: FastAPI) -> None:
    """Register typed exception mappers."""

    def _with_cors(response: JSONResponse, request: Request) -> JSONResponse:
        for k, v in cors_headers_for_request(request).items():
            response.headers[k] = v
        return response

    @app.exception_handler(MemoryNotFoundError)
    async def memory_not_found_handler(request: Request, exc: MemoryNotFoundError):  # noqa: ARG001
        return _with_cors(JSONResponse(status_code=404, content={"error": str(exc)}), request)

    @app.exception_handler(QuarantineNotFoundError)
    async def quarantine_not_found_handler(request: Request, exc: QuarantineNotFoundError):  # noqa: ARG001
        return _with_cors(JSONResponse(status_code=404, content={"error": str(exc)}), request)

    @app.exception_handler(AlreadyResolvedError)
    async def already_resolved_handler(request: Request, exc: AlreadyResolvedError):  # noqa: ARG001
        return _with_cors(JSONResponse(status_code=409, content={"error": str(exc)}), request)

    # Do not register a catch-all Exception handler here: it would intercept
    # Starlette/FastAPI HTTPException handling. UncaughtExceptionMiddleware
    # covers truly unhandled errors with CORS headers.
