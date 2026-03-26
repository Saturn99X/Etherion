# Local Authentication: Email + Password

## Why Support Local Auth?

While OAuth is the preferred path for most users, local authentication (email + password) serves important use cases:

- **Restricted Networks**: Enterprise environments that block OAuth providers (firewalls, proxies)
- **Offline Signup**: Users without existing Google/GitHub/Microsoft accounts
- **Custom Integration**: API clients or scripts that need username/password login
- **User Choice**: Some users simply prefer passwords to delegated auth

Etherion uses **PBKDF2-SHA256** for password hashing with 200,000 iterations—a standard that's resistant to brute force and GPU attacks.

## Password Hashing: PBKDF2-SHA256

### Why Not Bcrypt or Argon2?

PBKDF2 is not the latest recommendation, but it's:
- **Universally available**: Standard library in Python (`hashlib.pbkdf2_hmac`)
- **Predictable performance**: Iterations can be tuned for any hardware
- **Battle-tested**: Used by Django, many enterprises, and NIST-approved (SP 800-132)

Bcrypt or Argon2 would be fine too, but PBKDF2 requires no external dependencies.

### How It Works

The `_hash_password` function in `src/auth/service.py`:

```python
def _hash_password(password: str, iterations: int = 200_000) -> str:
    """Return a PBKDF2-SHA256 hash string: pbkdf2_sha256$iterations$salt_b64$hash_b64"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
```

For each password:

1. **Generate Random Salt**: 16 bytes of cryptographic randomness (128 bits)
2. **Derive Key**: Apply PBKDF2-HMAC-SHA256 with 200,000 iterations
   - Takes the password as input
   - Uses the random salt
   - Produces a 32-byte (256-bit) hash
3. **Encode for Storage**: Returns a formatted string: `pbkdf2_sha256$200000$<salt_b64>$<hash_b64>`
   - Algorithm prefix: Identifies this as PBKDF2-SHA256 (allows future migration)
   - Iterations: Stored so we can increase it later without re-hashing all passwords
   - Salt: Base64-encoded salt
   - Derived Key: Base64-encoded hash

Every password has a unique random salt, so the same password hashes differently each time.

### Verification: Constant-Time Comparison

When a user logs in, `_verify_password` does:

```python
def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_str, salt_b64, hash_b64 = stored.split('$', 3)
        if algo != 'pbkdf2_sha256':
            return False
        iterations = int(iters_str)
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(hash_b64.encode())
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(dk, expected)  # <-- Constant-time comparison
    except Exception:
        return False
```

1. **Parse stored hash**: Extract algorithm, iterations, salt, and expected hash
2. **Re-derive key**: Apply PBKDF2 with the extracted salt and iterations to the submitted password
3. **Compare**: Use `hmac.compare_digest` (constant-time comparison) to check if derived == expected

The **constant-time comparison** prevents timing attacks. If we used `==`, an attacker could guess one byte at a time and detect when they got it right by measuring response time. `hmac.compare_digest` always takes the same time regardless of where bytes differ.

## Password Signup

When a user signs up with email + password:

```
POST /graphql
{
  "operationName": "PasswordSignup",
  "variables": {
    "email": "alice@example.com",
    "password": "SecureP@ssw0rd!",
    "name": "Alice Smith",
    "subdomain": "alice-workspace"  # Optional; auto-generated if omitted
  }
}
```

The backend's `password_signup` function (in `src/auth/service.py`):

1. **Validate Email**: Check if the email is already registered
   ```python
   existing = get_user_by_email(session, email)
   if existing:
       raise HTTPException(status_code=400, detail="Email already registered")
   ```

2. **Optional: VPN/IP Checks** (feature-flagged):
   ```python
   if BLOCK_VPN_SIGNUP:
       vpn_res = await is_vpn_or_proxy(client_ip)
       if vpn_res.is_risky:
           raise HTTPException(status_code=403, detail="VPN signup blocked")
   ```

3. **Validate Subdomain**: If provided, check it's alphanumeric and not taken
   ```python
   is_valid, error = dns_manager.validate_subdomain(subdomain)
   if not is_valid:
       raise HTTPException(status_code=400, detail=f"Invalid subdomain: {error}")

   existing = session.exec(select(Tenant).where(Tenant.subdomain == subdomain)).first()
   if existing:
       raise HTTPException(status_code=400, detail="Subdomain already taken")
   ```

4. **Create Tenant**: If multi-tenant mode is enabled, auto-create a workspace
   ```python
   tenant = Tenant(
       tenant_id=Tenant.generate_unique_id(),
       subdomain=subdomain,
       name=f"{name}'s Workspace",
       admin_email=email
   )
   session.add(tenant)
   session.commit()
   tenant_id = tenant.id
   ```

5. **Hash Password**: Use PBKDF2-SHA256 with 200,000 iterations
   ```python
   pwd_hash = _hash_password(password)
   ```

6. **Create User**: Store in database with hashed password
   ```python
   user = User(
       user_id=f"pwd_{secrets.token_hex(8)}",  # Prefix to distinguish from OAuth IDs
       email=email,
       name=name,
       provider="password",
       password_hash=pwd_hash,
       tenant_id=tenant_id
   )
   session.add(user)
   session.commit()
   ```

7. **Issue JWT**: Generate access token
   ```python
   access_token = create_access_token(
       data={
           "sub": user.user_id,
           "email": user.email,
           "tenant_id": tenant_id,
       },
       expires_delta=timedelta(minutes=30)
   )
   return {"access_token": access_token, "user": {...}}
   ```

8. **Grant Initial Credits**: Issue starter credits (if the credit system is enabled)
   ```python
   await credit_mgr.allocate(user_id=user.id, amount=100, tenant_id=str(tenant_id))
   ```

The entire process is wrapped in a **15-second timeout** to prevent indefinite hangs if the database is slow.

## Password Login

When an existing user logs in:

```
POST /graphql
{
  "operationName": "PasswordLogin",
  "variables": {
    "email": "alice@example.com",
    "password": "SecureP@ssw0rd!"
  }
}
```

The `password_login` function:

1. **Look Up User**: Query by email
   ```python
   user = get_user_by_email(session, email)
   if not user or not user.password_hash:
       raise HTTPException(status_code=401, detail="Invalid credentials")
   ```

2. **Verify Password**: Use constant-time comparison
   ```python
   if not _verify_password(password, user.password_hash):
       raise HTTPException(status_code=401, detail="Invalid credentials")
   ```

3. **Update last_login**: Track when the user last logged in
   ```python
   user.last_login = datetime.utcnow()
   session.add(user)
   session.commit()
   ```

4. **Issue JWT**: Same as signup
   ```python
   access_token = create_access_token(
       data={
           "sub": user.user_id,
           "email": user.email,
           "tenant_id": user.tenant_id,
       }
   )
   ```

Note: Errors are intentionally generic ("Invalid credentials" vs. "Email not found" vs. "Password wrong"). This prevents attackers from enumerating registered emails.

## Password Reset Flow

Users who forget their password can request a reset:

```
POST /graphql
{
  "operationName": "RequestPasswordReset",
  "variables": {
    "email": "alice@example.com"
  }
}
```

Backend flow:

1. **Look Up User**:
   ```python
   user = get_user_by_email(session, email)
   if not user:
       # Return success anyway (don't leak email existence)
       return {"status": "ok"}
   ```

2. **Generate Reset Token**: One-time use, 1-hour expiration
   ```python
   reset_token = generate_password_reset_token(user.email)
   # reset_token is a JWT with:
   # {
   #   "email": "alice@example.com",
   #   "type": "password_reset",
   #   "nonce": <random>,
   #   "exp": <1 hour from now>
   # }
   ```

3. **Send Email**: Backend sends a link to the user
   ```
   https://app.etherion.ai/reset-password?token=<reset_token>
   ```
   (Email sending is handled by a separate service, not shown here)

4. **User Clicks Link**: Frontend extracts the token from the URL query param

5. **User Submits New Password**:
   ```
   POST /graphql
   {
     "operationName": "ResetPassword",
     "variables": {
       "token": "<reset_token>",
       "newPassword": "NewP@ssw0rd123"
     }
   }
   ```

6. **Verify Reset Token**: Check signature and type
   ```python
   email = verify_password_reset_token(token)
   if not email:
       raise HTTPException(status_code=400, detail="Invalid or expired token")
   ```

7. **Look Up User and Hash New Password**:
   ```python
   user = get_user_by_email(session, email)
   user.password_hash = _hash_password(newPassword)
   session.add(user)
   session.commit()
   ```

8. **Return Success**: User can now log in with the new password

The nonce in the reset token prevents replay attacks: even if someone intercepts a reset link, they can only use it once because the nonce ensures uniqueness.

## MFA (Multi-Factor Authentication)

For accounts with MFA enabled, the login flow changes slightly.

After password verification succeeds:

1. **Generate MFA Token**: Short-lived (5 minutes), bridges the gap between password and MFA code
   ```python
   mfa_token = generate_mfa_token(user.user_id, tenant_id=user.tenant_id)
   return {"mfa_required": True, "mfa_token": mfa_token}
   ```

2. **User Enters TOTP Code**: From their authenticator app (Google Authenticator, Authy, etc.)
   ```
   POST /graphql
   {
     "operationName": "VerifyMFA",
     "variables": {
       "mfa_token": "<mfa_token>",
       "code": "123456"
     }
   }
   ```

3. **Verify MFA Token and Code**:
   ```python
   token_data = verify_mfa_token(mfa_token)
   mfa_config = await mfa_manager.get_mfa_config(token_data.user_id)

   totp = pyotp.TOTP(mfa_config.totp_secret)
   if totp.verify(code, valid_window=1):
       # Code is correct; issue full JWT
       access_token = create_access_token(...)
   else:
       raise HTTPException(status_code=401, detail="Invalid code")
   ```

The MFA token is cryptographically signed (like access tokens) but typed as "mfa_verification" so it can't be used for API calls. Only after successful MFA verification do we issue a full access token.

MFA setup is handled separately:

1. **User Requests Setup**:
   ```
   POST /graphql
   {
     "operationName": "SetupMFA",
     "variables": { "type": "totp" }
   }
   ```

2. **Generate TOTP Secret and QR Code**:
   ```python
   mfa_config = await mfa_manager.setup_totp(user.user_id)
   return {
       "secret": "JBSWY3DPEHPK3PXP",
       "qr_code": "data:image/png;base64,iVBORw0K...",
       "backup_codes": ["ABC123XYZ", "DEF456UVW", ...]
   }
   ```

3. **User Scans QR Code**: With their authenticator app

4. **User Submits Verification Code**:
   ```
   POST /graphql
   {
     "operationName": "VerifyMFASetup",
     "variables": {
       "code": "123456"
     }
   }
   ```

5. **Confirm MFA**: If the code is correct, the secret is permanently stored in Redis
   ```python
   if await mfa_manager.verify_totp_setup(user.user_id, code):
       return {"status": "mfa_enabled"}
   ```

From then on, every login requires both password and TOTP code.

## Security Best Practices

1. **Never Log Passwords**: Never write passwords to logs, even hashed ones
2. **HTTPS Only**: Passwords must be transmitted over TLS/HTTPS
3. **Rate Limit Login**: Limit password login attempts to prevent brute force (per IP or per email)
4. **Password Policy**: Optionally enforce minimum length, complexity, etc. (not currently enforced, but can be added)
5. **Secure Password Reset**: Tokens are one-time, short-lived, and include a nonce
6. **Session Timeout**: Access tokens expire quickly (30 minutes); long sessions require refresh tokens
7. **Audit Logging**: Log successful and failed login attempts for security monitoring

## Next Steps

- To understand JWT refresh tokens and session management, see `jwt-and-sessions.md`
- To understand the OAuth path, see `oauth-flow.md`
- To understand the full middleware pipeline, see `middleware-pipeline.md`
