import pytest
from unittest.mock import MagicMock, AsyncMock

from src.services.goal_orchestrator import GoalOrchestrator
from src.services.platform_orchestrator import PlatformOrchestrator
from src.services.team_orchestrator import TeamOrchestrator

@pytest.fixture
def mock_platform_orchestrator():
    """Mocks the PlatformOrchestrator."""
    mock = MagicMock(spec=PlatformOrchestrator)
    mock.create_agent_team_blueprint = AsyncMock(return_value={
        "agent_requirements": [{"required_skills": ["test"], "description": "Test task"}]
    })
    return mock

@pytest.fixture
def mock_team_orchestrator():
    """Mocks the TeamOrchestrator."""
    mock = MagicMock(spec=TeamOrchestrator)
    mock.execute_2n_plus_1_loop = AsyncMock(return_value={"output": "Team task completed"})
    return mock

@pytest.mark.asyncio
async def test_goal_orchestrator_execute(monkeypatch, mock_platform_orchestrator, mock_team_orchestrator):
    """Tests the full execution flow of the GoalOrchestrator."""
    monkeypatch.setattr("src.services.goal_orchestrator.PlatformOrchestrator", lambda tenant_id, user_id: mock_platform_orchestrator)
    monkeypatch.setattr("src.services.goal_orchestrator.TeamOrchestrator", lambda team_id, tenant_id, user_id: mock_team_orchestrator)

    goal_orchestrator = GoalOrchestrator(goal="Test goal", user_id=1, tenant_id=1)
    result = await goal_orchestrator.execute()

    mock_platform_orchestrator.create_agent_team_blueprint.assert_called_once_with("Test goal")
    mock_team_orchestrator.execute_2n_plus_1_loop.assert_called_once()
    assert "final_result" in result
    assert "Team task completed" in result["final_result"]
