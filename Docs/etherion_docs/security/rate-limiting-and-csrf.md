# Rate Limiting and CSRF Protection in Etherion

## Overview

Etherion protects the API boundary using two complementary mechanisms: rate limiting prevents resource exhaustion and brute force attacks, while CSRF (Cross-Site Request Forgery) protection prevents unauthorized state changes from malicious websites. Both are transparent to legitimate clients and logged for forensics.

## Rate Limiting Strategy

Rate limiting is applied per-IP and per-tenant to prevent abuse. The system distinguishes between endpoint types (auth, GraphQL, general) and applies different limits:

```
┌─────────────┐
│ API Request │
│  (unknown)  │
└──────┬──────┘
       │
       ▼
   ┌───────────────────┐
   │ Identify IP/User  │
   └─────────┬─────────┘
             │
       ┌─────▼────────────────────────┐
       │ Determine Endpoint Type      │
       │ - auth_endpoints (strict)    │
       │ - graphql_queries (moderate) │
       │ - default (lenient)          │
       └─────┬────────────────────────┘
             │
       ┌─────▼────────────────────────┐
       │ Check Rate Limit             │
       │ Redis: ratelimit:{endpoint}  │
       └─────┬────────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
   ▼                  ▼
ALLOW (log)      REJECT (429, log)
```

### Rate Limit Configuration

Default limits (configurable):

```python
RATE_LIMIT_CONFIG = {
    "auth_endpoints": {
        "requests_per_minute": 5,      # Brute force protection
        "requests_per_hour": 20
    },
    "graphql_queries": {
        "requests_per_minute": 50,     # Prevent resource exhaustion
        "requests_per_hour": 500
    },
    "default": {
        "requests_per_minute": 100,    # General API endpoints
        "requests_per_hour": 1000
    }
}
```

### Why These Limits?

- **auth_endpoints (5/min)**: Prevents brute force. A legitimate user can try 5 times per minute if they keep forgetting their password; an attacker trying 1000 usernames/minute is blocked.

- **graphql_queries (50/min)**: GraphQL queries can be expensive (deep joins, N+1 queries). Limiting prevents a single client from overloading the database.

- **default (100/min)**: Most normal operations (reading profiles, creating posts) are fine at this rate.

### Identifying the Client

The rate limiter extracts the client identifier (IP or user):

```python
# If authenticated (JWT token), use tenant + user
if user_id and tenant_id:
    identifier = f"user_{tenant_id}_{user_id}"
else:
    # If not authenticated, use IP
    identifier = client_ip

# Per-IP limit is also checked for authenticated users
# (prevents a single user from overwhelming the system)
```

This means:
- Each IP address has separate limits (prevents users on the same network from hitting each other's limits)
- Authenticated users have stricter limits (prevents account compromise)
- Anonymous users have the loosest limits (encourages signup)

### Backend: Redis

Rate limits are stored in Redis with TTL:

```
# Key format: ratelimit:{endpoint}:{identifier}
# Value: count
# TTL: 60 seconds (for per-minute limits) or 3600 (for per-hour)

INCR ratelimit:auth_endpoints:203.0.113.42
-> 1 (first request, reset to 1)

INCR ratelimit:auth_endpoints:203.0.113.42
-> 2

INCR ratelimit:auth_endpoints:203.0.113.42
-> 3

INCR ratelimit:auth_endpoints:203.0.113.42
-> 4

INCR ratelimit:auth_endpoints:203.0.113.42
-> 5 (limit reached)

INCR ratelimit:auth_endpoints:203.0.113.42
-> 6 (EXCEED LIMIT → return 429)

# After 60 seconds, key expires, counter resets
```

Redis ensures atomic operations and automatic expiry.

### When Rate Limit is Exceeded

A 429 Too Many Requests response is returned:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
X-RateLimit-Limit-Minute: 5
X-RateLimit-Limit-Hour: 20
Retry-After: 45

{
  "detail": "Rate limit exceeded: 6/5 requests per minute"
}
```

The response includes headers indicating:
- **X-RateLimit-Limit-Minute**: The per-minute limit
- **X-RateLimit-Limit-Hour**: The per-hour limit
- **Retry-After**: Seconds until the limit resets

The client should wait and retry, or use exponential backoff.

### Audit Logging

Rate limit violations are logged:

```python
await log_rate_limit_exceeded(
    ip_address="203.0.113.42",
    user_agent="curl/7.68.0",
    endpoint="/graphql",
    method="POST",
    limit_type="requests_per_minute",
    limit_value=50,
    current_count=51,
    details={"operation": "GetUserProfile"}
)
```

This creates an audit event with severity MEDIUM, allowing operators to detect coordinated attacks or misconfigured clients.

### DDoS Mitigation

Rate limiting mitigates volumetric DDoS by rejecting excess traffic early. However, it's not a complete DDoS solution. For true DDoS protection, use:

1. **Cloudflare/WAF**: Rate limit at the edge before traffic reaches Etherion
2. **Load Balancer**: Distribute traffic across multiple servers
3. **Anycast CDN**: Route traffic through geographically distributed nodes

Etherion's rate limiter is a second line of defense for smaller attacks and application-level abuse.

## CSRF Protection

Cross-Site Request Forgery is an attack where a malicious website tricks your browser into making requests to Etherion while you're logged in. CSRF protection prevents this by requiring proof that the request originated from your own browser.

### CSRF Threat Scenario

```
1. User logs into etherion.example.com (JWT token in cookie/localStorage)
2. User visits evil.com (in same browser tab)
3. evil.com contains:
   <img src="https://etherion.example.com/api/delete-account">
4. Browser automatically sends the JWT token with the request
5. Etherion deletes the user's account (without their knowledge!)
```

### Double-Submit Cookie Pattern

Etherion uses the double-submit cookie pattern:

```
Step 1: Browser requests page
GET /dashboard HTTP/1.1
User-Agent: Mozilla/5.0

Step 2: Etherion returns HTML with CSRF token in body
HTTP/1.1 200 OK
Set-Cookie: csrf_token=abc123; SameSite=Strict; HttpOnly

<input type="hidden" name="csrf_token" value="abc123">

Step 3: Browser submits form with token in BODY and cookie in HEADER
POST /api/update-profile HTTP/1.1
Cookie: csrf_token=abc123
Content-Type: application/x-www-form-urlencoded

csrf_token=abc123&name=NewName

Step 4: Etherion verifies token in body matches token in cookie
if request.form.csrf_token == request.cookies.csrf_token:
    proceed()
else:
    return 403 Forbidden
```

### Why This Works

- **JavaScript from evil.com cannot read the token** (stored in HttpOnly cookie or DOM)
- **evil.com can POST, but cannot read the response** (browsers block cross-origin reads)
- **Legitimate Etherion requests include the token** (because they're from your own domain)

### Implementation in Etherion

GraphQL mutations require an Authorization header (Bearer token), which evil.com cannot set:

```python
# GraphQL CSRF Guard
if request.method == "POST" and request.url.path == "/graphql":
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(401, "Authorization header required")
```

REST API mutations require the `X-CSRF-Token` header:

```python
# REST CSRF Guard
CSRF_HEADER_NAME = "X-CSRF-Token"

csrf_token_from_header = request.headers.get(CSRF_HEADER_NAME)
csrf_token_from_session = get_session_csrf_token(request)

if csrf_token_from_header != csrf_token_from_session:
    raise HTTPException(403, "CSRF validation failed")
```

### Exempt Endpoints

Some endpoints are exempt from CSRF:

```python
CSRF_EXEMPT_PATHS = [
    "/auth/login",
    "/auth/signup",
    "/auth/oauth",
    "/webhook/",            # Webhooks use provider signatures, not CSRF
    "/health",
    "/docs",
]
```

These are intentionally exempt because:
- **Auth endpoints**: Called before token is issued
- **Webhooks**: Third-party services call these; CSRF doesn't apply
- **Health checks**: Non-state-changing

## Input Sanitization

Input sanitization prevents injection attacks (SQL, XSS, command injection). Etherion uses multiple layers:

### 1. Type Validation

GraphQL enforces schema types:

```graphql
input UpdateProfileInput {
    name: String!
    email: String!
    age: Int!
}
```

A client sending `{"name": ["array"], "email": null}` fails validation before reaching the resolver.

### 2. String Sanitization

All string inputs are validated against allowlists:

```python
# Email: RFC 5321 format
InputSanitizer.validate_email("user@example.com")  # OK
InputSanitizer.validate_email("user<script>")      # ❌ ValueError

# Identifier: alphanumeric + underscore
InputSanitizer.sanitize_string(
    "valid_name123",
    allowed_pattern=InputSanitizer.ALLOWED_IDENTIFIER
)  # OK

InputSanitizer.sanitize_string(
    "invalid<name>",
    allowed_pattern=InputSanitizer.ALLOWED_IDENTIFIER
)  # ❌ ValueError
```

### 3. SQL Injection Detection

Dangerous SQL patterns are detected:

```python
patterns = [
    r'(\bSELECT\b.*\bFROM\b)',           # SELECT...FROM
    r'(\bUNION\b.*\bSELECT\b)',          # UNION injection
    r'(\bOR\b.*\b1=1\b)',                # OR 1=1
    r'(\bINSERT\b.*\bINTO\b)',           # INSERT
    r'(\bDROP\b\s+\bTABLE\b)',           # DROP TABLE
]
```

If a user submits a search query with SQL-like syntax, it's logged as a SECURITY_VIOLATION:

```python
if InputSanitizer.detect_dangerous_patterns(user_input):
    await log_security_violation(
        user_id=user_id,
        tenant_id=tenant_id,
        ip_address=ip_address,
        violation_type="sql_injection_attempt",
        details={"input": user_input, "endpoint": endpoint}
    )
    raise ValueError("Invalid input")
```

### 4. XSS Prevention

HTML content is escaped:

```python
# Input
user_input = "<script>alert('xss')</script>"

# After sanitization
sanitized = html.escape(user_input)
# Result: "&lt;script&gt;alert('xss')&lt;/script&gt;"

# Stored in database
db.save(sanitized)

# Rendered in HTML
<p>{{ sanitized }}</p>
# Renders as: <p>&lt;script&gt;alert('xss')&lt;/script&gt;</p>
# NOT executed (safe!)
```

### 5. Dangerous Patterns

Additional patterns blocked:

```python
DANGEROUS_PATTERNS = [
    r'<script[^>]*>.*?</script>',         # Script tags
    r'javascript:',                        # javascript: protocol
    r'vbscript:',                          # vbscript: protocol
    r'data:text/html',                     # data: protocol with HTML
    r'<iframe[^>]*>.*?</iframe>',         # iframes
    r'<object[^>]*>.*?</object>',         # objects
    r'<embed[^>]*>.*?</embed>',           # embeds
    r'\.\./',                              # Path traversal (../)
    r'\.\.\\',                             # Path traversal (..\)
]
```

## Security Headers

Etherion includes HTTP headers that instruct browsers to apply additional security:

```http
HTTP/1.1 200 OK
Content-Security-Policy: default-src 'self'; script-src 'self' cdn.example.com; style-src 'self' 'unsafe-inline'
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

### What Each Header Does

- **Content-Security-Policy (CSP)**: Only allow scripts from trusted origins. Blocks inline scripts and eval().
- **Strict-Transport-Security (HSTS)**: Always use HTTPS. Browsers reject non-HTTPS connections.
- **X-Content-Type-Options**: Don't guess MIME types. Prevents polyglot attacks.
- **X-Frame-Options**: Don't allow framing. Prevents clickjacking.
- **X-XSS-Protection**: Enable browser XSS filter (legacy).
- **Referrer-Policy**: Don't leak the referring URL when clicking external links.

## Complete Request Flow with Security

```
Client Request
     │
     ▼
Is it GraphQL/REST?
     │
     ├─→ GraphQL
     │    │
     │    ▼
     │    CSRF Check: Require Authorization header
     │    │
     ├─→ REST (non-auth)
     │    │
     │    ▼
     │    CSRF Check: Require X-CSRF-Token header
     │    │
     └─→ Auth/Webhook/Public
          │
          ▼ (no CSRF)

          ▼
Rate Limit Check (Redis)
     │
     ├─→ Exceeded: 429 Too Many Requests
     │
     └─→ OK
          │
          ▼
Authorization Check (JWT)
     │
     ├─→ Invalid: 401 Unauthorized
     │
     └─→ Valid
          │
          ▼
Input Sanitization
     │
     ├─→ Invalid: 400 Bad Request (log as INPUT_VALIDATION_FAILURE)
     │
     ├─→ SQL-like: 400 + log SECURITY_VIOLATION
     │
     └─→ OK
          │
          ▼
Execute Handler
     │
     ├─→ Success
     │    │
     │    ▼ Log DATA_ACCESS/DATA_MODIFICATION
     │
     └─→ Error
          │
          ▼ Log error

          ▼
Add Security Headers
     │
     ▼
Return Response
```

## Monitoring and Alerting

Monitor these metrics in your dashboard:

1. **Rate Limit Hit Rate**: If > 1% of requests hit rate limits, consider raising limits or investigating abuse
2. **CSRF Failures**: If > 0.1%, investigate client issues (stale tokens, cross-domain requests)
3. **Input Validation Failures**: If > 0.5%, investigate whether clients are sending malformed data or attacks are occurring
4. **Security Violations**: Alert on any SQL/XSS/CSRF attempts

Example alerts:

```bash
# Alert if more than 10 CRITICAL security violations in 10 minutes
alert: high_security_violations
if: count(event_severity == "CRITICAL") > 10 within 10m

# Alert if rate limit violations exceed 5% of traffic
alert: high_ratelimit_ratio
if: count(event == "rate_limit_exceeded") / count(total_events) > 0.05
```

## Best Practices

1. **Use HTTPS Everywhere**: Rate limiting and CSRF are more effective with HTTPS
2. **Keep Tokens Short-Lived**: JWTs should expire in hours, not days
3. **Rotate CSRF Tokens**: Generate new tokens for each session or page load
4. **Monitor Redis**: Rate limiter Redis should have < 1 second latency
5. **Log Attacks**: All CSRF/rate limit/injection attempts should be logged
6. **Alert on Patterns**: If the same IP attacks multiple endpoints, investigate
7. **Whitelist Integrations**: If external services call your APIs, add them to CSRF exempt list with restrictions
