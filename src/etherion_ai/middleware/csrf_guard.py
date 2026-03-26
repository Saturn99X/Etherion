from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, HTTPException
import json


class GraphQLCSRFGuard(BaseHTTPMiddleware):
    """Require Authorization header on GraphQL POST to prevent CSRF on mutations.

    For same-site GET/WS this is skipped. Real CSRF tokens can be added later.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/graphql") and request.method.upper() == "POST":
            # Allow specific unauthenticated login/signup mutations to pass CSRF guard
            allowed_unauth_ops = {
                "GoogleLogin",
                "GithubLogin",
                "MicrosoftLogin",
                "PasswordSignup",
                "PasswordLogin",
            }

            op_name = None
            body_bytes = None
            try:
                body_bytes = await request.body()
                if body_bytes:
                    payload = json.loads(body_bytes.decode("utf-8"))
                    op_name = payload.get("operationName")
            except Exception:
                # If parsing fails, fall back to requiring Authorization
                op_name = None
            finally:
                # Re-inject body so downstream can read it again
                try:
                    if body_bytes is not None:
                        request._body = body_bytes  # type: ignore[attr-defined]
                except Exception:
                    pass

            if op_name in allowed_unauth_ops:
                return await call_next(request)

            # For all other GraphQL POSTs, require Authorization header
            auth = request.headers.get("authorization") or request.headers.get("Authorization")
            if not auth:
                raise HTTPException(status_code=401, detail="Authorization header required")
        return await call_next(request)


class RESTCSRFGuard(BaseHTTPMiddleware):
    """Require Authorization header on sensitive REST mutations (e.g., /secrets/*).

    Applies to POST/PUT/PATCH/DELETE on path prefixes that are security sensitive.
    """

    SENSITIVE_PREFIXES = ("/secrets/",)
    MUTATING_METHODS = ("POST", "PUT", "PATCH", "DELETE")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        method = request.method.upper()
        if method in self.MUTATING_METHODS and any(path.startswith(p) for p in self.SENSITIVE_PREFIXES):
            auth = request.headers.get("authorization") or request.headers.get("Authorization")
            if not auth:
                raise HTTPException(status_code=401, detail="Authorization header required")
        return await call_next(request)

