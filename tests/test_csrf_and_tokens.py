import os
import pytest

from fastapi import FastAPI
from starlette.testclient import TestClient

from src.etherion_ai.middleware.csrf_guard import GraphQLCSRFGuard
import importlib


def test_graphql_csrf_guard_post_without_auth_401():
    app = FastAPI()
    app.add_middleware(GraphQLCSRFGuard)

    @app.post("/graphql")
    def graphql_stub():
        return {"ok": True}

    client = TestClient(app)
    with pytest.raises(Exception):
        client.post("/graphql", json={"query": "mutation { noop }"})


def test_refresh_token_decode_and_blacklist_flow(monkeypatch):
    # Ensure JWT secret in env for token creation
    monkeypatch.setenv("JWT_SECRET_KEY", "testsecret")
    # Import lazily after setting env
    jwtmod = importlib.import_module("src.auth.jwt")

    pair = jwtmod.create_token_pair({"sub": "u1", "email": "e@x", "tenant_id": 1})
    rt = pair["refresh_token"]
    data = jwtmod.decode_refresh_token(rt)
    assert data.user_id == "u1" and data.email == "e@x" and data.tenant_id == 1


