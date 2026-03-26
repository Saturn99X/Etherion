"""
End-to-end integration tests for checklist-based orchestration.

Tests complete workflows including:
- Simple task with sequential execution
- Complex task with sequential execution
- Tool request approval/rejection
- Checklist completion detection
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from src.services.team_orchestrator import TeamOrchestrator
from src.services.checklist_manager import ChecklistManager
from src.services.tool_request_queue import ToolRequestQueue
from src.services.execution_mode import ExecutionModeController, ExecutionMode
from src.database.models import Job, JobStatus
from datetime import datetime
import os


@pytest.fixture
def enable_checklist_mode():
    """Enable checklist mode for tests."""
    original = os.environ.get('ENABLE_CHECKLIST_MODE')
    os.environ['ENABLE_CHECKLIST_MODE'] = 'true'
    yield
    if original is not None:
        os.environ['ENABLE_CHECKLIST_MODE'] = original
    else:
        os.environ.pop('ENABLE_CHECKLIST_MODE', None)


@pytest.fixture
def team_config():
    """Create a sample team configuration."""
    return {
        'job_id': 'test_job_e2e_123',
        'name': 'Test Team',
        'description': 'E2E test team',
        'approved_tools': [
            {'name': 'unified_research_tool', 'instance': Mock(), 'type': 'tool'}
        ],
        'specialist_agents': [
            {
                'agent_id': 'specialist_1',
                'name': 'Research Specialist',
                'description': 'Handles research tasks'
            },
            {
                'agent_id': 'specialist_2',
                'name': 'Analysis Specialist',
                'description': 'Handles analysis tasks'
            }
        ],
        'max_iterations': 3
    }


@pytest.mark.asyncio
async def test_simple_task_sequential_execution(enable_checklist_mode, team_config):
    """Test a simple task with sequential execution mode."""
    orchestrator = TeamOrchestrator(
        team_id='test_team_e2e',
        tenant_id=1,
        user_id=100
    )
    
    # Mock database and external dependencies
    with patch('src.services.team_orchestrator.session_scope'), \
         patch('src.services.team_orchestrator.get_agent_loader'), \
         patch('src.services.team_orchestrator.core_redis'), \
         patch('src.services.team_orchestrator.log_security_event'), \
         patch('src.services.team_orchestrator._get_replay_service_safe', return_value=None):
        
        # Mock team config loading
        orchestrator.team_config = team_config
        orchestrator.approved_tools = team_config['approved_tools']
        orchestrator.specialist_agents = team_config['specialist_agents']
        
        # Verify checklist manager is initialized
        assert orchestrator.checklist_manager is not None
        assert isinstance(orchestrator.checklist_manager, ChecklistManager)
        
        # Verify execution mode controller is initialized
        assert orchestrator.execution_mode_controller is not None
        assert isinstance(orchestrator.execution_mode_controller, ExecutionModeController)
        
        # Verify tool request queue is initialized
        assert orchestrator.tool_request_queue is not None
        assert isinstance(orchestrator.tool_request_queue, ToolRequestQueue)


@pytest.mark.asyncio
async def test_checklist_creation_on_job_start(enable_checklist_mode, team_config):
    """Test that checklists are created when a job starts."""
    orchestrator = TeamOrchestrator(
        team_id='test_team_e2e',
        tenant_id=1,
        user_id=100
    )
    
    with patch('src.services.team_orchestrator.session_scope'), \
         patch('src.services.team_orchestrator.get_agent_loader'), \
         patch('src.services.team_orchestrator.core_redis') as mock_redis, \
         patch('src.services.team_orchestrator.log_security_event'), \
         patch('src.services.team_orchestrator._get_replay_service_safe', return_value=None), \
         patch('src.services.team_orchestrator.build_runtime_from_config') as mock_runtime:
        
        # Mock runtime responses
        mock_runtime_instance = AsyncMock()
        mock_runtime_instance.ainvoke = AsyncMock(return_value={
            "output": '{"actions": [{"type": "finish"}]}',
            "analytics": {}
        })
        mock_runtime.return_value = mock_runtime_instance
        
        # Mock Redis methods
        mock_redis.publish_execution_trace = AsyncMock()
        mock_redis.is_job_cancelled = AsyncMock(return_value=False)
        
        orchestrator.team_config = team_config
        orchestrator.approved_tools = team_config['approved_tools']
        orchestrator.specialist_agents = team_config['specialist_agents']
        
        # Execute orchestration
        goal = "Simple test task"
        result = await orchestrator.execute_2n_plus_1_loop(goal, team_config)
        
        # Verify global checklist was created
        assert orchestrator.global_checklist is not None
        assert orchestrator.global_checklist.owner_type == "team"
        assert len(orchestrator.global_checklist.items) > 0
        
        # Verify specialist checklists were created
        assert len(orchestrator.specialist_checklists) == 2
        assert 'specialist_1' in orchestrator.specialist_checklists
        assert 'specialist_2' in orchestrator.specialist_checklists


@pytest.mark.asyncio
async def test_execution_mode_selection(enable_checklist_mode):
    """Test that execution mode is selected based on task complexity."""
    controller = ExecutionModeController()
    
    # Simple task should select sequential mode
    simple_decision = controller.select_mode(
        task_description="What is 2+2?",
        specialist_count=2,
        tool_count=3
    )
    assert simple_decision.mode == ExecutionMode.SEQUENTIAL
    assert simple_decision.confidence > 0.5
    
    # Complex task should also select sequential (parallel is deferred)
    complex_decision = controller.select_mode(
        task_description="Analyze the entire codebase, refactor all modules, update documentation, and deploy to production",
        specialist_count=5,
        tool_count=10
    )
    assert complex_decision.mode == ExecutionMode.SEQUENTIAL


@pytest.mark.asyncio
async def test_tool_request_validation(enable_checklist_mode):
    """Test tool request validation with justification."""
    orchestrator = TeamOrchestrator(
        team_id='test_team_e2e',
        tenant_id=1,
        user_id=100
    )
    
    with patch('src.services.team_orchestrator.core_redis') as mock_redis:
        mock_redis.publish_execution_trace = AsyncMock()
        
        # Valid justification should be approved
        valid_result = await orchestrator._validate_tool_request(
            tool_name="unified_research_tool",
            tool_input={
                "_justification": {
                    "what": "Execute unified_research_tool to search knowledge base",
                    "how": "Using unified_research_tool with query parameter to search for relevant documents",
                    "why": "Need to gather information from knowledge base to answer user question"
                }
            },
            job_id="test_job_123",
            step=0,
            index=0
        )
        assert valid_result["approved"] is True
        
        # Invalid justification (too short) should be rejected
        invalid_result = await orchestrator._validate_tool_request(
            tool_name="unified_research_tool",
            tool_input={
                "_justification": {
                    "what": "Search",
                    "how": "Tool",
                    "why": "Need"
                }
            },
            job_id="test_job_123",
            step=0,
            index=0
        )
        assert invalid_result["approved"] is False
        assert "too short" in invalid_result["reason"]


@pytest.mark.asyncio
async def test_tool_request_without_tool_name_mention(enable_checklist_mode):
    """Test that tool requests must mention the tool name in justification."""
    orchestrator = TeamOrchestrator(
        team_id='test_team_e2e',
        tenant_id=1,
        user_id=100
    )
    
    with patch('src.services.team_orchestrator.core_redis') as mock_redis:
        mock_redis.publish_execution_trace = AsyncMock()
        
        # Justification that doesn't mention tool name should be rejected
        result = await orchestrator._validate_tool_request(
            tool_name="unified_research_tool",
            tool_input={
                "_justification": {
                    "what": "Execute a search operation to find documents",
                    "how": "Using the search functionality with query parameters",
                    "why": "Need to gather information from the knowledge base"
                }
            },
            job_id="test_job_123",
            step=0,
            index=0
        )
        assert result["approved"] is False
        assert "does not mention tool name" in result["reason"]


@pytest.mark.asyncio
async def test_checklist_completion_detection():
    """Test that checklist completion is detected correctly."""
    manager = ChecklistManager()
    
    checklist = manager.create_checklist(
        owner_id="test_owner",
        owner_type="team",
        task_description="Task with 3 items"
    )
    
    # Initially not complete
    assert not manager.is_complete(checklist.id)
    
    # Complete all items
    for item in checklist.items:
        manager.mark_item_complete(checklist.id, item.id)
    
    # Now should be complete
    assert manager.is_complete(checklist.id)
    
    # Verify completion timestamp is set
    updated_checklist = manager.get_checklist(checklist.id)
    assert updated_checklist.completed_at is not None


@pytest.mark.asyncio
async def test_backward_compatibility_legacy_mode():
    """Test that legacy mode (ENABLE_CHECKLIST_MODE=false) works."""
    # Disable checklist mode
    os.environ['ENABLE_CHECKLIST_MODE'] = 'false'
    
    try:
        orchestrator = TeamOrchestrator(
            team_id='test_team_legacy',
            tenant_id=1,
            user_id=100
        )
        
        with patch('src.services.team_orchestrator.core_redis') as mock_redis:
            mock_redis.publish_execution_trace = AsyncMock()
            
            # In legacy mode, all tools should be auto-approved
            result = await orchestrator._validate_tool_request(
                tool_name="any_tool",
                tool_input={},
                job_id="test_job_123",
                step=0,
                index=0
            )
            assert result["approved"] is True
            assert "Legacy mode" in result["reason"]
    finally:
        os.environ['ENABLE_CHECKLIST_MODE'] = 'true'


@pytest.mark.asyncio
async def test_tool_request_queue_fifo_ordering():
    """Test that tool request queue maintains FIFO ordering."""
    queue = ToolRequestQueue()
    
    from src.services.tool_request_queue import ToolJustification
    
    # Submit multiple requests
    request1 = queue.submit_request(
        specialist_id="specialist_1",
        tool_name="tool_a",
        parameters={},
        justification=ToolJustification(
            what="Execute tool_a",
            how="Using tool_a with parameters",
            why="Required for task"
        )
    )
    
    request2 = queue.submit_request(
        specialist_id="specialist_2",
        tool_name="tool_b",
        parameters={},
        justification=ToolJustification(
            what="Execute tool_b",
            how="Using tool_b with parameters",
            why="Required for task"
        )
    )
    
    request3 = queue.submit_request(
        specialist_id="specialist_1",
        tool_name="tool_c",
        parameters={},
        justification=ToolJustification(
            what="Execute tool_c",
            how="Using tool_c with parameters",
            why="Required for task"
        )
    )
    
    # Get next pending requests in FIFO order
    next1 = queue.get_next_pending()
    assert next1.id == request1.id
    
    # Approve first request
    queue.approve_request(request1.id, reviewed_by="orchestrator")
    
    # Next pending should be request2
    next2 = queue.get_next_pending()
    assert next2.id == request2.id
    
    # Reject second request
    queue.reject_request(request2.id, reviewed_by="orchestrator", reason="Test rejection")
    
    # Next pending should be request3
    next3 = queue.get_next_pending()
    assert next3.id == request3.id


@pytest.mark.asyncio
async def test_trace_events_emitted(enable_checklist_mode, team_config):
    """Test that all required trace events are emitted."""
    orchestrator = TeamOrchestrator(
        team_id='test_team_e2e',
        tenant_id=1,
        user_id=100
    )
    
    emitted_events = []
    
    async def capture_event(job_id, event_data):
        emitted_events.append(event_data.get("type"))
    
    with patch('src.services.team_orchestrator.session_scope'), \
         patch('src.services.team_orchestrator.get_agent_loader'), \
         patch('src.services.team_orchestrator.core_redis') as mock_redis, \
         patch('src.services.team_orchestrator.log_security_event'), \
         patch('src.services.team_orchestrator._get_replay_service_safe', return_value=None), \
         patch('src.services.team_orchestrator.build_runtime_from_config') as mock_runtime:
        
        # Mock runtime responses
        mock_runtime_instance = AsyncMock()
        mock_runtime_instance.ainvoke = AsyncMock(return_value={
            "output": '{"actions": [{"type": "finish"}]}',
            "analytics": {}
        })
        mock_runtime.return_value = mock_runtime_instance
        
        # Capture emitted events
        mock_redis.publish_execution_trace = AsyncMock(side_effect=capture_event)
        mock_redis.is_job_cancelled = AsyncMock(return_value=False)
        
        orchestrator.team_config = team_config
        orchestrator.approved_tools = team_config['approved_tools']
        orchestrator.specialist_agents = team_config['specialist_agents']
        
        # Execute orchestration
        goal = "Test task for event emission"
        result = await orchestrator.execute_2n_plus_1_loop(goal, team_config)
        
        # Verify required events were emitted
        assert "execution_trace_start" in emitted_events
        assert "TEAM_LOAD" in emitted_events
        assert "CHECKLIST_CREATED" in emitted_events
        assert "EXECUTION_MODE_SELECTED" in emitted_events
        assert "execution_trace_end" in emitted_events


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
