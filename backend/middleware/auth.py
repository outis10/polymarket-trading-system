"""API Key authentication middleware."""

import os

from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

_API_KEY = os.getenv("API_KEY", "")

# Paths that bypass API Key check (health/ping if ever needed)
_EXEMPT_PATHS: set[str] = set()


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not _API_KEY:
            # No key configured — allow all (dev mode)
            return await call_next(request)

        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # WebSocket upgrades are handled separately in ws_auth_required
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        key = request.headers.get("X-API-Key", "")
        if key != _API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)


def verify_ws_api_key(websocket: WebSocket) -> bool:
    """Validate API Key for WebSocket connections (passed as query param or header)."""
    if not _API_KEY:
        return True
    # Accept key from header or query param ?api_key=...
    key = websocket.headers.get("X-API-Key", "") or websocket.query_params.get("api_key", "")
    return key == _API_KEY
