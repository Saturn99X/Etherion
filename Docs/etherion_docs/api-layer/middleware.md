# Middleware: The Request Pipeline

## Overview

Before a GraphQL query reaches a resolver, it travels through a middleware stack. Each middleware layer performs a specific task: extracting the user from headers, checking CSRF tokens, validating the API version, assigning a request ID, or logging the request. This layered approach keeps concerns separated and makes each middleware testable.

The middleware stack in `src/etherion_ai/app.py` is assembled like this:

```python
# Add security middleware (must be first)
app.middleware("http")(secure_request_handler)
app.add_middleware(GraphQLCSRFGuard)
app.add_middleware(RESTCSRFGuard)

# Request logging
app.middleware("http")(request_logger_middleware)

# Rate limiting
app.add_middleware(PerIPRateLimitMiddleware)

# Versioning
app.middleware("http")(versioning_middleware)

# Error handling
app.middleware("http")(error_handling_middleware)

# Auth context
app.middleware("http")(graphql_auth_middleware)

# Tenant isolation
app.middleware("http")(tenant_middleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

The order matters. Security runs first; error handling runs late (to catch errors from everything else); CORS runs last (outermost).

## Authentication Middleware

The `graphql_auth_middleware` is responsible for extracting the JWT token from the request and resolving the authenticated user:

```python
async def graphql_auth_middleware(request: Request, call_next):
    """Extract JWT from Authorization header and populate auth context."""
    # Skip auth for certain paths (health, root, OAuth endpoints)
    path = request.url.path or ""
    if path in ("/health", "/", "/metrics") or path.startswith("/oauth/"):
        return await call_next(request)

    # Extract Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        # Not authenticated, but we don't fail here
        # Some endpoints (like health checks) don't require auth
        return await call_next(request)

    token = auth_header[7:]  # Remove "Bearer "

    try:
        # Decode JWT
        from src.auth.jwt import decode_access_token
        token_data = decode_access_token(token)

        # Query database for user
        from src.database.db import get_scoped_session
        async with get_scoped_session() as session:
            stmt = select(User).where(User.user_id == token_data.sub)
            result = await session.execute(stmt)
            user = result.scalars().first()

            if not user:
                # Token is valid but user no longer exists
                request.state.auth_context = {"current_user": None}
            else:
                # Attach user and tenant context
                request.state.auth_context = {
                    "current_user": user,
                    "db_session": session,
                    "tenant_id": user.tenant_id,
                }
                request.state.tenant_id = user.tenant_id

    except jwt.ExpiredSignatureError:
        # Token has expired
        request.state.auth_context = {"current_user": None}
    except jwt.JWTError:
        # Token is invalid (tampered, wrong key, etc.)
        request.state.auth_context = {"current_user": None}

    return await call_next(request)
```

**Key points**:

1. **Token Extraction**: The JWT is extracted from the `Authorization: Bearer <token>` header.
2. **JWT Decode**: We use `decode_access_token` to parse the JWT without validation (just checking the signature). This tells us the user ID encoded in the token.
3. **User Lookup**: We query the User table for the user with that ID. If the user doesn't exist (e.g., account was deleted), we treat it as unauthenticated.
4. **Context Attachment**: The user object and tenant ID are attached to the request state. Resolvers later access this via `info.context["request"].state.auth_context`.
5. **Graceful Degradation**: If authentication fails, we don't immediately return a 401. Instead, we attach `{"current_user": None}`. Individual resolvers then check if they require authentication and raise an error if needed. This allows public endpoints to work.

## Tenant Middleware

Multi-tenancy is enforced at the middleware level:

```python
async def tenant_middleware(request: Request, call_next):
    """Set tenant context for the request."""
    # Extract tenant_id from auth context (set by auth_middleware)
    auth_context = getattr(request.state, "auth_context", None)
    tenant_id = None

    if auth_context and auth_context.get("current_user"):
        tenant_id = auth_context["current_user"].tenant_id
    else:
        # Try to extract from request (e.g., subdomain for multi-tenant SaaS)
        from src.utils.tenant_context import resolve_tenant_from_request
        tenant_id = await resolve_tenant_from_request(request)

    # Set tenant context for the entire request lifecycle
    set_tenant_context(tenant_id)
    request.state.tenant_id = tenant_id

    return await call_next(request)
```

This sets a thread-local variable so that if any service function queries the database without an explicit WHERE clause, the tenant filter is applied implicitly. This is a safety net: even if a developer forgets to add a tenant filter, data leaks are prevented.

## Versioning Middleware

The `versioning_middleware` reads the `Accept-Version` header to support API versioning:

```python
async def versioning_middleware(request: Request, call_next):
    """Handle API versioning via Accept-Version header."""
    version_header = request.headers.get("Accept-Version")

    if not version_header:
        # Default to latest stable version
        version = "v0.5"
        full_version = "0.5.0"
    elif version_header not in SUPPORTED_VERSIONS:
        # Unsupported version
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported version: {version_header}"
        )
    else:
        version = version_header
        full_version = SUPPORTED_VERSIONS[version_header]

    # Attach version info to request state
    request.state.api_version = version
    request.state.api_full_version = full_version

    response = await call_next(request)

    # Add version headers to response
    response.headers["API-Version"] = version
    response.headers["API-Full-Version"] = full_version

    return response
```

This allows Etherion to support multiple API versions simultaneously. If a breaking change is introduced in v1.0, clients specifying `Accept-Version: v0.5` continue to work with the old behavior. New clients can opt into `Accept-Version: v1.0` for new features.

## Error Handling Middleware

The `error_handling_middleware` catches exceptions and formats them consistently:

```python
async def error_handling_middleware(request: Request, call_next):
    """Catch exceptions and return structured error responses."""
    try:
        response = await call_next(request)
        return response
    except BaseEtherionException as e:
        # Application-specific errors
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

        log_error(
            request_id=request_id,
            error=e,
            context={
                "error_code": e.error_code,
                "status_code": e.status_code,
            }
        )

        return JSONResponse(
            status_code=e.status_code,
            content=format_error_response(
                message=e.message,
                error_code=e.error_code,
                status_code=e.status_code,
                request_id=request_id,
            )
        )
    except HTTPException as e:
        # FastAPI HTTP exceptions
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

        return JSONResponse(
            status_code=e.status_code,
            content={
                "error": {
                    "message": e.detail,
                    "code": "HTTP_ERROR",
                    "request_id": request_id,
                }
            }
        )
    except Exception as e:
        # Unexpected errors
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

        logger.error(f"Unhandled exception: {str(e)}", exc_info=True)

        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "An unexpected error occurred",
                    "code": "INTERNAL_SERVER_ERROR",
                    "request_id": request_id,
                }
            }
        )
```

All errors return a consistent structure:

```json
{
  "error": {
    "message": "User not found",
    "code": "NOT_FOUND",
    "status": 404,
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "details": {
      "user_id": "12345"
    }
  }
}
```

The `request_id` in every error response allows clients to report issues to support ("Error during job submission; request ID: xyz"). Support can then search logs for that request_id to debug the problem.

## Request Logger Middleware

The `request_logger_middleware` logs every incoming request and assigns it a unique request ID:

```python
async def request_logger_middleware(request: Request, call_next):
    """Log requests and assign unique request IDs."""
    # Generate request ID
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    # Log request
    path = request.url.path
    method = request.method
    client_ip = request.client.host if request.client else "unknown"

    logger.info(f"[{request_id}] {method} {path} from {client_ip}")

    # Process request
    start_time = time.time()
    try:
        response = await call_next(request)
        elapsed = time.time() - start_time

        # Log response
        logger.info(
            f"[{request_id}] {method} {path} -> {response.status_code} ({elapsed:.3f}s)"
        )

        return response
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            f"[{request_id}] {method} {path} FAILED ({elapsed:.3f}s): {str(e)}"
        )
        raise
```

Logs look like:

```
[550e8400-e29b-41d4-a716-446655440000] POST /graphql from 192.168.1.100
[550e8400-e29b-41d4-a716-446655440000] POST /graphql -> 200 (0.245s)
```

This makes it trivial to trace a request end-to-end through logs. Every log line related to a request includes its request_id, so you can search logs for that ID and see the entire request lifecycle.

## CSRF Protection

The `GraphQLCSRFGuard` middleware validates that mutations originating from browsers are from allowed origins:

```python
class GraphQLCSRFGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip CSRF check for safe methods (GET)
        if request.method == "GET":
            return await call_next(request)

        # Skip CSRF check for non-mutation GraphQL requests (e.g., queries)
        if request.url.path == "/graphql":
            try:
                body = await request.body()
                data = json.loads(body)
                # Only mutations and subscriptions need CSRF protection
                if data.get("operationName") in ("query", None):
                    # This is likely a query; skip CSRF
                    pass
            except Exception:
                pass

        # Check Origin header against allowed origins
        origin = request.headers.get("Origin")
        allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

        if origin and origin not in allowed_origins:
            return JSONResponse(
                status_code=403,
                content={"error": "CSRF validation failed"}
            )

        return await call_next(request)
```

This prevents a malicious website from making mutations on behalf of an authenticated user. If a user is logged into Etherion in their browser, and then visits `evil.com`, that site cannot make authenticated requests to your Etherion API from their browser. CSRF tokens or Origin checking prevents it.

## Structured Logging with GraphQL Logger

The `graphql_logger.py` middleware (specific to GraphQL operations) logs GraphQL-specific information:

```python
class GraphQLOperationLogger:
    @staticmethod
    async def log_operation(
        info: GraphQLResolveInfo,
        operation_name: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log GraphQL operation information."""
        try:
            request_id = getattr(info.context, "request_id", "unknown")
            query = str(info.field_nodes)[:100]  # First 100 chars of query

            log_info(
                "GraphQL operation executed",
                request_id=request_id,
                operation_name=operation_name,
                query=query,
                variables_count=len(variables) if variables else 0
            )
        except Exception as e:
            logger.error(f"Error logging GraphQL operation: {str(e)}")
```

This logs are structured (JSON-formatted) so they can be parsed and analyzed by log aggregation tools like Datadog or Elastic.

A typical log looks like:

```json
{
  "timestamp": "2026-03-26T16:30:00Z",
  "level": "INFO",
  "message": "GraphQL operation executed",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "operation_name": "ExecuteGoal",
  "query": "mutation ExecuteGoal($goal_input: GoalInput!) { executeGoal(goal_input: $goal_input) {...}}",
  "variables_count": 1
}
```

## Rate Limiting

The `PerIPRateLimitMiddleware` prevents abuse by limiting requests per IP:

```python
class PerIPRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int = None):
        super().__init__(app)
        self.per_minute = int(per_minute or os.getenv("RATE_LIMIT_PER_MINUTE", "120"))

    async def dispatch(self, request: Request, call_next):
        # Exempt certain paths
        path = request.url.path or ""
        if path in ("/health", "/") or path.startswith("/webhook/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"iprl:{client_ip}:{int(time.time() // 60)}"

        # Check rate limit in Redis
        redis = get_redis_client()
        current = await redis.incr(key)

        if int(current) == 1:
            # First request this minute; set expiry
            await redis.expire(key, 70)

        if int(current) > self.per_minute:
            raise HTTPException(
                status_code=429,
                detail="Too Many Requests",
                headers={"Retry-After": "60"}
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.per_minute - int(current)))

        return response
```

Rate limiting is tracked in Redis per IP address per minute. If an IP exceeds the limit, it gets a 429 response. This prevents brute-force attacks and DDoS.

## Why Structured Logs Matter

Structured logging (JSON-formatted logs with consistent keys) is critical for debugging production issues. Instead of grepping through text logs, you can query your log aggregation system:

```
request_id = "550e8400..." AND level = "ERROR"
```

And get all errors related to that request, in chronological order, with context.

Log keys are consistent across the platform:
- `request_id`: Unique request identifier
- `tenant_id`: Tenant for the request
- `user_id`: Authenticated user ID
- `operation_name`: GraphQL operation name
- `error_code`: Application error code
- `status_code`: HTTP status code

This structure allows you to:

1. **Trace a Request**: Search for request_id to see everything that happened
2. **Monitor a User**: Search for user_id to see their activity
3. **Debug by Error Code**: Search for error_code to find all occurrences of a specific error
4. **Analyze Performance**: Query all operations taking > 1 second

## Next Steps

- **Mutations** (`mutations.md`): See how mutations validate and sanitize input before processing.
- **Subscriptions** (`subscriptions.md`): Learn how subscriptions authenticate over WebSocket.
- **Schema Structure** (`schema-structure.md`): Review how the Info object carries context through resolvers.
