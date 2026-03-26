import pytest

from src.services.platform_orchestrator import AgentTeamCreator


@pytest.mark.asyncio
async def test_agent_team_creator_uses_llm_blueprint_and_enforces_exactly_three(monkeypatch):
    creator = AgentTeamCreator(tenant_id=1)

    # tool_registry_tool is now mandatory for blueprint creation; stub it with a small registry.
    import src.tools.tool_registry_tool as tr
    monkeypatch.setattr(
        tr,
        "tool_registry_tool",
        lambda *args, **kwargs: {
            "tools": [
                {"name": "unified_research_tool"},
                {"name": "multimodal_kb_search"},
                {"name": "fetch_document_content"},
            ]
        },
        raising=True,
    )

    spec = (
        "Create a physics teaching team with exactly 3 specialists: "
        "(1) an Information Theory specialist (Shannon entropy, coding, KL divergence), "
        "(2) a Thermodynamics specialist (stat mech foundations, ensembles, Boltzmann/Gibbs entropy), "
        "(3) an Entropy specialist that bridges both and focuses on intuition and worked examples. "
        "The team should be able to teach progressively from basics to advanced, create exercises, "
        "and produce structured learning artifacts when helpful."
    )

    personality = {"personality": {"technical_level": "intermediate"}}
    import json as _json

    llm_payload = {
        "agent_requirements": [
            {
                "name": "Information Theory Specialist",
                "description": "Information theory fundamentals and Shannon entropy.",
                "system_prompt": "You are the Information Theory Specialist.",
                "capabilities": ["Shannon entropy", "coding theory", "KL divergence"],
                "required_skills": ["Shannon entropy", "coding theory", "KL divergence"],
                "complexity": "medium",
                "estimated_steps": 3,
                "personality_alignment": "intermediate",
            },
            {
                "name": "Thermodynamics Specialist",
                "description": "Thermodynamics and statistical mechanics foundations.",
                "system_prompt": "You are the Thermodynamics Specialist.",
                "capabilities": ["stat mech", "ensembles", "Boltzmann entropy", "Gibbs entropy"],
                "required_skills": ["stat mech", "ensembles", "Boltzmann entropy", "Gibbs entropy"],
                "complexity": "medium",
                "estimated_steps": 3,
                "personality_alignment": "intermediate",
            },
            {
                "name": "Entropy Bridge Specialist",
                "description": "Bridges information entropy and thermodynamic entropy with intuition.",
                "system_prompt": "You are the Entropy Bridge Specialist.",
                "capabilities": ["intuition", "worked examples", "bridging analogies"],
                "required_skills": ["intuition", "worked examples", "bridging analogies"],
                "complexity": "medium",
                "estimated_steps": 3,
                "personality_alignment": "intermediate",
            },
        ],
        "tool_requirements": ["unified_research_tool", "multimodal_kb_search", "fetch_document_content"],
        "team_structure": {"team_type": "specialized", "agent_count": 3, "coordination_style": "collaborative"},
    }

    async def _fake_invoke_blueprint_llm2(*, specification: str, user_personality, tenant_id: int, available_tool_names):
        assert "exactly 3" in (specification or "").lower()
        assert "fetch_document_content" in (available_tool_names or [])
        return _json.dumps(llm_payload)

    monkeypatch.setattr(creator, "_invoke_blueprint_llm", _fake_invoke_blueprint_llm2, raising=True)

    bp = await creator.create_blueprint(spec, personality, tenant_id=1)
    reqs = bp.get("agent_requirements")
    assert isinstance(reqs, list)
    assert len(reqs) == 3

    assert [r.get("name") for r in reqs] == [
        "Information Theory Specialist",
        "Thermodynamics Specialist",
        "Entropy Bridge Specialist",
    ]
