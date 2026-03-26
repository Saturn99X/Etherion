import asyncio
import pytest

from src.tools.natural_language_tool_router import NaturalLanguageToolRouter


class DummyToolManager:
    def __init__(self):
        self.calls = []

    def get_tool_instance(self, tool_name, tenant_id, job_id, **kwargs):
        async def _fn(input_data):
            # record then echo
            self.calls.append((tool_name, tenant_id, job_id, input_data))
            return {"ok": True, "tool": tool_name, "input": input_data}

        return _fn


@pytest.mark.asyncio
async def test_router_classifies_and_builds_image_request():
    tm = DummyToolManager()
    router = NaturalLanguageToolRouter(tool_manager=tm)

    text = "Generate an image of a sunset over the ocean in watercolor style."
    dry = await router.execute(text, tenant_id="1", job_id="j1", dry_run=True)
    assert dry["success"] is True
    assert dry["tool"] == "generate_image_file"
    assert dry["input_data"]["data"]["prompt"].startswith("Generate an image")

    res = await router.execute(text, tenant_id="1", job_id="j1", dry_run=False)
    assert res["ok"] is True
    assert tm.calls and tm.calls[0][0] == "generate_image_file"


@pytest.mark.asyncio
async def test_router_classifies_pdf_and_includes_template():
    tm = DummyToolManager()
    router = NaturalLanguageToolRouter(tool_manager=tm)

    text = "Create a one-page PDF resume for Jane Doe with sections: Summary, Skills, Experience."
    dry = await router.execute(text, tenant_id="2", job_id="j2", dry_run=True)
    assert dry["success"] is True
    assert dry["tool"] == "generate_pdf_file"
    assert dry["input_data"]["template"] in ("resume_one_page", "generic_one_pager")

    res = await router.execute(text, tenant_id="2", job_id="j2", dry_run=False)
    assert res["ok"] is True
    assert tm.calls and tm.calls[0][0] == "generate_pdf_file"
