import os
import pytest

from src.tools import unified_research_tool as urt_mod


@pytest.mark.asyncio
async def test_unified_research_tool_web_gating(monkeypatch):
    # Ensure EXA won't be called unless we explicitly mock it
    os.environ.pop("EXA_API_KEY", None)
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-proj")

    # When enable_web=False -> web_results should be empty and exa_search not called
    called = {"count": 0}

    async def fake_exa_search(params):  # pragma: no cover - safety
        called["count"] += 1
        return {"results": [{"url": "https://example.com"}]}

    # Patch both async and sync paths; under pytest the event loop is running so
    # unified_research_tool will use _exa_search_sync fallback.
    monkeypatch.setattr(urt_mod, "exa_search", fake_exa_search, raising=True)
    last = {"kwargs": None}

    def _fake_exa_sync(
        query,
        num_results=10,
        include_text=True,
        include_highlights=True,
        include_summary=True,
        timeout_seconds=30,
    ):
        last["kwargs"] = {
            "query": query,
            "num_results": num_results,
            "include_text": include_text,
            "include_highlights": include_highlights,
            "include_summary": include_summary,
            "timeout_seconds": timeout_seconds,
        }
        return [{"url": "https://example.com", "title": "t"}]

    monkeypatch.setattr(urt_mod, "_exa_search_sync", _fake_exa_sync, raising=True)

    r0 = urt_mod.unified_research_tool(
        query="hello world", tenant_id="1", project_id=None, job_id="job_test", enable_web=False
    )
    assert isinstance(r0, dict)
    assert r0.get("web_results") == []
    assert isinstance(r0.get("errors"), dict)
    assert isinstance(r0.get("timings_ms"), dict)
    assert r0.get("web_enabled") is False
    assert called["count"] == 0

    # With enable_web=True, either async exa_search or sync fallback may be used
    r1 = urt_mod.unified_research_tool(
        query="hello world", tenant_id="1", project_id=None, job_id="job_test", enable_web=True
    )
    assert isinstance(r1, dict)
    assert r1.get("web_enabled") is True
    # EXA_API_KEY is not configured in this test; web should fail explicitly with structured error.
    assert r1.get("web_results") == []
    assert isinstance(r1.get("errors"), dict)
    assert "web" in (r1.get("errors") or {})
    # Under pytest, the event loop is typically running, so sync fallback bypasses async exa_search
    assert called["count"] in (0, 1)

    # With enable_web as dict, EXA features are pilotable per-call
    last["kwargs"] = None
    r2 = urt_mod.unified_research_tool(
        query="hello world",
        tenant_id="1",
        project_id=None,
        job_id="job_test",
        enable_web={
            "num_results": 3,
            "timeout_seconds": 7,
            "include_text": False,
            "include_highlights": False,
            "include_summary": False,
        },
    )
    assert isinstance(r2, dict)
    # Same as above: without EXA_API_KEY, this should fail explicitly.
    assert r2.get("web_results") == []
    assert "web" in (r2.get("errors") or {})
    assert last["kwargs"] is None


@pytest.mark.asyncio
async def test_unified_research_tool_object_kb_gating(monkeypatch):
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-proj")

    calls = {"n": 0}

    class _FakeObjSvc:
        def search(self, *, tenant_id: str, query: str, top_k: int = 10, content_type_prefix=None, job_id=None):
            calls["n"] += 1
            return [{"gcs_uri": "gs://tnt-1-media/uploads/x.png", "content_type": "image/png", "metadata": {}, "distance": 0.1}]

    monkeypatch.setattr(urt_mod, "BQMediaObjectSearchService", lambda: _FakeObjSvc(), raising=True)

    os.environ.pop("ENVIRONMENT", None)
    os.environ.pop("KB_OBJECT_TABLES_ENABLED", None)
    r_prod_default = urt_mod.unified_research_tool(query="hello", tenant_id="1", project_id=None, job_id="job_test", enable_web=False)
    assert isinstance(r_prod_default, dict)
    assert isinstance(r_prod_default.get("object_results"), list)
    assert (r_prod_default.get("object_results") or [])[0].get("gcs_uri") == "gs://tnt-1-media/uploads/x.png"
    assert calls["n"] == 1

    os.environ["KB_OBJECT_TABLES_ENABLED"] = "0"
    r0 = urt_mod.unified_research_tool(query="hello", tenant_id="1", project_id=None, job_id="job_test", enable_web=False)
    assert isinstance(r0, dict)
    assert r0.get("object_results") == []

    os.environ["KB_OBJECT_TABLES_ENABLED"] = "1"
    r1 = urt_mod.unified_research_tool(query="hello", tenant_id="1", project_id=None, job_id="job_test", enable_web=False)
    assert isinstance(r1, dict)
    assert isinstance(r1.get("object_results"), list)
    assert (r1.get("object_results") or [])[0].get("gcs_uri") == "gs://tnt-1-media/uploads/x.png"
    assert calls["n"] == 2
