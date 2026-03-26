import os
import pytest
from httpx import AsyncClient, ASGITransport

from tests.e2e._dummy_redis import setup_dummy_redis
from src.services.oauth_state import OAuthStateManager


@pytest.mark.asyncio
async def test_oauth_silo_start_and_callback_slack(monkeypatch):
    # Env setup
    os.environ.setdefault("JWT_SECRET_KEY", "jwt-test-secret")
    os.environ.setdefault("SECRET_KEY", "server-secret")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "dev-proj")
    os.environ.setdefault("OAUTH_STATE_SECRET", "oauth-secret")
    # Slack client creds resolved via env by SiloOAuthService
    os.environ.setdefault("SLACK_USER_OAUTH_CLIENT_ID", "cid")
    os.environ.setdefault("SLACK_USER_OAUTH_CLIENT_SECRET", "csec")

    # Patch Redis
    setup_dummy_redis(monkeypatch)

    # Patch TenantSecretsManager.set_secret to capture token storage
    saved = {"calls": []}

    async def fake_set_secret(self, tenant_id, service, key, payload=None, value=None, secret_value=None):
        saved["calls"].append((tenant_id, service, key, payload or value or secret_value))
        return True

    monkeypatch.setattr(
        "src.services.silo_oauth_service.TenantSecretsManager.set_secret",
        fake_set_secret,
        raising=True,
    )

    # Patch httpx.AsyncClient for Slack token exchange
    class DummyResp:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200

        def json(self):
            return self._payload

        def raise_for_status(self):
            return None

    class DummyClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, json=None, headers=None):
            # slack oauth.v2.access response shape
            return DummyResp({
                "ok": True,
                "access_token": "xoxb-token",
                "token_type": "bot",
                "scope": "chat:write",
                "authed_user": {"id": "U123", "refresh_token": "rtok"},
                "team": {"id": "T1"},
            })

    monkeypatch.setattr("src.services.silo_oauth_service.httpx.AsyncClient", DummyClient, raising=True)

    # Build state using the same secret/nonce store
    state_mgr = OAuthStateManager(ttl_seconds=900)
    state = await state_mgr.encode(tenant_id="1", provider="slack", extra={"redirect_to": "https://app.local/ok"})

    # Create app after patches
    from src.etherion_ai.app import create_app
    from src.auth.jwt import create_access_token

    token = create_access_token({"sub": "user-1", "email": "u@example.com", "tenant_id": 1})
    app = create_app()

    # Start
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/oauth/silo/slack/start", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "authorize_url" in data
        assert "slack.com" in data["authorize_url"]

        # Callback
        r2 = await client.get(f"/oauth/silo/slack/callback?code=abc&state={state}")
        assert r2.status_code == 200 or r2.status_code == 302

    # Token storage invoked
    assert any(k == "oauth_tokens" and s == "slack" for (_t, s, k, _p) in saved["calls"])  # noqa: E712
