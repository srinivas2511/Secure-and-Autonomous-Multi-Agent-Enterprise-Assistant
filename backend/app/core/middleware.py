"""Request-level middleware: correlation IDs and structured-logging context."""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Accessible from anywhere in the same request context.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Stamp every request with an X-Request-ID header and expose it via
    a ContextVar so log lines anywhere in the call-stack can include it."""

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(req_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_var.reset(token)
