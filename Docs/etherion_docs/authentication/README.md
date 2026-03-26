# Authentication in Etherion AI

## Overview

Etherion AI implements a dual-path authentication system that serves both OAuth-based (social login) and traditional password-based access. This design lets users choose their preferred entry point while maintaining a unified token and authorization model underneath.

The system is built on **JWTs** (JSON Web Tokens) for stateless authentication and uses **multi-tenant isolation** with row-level security at the database layer. Every authenticated request carries both user identity and tenant context, enabling the platform to enforce strict data boundaries between workspaces.

## The Two Paths: OAuth and Local Auth

### Path 1: OAuth (Google, GitHub, Microsoft)

OAuth is the preferred entry point for most users. It offloads password management to trusted identity providers and eliminates the need to store sensitive credentials.

When a user clicks "Sign in with Google," here's what happens:

1. **Authorization Request**: The frontend redirects to Google's authorization endpoint with a scoped request (email, profile)
2. **User Grants Permission**: Google displays a consent screen; the user authorizes
3. **Callback with Code**: Google redirects back to our callback endpoint with an authorization code (never the access token directly)
4. **Code Exchange**: Our backend exchanges the code for a token with Google's token endpoint
5. **User Lookup**: We fetch the user's email and name from Google's userinfo endpoint
6. **Provision or Update**: We check if the user exists; if not, we auto-provision them (creating a tenant if needed)
7. **JWT Issuance**: We generate our own JWT containing user_id, email, tenant_id, and an expiration
8. **Client Receives Token**: The frontend stores the JWT and uses it for subsequent API calls

All OAuth logic lives in `src/auth/oauth.py` and is orchestrated by the `handle_oauth_callback` function in `src/auth/service.py`.

### Path 2: Local Authentication (Email + Password)

For users who prefer traditional login or operate in restricted network environments, we support email/password authentication with PBKDF2-SHA256 hashing.

Local login flow:

1. **User Submits Credentials**: Frontend sends email and password to `/auth/password-login`
2. **Credential Validation**: We fetch the user by email, then verify the password hash using constant-time comparison
3. **Session Update**: We update the user's `last_login` timestamp
4. **JWT Issuance**: We generate a JWT identical to the OAuth path (same structure, same expiration)
5. **Client Stores Token**: The frontend receives the same bearer token format

Password hashing is handled by `_hash_password` and `_verify_password` in `src/auth/service.py`, which use PBKDF2 with 200,000 iterations for strong resistance against brute force.

## JWT Structure: What's Inside the Token

When authentication succeeds, the system issues a JWT with this payload:

```json
{
  "sub": "user_id_from_provider",
  "email": "user@example.com",
  "tenant_id": 42,
  "tenant_subdomain": "example-workspace",
  "exp": 1704067200
}
```

- **sub** (subject): The unique user identifier (either from OAuth provider or generated for password auth)
- **email**: The user's email, used for lookups and display
- **tenant_id**: The numeric ID of the user's tenant (workspace), critical for multi-tenant isolation
- **tenant_subdomain**: The subdomain slug (e.g., "acme-inc"), used by the frontend to route requests
- **exp** (expiration): Unix timestamp when the token becomes invalid (typically 30 minutes from issuance)

The token is signed with `HS256` (HMAC-SHA256) using a secret key stored in the environment (`JWT_SECRET_KEY`). The signature ensures that nobody can tamper with the claims without invalidating the token.

## How the Middleware Validates Tokens

When a client calls a protected endpoint, the middleware does the following:

1. **Extract the Token**: Looks for `Authorization: Bearer <token>` in the request header, or falls back to `access_token` cookie
2. **Decode and Verify Signature**: Uses the secret key to validate the token signature hasn't been modified
3. **Check Expiration**: Compares the `exp` claim against the current time; rejected if expired
4. **Validate Token Type**: Ensures this is an access token, not a refresh token or password reset token (each has a `type` claim)
5. **Look Up User**: Queries the database for the user record using the `sub` claim
6. **Verify User Status**: Checks that the user's `is_active` flag is true (allows admin to disable accounts)
7. **Set Request Context**: Attaches the decoded user, tenant, and token data to `request.state` for downstream handlers
8. **Tenant Context**: Sets the PostgreSQL session variable `app.tenant_id` to enforce row-level security

Token validation is performed by `AuthMiddleware` in `src/auth/middleware.py`, which processes every request except a whitelist of public paths (login, signup, OAuth callbacks, health checks).

## Token Types and Special Use Cases

The system uses typed tokens to prevent accidental misuse:

- **Access Token**: Short-lived (30 minutes), used for API calls. Decoded by `decode_access_token()`
- **Refresh Token**: Long-lived (7 days), used to obtain a new access token without re-authenticating. Has `"type": "refresh"`
- **MFA Token**: Very short-lived (5 minutes), issued after password entry but before MFA code verification. Bridges the login flow
- **Password Reset Token**: One-time use (1 hour), issued by the password reset endpoint, contains a nonce to prevent reuse

Each token type is validated by a dedicated decoder that checks the `type` claim.

## Multi-Tenant Isolation

Every tenant is a separate workspace with its own data, users, and configuration. The JWT's `tenant_id` claim ensures that when a user makes a request, the database's row-level security policies automatically filter results to only that tenant's data.

Here's the enforcement chain:

1. **JWT contains tenant_id**: User's primary workspace ID
2. **Middleware sets PostgreSQL GUC**: `SET app.tenant_id = <tenant_id>` on the database connection
3. **RLS Policies enforce isolation**: PostgreSQL policies on every table check `current_setting('app.tenant_id')` and filter rows
4. **Queries return scoped results**: Any attempt to access another tenant's data is blocked at the database layer

If a user belongs to multiple tenants, they can switch contexts by obtaining a new JWT for a different tenant (usually by accepting an invite and logging in again). Each JWT is bound to a single tenant.

## Security Assumptions

- **JWT Secret is Strong**: The `JWT_SECRET_KEY` is at least 32 bytes of cryptographic randomness
- **HTTPS in Production**: Tokens are transmitted in clear text in the `Authorization` header, so HTTPS is mandatory
- **Secret Key Never Shared**: The key is stored securely (not in code, not in git, managed by ops)
- **Token Expiration Enforced**: Tokens expire relatively quickly (30 minutes); a lost token is only useful briefly
- **Database RLS Policies Work**: The PostgreSQL RLS policies are correctly written and enabled on all sensitive tables

## What Happens on First Login

For new users coming via OAuth:

1. System checks if a user with that provider ID exists
2. If not, auto-provisions a new user record
3. Auto-creates a tenant (workspace) for them if multi-tenant mode is enabled
4. Generates a unique subdomain for the tenant (e.g., "alice-42d8e")
5. Issues a JWT and returns the tenant subdomain to the frontend
6. Frontend redirects to the tenant's subdomain (e.g., `alice-42d8e.app.etherion.ai`)

For new users via password signup:

1. User provides email, password, and optionally a desired subdomain
2. System validates the subdomain is available and alphanumeric
3. Creates a new tenant
4. Hashes the password with PBKDF2
5. Creates the user record
6. Issues a JWT and returns the subdomain

This auto-provisioning makes onboarding seamless and eliminates the need for admin involvement.

## Next Steps

To understand the complete flow:

- See `oauth-flow.md` for a detailed OAuth walkthrough with ASCII diagrams
- See `local-auth.md` for password hashing details and password reset flow
- See `jwt-and-sessions.md` for token internals and session management
- See `middleware-pipeline.md` for the full request processing pipeline and middleware ordering
