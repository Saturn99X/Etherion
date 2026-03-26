import os
import hmac
import hashlib
import base64
import json
import time
import secrets
from typing import Any, Dict, Optional, Tuple

from src.core.redis import get_redis_client


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))


class OAuthStateManager:
    """
    HMAC-signed OAuth state manager with nonce replay protection via Redis.

    State format: base64url(json_payload).base64url(hmac_sha256)
    json_payload includes: {"tenant_id","provider","nonce","ts","redirect_to",...}
    """

    def __init__(self, ttl_seconds: int = 600):
        self._secret = (os.getenv("OAUTH_STATE_SECRET") or "dev-secret").encode("utf-8")
        self._ttl = int(ttl_seconds)

    def _sign(self, payload_json: str) -> str:
        mac = hmac.new(self._secret, payload_json.encode("utf-8"), hashlib.sha256).digest()
        return _b64url_encode(mac)

    async def encode(self, *, tenant_id: str, provider: str, extra: Optional[Dict[str, Any]] = None) -> str:
        payload: Dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "provider": provider,
            "nonce": secrets.token_urlsafe(16),
            "ts": int(time.time()),
        }
        if extra:
            for k, v in extra.items():
                if v is not None:
                    payload[k] = v
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        sig = self._sign(payload_json)
        state = f"{_b64url_encode(payload_json.encode('utf-8'))}.{sig}"
        # Store nonce in Redis to enforce one-time use
        try:
            client = await get_redis_client().get_client()
            await client.setex(f"oauth_state_nonce:{payload['nonce']}", self._ttl, "1")
        except Exception:
            # Best effort; still return state
            pass
        return state

    async def decode_and_verify(self, state: str) -> Dict[str, Any]:
        try:
            b64payload, sig = state.split(".", 1)
        except ValueError:
            raise ValueError("invalid_state_format")
        payload_json = _b64url_decode(b64payload).decode("utf-8")
        expected = self._sign(payload_json)
        if not hmac.compare_digest(expected, sig):
            raise ValueError("invalid_state_signature")
        payload = json.loads(payload_json)
        # Check age
        ts = int(payload.get("ts") or 0)
        if int(time.time()) - ts > self._ttl:
            raise ValueError("state_expired")
        # Check nonce (one-time)
        nonce = payload.get("nonce")
        if not nonce:
            raise ValueError("missing_nonce")
        try:
            client = await get_redis_client().get_client()
            key = f"oauth_state_nonce:{nonce}"
            exists = await client.get(key)
            if not exists:
                raise ValueError("state_nonce_not_found")
            # Invalidate
            try:
                await client.delete(key)
            except Exception:
                pass
        except ValueError:
            raise
        except Exception:
            # If Redis unavailable, allow best-effort but logically this weakens replay protection
            pass
        return payload
