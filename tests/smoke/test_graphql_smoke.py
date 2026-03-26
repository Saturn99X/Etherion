import os
import sys
import json
import importlib
import pytest
from starlette.testclient import TestClient


def make_app_with_env(monkeypatch):
    # Minimal env for app and JWT
    monkeypatch.setenv("SECRET_KEY", "testsecret")
    monkeypatch.setenv("JWT_SECRET_KEY", "testsecret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    # Use repo's SQLite DB to avoid needing migrations in CI/LES
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./etherion.db")
    monkeypatch.setenv("ASYNC_DATABASE_URL", "sqlite+aiosqlite:///./etherion.db")
    # Rate limit/perf related env (optional)
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")

    # Import app after env is set
    if "src.etherion_ai.app" in sys.modules:
        del sys.modules["src.etherion_ai.app"]
    appmod = importlib.import_module("src.etherion_ai.app")
    return appmod.app


def make_bearer_token():
    if "src.auth.jwt" in sys.modules:
        del sys.modules["src.auth.jwt"]
    jwtmod = importlib.import_module("src.auth.jwt")
    # Minimal token payload; tenant 1 assumed for local SQLite
    return jwtmod.create_access_token({"sub": "u1", "email": "u1@local", "tenant_id": 1})


@pytest.mark.smoke
def test_list_agent_teams_smoke(monkeypatch):
    app = make_app_with_env(monkeypatch)
    token = make_bearer_token()
    client = TestClient(app)

    query = """
    query ListAgentTeams($limit: Int!, $offset: Int!) {
      listAgentTeams(limit: $limit, offset: $offset) {
        id
        name
      }
    }
    """
    variables = {"limit": 1, "offset": 0}

    resp = client.post(
        "/graphql",
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    # Accept empty list as valid in smoke context
    assert "listAgentTeams" in data["data"]
    assert isinstance(data["data"]["listAgentTeams"], list)


@pytest.mark.smoke
def test_execute_goal_smoke(monkeypatch):
    app = make_app_with_env(monkeypatch)
    token = make_bearer_token()
    client = TestClient(app)

    mutation = """
    mutation Exec($gi: GoalInput!) {
      executeGoal(goalInput: $gi) {
        success
        status
        message
        job_id
      }
    }
    """
    variables = {
        "gi": {
            "goal": "Run a quick smoke test",
            "userId": "u1",
            # optional context/output_format_instructions omitted for brevity
        }
    }

    resp = client.post(
        "/graphql",
        json={"query": mutation, "variables": variables},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "executeGoal" in data["data"], data
    # The path should execute without server errors; acceptance criteria is shape
    eg = data["data"]["executeGoal"]
    assert isinstance(eg, dict)
    assert set(["success", "status", "message", "job_id"]) <= set(eg.keys())
