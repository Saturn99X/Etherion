import importlib
import os
import sys

import pytest
from starlette.testclient import TestClient


def make_app_with_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "testsecret")
    monkeypatch.setenv("JWT_SECRET_KEY", "testsecret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./etherion.db")
    monkeypatch.setenv("ASYNC_DATABASE_URL", "sqlite+aiosqlite:///./etherion.db")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")

    if "src.etherion_ai.app" in sys.modules:
        del sys.modules["src.etherion_ai.app"]
    appmod = importlib.import_module("src.etherion_ai.app")
    return appmod.app


def make_bearer_token():
    if "src.auth.jwt" in sys.modules:
        del sys.modules["src.auth.jwt"]
    jwtmod = importlib.import_module("src.auth.jwt")
    return jwtmod.create_access_token({"sub": "u1", "email": "u1@local", "tenant_id": 1})


@pytest.mark.smoke
def test_graphql_ws_connection_init_ack(monkeypatch):
    app = make_app_with_env(monkeypatch)
    token = make_bearer_token()
    client = TestClient(app)

    with client.websocket_connect(
        "/graphql",
        subprotocols=["graphql-ws"],
        headers={"Authorization": f"Bearer {token}"},
    ) as ws:
        ws.send_json({"type": "connection_init", "payload": {}})
        msg = ws.receive_json()
        assert msg.get("type") == "connection_ack"
