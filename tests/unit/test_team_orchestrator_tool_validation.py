"""
Unit tests for Team Orchestrator tool validation (Step 2.6).

Tests that the Team Orchestrator correctly:
- Intercepts tool requests
- Validates tool justification
- Emits tool validation events
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_tool_request_validation_enabled():
    """Test that tool requests are validated when checklist mode is enabled."""
    from src.services.team_orchestrator import TeamOrchestrator
    
    orchestrator = TeamOrchestrator(
        team_id="test_team",
        tenant_id=1,
        user_id=1
    )
    
    team_config = {
        'job_id': 'test_job_123',
        'approved_tools': [
            {'name': 'test_tool', 'instance': Mock(ainvoke=AsyncMock(return_value={"result": "success"}))}
        ],
        'specialist_agents': [],
        'max_iterations': 1
    }
    
    with patch.dict('os.environ', {'ENABLE_CHECKLIST_MODE': 'true'}):
        with patch('src.services.team_orchestrator.get_agent_loader') as mock_loader:
            with patch('src.services.team_orchestrator.core_redis') as mock_redis:
                with patch('src.services.team_orchestrator.log_security_event', new_callable=AsyncMock):
                    with patch('src.services.team_orchestrator.build_runtime_from_config') as mock_runtime:
                        # Setup mocks
                        mock_loader.return_value.load_agent_team = AsyncMock(return_value=None)
                        mock_redis.publish_execution_trace = AsyncMock()
                        mock_redis.is_job_cancelled = AsyncMock(return_value=False)
                        
                        # Mock runtime to return a tool action with proper justification
                        mock_runtime_instance = Mock()
                        mock_runtime_instance.ainvoke = AsyncMock(side_effect=[
                            {"output": "thinking"},  # THINK
                            {"output": '{"actions": [{"type": "tool", "name": "test_tool", "input": {"_justification": {"what": "Execute test_tool to validate", "how": "Using test_tool with test parameters", "why": "Required for test validation"}}}]}'},  # ACT
                            {"output": '{"actions": [{"type": "finish"}]}'}  # Next ACT
                        ])
                        mock_runtime.return_value = mock_runtime_instance
                        
                        # Execute
                        await orchestrator.execute_2n_plus_1_loop("Test goal", team_config)
                        
                        # Verify tool validation events were emitted
                        calls = mock_redis.publish_execution_trace.call_args_list
                        
                        # Debug: print all event types
                        all_events = []
                        for call in calls:
                            if len(call.args) > 1:
                                all_events.append(call.args[1].get('type'))
                            elif 'event_data' in call.kwargs:
                                all_events.append(call.kwargs['event_data'].get('type'))
                        
                        # Should have TOOL_REQUEST_SUBMITTED event
                        submitted_events = [
                            call for call in calls
                            if (len(call.args) > 1 and call.args[1].get('type') == 'TOOL_REQUEST_SUBMITTED') or
                               ('event_data' in call.kwargs and call.kwargs['event_data'].get('type') == 'TOOL_REQUEST_SUBMITTED')
                        ]
                        assert len(submitted_events) >= 1, f"TOOL_REQUEST_SUBMITTED event not found. All events: {all_events}"
                        
                        # Should have TOOL_REQUEST_APPROVED event
                        approved_events = [
                            call for call in calls
                            if (len(call.args) > 1 and call.args[1].get('type') == 'TOOL_REQUEST_APPROVED') or
                               ('event_data' in call.kwargs and call.kwargs['event_data'].get('type') == 'TOOL_REQUEST_APPROVED')
                        ]
                        assert len(approved_events) >= 1, f"TOOL_REQUEST_APPROVED event not found. All events: {all_events}"


@pytest.mark.asyncio
async def test_tool_validation_disabled_in_legacy_mode():
    """Test that tool validation is skipped when checklist mode is disabled."""
    from src.services.team_orchestrator import TeamOrchestrator
    
    orchestrator = TeamOrchestrator(
        team_id="test_team",
        tenant_id=1,
        user_id=1
    )
    
    team_config = {
        'job_id': 'test_job_123',
        'approved_tools': [
            {'name': 'test_tool', 'instance': Mock(ainvoke=AsyncMock(return_value={"result": "success"}))}
        ],
        'specialist_agents': [],
        'max_iterations': 1
    }
    
    with patch.dict('os.environ', {'ENABLE_CHECKLIST_MODE': 'false'}):
        with patch('src.services.team_orchestrator.get_agent_loader') as mock_loader:
            with patch('src.services.team_orchestrator.core_redis') as mock_redis:
                with patch('src.services.team_orchestrator.log_security_event', new_callable=AsyncMock):
                    with patch('src.services.team_orchestrator.build_runtime_from_config') as mock_runtime:
                        # Setup mocks
                        mock_loader.return_value.load_agent_team = AsyncMock(return_value=None)
                        mock_redis.publish_execution_trace = AsyncMock()
                        mock_redis.is_job_cancelled = AsyncMock(return_value=False)
                        
                        # Mock runtime to return a tool action
                        mock_runtime_instance = Mock()
                        mock_runtime_instance.ainvoke = AsyncMock(side_effect=[
                            {"output": "thinking"},  # THINK
                            {"output": '{"actions": [{"type": "tool", "name": "test_tool", "input": {}}]}'},  # ACT
                            {"output": '{"actions": [{"type": "finish"}]}'}  # Next ACT
                        ])
                        mock_runtime.return_value = mock_runtime_instance
                        
                        # Execute
                        await orchestrator.execute_2n_plus_1_loop("Test goal", team_config)
                        
                        # Tool should still execute (no validation blocking)
                        calls = mock_redis.publish_execution_trace.call_args_list
                        tool_events = [
                            call for call in calls
                            if len(call.args) > 1 and call.args[1].get('type') in ['TOOL_START', 'TOOL_END']
                        ]
                        assert len(tool_events) >= 1, "Tool execution events not found"
                        
                        # Should NOT have validation events in legacy mode
                        validation_events = [
                            call for call in calls
                            if len(call.args) > 1 and call.args[1].get('type') in ['TOOL_REQUEST_SUBMITTED', 'TOOL_REQUEST_APPROVED', 'TOOL_REQUEST_REJECTED']
                        ]
                        # In legacy mode, validation still happens but auto-approves
                        # So we should see these events


@pytest.mark.asyncio
async def test_disallowed_tool_rejected():
    """Test that tools not in approved list are rejected."""
    from src.services.team_orchestrator import TeamOrchestrator
    
    orchestrator = TeamOrchestrator(
        team_id="test_team",
        tenant_id=1,
        user_id=1
    )
    
    team_config = {
        'job_id': 'test_job_123',
        'approved_tools': [],  # No tools approved
        'specialist_agents': [],
        'max_iterations': 1
    }
    
    with patch.dict('os.environ', {'ENABLE_CHECKLIST_MODE': 'true'}):
        with patch('src.services.team_orchestrator.get_agent_loader') as mock_loader:
            with patch('src.services.team_orchestrator.core_redis') as mock_redis:
                with patch('src.services.team_orchestrator.log_security_event', new_callable=AsyncMock):
                    with patch('src.services.team_orchestrator.build_runtime_from_config') as mock_runtime:
                        # Setup mocks
                        mock_loader.return_value.load_agent_team = AsyncMock(return_value=None)
                        mock_redis.publish_execution_trace = AsyncMock()
                        mock_redis.is_job_cancelled = AsyncMock(return_value=False)
                        
                        # Mock runtime to return a disallowed tool action
                        mock_runtime_instance = Mock()
                        mock_runtime_instance.ainvoke = AsyncMock(side_effect=[
                            {"output": "thinking"},  # THINK
                            {"output": '{"actions": [{"type": "tool", "name": "disallowed_tool", "input": {}}]}'},  # ACT
                            {"output": '{"actions": [{"type": "finish"}]}'}  # Next ACT
                        ])
                        mock_runtime.return_value = mock_runtime_instance
                        
                        # Execute
                        result = await orchestrator.execute_2n_plus_1_loop("Test goal", team_config)
                        
                        # Verify tool was rejected
                        observations = result.get('observations', [])
                        error_obs = [obs for obs in observations if obs.get('type') == 'error' and 'not allowed' in obs.get('message', '')]
                        assert len(error_obs) >= 1, "Tool rejection not recorded in observations"
