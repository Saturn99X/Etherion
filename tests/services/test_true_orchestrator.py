"""
Comprehensive tests for the True Orchestrator implementation.

This test suite validates:
- 2N+1 reasoning loop execution
- Specialist agent coordination
- Tool approval and validation
- Error handling and recovery
- Security validation
- Performance characteristics
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime
from typing import Dict, Any, List
import json

from src.services.true_orchestrator import TrueOrchestrator
from src.services.orchestrator_security import get_orchestrator_security_validator
from src.services.orchestrator_error_handler import (
    get_orchestrator_error_handler,
    OrchestratorError,
    AgentTeamNotFoundError,
    ToolApprovalError
)


class TestTrueOrchestrator:
    """Test suite for TrueOrchestrator class."""

    @pytest.fixture
    def mock_orchestrator_config(self) -> Dict[str, Any]:
        """Create a mock orchestrator configuration for testing."""
        return {
            'orchestrator_id': 'test_orch_12345',
            'team_id': 'test_team_1',
            'team_config': {
                'name': 'Test Team',
                'description': 'Test team for orchestrator',
                'pre_approved_tools': [
                    {'name': 'test_tool_1', 'instance': Mock(name='test_tool_1', is_stable=True)},
                    {'name': 'test_tool_2', 'instance': Mock(name='test_tool_2', is_stable=True)}
                ],
                'custom_agents': [
                    {
                        'agent_id': 'agent_1',
                        'name': 'Research Agent',
                        'description': 'Handles research tasks',
                        'system_prompt': 'You are a research specialist.',
                        'tool_names': ['test_tool_1']
                    },
                    {
                        'agent_id': 'agent_2',
                        'name': 'Analysis Agent',
                        'description': 'Handles analysis tasks',
                        'system_prompt': 'You are an analysis specialist.',
                        'tool_names': ['test_tool_2']
                    }
                ]
            },
            'approved_tools': [
                Mock(name='test_tool_1', is_stable=True),
                Mock(name='test_tool_2', is_stable=True)
            ],
            'specialist_agents': [
                {
                    'agent_id': 'agent_1',
                    'name': 'Research Agent',
                    'description': 'Handles research tasks'
                }
            ],
            'execution_context': {
                'tenant_id': 1,
                'user_id': 1,
                'job_id': 'test_job_123'
            }
        }

    @pytest.fixture
    def mock_goal(self) -> str:
        """Create a mock goal for testing."""
        return "Create a comprehensive research report on artificial intelligence trends in 2024"

    @pytest.fixture
    def mock_context(self) -> Dict[str, Any]:
        """Create mock context for testing."""
        return {
            "priority": "high",
            "deadline": "2024-12-31",
            "target_audience": "business_executives"
        }

    @pytest.fixture
    def mock_output_format(self) -> str:
        """Create mock output format instructions."""
        return "Return results as a JSON object with keys: summary, findings, recommendations"

    @pytest.fixture
    def true_orchestrator(
        self,
        mock_orchestrator_config: Dict[str, Any],
        mock_goal: str,
        mock_context: Dict[str, Any],
        mock_output_format: str
    ) -> TrueOrchestrator:
        """Create a TrueOrchestrator instance for testing."""
        return TrueOrchestrator(
            orchestrator_config=mock_orchestrator_config,
            goal=mock_goal,
            context=mock_context,
            output_format_instructions=mock_output_format
        )

    def test_true_orchestrator_initialization(
        self,
        true_orchestrator: TrueOrchestrator,
        mock_orchestrator_config: Dict[str, Any],
        mock_goal: str,
        mock_context: Dict[str, Any],
        mock_output_format: str
    ):
        """Test TrueOrchestrator initialization."""
        assert true_orchestrator.config == mock_orchestrator_config
        assert true_orchestrator.goal == mock_goal
        assert true_orchestrator.context == mock_context
        assert true_orchestrator.output_format_instructions == mock_output_format
        assert true_orchestrator.orchestrator_id == mock_orchestrator_config['orchestrator_id']
        assert len(true_orchestrator.execution_results) == 0
        assert true_orchestrator.current_plan is None

    @pytest.mark.asyncio
    async def test_analyze_goal_success(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test successful goal analysis."""
        # Mock the orchestrator agent since it's a dict in test mode
        mock_ainvoke = AsyncMock(return_value={
            'output': json.dumps({
                "analysis": "Goal analysis completed successfully",
                "execution_plan": {
                    "total_steps": 3,
                    "estimated_complexity": "medium",
                    "steps": [
                        {
                            "step_id": "1",
                            "description": "Research AI trends",
                            "agent_id": "agent_1",
                            "estimated_time": "2-3 minutes",
                            "dependencies": [],
                            "success_criteria": "Gather comprehensive AI trend data"
                        },
                        {
                            "step_id": "2",
                            "description": "Analyze findings",
                            "agent_id": "agent_1",
                            "estimated_time": "1-2 minutes",
                            "dependencies": ["1"],
                            "success_criteria": "Provide clear analysis of trends"
                        },
                        {
                            "step_id": "3",
                            "description": "Generate report",
                            "agent_id": "agent_1",
                            "estimated_time": "1-2 minutes",
                            "dependencies": ["1", "2"],
                            "success_criteria": "Create comprehensive report"
                        }
                    ]
                }
            })
        })
        true_orchestrator.orchestrator_agent["ainvoke"] = mock_ainvoke

        result = await true_orchestrator._analyze_goal()

        assert 'analysis' in result
        assert 'execution_plan' in result
        assert result['execution_plan']['total_steps'] == 3
        assert len(result['execution_plan']['steps']) == 3
        assert result['execution_plan']['estimated_complexity'] == "medium"

    @pytest.mark.asyncio
    async def test_analyze_goal_fallback(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test goal analysis fallback when orchestrator agent fails."""
        # Mock the orchestrator agent since it's a dict in test mode
        mock_ainvoke = AsyncMock(return_value={
            'output': "Invalid JSON response"
        })
        true_orchestrator.orchestrator_agent["ainvoke"] = mock_ainvoke

        result = await true_orchestrator._analyze_goal()

        # Should return fallback plan
        assert 'analysis' in result
        assert 'execution_plan' in result
        assert result['execution_plan']['total_steps'] == 1
        assert len(result['execution_plan']['steps']) == 1

    @pytest.mark.asyncio
    async def test_formulate_specialist_instruction(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test specialist instruction formulation."""
        step = {
            "step_id": "1",
            "description": "Research AI trends",
            "agent_id": "agent_1",
            "success_criteria": "Gather comprehensive AI trend data"
        }

        previous_results = [
            {
                "agent_id": "setup_agent",
                "step_id": "0",
                "description": "Initial setup",
                "output": "Setup completed successfully"
            }
        ]

        goal = "Create research report"

        instruction = await true_orchestrator._formulate_specialist_instruction(
            step, previous_results, goal
        )

        assert isinstance(instruction, str)
        assert "Research AI trends" in instruction
        assert "agent_1" not in instruction  # agent_id is not in the instruction text, it's in the JSON structure
        assert "Previous step results" in instruction
        assert "Create research report" in instruction

    @pytest.mark.asyncio
    async def test_execute_specialist_success(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test successful specialist execution."""
        # This is a mock test since actual agent execution would require
        # complex setup. In real tests, we would mock the agent runtime.

        agent_id = "agent_1"
        instruction = "Test instruction"

        result = await true_orchestrator._execute_specialist(agent_id, instruction)

        assert isinstance(result, dict)
        assert result["agent_id"] == agent_id
        assert "execution_summary" in result
        assert "output" in result
        assert "confidence_score" in result

    @pytest.mark.asyncio
    async def test_execute_specialist_not_found(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test specialist execution when agent not found."""
        agent_id = "nonexistent_agent"
        instruction = "Test instruction"

        result = await true_orchestrator._execute_specialist(agent_id, instruction)

        assert isinstance(result, dict)
        assert result["agent_id"] == agent_id
        assert result["metadata"]["error"] is True
        assert "not found" in result["output"].lower()

    @pytest.mark.asyncio
    async def test_validate_specialist_output_valid(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test validation of valid specialist output."""
        result = {
            "agent_id": "agent_1",
            "step_id": "1",
            "execution_summary": "Task completed successfully",
            "output": "Detailed analysis results",
            "confidence_score": 85,
            "metadata": {}
        }

        step = {
            "step_id": "1",
            "description": "Test step"
        }

        goal = "Test goal"

        validation = await true_orchestrator._validate_specialist_output(result, step, goal)

        assert validation["valid"] is True
        assert len(validation["issues"]) == 0
        assert validation["confidence"] == 85

    @pytest.mark.asyncio
    async def test_validate_specialist_output_invalid(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test validation of invalid specialist output."""
        result = {
            "agent_id": "agent_1",
            "step_id": "1",
            "execution_summary": "Task failed",
            "output": "",  # Empty output
            "confidence_score": 10,  # Low confidence
            "metadata": {"error": True}
        }

        step = {
            "step_id": "1",
            "description": "Test step"
        }

        goal = "Test goal"

        validation = await true_orchestrator._validate_specialist_output(result, step, goal)

        assert validation["valid"] is False
        assert len(validation["issues"]) > 0
        assert "Low confidence score: 10" in validation["issues"]  # The actual issue message includes the score
        assert "Output appears to be too short or empty" in validation["issues"]  # The actual issue message

    @pytest.mark.asyncio
    async def test_synthesize_results_success(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test successful result synthesis."""
        # Mock the orchestrator agent since it's a dict in test mode
        mock_ainvoke = AsyncMock(return_value={
            'output': json.dumps({
                "success": True,
                "output": "Final synthesized report",
                "summary": "All tasks completed successfully",
                "key_insights": ["Insight 1", "Insight 2"],
                "limitations": [],
                "metadata": {
                    "steps_completed": 3,
                    "total_confidence": 85
                }
            })
        })
        true_orchestrator.orchestrator_agent["ainvoke"] = mock_ainvoke

        execution_results = [
            {
                "agent_id": "agent_1",
                "step_id": "1",
                "output": "Research completed",
                "confidence_score": 90
            },
            {
                "agent_id": "agent_2",
                "step_id": "2",
                "output": "Analysis completed",
                "confidence_score": 80
            }
        ]

        goal = "Create research report"

        result = await true_orchestrator._synthesize_results(execution_results, goal)

        assert result["success"] is True
        assert "output" in result
        assert "summary" in result
        assert "key_insights" in result

    @pytest.mark.asyncio
    async def test_synthesize_results_fallback(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test result synthesis fallback."""
        # Mock the orchestrator agent since it's a dict in test mode
        mock_ainvoke = AsyncMock(return_value={
            'output': "Invalid JSON response"
        })
        true_orchestrator.orchestrator_agent["ainvoke"] = mock_ainvoke

        execution_results = [
            {
                "agent_id": "agent_1",
                "step_id": "1",
                "output": "Research completed",
                "confidence_score": 90
            }
        ]

        goal = "Create research report"

        result = await true_orchestrator._synthesize_results(execution_results, goal)

        # Should return fallback response
        assert result["success"] is True
        assert "output" in result
        assert "Goal completed" in result["output"]

    @pytest.mark.asyncio
    async def test_execute_2n_plus_1_loop_success(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test successful 2N+1 loop execution."""
        with patch.object(true_orchestrator, '_analyze_goal', new_callable=AsyncMock) as mock_analyze, \
             patch.object(true_orchestrator, '_execute_specialist', new_callable=AsyncMock) as mock_execute, \
             patch.object(true_orchestrator, '_validate_specialist_output', new_callable=AsyncMock) as mock_validate, \
             patch.object(true_orchestrator, '_synthesize_results', new_callable=AsyncMock) as mock_synthesize:

            # Mock successful responses
            mock_analyze.return_value = {
                "analysis": "Analysis completed",
                "execution_plan": {
                    "total_steps": 2,
                    "estimated_complexity": "simple",
                    "steps": [
                        {
                            "step_id": "1",
                            "description": "Step 1",
                            "agent_id": "agent_1",
                            "success_criteria": "Complete step 1"
                        },
                        {
                            "step_id": "2",
                            "description": "Step 2",
                            "agent_id": "agent_1",
                            "success_criteria": "Complete step 2"
                        }
                    ]
                }
            }

            mock_execute.return_value = {
                "agent_id": "agent_1",
                "step_id": "1",
                "execution_summary": "Step completed",
                "output": "Step result",
                "confidence_score": 85,
                "metadata": {}
            }

            mock_validate.return_value = {
                "valid": True,
                "issues": [],
                "confidence": 85
            }

            mock_synthesize.return_value = {
                "success": True,
                "output": "Final result",
                "summary": "All steps completed",
                "key_insights": ["Insight 1"],
                "metadata": {"steps_completed": 2}
            }

            result = await true_orchestrator.execute_2n_plus_1_loop()

            assert result["success"] is True
            assert "result" in result
            assert "execution_metadata" in result
            assert result["execution_metadata"]["steps_executed"] == 2
            assert result["execution_metadata"]["orchestrator_id"] == true_orchestrator.orchestrator_id

    @pytest.mark.asyncio
    async def test_execute_2n_plus_1_loop_with_replanning(
        self,
        true_orchestrator: TrueOrchestrator
    ):
        """Test 2N+1 loop with replanning due to validation failure."""
        with patch.object(true_orchestrator, '_analyze_goal', new_callable=AsyncMock) as mock_analyze, \
             patch.object(true_orchestrator, '_execute_specialist', new_callable=AsyncMock) as mock_execute, \
             patch.object(true_orchestrator, '_validate_specialist_output', new_callable=AsyncMock) as mock_validate, \
             patch.object(true_orchestrator, '_replan_execution', new_callable=AsyncMock) as mock_replan, \
             patch.object(true_orchestrator, '_synthesize_results', new_callable=AsyncMock) as mock_synthesize:

            # Mock initial analysis
            mock_analyze.return_value = {
                "analysis": "Analysis completed",
                "execution_plan": {
                    "total_steps": 2,
                    "estimated_complexity": "simple",
                    "steps": [
                        {
                            "step_id": "1",
                            "description": "Step 1",
                            "agent_id": "agent_1",
                            "success_criteria": "Complete step 1"
                        }
                    ]
                }
            }

            # Mock execution and validation failure
            mock_execute.return_value = {
                "agent_id": "agent_1",
                "step_id": "1",
                "execution_summary": "Step failed",
                "output": "Poor result",
                "confidence_score": 20,
                "metadata": {}
            }

            mock_validate.return_value = {
                "valid": False,
                "issues": ["Low confidence", "Poor quality"],
                "confidence": 20
            }

            # Mock replanning
            mock_replan.return_value = {
                "total_steps": 1,
                "estimated_complexity": "simple",
                "steps": [
                    {
                        "step_id": "1_replanned",
                        "description": "Replanned step 1",
                        "agent_id": "agent_1",
                        "success_criteria": "Complete replanned step 1"
                    }
                ]
            }

            # Mock successful synthesis after replanning
            mock_synthesize.return_value = {
                "success": True,
                "output": "Final result after replanning",
                "summary": "Replanning successful",
                "key_insights": ["Replanning worked"],
                "metadata": {"steps_completed": 1}
            }

            result = await true_orchestrator.execute_2n_plus_1_loop()

            # Verify replanning was called
            mock_replan.assert_called_once()

            assert result["success"] is True
            assert "result" in result
            # The result is the output string from the synthesis result
            output = result["result"]
            assert isinstance(output, str)
            assert "Final result after replanning" in output  # The synthesis output contains this text


class TestOrchestratorErrorHandling:
    """Test suite for orchestrator error handling."""

    @pytest.mark.asyncio
    async def test_error_handler_creation(self):
        """Test error handler creation."""
        error_handler = get_orchestrator_error_handler()
        assert error_handler is not None
        assert error_handler.circuit_breaker_threshold == 5
        assert error_handler.circuit_breaker_timeout == 60

    @pytest.mark.asyncio
    async def test_error_classification(self):
        """Test error classification."""
        error_handler = get_orchestrator_error_handler()

        # Test AgentTeamNotFoundError
        error = AgentTeamNotFoundError("test_team", 1)
        classification = error_handler._classify_error(error)

        assert classification["severity"] == "high"
        assert classification["category"] == "configuration"
        assert classification["error_type"] == "AgentTeamNotFoundError"
        assert classification["recoverable"] is True

        # Test ToolApprovalError
        error = ToolApprovalError("test_tool", "test_team", "Not approved")
        classification = error_handler._classify_error(error)

        assert classification["severity"] == "high"
        assert classification["category"] == "security"
        assert classification["error_type"] == "ToolApprovalError"
        assert classification["recoverable"] is True

    @pytest.mark.asyncio
    async def test_circuit_breaker(self):
        """Test circuit breaker functionality."""
        error_handler = get_orchestrator_error_handler()

        # Test initial state
        assert await error_handler.check_circuit_breaker("test_component") is True

        # Simulate failures
        for i in range(6):
            error_handler._update_circuit_breaker(
                Exception("Test error"),
                {"component": "test_component"}
            )

        # Circuit should be open after threshold
        assert await error_handler.check_circuit_breaker("test_component") is False

        # Test circuit breaker reset
        error_handler.circuit_breaker_state["test_component"]["opened_at"] = datetime(
            datetime.now().year - 2, 1, 1  # 2 years ago
        )

        assert await error_handler.check_circuit_breaker("test_component") is True


class TestOrchestratorSecurity:
    """Test suite for orchestrator security validation."""

    @pytest.mark.asyncio
    async def test_security_validator_creation(self):
        """Test security validator creation."""
        security_validator = get_orchestrator_security_validator()
        assert security_validator is not None
        assert security_validator.tool_manager is not None

    @pytest.mark.asyncio
    async def test_tenant_isolation_validation(self):
        """Test tenant isolation validation."""
        security_validator = get_orchestrator_security_validator()

        # Test valid tenant/user
        result = await security_validator._validate_tenant_isolation(1, 1)
        assert result["check"] == "tenant_isolation"
        assert result["valid"] is True

        # Test invalid tenant
        result = await security_validator._validate_tenant_isolation(0, 1)
        assert result["check"] == "tenant_isolation"
        assert result["valid"] is False

        # Test invalid user
        result = await security_validator._validate_tenant_isolation(1, 0)
        assert result["check"] == "tenant_isolation"
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_job_context_validation(self):
        """Test job context validation."""
        security_validator = get_orchestrator_security_validator()

        # Test valid job ID
        result = security_validator._validate_job_context("job_123456", 1, 1)
        assert result["check"] == "job_context"
        assert result["valid"] is True

        # Test invalid job ID (too short)
        result = security_validator._validate_job_context("job", 1, 1)
        assert result["check"] == "job_context"
        assert result["valid"] is False

        # Test invalid job ID (invalid characters)
        result = security_validator._validate_job_context("job@#$%", 1, 1)
        assert result["check"] == "job_context"
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_execution_limits_validation(self):
        """Test execution limits validation."""
        security_validator = get_orchestrator_security_validator()

        # Mock current executions
        with patch.object(security_validator, '_get_current_executions', return_value=3):
            result = await security_validator.validate_execution_limits(1, 1)
            assert result["check"] == "execution_limits"
            assert result["valid"] is True

        # Test limit exceeded
        with patch.object(security_validator, '_get_current_executions', return_value=15):
            result = await security_validator.validate_execution_limits(1, 1)
            assert result["check"] == "execution_limits"
            assert result["valid"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
