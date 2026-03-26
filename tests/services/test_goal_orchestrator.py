"""
Comprehensive tests for the Goal Orchestrator implementation.

This test suite validates:
- Agent team loading and validation
- Tool approval system
- Error handling and recovery
- Integration with security validation
- Celery task execution
- Database interactions
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime
from typing import Dict, Any, List
import json

from src.services.goal_orchestrator import GoalOrchestrator, orchestrate_goal_task
from src.services.orchestrator_security import get_orchestrator_security_validator
from src.services.orchestrator_error_handler import (
    get_orchestrator_error_handler,
    AgentTeamNotFoundError,
    ToolApprovalError
)


class TestGoalOrchestrator:
    """Test suite for GoalOrchestrator class."""

    @pytest.fixture
    def mock_agent_loader(self):
        """Create a mock agent loader."""
        # Create proper mock tools with correct attributes
        tool1 = Mock()
        tool1.name = 'test_tool_1'
        tool1.is_stable = True

        tool2 = Mock()
        tool2.name = 'test_tool_2'
        tool2.is_stable = True

        basic_tool = Mock()
        basic_tool.name = 'basic_tool'
        basic_tool.is_stable = True

        loader = Mock()
        loader.load_agent_team.return_value = {
            'team_id': 'test_team_1',
            'name': 'Test Team',
            'description': 'Test team for orchestrator',
            'pre_approved_tools': [
                {'name': 'test_tool_1', 'instance': tool1},
                {'name': 'test_tool_2', 'instance': tool2}
            ],
            'custom_agents': [
                {
                    'agent_id': 'agent_1',
                    'name': 'Research Agent',
                    'description': 'Handles research tasks',
                    'system_prompt': 'You are a research specialist.',
                    'tool_names': ['test_tool_1']
                }
            ]
        }
        loader.load_system_teams.return_value = [{
            'team_id': 'system_team_1',
            'name': 'System Team',
            'description': 'Default system team',
            'pre_approved_tools': [
                {'name': 'basic_tool', 'instance': basic_tool}
            ],
            'custom_agents': []
        }]
        return loader

    @pytest.fixture
    def goal_orchestrator(self, mock_agent_loader):
        """Create a GoalOrchestrator instance for testing."""
        with patch('src.services.goal_orchestrator.get_agent_loader', return_value=mock_agent_loader):
            orchestrator = GoalOrchestrator(
                tenant_id=1,
                user_id=1,
                agent_team_id='test_team_1',
                job_id='test_job_123'
            )
        return orchestrator

    def test_goal_orchestrator_initialization(self, goal_orchestrator: GoalOrchestrator):
        """Test GoalOrchestrator initialization."""
        assert goal_orchestrator.tenant_id == 1
        assert goal_orchestrator.user_id == 1
        assert goal_orchestrator.agent_team_id == 'test_team_1'
        assert goal_orchestrator.job_id == 'test_job_123'
        assert goal_orchestrator.agent_loader is not None

    @pytest.mark.asyncio
    async def test_load_orchestrator_context_success(self, goal_orchestrator: GoalOrchestrator):
        """Test successful orchestrator context loading."""
        result = await goal_orchestrator._load_orchestrator_context()

        assert result is not None
        assert result['team_id'] == 'test_team_1'
        assert result['orchestrator_id'].startswith('orch_1_')
        assert len(result['approved_tools']) == 2
        assert len(result['specialist_agents']) == 1

    @pytest.mark.asyncio
    async def test_load_orchestrator_context_fallback(self, mock_agent_loader):
        """Test orchestrator context loading fallback to system team."""
        # Mock agent team not found
        mock_agent_loader.load_agent_team.return_value = None

        with patch('src.services.goal_orchestrator.get_agent_loader', return_value=mock_agent_loader):
            orchestrator = GoalOrchestrator(
                tenant_id=1,
                user_id=1,
                agent_team_id='nonexistent_team',
                job_id='test_job_123'
            )

            result = await orchestrator._load_orchestrator_context()

            # Should fallback to system team
            assert result is not None
            assert result['team_id'] == 'system_team_1'

    @pytest.mark.asyncio
    async def test_load_orchestrator_context_failure(self, mock_agent_loader):
        """Test orchestrator context loading failure."""
        # Mock both agent team and system teams not found
        mock_agent_loader.load_agent_team.return_value = None
        mock_agent_loader.load_system_teams.return_value = []

        with patch('src.services.goal_orchestrator.get_agent_loader', return_value=mock_agent_loader):
            orchestrator = GoalOrchestrator(
                tenant_id=1,
                user_id=1,
                agent_team_id='nonexistent_team',
                job_id='test_job_123'
            )

            result = await orchestrator._load_orchestrator_context()

            assert result is None

    @pytest.mark.asyncio
    async def test_create_team_orchestrator(self, goal_orchestrator: GoalOrchestrator):
        """Test team orchestrator creation."""
        # Create proper mock tools with correct attributes
        tool1 = Mock()
        tool1.name = 'test_tool_1'
        tool1.is_stable = True

        tool2 = Mock()
        tool2.name = 'test_tool_2'
        tool2.is_stable = True

        team_config = {
            'team_id': 'test_team_1',
            'name': 'Test Team',
            'pre_approved_tools': [
                {'name': 'test_tool_1', 'instance': tool1},
                {'name': 'test_tool_2', 'instance': tool2}
            ],
            'custom_agents': [
                {
                    'agent_id': 'agent_1',
                    'name': 'Research Agent',
                    'tool_names': ['test_tool_1']
                }
            ]
        }

        result = goal_orchestrator._create_team_orchestrator(team_config)

        assert result['team_id'] == 'test_team_1'
        assert result['orchestrator_id'].startswith('orch_1_')
        assert len(result['approved_tools']) == 2
        assert len(result['specialist_agents']) == 1
        assert result['execution_context']['tenant_id'] == 1
        assert result['execution_context']['user_id'] == 1
        assert result['execution_context']['job_id'] == 'test_job_123'

    @pytest.mark.asyncio
    async def test_validate_tool_approval_valid(self, goal_orchestrator: GoalOrchestrator):
        """Test tool approval validation for valid tool."""
        tool_instance = Mock()
        tool_instance.name = 'test_tool_1'

        team_config = {
            'team_id': 'test_team_1',
            'pre_approved_tools': [
                {'name': 'test_tool_1', 'instance': Mock()},
                {'name': 'test_tool_2', 'instance': Mock()}
            ]
        }

        result = goal_orchestrator._validate_tool_approval(tool_instance, team_config)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_tool_approval_invalid(self, goal_orchestrator: GoalOrchestrator):
        """Test tool approval validation for invalid tool."""
        tool_instance = Mock()
        tool_instance.name = 'unapproved_tool'

        team_config = {
            'team_id': 'test_team_1',
            'pre_approved_tools': [
                {'name': 'test_tool_1', 'instance': Mock()},
                {'name': 'test_tool_2', 'instance': Mock()}
            ]
        }

        result = goal_orchestrator._validate_tool_approval(tool_instance, team_config)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_tool_approval_unstable(self, goal_orchestrator: GoalOrchestrator):
        """Test tool approval validation for unstable tool."""
        tool_instance = Mock()
        tool_instance.name = 'test_tool_1'
        tool_instance.is_stable = False

        team_config = {
            'team_id': 'test_team_1',
            'pre_approved_tools': [
                {'name': 'test_tool_1', 'instance': Mock()}
            ]
        }

        result = goal_orchestrator._validate_tool_approval(tool_instance, team_config)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_all_tools_valid(self, goal_orchestrator: GoalOrchestrator):
        """Test validation of all tools in orchestrator config."""
        orchestrator_config = {
            'approved_tools': [
                Mock(name='test_tool_1', is_stable=True),
                Mock(name='test_tool_2', is_stable=True)
            ],
            'specialist_agents': [
                {
                    'agent_id': 'agent_1',
                    'name': 'Research Agent',
                    'tool_names': ['test_tool_1']
                }
            ]
        }

        result = goal_orchestrator._validate_all_tools(orchestrator_config)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_all_tools_invalid(self, goal_orchestrator: GoalOrchestrator):
        """Test validation of all tools with invalid tools."""
        orchestrator_config = {
            'approved_tools': [],  # Empty approved tools
            'specialist_agents': []
        }

        result = goal_orchestrator._validate_all_tools(orchestrator_config)
        assert result is False

    @pytest.mark.asyncio
    async def test_orchestrate_goal_success(self, goal_orchestrator: GoalOrchestrator):
        """Test successful goal orchestration."""
        with patch.object(goal_orchestrator, '_load_orchestrator_context', new_callable=AsyncMock) as mock_load, \
             patch.object(goal_orchestrator, '_validate_all_tools', return_value=True), \
             patch('src.services.goal_orchestrator.TrueOrchestrator') as mock_true_orchestrator_class, \
             patch('src.services.goal_orchestrator.log_security_event', new_callable=AsyncMock), \
             patch('src.services.goal_orchestrator.get_orchestrator_security_validator') as mock_security, \
             patch('src.services.goal_orchestrator.get_orchestrator_error_handler') as mock_error_handler:

            # Mock orchestrator context
            mock_load.return_value = {
                'orchestrator_id': 'test_orch_123',
                'team_id': 'test_team_1',
                'approved_tools': [Mock()],
                'specialist_agents': [],
                'execution_context': {'tenant_id': 1, 'user_id': 1, 'job_id': 'test_job_123'}
            }

            # Mock security validator
            mock_security_validator = AsyncMock()
            mock_security_validator.validate_orchestrator_execution = AsyncMock(return_value={
                'valid': True,
                'checks': [],
                'warnings': [],
                'errors': []
            })
            mock_security.return_value = mock_security_validator

            # Mock error handler
            mock_handler = AsyncMock()
            mock_handler.update_job_status = AsyncMock()
            mock_error_handler.return_value = mock_handler

            # Mock TrueOrchestrator
            mock_true_orchestrator = Mock()
            mock_true_orchestrator.execute_2n_plus_1_loop = AsyncMock(return_value={
                'success': True,
                'result': 'Test result',
                'execution_metadata': {'orchestrator_id': 'test_orch_123'}
            })
            mock_true_orchestrator_class.return_value = mock_true_orchestrator

            goal = "Test goal"
            context = {"priority": "high"}

            result = await goal_orchestrator.orchestrate_goal(goal, context)

            assert result["success"] is True
            assert result["result"]["result"] == 'Test result'
            assert result["orchestrator_id"] == 'test_orch_123'
            assert result["agent_team_id"] == 'test_team_1'
            assert result["job_id"] == 'test_job_123'

    @pytest.mark.asyncio
    async def test_orchestrate_goal_agent_team_not_found(self, goal_orchestrator: GoalOrchestrator):
        """Test goal orchestration with agent team not found."""
        with patch.object(goal_orchestrator, '_load_orchestrator_context', new_callable=AsyncMock) as mock_load, \
             patch('src.services.goal_orchestrator.log_security_event', new_callable=AsyncMock), \
             patch('src.services.goal_orchestrator.get_orchestrator_error_handler') as mock_error_handler:

            # Mock orchestrator context loading failure
            mock_load.return_value = None

            mock_handler = AsyncMock()
            mock_handler.handle_error = AsyncMock(return_value={"recovery_success": False})
            mock_handler.update_job_status = AsyncMock()
            mock_error_handler.return_value = mock_handler

            goal = "Test goal"

            result = await goal_orchestrator.orchestrate_goal(goal)

            assert result["success"] is False
            assert "not found" in result["error"].lower()
            assert result["error_handling"]["recovery_success"] is False

    @pytest.mark.asyncio
    async def test_orchestrate_goal_tool_validation_failed(self, goal_orchestrator: GoalOrchestrator):
        """Test goal orchestration with tool validation failure."""
        with patch.object(goal_orchestrator, '_load_orchestrator_context', new_callable=AsyncMock) as mock_load, \
             patch.object(goal_orchestrator, '_validate_all_tools', return_value=False), \
             patch('src.services.goal_orchestrator.log_security_event', new_callable=AsyncMock), \
             patch('src.services.goal_orchestrator.get_orchestrator_security_validator') as mock_security, \
             patch('src.services.goal_orchestrator.get_orchestrator_error_handler') as mock_error_handler:

            # Mock orchestrator context
            mock_load.return_value = {
                'orchestrator_id': 'test_orch_123',
                'team_id': 'test_team_1',
                'approved_tools': [],
                'specialist_agents': [],
                'execution_context': {'tenant_id': 1, 'user_id': 1, 'job_id': 'test_job_123'}
            }

            # Mock security validator
            mock_security_validator = AsyncMock()
            mock_security_validator.validate_orchestrator_execution = AsyncMock(return_value={
                'valid': True,
                'checks': [],
                'warnings': [],
                'errors': []
            })
            mock_security.return_value = mock_security_validator

            mock_handler = AsyncMock()
            mock_handler.update_job_status = AsyncMock()
            mock_error_handler.return_value = mock_handler

            goal = "Test goal"

            result = await goal_orchestrator.orchestrate_goal(goal)

            assert result["success"] is False
            assert "tool validation failed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_update_execution_metrics(self, goal_orchestrator: GoalOrchestrator):
        """Test execution metrics update."""
        with patch('src.services.goal_orchestrator.session_scope') as mock_session_scope:
            mock_session = Mock()
            mock_session_scope.return_value.__enter__.return_value = mock_session

            # Mock agent team
            mock_team = Mock()
            mock_team.increment_execution_count = Mock()
            mock_session.query.return_value.filter.return_value.first.return_value = mock_team

            await goal_orchestrator._update_execution_metrics('test_team_1')

            # Verify team was updated
            mock_team.increment_execution_count.assert_called_once()
            mock_session.add.assert_called_once_with(mock_team)
            mock_session.commit.assert_called_once()


class TestOrchestrateGoalTask:
    """Test suite for orchestrate_goal_task function."""

    @pytest.mark.asyncio
    async def test_orchestrate_goal_task_success(self):
        """Test successful goal orchestration task."""
        with patch('src.services.goal_orchestrator.GoalOrchestrator') as mock_orchestrator_class, \
             patch('src.services.goal_orchestrator.log_security_event', new_callable=AsyncMock):

            # Mock orchestrator
            mock_orchestrator = Mock()
            mock_orchestrator.orchestrate_goal = AsyncMock(return_value={
                'success': True,
                'result': 'Test result',
                'execution_time': 1.5,
                'orchestrator_id': 'test_orch_123',
                'job_id': 'test_job_123'
            })
            mock_orchestrator_class.return_value = mock_orchestrator

            result = await orchestrate_goal_task(
                job_id='test_job_123',
                goal_description='Test goal',
                context={'priority': 'high'},
                output_format_instructions='JSON format',
                user_id=1,
                tenant_id=1,
                agent_team_id='test_team_1'
            )

            assert result['success'] is True
            assert result['result'] == 'Test result'
            assert result['job_id'] == 'test_job_123'

    @pytest.mark.asyncio
    async def test_orchestrate_goal_task_missing_params(self):
        """Test goal orchestration task with missing parameters."""
        with patch('src.services.goal_orchestrator.log_security_event', new_callable=AsyncMock), \
             patch('src.services.goal_orchestrator.get_orchestrator_error_handler') as mock_error_handler:

            # Missing tenant_id and user_id should result in error
            mock_handler = AsyncMock()
            mock_handler.handle_error = AsyncMock(return_value={"recovery_success": False})
            mock_handler.update_job_status = AsyncMock()
            mock_error_handler.return_value = mock_handler

            result = await orchestrate_goal_task(
                job_id='test_job_123',
                goal_description='Test goal',
                user_id=None,
                tenant_id=None
            )

            assert result["success"] is False
            assert "tenant_id and user_id are required" in result["error"]

    @pytest.mark.asyncio
    async def test_orchestrate_goal_task_error_handling(self):
        """Test goal orchestration task error handling."""
        with patch('src.services.goal_orchestrator.GoalOrchestrator') as mock_orchestrator_class, \
             patch('src.services.goal_orchestrator.get_orchestrator_error_handler') as mock_error_handler, \
             patch('src.services.goal_orchestrator.log_security_event', new_callable=AsyncMock):

            # Mock orchestrator to raise exception
            mock_orchestrator = Mock()
            mock_orchestrator.orchestrate_goal = AsyncMock(side_effect=Exception('Test error'))
            mock_orchestrator_class.return_value = mock_orchestrator

            mock_handler = AsyncMock()
            mock_handler.handle_error = AsyncMock(return_value={"recovery_success": False})
            mock_handler.update_job_status = AsyncMock()
            mock_error_handler.return_value = mock_handler

            result = await orchestrate_goal_task(
                job_id='test_job_123',
                goal_description='Test goal',
                user_id=1,
                tenant_id=1,
                agent_team_id='test_team_1'
            )

            assert result['success'] is False
            assert 'Test error' in result['error']
            assert result['job_id'] == 'test_job_123'
            assert 'error_handling' in result


class TestOrchestratorIntegration:
    """Integration tests for orchestrator components."""

    @pytest.mark.asyncio
    async def test_full_orchestration_workflow(self):
        """Test full orchestration workflow with all components."""
        # This would be a comprehensive integration test
        # that validates the entire workflow from goal input to completion

        # Mock all dependencies
        with patch('src.services.goal_orchestrator.get_agent_loader') as mock_loader, \
             patch('src.services.goal_orchestrator.get_orchestrator_security_validator') as mock_security, \
             patch('src.services.goal_orchestrator.TrueOrchestrator') as mock_true_orchestrator, \
             patch('src.services.goal_orchestrator.log_security_event', new_callable=AsyncMock), \
             patch('src.services.goal_orchestrator.get_orchestrator_error_handler') as mock_error_handler:

            # Setup mocks
            mock_agent_loader = Mock()

            # Create proper mock tools with correct attributes
            tool = Mock()
            tool.name = 'test_tool'
            tool.is_stable = True

            mock_agent_loader.load_agent_team.return_value = {
                'team_id': 'test_team_1',
                'pre_approved_tools': [{'name': 'test_tool', 'instance': tool}],
                'custom_agents': []
            }

            mock_security_validator = Mock()
            mock_security_validator.validate_orchestrator_execution = AsyncMock(return_value={
                'valid': True,
                'checks': [],
                'warnings': [],
                'errors': []
            })

            mock_true_orchestrator_instance = Mock()
            mock_true_orchestrator_instance.execute_2n_plus_1_loop = AsyncMock(return_value={
                'success': True,
                'result': 'Final result',
                'execution_metadata': {'orchestrator_id': 'test_orch_123'}
            })

            mock_handler = AsyncMock()
            mock_handler.update_job_status = AsyncMock()
            mock_error_handler.return_value = mock_handler

            mock_loader.return_value = mock_agent_loader
            mock_security.return_value = mock_security_validator
            mock_true_orchestrator.return_value = mock_true_orchestrator_instance

            # Create orchestrator and execute
            orchestrator = GoalOrchestrator(
                tenant_id=1,
                user_id=1,
                agent_team_id='test_team_1',
                job_id='test_job_123'
            )

            result = await orchestrator.orchestrate_goal('Test goal')

            # Verify all components were called
            mock_security_validator.validate_orchestrator_execution.assert_called_once()
            mock_agent_loader.load_agent_team.assert_called_once()
            mock_true_orchestrator_instance.execute_2n_plus_1_loop.assert_called_once()

            assert result['success'] is True
            assert result['result']['result'] == 'Final result'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
