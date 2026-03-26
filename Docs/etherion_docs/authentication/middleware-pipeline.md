# Middleware Pipeline: The Request Processing Stack

## Why Middleware Order Matters

When a request arrives at Etherion, it passes through multiple layers of middleware. Each layer can inspect, modify, or reject the request. The **order is critical**: if you validate authentication before extracting the tenant context, the tenant_id won't be available for authorization checks.

Think of it like airport security:
1. First, check if you have a valid ticket (authentication)
2. Then, verify your ticket matches the flight route (authorization/tenant check)
3. Then, enforce additional rules (rate limits, CSRF, etc.)

If you enforce rate limits before authentication, you might rate-limit legitimate users who couldn't authenticate. If you enforce CSRF before extracting the user, you can't apply user-specific CSRF protection.

## The Middleware Stack

Etherion's middleware pipeline, in order from outside to inside:

```
Request arrives
     |
     v
1. CORS Middleware
   (preflight, origin validation)
     |
     v
2. Security Headers Middleware
   (X-Content-Type-Options, CSP, etc.)
     |
     v
3. Rate Limit Middleware
   (per-IP, per-user throttling)
     |
     v
4. CSRF Guard Middleware
   (Authorization header requirement for mutations)
     |
     v
5. Auth Context Middleware
   (JWT decode, user lookup, tenant context setup)
     |
     v
6. Tenant Middleware
   (resolve subdomain tenant, finalize tenant_id)
     |
     v
7. Application Logic
   (route handlers, GraphQL resolvers, etc.)
     |
     v
Response is generated and flows back through middleware in reverse order
```

## Layer 1: CORS Middleware (Preflight & Origin)

**File**: Typically FastAPI's built-in `CORSMiddleware`

**Purpose**: Control cross-origin requests from browsers

**What it does**:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.etherion.ai", "https://*.etherion.ai"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600
)
```

1. **Preflight Handling**: Browser sends `OPTIONS` request before POST/PUT/DELETE
   - Middleware responds with CORS headers
   - Browser then sends the actual request
   - No authentication needed for preflight (it's just metadata)

2. **Origin Checking**: Verifies the `Origin` header matches allowed origins
   - If origin not allowed: Response includes no `Access-Control-Allow-Origin` header
   - Browser blocks the response

3. **Credentials Handling**: `allow_credentials=True` means cookies/tokens are allowed
   - Requires explicit origin (not `*`)

**Why here**: CORS applies globally and doesn't depend on authentication state. Checking early avoids wasting cycles on requests from malicious origins.

## Layer 2: Security Headers Middleware

**File**: Typically Starlette's built-in `middleware.middleware`

**Purpose**: Add security headers to all responses

**What it does**:

```python
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'"
    return response
```

1. **X-Content-Type-Options: nosniff**: Browser won't guess content type; prevents MIME sniffing attacks
2. **X-Frame-Options: DENY**: Prevents embedding in `<iframe>`, stops clickjacking
3. **X-XSS-Protection**: Legacy (modern browsers use CSP), instructs old browsers to block XSS
4. **Strict-Transport-Security**: Tells browser to always use HTTPS for this domain
5. **Content-Security-Policy**: Restricts what scripts can execute and where styles can load from

**Why here**: Applies to all responses regardless of handler. No need to repeat in every route.

## Layer 3: Rate Limit Middleware

**File**: `src/auth/middleware.py::RateLimitMiddleware`

**Purpose**: Prevent abuse by limiting requests per client

**What it does**:

```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get client ID
        if hasattr(request.state, 'user') and request.state.user:
            client_id = f"user:{request.state.user.user_id}"
        else:
            client_id = f"ip:{request.client.host}"

        # Check rate limit (Redis-backed)
        if await self._is_rate_limited(client_id):
            return Response(
                content='{"detail": "Rate limit exceeded"}',
                status_code=429
            )

        # Increment counter
        await self._increment_request_count(client_id)
        return await call_next(request)
```

1. **Identify Client**: Use user_id if authenticated, else IP address
2. **Check Redis**: Query key `rate_limit:user:123` or `rate_limit:ip:192.168.1.1`
3. **Compare Against Limit**: 60 requests per minute (default)
4. **Increment Counter**: `INCR` the Redis key, set TTL to 60 seconds
5. **Reject if Over**: Return 429 Too Many Requests

**Why here**: After CORS but before expensive operations. If using user_id, requires auth context from layer 5, so this is before auth actually. However, it can infer whether a request is authenticated yet and treat accordingly.

## Layer 4: CSRF Guard Middleware

**File**: `src/etherion_ai/middleware/csrf_guard.py`

**Purpose**: Prevent cross-site request forgery on mutations

**What it does**:

```python
class GraphQLCSRFGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/graphql") and request.method == "POST":
            # Whitelist unauthenticated mutations
            allowed_unauth = {"GoogleLogin", "GithubLogin", "PasswordSignup", "PasswordLogin"}

            op_name = None
            try:
                body = await request.body()
                payload = json.loads(body.decode())
                op_name = payload.get("operationName")
            except:
                op_name = None
            finally:
                request._body = body

            # If it's a whitelisted op, allow without auth header
            if op_name in allowed_unauth:
                return await call_next(request)

            # All other GraphQL POSTs require Authorization header
            auth = request.headers.get("authorization") or request.headers.get("Authorization")
            if not auth:
                raise HTTPException(status_code=401, detail="Authorization header required")

        return await call_next(request)
```

1. **Path & Method Check**: Only applies to POST /graphql
2. **Parse Operation Name**: Extracts the GraphQL operation name from the request body
3. **Whitelist Check**: If it's a login/signup mutation, allow without auth
4. **Require Auth Header**: All other mutations require Authorization header
5. **Note**: Real CSRF tokens are not used; we rely on SameSite cookies + Authorization header

**Why here**: After CORS and rate limiting, but before auth context (so we can whitelist login ops). We need to read the request body, so it's a heavier middleware placed strategically.

**Why this approach**: OAuth/password login requests shouldn't require auth (they're how users get authenticated). But by requiring the Authorization header for all other mutations, we prevent CSRF:
- CSRF attacker can't add custom headers from another site
- SameSite cookie policies prevent cookies from being sent cross-site anyway

## Layer 5: Auth Context Middleware

**File**: `src/etherion_ai/middleware/auth_context.py::graphql_auth_middleware`

**Purpose**: Extract and validate JWT, look up user, set tenant context

**What it does**:

```python
async def graphql_auth_middleware(request: Request, call_next):
    if request.url.path != "/graphql":
        return await call_next(request)

    # Resolve user from JWT
    current_user, tenant_id = await resolve_current_user_from_headers(request.headers)

    # Extract token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            token_data = decode_access_token(token)
            tenant_id = token_data.tenant_id

            # Check if token is blacklisted (revoked)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            if await redis.get(f"token:blacklist:{token_hash}"):
                return 401  # Revoked token

            # Look up user from database
            with session_scope() as auth_session:
                user = auth_session.exec(select(User).where(User.user_id == token_data.user_id)).first()
                if user:
                    current_user = user

        except:
            pass

    # Set database session's tenant context (PostgreSQL RLS)
    db_session = get_db()
    if tenant_id:
        db_session.execute(text(f"SET app.tenant_id = {tenant_id}"))
    else:
        db_session.execute(text("SELECT set_config('app.tenant_id', NULL, false)"))

    # Attach to request state
    request.state.auth_context = {
        "current_user": current_user,
        "db_session": db_session,
        "tenant_id": tenant_id,
    }
    request.state.tenant_id = tenant_id

    response = await call_next(request)

    # Commit transaction if needed
    try:
        db_session.commit()
    except:
        pass
    finally:
        db_session.close()

    return response
```

1. **Extract JWT**: Get Authorization header
2. **Decode & Verify**: Validate signature, expiration, type claims
3. **Check Blacklist**: See if token was revoked
4. **Look Up User**: Query database by user_id from JWT
5. **Verify User Active**: Check `is_active` flag
6. **Set Tenant Context**: Execute PostgreSQL `SET app.tenant_id = ...`
   - This configures Row-Level Security (RLS) policies
   - Any query on an RLS-protected table will automatically be filtered
7. **Keep Database Session Open**: Store `db_session` on `request.state` so handlers can use it
8. **Attach to Request**: Set `request.state.current_user`, `request.state.tenant_id`

**Why here**: After CSRF (so we can allow login ops), and before the database is used. JWT extraction is critical for authorization.

**Important**: PostgreSQL RLS policies rely on `app.tenant_id` being set. If this middleware runs too late, queries before it runs won't be scoped. If it runs too early (before tenant is resolved), it can't set the right context.

## Layer 6: Tenant Middleware

**File**: `src/etherion_ai/middleware/tenant_middleware.py::tenant_middleware`

**Purpose**: Resolve tenant from JWT or Host subdomain

**What it does**:

```python
async def tenant_middleware(request: Request, call_next):
    tenant_id = None
    subdomain = None

    # Priority 1: JWT token (authenticated requests)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        try:
            token_data = decode_access_token(token)
            tenant_id = token_data.tenant_id
        except:
            pass

    # Priority 2: Extract subdomain from Host header
    subdomain = extract_subdomain_from_request(request)

    # If subdomain is not reserved and we don't have tenant from JWT, look it up
    if subdomain and subdomain not in RESERVED_SUBDOMAINS and not tenant_id:
        auth_ctx = getattr(request.state, "auth_context", None)
        if auth_ctx and auth_ctx.get("db_session"):
            try:
                tenant = auth_ctx["db_session"].exec(
                    select(Tenant).where(Tenant.subdomain == subdomain)
                ).first()
                if tenant:
                    tenant_id = tenant.id
            except:
                pass

    # Store on request state
    request.state.subdomain = subdomain
    request.state.tenant_id = tenant_id

    response = await call_next(request)
    return response
```

1. **Try JWT**: If authenticated, extract tenant_id from token
2. **Extract Subdomain**: Parse Host header (e.g., "alice-workspace.app.etherion.ai" → "alice-workspace")
3. **Validate Subdomain**: Check it's not reserved (api, app, auth, www, etc.)
4. **Lookup if Needed**: If subdomain exists but no JWT, query database to find tenant_id
5. **Store on Request**: Set `request.state.subdomain` and `request.state.tenant_id` for handlers

**Why here**: After auth context (so JWT is already decoded and user is looked up). This finalizes the tenant resolution, ensuring downstream handlers have `request.state.tenant_id` set.

**Resolution Priority**:
- If authenticated with JWT: Use JWT's tenant_id (most authoritative)
- If unauthenticated but accessing a subdomain: Look up the subdomain to get tenant_id
- If neither: tenant_id remains None (typically 403 Forbidden for protected endpoints)

## What Happens on a Protected Request

Let's trace a request to create a query:

```
POST /graphql
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
{"operationName": "CreateQuery", "variables": {"name": "Sales Data"}}
Host: alice-workspace.app.etherion.ai
```

**Layer 1 (CORS)**: ✓ Origin is in allowed list

**Layer 2 (Security Headers)**: ✓ Headers will be added to response

**Layer 3 (Rate Limit)**: ✓ user_id extracted after layer 5, use IP for now; passes

**Layer 4 (CSRF Guard)**: ✓ POST to /graphql with "CreateQuery" operation; not in whitelist; has Authorization header; passes

**Layer 5 (Auth Context)**:
- Extracts JWT from header
- Decodes: `{"sub": "user_123", "email": "alice@example.com", "tenant_id": 42}`
- Looks up user in database
- Sets `app.tenant_id = 42` on PostgreSQL session
- Attaches to `request.state.auth_context`

**Layer 6 (Tenant)**:
- Extracts subdomain "alice-workspace" from Host header
- Tenant already set from JWT (42), so uses that
- Confirms consistency

**Application Logic**:
- Handler receives `request.state.current_user` (Alice) and `request.state.tenant_id` (42)
- Queries database for queries: `SELECT * FROM queries WHERE tenant_id = 42`
- PostgreSQL RLS policy double-checks: `current_setting('app.tenant_id') = 42`
- Only Alice's queries are returned

**Response**: Flows back through middleware, security headers added, CORS header included

## Unprotected Request Example

```
GET /health
```

No Authorization header.

**Layers 1-4**: ✓ Pass through

**Layer 5 (Auth Context)**:
- No Authorization header
- current_user = None
- Allows GET requests without auth
- tenant_id = None

**Layer 6 (Tenant)**:
- No subdomain in Host (e.g., "api.etherion.ai" is reserved)
- tenant_id remains None

**Application Logic**:
- Handler for /health doesn't require auth
- Returns `{"status": "ok"}`

## Critical Ordering Rules

1. **CORS before rate limiting**: CORS is about browser metadata, independent of app logic
2. **Rate limiting before expensive operations**: Rejects requests early if over limit
3. **CSRF before auth**: Can whitelist login ops without auth
4. **Auth context before tenant middleware**: JWT must be decoded before tenant lookup
5. **Tenant middleware before app logic**: Handlers assume tenant_id is set on request.state

Breaking this order creates bugs:
- Rate limiting after auth: Authenticated users consume auth cycles even if over rate limit
- Tenant middleware before auth: tenant_id not available for auth decisions
- Auth context after app logic: User and tenant info not available in handlers

## Debugging Middleware Issues

Common problems and solutions:

1. **"Invalid token" on every request**: Auth context middleware running too late or secret key changed
2. **"Tenant not found" errors**: Tenant middleware running before tenant is resolved
3. **CORS errors in browser**: CORS middleware missing or incorrect allowed_origins
4. **Rate limit bypassed**: Rate limit middleware using wrong client identifier
5. **CSRF errors on mutations**: CSRF middleware whitelist missing your operation name

Each middleware logs to `logging.getLogger(__name__)`, so enable debug logging to trace:

```python
import logging
logging.getLogger("src.auth.middleware").setLevel(logging.DEBUG)
logging.getLogger("src.etherion_ai.middleware").setLevel(logging.DEBUG)
```

## Next Steps

- To understand JWT validation in detail, see `jwt-and-sessions.md`
- To understand OAuth flows, see `oauth-flow.md`
- To understand password authentication, see `local-auth.md`
