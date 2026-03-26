# OAuth Flow: Step by Step

## Why OAuth?

OAuth delegates authentication to trusted third-party providers (Google, GitHub, Microsoft). Instead of storing passwords ourselves, we leverage the user's existing identity. This reduces our security surface, improves user experience (no password to remember), and provides verified email addresses and profile info out of the box.

Etherion supports Google, GitHub, and Microsoft OAuth. (Apple OAuth is intentionally disabled per Phase 8 restrictions.)

## The OAuth 2.0 Authorization Code Flow

Etherion uses the standard OAuth 2.0 authorization code flow, which is designed specifically for web applications.

```
User                Frontend              Etherion Backend      OAuth Provider
  |                    |                       |                    |
  |--[Click Sign In]-->|                       |                    |
  |                    |--[Redirect to auth]-->|                    |
  |                    |                       |--[Redirect]------->|
  |                    |                       |                    |
  |                    |<-----[Consent Screen]---(user sees)--------->|
  |                    |                                             |
  |--[Authorize]-----------------------------------[Grant Permission]|
  |                    |                       |                    |
  |                    |<--[Redirect + Code]---|<--[Code]-----------|
  |                    |                       |                    |
  |                    |                   (Code Exchange)          |
  |                    |                   (Behind the scenes)      |
  |                    |                       |--[Code + Secret]-->|
  |                    |                       |<--[Access Token]---|
  |                    |                       |                    |
  |                    |<--[JWT + Redirect]----|                    |
  |                    |                       |                    |
  |--[Stored JWT]----->|                       |                    |
```

## Step 1: Initiating the OAuth Flow

When a user clicks "Sign in with Google," the frontend redirects to Google's authorization endpoint:

```
https://accounts.google.com/o/oauth2/v2/auth
  ?client_id=YOUR_CLIENT_ID.apps.googleusercontent.com
  &redirect_uri=https://api.etherion.ai/api/auth/callback/google
  &response_type=code
  &scope=openid%20email%20profile
  &state=<random-string>
```

Key parameters:

- **client_id**: Identifies our application to Google; issued when we register on Google Console
- **redirect_uri**: Where Google will send the user back after they authorize. Must match exactly what we registered
- **response_type=code**: Tells Google we want the authorization code flow (not implicit or others)
- **scope**: Requests access to openid, email, and profile info
- **state**: Random string that prevents CSRF attacks; we verify it when the callback arrives

The frontend generates a random state, stores it in session storage, and includes it in the redirect.

## Step 2: User Authorizes on Provider

Google displays a consent screen:

```
"Etherion AI wants to access:
  - Your email address
  - Your name and picture"
```

The user clicks "Allow" or "Deny". If they allow, Google redirects back to our callback endpoint with an authorization code.

## Step 3: Callback Endpoint Receives the Code

The browser is redirected to:

```
https://api.etherion.ai/api/auth/callback/google
  ?code=4/0AY0e-g7...
  &state=<same-random-string>
```

The callback handler (in the frontend or backend, depending on architecture) receives the code and state.

In Etherion, this is typically handled by the frontend's OAuth routing logic, which immediately calls the backend's callback endpoint:

```
POST /graphql
{
  "operationName": "GoogleLogin",
  "variables": {
    "code": "4/0AY0e-g7...",
    "redirectUri": "https://app.etherion.ai/login/callback"
  }
}
```

The backend's `handle_oauth_callback` function (in `src/auth/service.py`) processes this.

## Step 4: Code Exchange (Server to Server)

The backend now exchanges the authorization code for a real access token. This happens entirely server-to-server; the client is not involved.

Code from `exchange_google_code_for_token` in `src/auth/oauth.py`:

```python
async with AsyncOAuth2Client(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    redirect_uri="https://api.etherion.ai/api/auth/callback/google"
) as client:
    token = await client.fetch_token(
        "https://oauth2.googleapis.com/token",
        code=authorization_code,
        redirect_uri="https://api.etherion.ai/api/auth/callback/google"
    )
    return token  # Contains: access_token, id_token, refresh_token, etc.
```

Google validates:
- The authorization code hasn't been used before
- The redirect_uri matches the one from step 1
- Our client_secret is correct
- The code hasn't expired (typically 10 minutes)

If all checks pass, Google returns an access token.

## Step 5: Fetch User Profile

With the access token in hand, we query Google's userinfo endpoint to get the user's email, name, and picture:

```python
async def get_google_user_info(token: Dict[str, Any]) -> Dict[str, Any]:
    async with AsyncClient() as http_client:
        response = await http_client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token['access_token']}"}
        )
        return response.json()
```

Google returns:

```json
{
  "id": "1234567890",
  "email": "alice@example.com",
  "name": "Alice Smith",
  "picture": "https://lh3.googleusercontent.com/a/..."
}
```

We now have the user's identity information, verified by Google.

## Step 6: Provision or Update User

In `handle_oauth_callback`, after fetching user info:

```python
# Check if user already exists by provider ID
existing_user = get_user_by_provider_id(session, user_auth.user_id)

if existing_user:
    # Update last_login and any changed profile info
    existing_user.last_login = datetime.utcnow()
    session.add(existing_user)
    session.commit()
    tenant_id = existing_user.tenant_id
else:
    # New user: auto-create tenant if multi-tenant enabled
    if ENABLE_MULTI_TENANT:
        # Generate unique subdomain (e.g., "alice-s42d8")
        subdomain = generate_unique_subdomain(user_auth.name)

        # Create tenant
        tenant = Tenant(
            subdomain=subdomain,
            name=f"{user_auth.name}'s Workspace"
        )
        session.add(tenant)
        session.flush()  # Get the ID without committing yet
        tenant_id = tenant.id

    # Create user
    user = User(
        user_id=user_auth.user_id,  # e.g., "1234567890" from Google
        email=user_auth.email,
        name=user_auth.name,
        provider="google",
        tenant_id=tenant_id
    )
    session.add(user)
    session.commit()
```

This is the first-login magic: if the user is new, we automatically create a workspace for them. No admin intervention needed.

## Step 7: Issue JWT

Now we generate our own JWT token:

```python
access_token = create_access_token(
    data={
        "sub": user.user_id,              # "1234567890"
        "email": user.email,              # "alice@example.com"
        "tenant_id": tenant_id,           # 42
        "tenant_subdomain": subdomain,    # "alice-s42d8"
    },
    expires_delta=timedelta(minutes=30)
)
```

The JWT is signed with our secret key and becomes the session token for all future API calls. It's stateless (no database lookup needed on every request) but cryptographically signed so we can trust it.

## Step 8: Return Token to Client

The backend returns the JWT to the frontend:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "user_id": "1234567890",
    "email": "alice@example.com",
    "name": "Alice Smith",
    "tenant_subdomain": "alice-s42d8"
  }
}
```

## Step 9: Frontend Stores and Uses Token

The frontend:

1. Stores the JWT in localStorage or a secure cookie
2. Redirects to the tenant subdomain: `https://alice-s42d8.app.etherion.ai`
3. Includes the JWT in the `Authorization: Bearer` header on all subsequent requests

Subsequent API calls now include the token:

```
GET /api/queries
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

## GitHub and Microsoft Flows

GitHub and Microsoft follow the same overall pattern but with provider-specific details:

### GitHub

- **Authorization URL**: `https://github.com/login/oauth/authorize`
- **Token URL**: `https://github.com/login/oauth/access_token`
- **User Info URL**: `https://api.github.com/user`
- **Scopes**: `read:user user:email`
- **Challenge**: GitHub's userinfo endpoint doesn't always return email; we fall back to `/user/emails` to find the primary verified email

### Microsoft

- **Authorization URL**: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize`
- **Token URL**: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
- **User Info URL**: `https://graph.microsoft.com/oidc/userinfo`
- **Scopes**: `openid profile email offline_access`
- **Challenge**: May need to handle both Entra ID (corporate) and consumer Microsoft accounts

All provider-specific code is isolated in `src/auth/oauth.py` with dedicated functions: `exchange_google_code_for_token`, `exchange_github_code_for_token`, etc.

## Error Handling: What Can Go Wrong

1. **Mismatched redirect_uri**: Frontend and backend have different callback URLs → "redirect_uri mismatch" error
2. **Expired or reused code**: Code was issued >10 minutes ago or already used → "invalid_grant" error
3. **Invalid client credentials**: Client ID or secret is wrong → "invalid_client" error
4. **VPN or Proxy Detected**: If `BLOCK_VPN_SIGNUP` is enabled and the user's IP is flagged as VPN → signup rejected
5. **Email Already Registered**: User with this email exists but via different provider (rare) → conflict error

Error messages are logged and returned to the client with HTTP 4xx or 5xx status codes. The user can retry; nothing is persisted until the JWT is issued.

## Tenant-Scoped OAuth Overrides

For multi-tenant platforms, each tenant can configure their own OAuth app credentials (Google, GitHub, etc.) instead of using the global app credentials. This is useful when:

- A large enterprise wants to use their own Google Workspace app
- A SaaS customer wants to white-label authentication

The override is resolved in `handle_oauth_callback`:

```python
# Try to get tenant-specific OAuth credentials from secrets manager
if tenant_id:
    tsm = TenantSecretsManager()
    creds = await tsm.get_secret(str(tenant_id), "google", "oauth_credentials")
    if creds:
        client_id_override = creds.get("client_id")
        client_secret_override = creds.get("client_secret")

# Use override if available, else fall back to env-configured app
token_data = await exchange_google_code_for_token(
    code,
    client_id=client_id_override,
    client_secret=client_secret_override
)
```

This allows the platform to support bring-your-own-OAuth scenarios while keeping the default app for single-tenant deployments.

## Next Steps

- To understand JWT internals and token refresh, see `jwt-and-sessions.md`
- To understand local password authentication, see `local-auth.md`
- To understand the middleware pipeline, see `middleware-pipeline.md`
