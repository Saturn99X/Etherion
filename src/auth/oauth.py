import os
from typing import Dict, Any, Optional
from authlib.integrations.starlette_client import OAuth
from authlib.integrations.httpx_client import AsyncOAuth2Client
from httpx import AsyncClient
import json


# OAuth Configuration
AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "http://localhost:8000")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common")

# Slack OAuth (optional)
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET", "")



def _provider_redirect_uri(provider: str) -> str:
    base = AUTH_BASE_URL.rstrip("/")
    return f"{base}/api/auth/callback/{provider}"


class OAuthProvider:
    def __init__(self):
        self.oauth = OAuth()
        # Configure Google OAuth
        if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
            self.oauth.register(
                name='google',
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET,
                server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
                client_kwargs={
                    'scope': 'openid email profile'
                }
            )
        # Configure GitHub OAuth
        if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET:
            self.oauth.register(
                name='github',
                client_id=GITHUB_CLIENT_ID,
                client_secret=GITHUB_CLIENT_SECRET,
                authorize_url='https://github.com/login/oauth/authorize',
                access_token_url='https://github.com/login/oauth/access_token',
                api_base_url='https://api.github.com/',
                client_kwargs={
                    'scope': 'read:user user:email'
                }
            )
        # Configure Microsoft OAuth (OIDC v2.0 common)
        if MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET:
            tenant = MICROSOFT_TENANT_ID or 'common'
            self.oauth.register(
                name='microsoft',
                client_id=MICROSOFT_CLIENT_ID,
                client_secret=MICROSOFT_CLIENT_SECRET,
                authorize_url=f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize',
                access_token_url=f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token',
                api_base_url='https://graph.microsoft.com/',
                client_kwargs={
                    'scope': 'openid profile email offline_access'
                }
            )
        
        # Apple OAuth intentionally disabled (Phase 8 restriction)


oauth_provider = OAuthProvider()


async def exchange_google_code_for_token(
    code: str,
    redirect_uri: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """Exchange Google OAuth authorization code for access token with validation.

    The redirect_uri must match the one used in the authorization step. If not provided,
    fallback to the server callback endpoint.
    
    Raises:
        ValueError: If OAuth credentials are not configured or code is invalid
    """
    # Resolve credentials
    resolved_client_id = (client_id or GOOGLE_CLIENT_ID or "").strip()
    resolved_client_secret = (client_secret or GOOGLE_CLIENT_SECRET or "").strip()
    
    # Pre-flight validation
    if not resolved_client_id:
        raise ValueError("Google OAuth is not configured: GOOGLE_CLIENT_ID missing")
    if not resolved_client_secret:
        raise ValueError("Google OAuth is not configured: GOOGLE_CLIENT_SECRET missing")
    if not code or not code.strip():
        raise ValueError("Authorization code is required")
    
    async with AsyncOAuth2Client(
        client_id=resolved_client_id,
        client_secret=resolved_client_secret,
        redirect_uri=redirect_uri or _provider_redirect_uri('google')
    ) as client:
        token_url = "https://oauth2.googleapis.com/token"
        try:
            token = await client.fetch_token(
                token_url,
                code=code.strip(),
                redirect_uri=redirect_uri or _provider_redirect_uri('google')
            )
            return token
        except Exception as e:
            # Enhanced error message for debugging
            error_msg = str(e).lower()
            if "invalid_client" in error_msg:
                raise ValueError("Google OAuth client credentials are invalid. Check GOOGLE_CLIENT_ID configuration.")
            elif "invalid_grant" in error_msg or "code" in error_msg:
                raise ValueError("Authorization code is invalid or expired. Please try logging in again.")
            elif "redirect_uri" in error_msg:
                raise ValueError(f"OAuth redirect URI mismatch. Expected: {redirect_uri or _provider_redirect_uri('google')}")
            else:
                raise ValueError(f"Google OAuth token exchange failed: {str(e)}")


async def get_google_user_info(token: Dict[str, Any]) -> Dict[str, Any]:
    """Get user information from Google using access token."""
    async with AsyncClient() as http_client:
        response = await http_client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token['access_token']}"}
        )
        response.raise_for_status()
        return response.json()


async def exchange_github_code_for_token(
    code: str,
    redirect_uri: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """Exchange GitHub OAuth authorization code for access token with validation.
    
    Raises:
        ValueError: If OAuth credentials are not configured or code is invalid
    """
    # Resolve credentials
    resolved_client_id = (client_id or GITHUB_CLIENT_ID or "").strip()
    resolved_client_secret = (client_secret or GITHUB_CLIENT_SECRET or "").strip()
    
    # Pre-flight validation
    if not resolved_client_id:
        raise ValueError("GitHub OAuth is not configured: GITHUB_CLIENT_ID missing")
    if not resolved_client_secret:
        raise ValueError("GitHub OAuth is not configured: GITHUB_CLIENT_SECRET missing")
    if not code or not code.strip():
        raise ValueError("Authorization code is required")
    
    async with AsyncOAuth2Client(
        client_id=resolved_client_id,
        client_secret=resolved_client_secret,
        redirect_uri=redirect_uri or _provider_redirect_uri('github')
    ) as client:
        token_url = 'https://github.com/login/oauth/access_token'
        try:
            token = await client.fetch_token(
                token_url,
                code=code.strip(),
                include_client_id=True,
                include_client_secret=True,
                headers={'Accept': 'application/json'},
                redirect_uri=redirect_uri or _provider_redirect_uri('github')
            )
            return token
        except Exception as e:
            error_msg = str(e).lower()
            if "bad_verification_code" in error_msg:
                raise ValueError("Authorization code is invalid or expired. Please try logging in again.")
            elif "redirect_uri" in error_msg:
                raise ValueError(f"OAuth redirect URI mismatch. Expected: {redirect_uri or _provider_redirect_uri('github')}")
            else:
                raise ValueError(f"GitHub OAuth token exchange failed: {str(e)}")


async def get_github_user_info(token: Dict[str, Any]) -> Dict[str, Any]:
    """Get user information from GitHub using access token."""
    async with AsyncClient() as http_client:
        user_resp = await http_client.get(
            'https://api.github.com/user',
            headers={"Authorization": f"Bearer {token['access_token']}", "Accept": "application/vnd.github+json"}
        )
        user_resp.raise_for_status()
        user = user_resp.json()

        email = user.get('email')
        if not email:
            emails_resp = await http_client.get(
                'https://api.github.com/user/emails',
                headers={"Authorization": f"Bearer {token['access_token']}", "Accept": "application/vnd.github+json"}
            )
            if emails_resp.status_code == 200:
                emails = emails_resp.json()
                primary = next((e['email'] for e in emails if e.get('primary') and e.get('verified')), None)
                email = primary or (emails[0]['email'] if emails else None)

        return {
            "id": str(user.get('id')),
            "email": email,
            "name": user.get('name') or user.get('login'),
            "picture": user.get('avatar_url')
        }


async def exchange_microsoft_code_for_token(
    code: str,
    redirect_uri: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """Exchange Microsoft OAuth authorization code for access token with validation.
    
    Raises:
        ValueError: If OAuth credentials are not configured or code is invalid
    """
    # Resolve credentials
    resolved_client_id = (client_id or MICROSOFT_CLIENT_ID or "").strip()
    resolved_client_secret = (client_secret or MICROSOFT_CLIENT_SECRET or "").strip()
    
    # Pre-flight validation
    if not resolved_client_id:
        raise ValueError("Microsoft OAuth is not configured: MICROSOFT_CLIENT_ID missing")
    if not resolved_client_secret:
        raise ValueError("Microsoft OAuth is not configured: MICROSOFT_CLIENT_SECRET missing")
    if not code or not code.strip():
        raise ValueError("Authorization code is required")
    
    tenant = MICROSOFT_TENANT_ID or 'common'
    async with AsyncOAuth2Client(
        client_id=resolved_client_id,
        client_secret=resolved_client_secret,
        redirect_uri=redirect_uri or _provider_redirect_uri('microsoft')
    ) as client:
        token_url = f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token'
        try:
            token = await client.fetch_token(
                token_url,
                code=code.strip(),
                redirect_uri=redirect_uri or _provider_redirect_uri('microsoft')
            )
            return token
        except Exception as e:
            error_msg = str(e).lower()
            if "invalid_client" in error_msg:
                raise ValueError("Microsoft OAuth client credentials are invalid. Check MICROSOFT_CLIENT_ID configuration.")
            elif "invalid_grant" in error_msg:
                raise ValueError("Authorization code is invalid or expired. Please try logging in again.")
            elif "redirect_uri" in error_msg:
                raise ValueError(f"OAuth redirect URI mismatch. Expected: {redirect_uri or _provider_redirect_uri('microsoft')}")
            else:
                raise ValueError(f"Microsoft OAuth token exchange failed: {str(e)}")


async def get_microsoft_user_info(token: Dict[str, Any]) -> Dict[str, Any]:
    """Get user information from Microsoft using access token."""
    async with AsyncClient() as http_client:
        resp = await http_client.get(
            'https://graph.microsoft.com/oidc/userinfo',
            headers={"Authorization": f"Bearer {token['access_token']}"}
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "id": data.get('sub') or data.get('oid') or data.get('id'),
            "email": data.get('email') or data.get('preferred_username'),
            "name": data.get('name'),
            "picture": None
        }


async def exchange_slack_code_for_token(
    code: str,
    redirect_uri: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """Exchange Slack OAuth v2 authorization code for access token.
    Requires SLACK_CLIENT_ID/SLACK_CLIENT_SECRET.
    """
    async with AsyncClient() as http_client:
        resp = await http_client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": client_id or SLACK_CLIENT_ID,
                "client_secret": client_secret or SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri or _provider_redirect_uri('slack'),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack token exchange failed: {data}")
        return data


async def get_slack_user_info(token: Dict[str, Any]) -> Dict[str, Any]:
    """Get Slack user info using the access token.
    Tries users.identity (legacy) then users.info using authed_user id.
    """
    access_token = token.get("access_token")
    authed_user = (token.get("authed_user") or {}).get("id")
    async with AsyncClient() as http_client:
        # Prefer users.identity if available (requires identity.* scopes)
        resp = await http_client.get(
            "https://slack.com/api/users.identity",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        data = resp.json()
        if data.get("ok") and data.get("user"):
            u = data["user"]
            return {
                "id": u.get("id"),
                "email": (u.get("email") or None),
                "name": (u.get("name") or "Slack User"),
                "picture": (u.get("image_192") or None),
            }
        # Fallback to users.info if we have authed_user id (requires users:read)
        if authed_user:
            info = await http_client.get(
                "https://slack.com/api/users.info",
                params={"user": authed_user},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            j = info.json()
            if j.get("ok") and j.get("user"):
                u = j["user"]
                prof = u.get("profile") or {}
                return {
                    "id": u.get("id"),
                    "email": prof.get("email"),
                    "name": prof.get("real_name") or prof.get("display_name") or "Slack User",
                    "picture": prof.get("image_192"),
                }
    # Last resort minimal payload
    return {
        "id": authed_user or "",
        "email": None,
        "name": "Slack User",
        "picture": None,
    }


# Apple OAuth Implementation (Placeholder)
async def exchange_apple_code_for_token(code: str) -> Dict[str, Any]:
    """
    Exchange Apple OAuth authorization code for access token.
    
    Note: Apple OAuth requires a more complex implementation including:
    1. Client secret generation using JWT
    2. Specific redirect URI handling
    3. Proper handling of Apple's unique response format
    
    This is a simplified placeholder - actual implementation would require
    generating a client secret JWT and handling Apple's specific token endpoint
    """
    # This is a simplified placeholder - actual implementation would require
    # generating a client secret JWT and handling Apple's specific token endpoint
    raise NotImplementedError("Apple OAuth implementation pending")


async def get_apple_user_info(token: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get user information from Apple using access token.
    
    Note: Apple only provides user info during the initial authorization,
    and it's returned directly in the callback. Subsequent requests to
    get user info require a different approach.
    """
    # Apple doesn't have a standard user info endpoint like Google
    # User info is provided in the initial authorization response
    raise NotImplementedError("Apple user info retrieval pending")