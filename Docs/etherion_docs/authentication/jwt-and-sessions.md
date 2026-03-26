# JWT Internals and Session Management

## What Is a JWT?

A JSON Web Token (JWT) is a compact, URL-safe representation of claims (facts about a user or system). It consists of three parts separated by dots:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzEyMyIsImVtYWlsIjoiYWxpY2VAZXhhbXBsZS5jb20iLCJ0ZW5hbnRfaWQiOjQyLCJleHAiOjE3MDQwNjcyMDB9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
   ^                                       ^                                                      ^
   Header                                  Payload                                              Signature
```

- **Header**: Metadata about the token (algorithm, type)
- **Payload**: The actual claims (user_id, email, etc.)
- **Signature**: Cryptographic proof that the header and payload haven't been tampered with

Etherion uses **HS256** (HMAC-SHA256) for signing, which means we use a shared secret key (stored on the server) to generate the signature.

## Token Anatomy

### Header

```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

Base64-encoded (URL-safe):
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
```

### Payload (Claims)

```json
{
  "sub": "user_google_1234567890",
  "email": "alice@example.com",
  "tenant_id": 42,
  "tenant_subdomain": "alice-workspace",
  "exp": 1704067200,
  "type": "access"
}
```

Base64-encoded:
```
eyJzdWIiOiJ1c2VyX2dvb2dsZV8xMjM0NTY3ODkwIiwiZW1haWwiOiJhbGljZUBleGFtcGxlLmNvbSIsInRlbmFudF9pZCI6NDIsInRlbmFudF9zdWJkb21haW4iOiJhbGljZS13b3Jrc3BhY2UiLCJleHAiOjE3MDQwNjcyMDAsInR5cGUiOiJhY2Nlc3MifQ
```

**Key claims explained:**

- **sub** (Subject): The user's unique identifier. For OAuth, this is the provider's user ID. For password, it's a generated ID prefixed with "pwd_"
- **email**: The user's email address, used for lookups and display
- **tenant_id**: Numeric tenant ID; used to enforce row-level security
- **tenant_subdomain**: The tenant's slug (e.g., "acme-inc"), helps the frontend route to the right domain
- **exp** (Expiration): Unix timestamp when the token expires (typically 30 minutes from issuance)
- **type**: Optional, distinguishes access tokens from refresh tokens or MFA tokens

### Signature

The signature is computed as:

```
HMAC-SHA256(
  base64(header) + "." + base64(payload),
  SECRET_KEY
)
```

The result is Base64-encoded (URL-safe):

```
SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
```

Only the server (with the secret key) can generate a valid signature. If someone modifies the header or payload, the signature becomes invalid.

## Creating a JWT

The `create_access_token` function in `src/auth/jwt.py`:

```python
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token with the provided data and expiration."""
    to_encode = data.copy()

    # Set expiration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Add exp claim
    to_encode.update({"exp": expire})

    # Sign and encode
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
```

The `jwt` library (python-jose) handles the Base64 encoding and HMAC-SHA256 signing internally.

## Decoding and Validating a JWT

When a request arrives with a token, the middleware validates it:

```python
def decode_access_token(token: str) -> TokenData:
    """Decode and verify a JWT access token, returning the token data."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check if this is a refresh token (should not be used for API calls)
        if payload.get("type") == "refresh":
            raise ValueError("Invalid token type")

        # Extract claims
        user_id = payload.get("sub")
        email = payload.get("email")
        tenant_id = payload.get("tenant_id")

        if user_id is None or email is None:
            raise ValueError("Invalid token payload")

        return TokenData(user_id=user_id, email=email, tenant_id=tenant_id)
    except JWTError:
        raise ValueError("Invalid token")
```

The `jwt.decode()` function:

1. **Splits the token** by the dots to extract header, payload, signature
2. **Verifies the signature**: Recomputes HMAC-SHA256 with the secret key and compares it
3. **Checks expiration**: Verifies that `exp` is in the future (rejects if expired)
4. **Returns the payload**: If all checks pass, returns the claims as a dictionary

If any check fails, `jwt.decode()` raises `JWTError`, which we catch and return a 401 Unauthorized.

## Access Token Lifecycle

```
[User Logs In]
      |
      v
[Issue Access Token]
  Expiration: now + 30 minutes
  Stored in: frontend localStorage or cookie
      |
      v
[User Makes API Calls]
  Token included in Authorization header
  Middleware validates on every request
      |
      +---> If valid: Continue processing
      |
      +---> If expired: Return 401 Unauthorized
      |
      +---> If invalid signature: Return 401 Unauthorized
      |
      v
[After 30 minutes]
  Token is expired
  User's next request gets 401 Unauthorized
  Frontend catches 401 → requests new token with refresh token
```

## Refresh Tokens: Getting a New Access Token

Access tokens are short-lived (30 minutes) for security. If a token is stolen, its window of misuse is limited. To allow users to stay logged in without repeatedly entering credentials, we use **refresh tokens**.

When authentication succeeds, we issue a token pair:

```python
def create_token_pair(data: dict, expires_delta: Optional[timedelta] = None) -> Dict[str, str]:
    """Create both access and refresh tokens."""
    access_token = create_access_token(data, expires_delta)
    refresh_token = create_refresh_token(data)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }
```

**Access Token:**
- Duration: 30 minutes
- Usage: Included in every API request
- Visible to: Frontend and possibly network traffic
- If compromised: Window of misuse is 30 minutes

**Refresh Token:**
- Duration: 7 days
- Usage: Only sent to the refresh endpoint, never in regular API calls
- Visible to: Frontend only (ideally in an httpOnly cookie)
- If compromised: 7-day window; typically rotated on use for added security

### Refresh Token Creation

```python
def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token with longer expiration."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
```

Note the `"type": "refresh"` claim. This prevents the refresh token from being mistakenly used as an access token.

### Refreshing an Access Token

When the access token expires, the frontend calls:

```
POST /api/auth/refresh
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

Backend validation:

```python
def decode_refresh_token(token: str) -> TokenData:
    """Decode and verify a JWT refresh token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check if this is actually a refresh token
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")

        user_id = payload.get("sub")
        email = payload.get("email")
        tenant_id = payload.get("tenant_id")

        if user_id is None or email is None:
            raise ValueError("Invalid token payload")

        return TokenData(user_id=user_id, email=email, tenant_id=tenant_id)
    except JWTError:
        raise ValueError("Invalid refresh token")
```

If valid, we issue a new access token (and optionally a new refresh token):

```python
token_data = decode_refresh_token(refresh_token)
new_access_token = create_access_token({
    "sub": token_data.user_id,
    "email": token_data.email,
    "tenant_id": token_data.tenant_id
})
return {"access_token": new_access_token}
```

This allows the user to stay logged in as long as they're actively using the app (refresh tokens can be chained indefinitely as long as each is used before the next one expires).

## Session Management

Sessions are transient records of active users, tracked in Redis for quick lookups. They complement JWTs but serve different purposes:

- **JWTs**: Stateless proof of identity; can be validated offline
- **Sessions**: Stateful tracking; allows admin to revoke or monitor user activity

The `SessionManager` in `src/auth/session_manager.py` handles session lifecycle.

### Creating a Session

```python
async def create_session(self, session_data: SessionCreate) -> SessionInfo:
    """Create a new user session."""

    # Verify user exists
    user = db_session.query(User).filter(User.user_id == session_data.user_id).first()
    if not user:
        raise ValueError(f"User not found")

    # Generate session ID
    session_id = secrets.token_urlsafe(32)  # Cryptographically secure

    # Create session record
    session_info = SessionInfo(
        session_id=session_id,
        user_id=session_data.user_id,
        tenant_id=session_data.tenant_id,
        created_at=datetime.utcnow(),
        last_accessed=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=session_data.expires_in_hours),
        ip_address=session_data.ip_address,
        user_agent=session_data.user_agent,
        is_active=True
    )

    # Store in Redis with TTL
    redis.setex(f"session:{session_id}", session_data.expires_in_hours * 3600, json_dump(session_info))

    # Add to user's session set (for listing active sessions)
    redis.sadd(f"user_sessions:{user_id}", session_id)

    return session_info
```

Sessions are stored in Redis (not the database) because they're temporary and accessed frequently. The TTL (time-to-live) automatically expires old sessions.

### Using a Session

Optionally, a JWT can embed a session_id, allowing the middleware to track which session a request belongs to:

```python
# Middleware extracts session_id from JWT (if present)
session_id = token_data.get("session_id")

# Updates last_accessed timestamp
if session_id:
    await session_manager.update_session_access(session_id)
```

This allows operators to answer questions like "When did Alice last use the app?" and "Which devices is she logged in from?"

### Revoking a Session

An admin can revoke a specific session:

```python
await session_manager.delete_session(session_id)
```

Or delete all of a user's sessions (forcing logout everywhere):

```python
deleted_count = await session_manager.delete_user_sessions(user_id)
```

The next request with a JWT referencing that session will be rejected when the middleware checks the session status.

## Special Token Types

### MFA Token

Used during multi-factor authentication:

```python
def generate_mfa_token(user_id: str, tenant_id: Optional[int] = None) -> str:
    """Generate a temporary MFA verification token."""
    data = {
        "sub": user_id,
        "type": "mfa_verification",
        "tenant_id": tenant_id,
        "nonce": secrets.token_urlsafe(32)  # Prevents reuse
    }
    expire = datetime.utcnow() + timedelta(minutes=5)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)
```

- **Duration**: 5 minutes
- **Usage**: Bridges password verification and MFA code verification
- **Nonce**: Prevents accidental token reuse (cryptographic randomness)

If the user doesn't submit an MFA code within 5 minutes, they must log in again.

### Password Reset Token

Used for password recovery:

```python
def generate_password_reset_token(email: str) -> str:
    """Generate a secure password reset token."""
    data = {
        "email": email,
        "type": "password_reset",
        "nonce": secrets.token_urlsafe(32)
    }
    expire = datetime.utcnow() + timedelta(hours=1)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)
```

- **Duration**: 1 hour
- **Usage**: Embedded in password reset links sent via email
- **Nonce**: Ensures the link is unique; can't accidentally use an old reset link

## Security Considerations

### Secret Key Management

The JWT secret (`JWT_SECRET_KEY`) must be:
- **At least 32 bytes**: Sufficient entropy for HS256 (HMAC-SHA256 produces a 256-bit signature)
- **Generated cryptographically**: Not a weak or guessable string
- **Never in code or git**: Stored in environment variables or a secrets manager
- **Rotated on breach**: If compromised, all active tokens are instantly invalid (because the signature is tied to the old key)

Generation example:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Algorithm Choice: HS256 vs. RS256

Etherion uses **HS256** (symmetric key, HMAC), which means:
- Pro: Simple, no infrastructure needed for key distribution
- Con: Requires keeping the secret safe on all servers that need to verify tokens

An alternative is **RS256** (asymmetric, RSA), where:
- The server has a private key (for signing)
- Multiple servers share a public key (for verification)
- Even if a verification server is compromised, it can't forge tokens

For single-server or containerized deployments, HS256 is fine. For large distributed systems, RS256 is preferred.

### Token Expiration and Refresh

The 30-minute access token expiration balances security and UX:
- **Too short** (e.g., 1 minute): Users must refresh constantly; degrades experience
- **Too long** (e.g., 24 hours): A stolen token is useful for a full day

30 minutes is a common standard.

### Claiming the Token

When you use a JWT library to decode, always:
1. Specify the algorithm(s) you expect: `jwt.decode(..., algorithms=["HS256"])`
2. Validate all required claims: `if payload.get("sub") is None: raise error`
3. Use type claims to prevent misuse: `if payload.get("type") != "access": raise error`

Without these checks, an attacker could:
- Craft a token with a different algorithm (algorithm substitution attack)
- Claim to be a different user (claim manipulation)
- Use a refresh token as an access token (token type confusion)

## Next Steps

- To understand the OAuth flow that generates these tokens, see `oauth-flow.md`
- To understand password authentication, see `local-auth.md`
- To understand how middleware validates tokens, see `middleware-pipeline.md`
