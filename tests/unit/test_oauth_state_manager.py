import os
import pytest

from types import SimpleNamespace

from src.services.oauth_state import OAuthStateManager
from tests.e2e._dummy_redis import setup_dummy_redis


@pytest.mark.asyncio
async def test_oauth_state_hmac_and_nonce(monkeypatch):
    # Ensure deterministic secret and dummy redis
    os.environ["OAUTH_STATE_SECRET"] = "test-secret"
    dummy = setup_dummy_redis(monkeypatch)
    # Also patch the bound import inside oauth_state module
    import src.services.oauth_state as oauth_state_mod
    monkeypatch.setattr(oauth_state_mod, "get_redis_client", lambda: dummy, raising=True)

    mgr = OAuthStateManager(ttl_seconds=5)

    state = await mgr.encode(tenant_id="7", provider="google", extra={"redirect_to": "https://app.example.com/integrations"})
    assert "." in state  # format: payload.sig

    payload = await mgr.decode_and_verify(state)
    assert payload["tenant_id"] == "7"
    assert payload["provider"] == "google"
    assert payload["redirect_to"] == "https://app.example.com/integrations"
    assert payload["nonce"]

    # Nonce must be one-time use
    with pytest.raises(ValueError) as ei:
        await mgr.decode_and_verify(state)
    assert "nonce" in str(ei.value).lower() or "state_nonce_not_found" in str(ei.value)
