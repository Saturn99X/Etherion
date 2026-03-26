"""
Unit tests for Team Orchestrator checklist creation (Step 2.5).

Tests that the Team Orchestrator correctly creates:
- Global checklist at job start
- Specialist checklists for each team member
- Emits checklist events to trace
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.services.team_orchestrator import TeamOrchestrator


@pytest.mark.asyncio
async def test_global_checklist_created():
    """Test that global checklist is created at job start."""
    orchestrator = TeamOrchestrator(
        team_id="test_team",
        tenant_id=1,
        user_id=1
    )
    
    team_config = {
        'job_id': 'test_job_123',
        'approved_tools': [],
        'specialist_agents': [],
        'max_iterations': 2
    }
    
    with patch.dict('os.environ', {'ENABLE_CHECKLIST_MODE': 'true'}):
        with patch('src.services.team_orchestrator.get_agent_loader') as mock_loader:
            with patch('src.services.team_orchestrator.core_redis') as mock_redis:
                with patch('src.services.team_orchestrator.log_security_event', new_callable=AsyncMock):
                    with patch('src.services.team_orchestrator.build_runtime_from_config') as mock_runtime:
                        # Setup mocks
                        mock_loader.return_value.load_agent_team = AsyncMock(return_value=None)
                        mock_redis.publish_execution_trace = AsyncMock()
                        mock_redis.is_job_cancelled = AsyncMock(return_value=True)  # Stop immediately
                        
                        # Mock runtime to return finish immediately
                        mock_runtime_instance = Mock()
                        mock_runtime_instance.ainvoke = AsyncMock(return_value={"output": '{"actions": [{"type": "finish"}]}'})
                        mock_runtime.return_value = mock_runtime_instance
                        
                        # Execute
                        await orchestrator.execute_2n_plus_1_loop("Test goal", team_config)
                        
                        # Verify global checklist was created
                        assert orchestrator.global_checklist is not None
                        assert orchestrator.global_checklist.owner_type == "team"
                        assert orchestrator.global_checklist.owner_id == "test_team"


@pytest.mark.asyncio
async def test_specialist_checklists_created():
    """Test that specialist checklists are created for each team member."""
    orchestrator = TeamOrchestrator(
        team_id="test_team",
        tenant_id=1,
        user_id=1
    )
    
    team_config = {
        'job_id': 'test_job_123',
        'approved_tools': [],
        'specialist_agents': [
            {'agent_id': 'specialist_1', 'name': 'Specialist One'},
            {'agent_id': 'specialist_2', 'name': 'Specialist Two'}
        ],
        'max_iterations': 2
    }
    
    with patch.dict('os.environ', {'ENABLE_CHECKLIST_MODE': 'true'}):
        with patch('src.services.team_orchestrator.get_agent_loader') as mock_loader:
            with patch('src.services.team_orchestrator.core_redis') as mock_redis:
                with patch('src.services.team_orchestrator.log_security_event', new_callable=AsyncMock):
                    with patch('src.services.team_orchestrator.build_runtime_from_config') as mock_runtime:
                        # Setup mocks
                        mock_loader.return_value.load_agent_team = AsyncMock(return_value=None)
                        mock_loader.return_value.create_agent_executor = Mock(return_value=None)
                        mock_redis.publish_execution_trace = AsyncMock()
                        mock_redis.is_job_cancelled = AsyncMock(return_value=True)
                        
                        mock_runtime_instance = Mock()
                        mock_runtime_instance.ainvoke = AsyncMock(return_value={"output": '{"actions": [{"type": "finish"}]}'})
                        mock_runtime.return_value = mock_runtime_instance
                        
                        # Execute
                        await orchestrator.execute_2n_plus_1_loop("Test goal", team_config)
                        
                        # Verify specialist checklists were created
                        assert len(orchestrator.specialist_checklists) == 2
                        assert 'specialist_1' in orchestrator.specialist_checklists
                        assert 'specialist_2' in orchestrator.specialist_checklists
                        
                        # Verify checklist properties
                        checklist_1 = orchestrator.specialist_checklists['specialist_1']
                        assert checklist_1.owner_type == "specialist"
                        assert checklist_1.owner_id == "specialist_1"


@pytest.mark.asyncio
async def test_checklist_events_emitted():
    """Test that CHECKLIST_CREATED events are emitted to trace."""
    orchestrator = TeamOrchestrator(
        team_id="test_team",
        tenant_id=1,
        user_id=1
    )
    
    team_config = {
        'job_id': 'test_job_123',
        'approved_tools': [],
        'specialist_agents': [{'agent_id': 'specialist_1', 'name': 'Specialist One'}],
        'max_iterations': 2
    }
    
    with patch.dict('os.environ', {'ENABLE_CHECKLIST_MODE': 'true'}):
        with patch('src.services.team_orchestrator.get_agent_loader') as mock_loader:
            with patch('src.services.team_orchestrator.core_redis') as mock_redis:
                with patch('src.services.team_orchestrator.log_security_event', new_callable=AsyncMock):
                    with patch('src.services.team_orchestrator.build_runtime_from_config') as mock_runtime:
                        # Setup mocks
                        mock_loader.return_value.load_agent_team = AsyncMock(return_value=None)
                        mock_loader.return_value.create_agent_executor = Mock(return_value=None)
                        mock_redis.publish_execution_trace = AsyncMock()
                        mock_redis.is_job_cancelled = AsyncMock(return_value=True)
                        
                        mock_runtime_instance = Mock()
                        mock_runtime_instance.ainvoke = AsyncMock(return_value={"output": '{"actions": [{"type": "finish"}]}'})
                        mock_runtime.return_value = mock_runtime_instance
                        
                        # Execute
                        await orchestrator.execute_2n_plus_1_loop("Test goal", team_config)
                        
                        # Verify CHECKLIST_CREATED events were emitted
                        calls = mock_redis.publish_execution_trace.call_args_list
                        checklist_events = [
                            call for call in calls
                            if len(call.kwargs) > 0 and call.kwargs.get('event_data', {}).get('type') == 'CHECKLIST_CREATED'
                        ]
                        
                        # Should have 2 events: 1 global + 1 specialist
                        assert len(checklist_events) >= 2
                        
                        # Verify global checklist event
                        global_event = next(
                            (e for e in checklist_events if e.kwargs.get('event_data', {}).get('owner_type') == 'team'),
                            None
                        )
                        assert global_event is not None
                        assert global_event.kwargs['event_data']['owner_id'] == 'test_team'
                        
                        # Verify specialist checklist event
                        specialist_event = next(
                            (e for e in checklist_events if e.kwargs.get('event_data', {}).get('owner_type') == 'specialist'),
                            None
                        )
                        assert specialist_event is not None
                        assert specialist_event.kwargs['event_data']['owner_id'] == 'specialist_1'


@pytest.mark.asyncio
async def test_execution_mode_selected_event():
    """Test that EXECUTION_MODE_SELECTED event is emitted."""
    orchestrator = TeamOrchestrator(
        team_id="test_team",
        tenant_id=1,
        user_id=1
    )
    
    team_config = {
        'job_id': 'test_job_123',
        'approved_tools': [],
        'specialist_agents': [
            {'agent_id': 'specialist_1', 'name': 'Specialist One'},
            {'agent_id': 'specialist_2', 'name': 'Specialist Two'}
        ],
        'max_iterations': 2
    }
    
    with patch.dict('os.environ', {'ENABLE_CHECKLIST_MODE': 'true'}):
        with patch('src.services.team_orchestrator.get_agent_loader') as mock_loader:
            with patch('src.services.team_orchestrator.core_redis') as mock_redis:
                with patch('src.services.team_orchestrator.log_security_event', new_callable=AsyncMock):
                    with patch('src.services.team_orchestrator.build_runtime_from_config') as mock_runtime:
                        # Setup mocks
                        mock_loader.return_value.load_agent_team = AsyncMock(return_value=None)
                        mock_loader.return_value.create_agent_executor = Mock(return_value=None)
                        mock_redis.publish_execution_trace = AsyncMock()
                        mock_redis.is_job_cancelled = AsyncMock(return_value=True)
                        
                        mock_runtime_instance = Mock()
                        mock_runtime_instance.ainvoke = AsyncMock(return_value={"output": '{"actions": [{"type": "finish"}]}'})
                        mock_runtime.return_value = mock_runtime_instance
                        
                        # Execute
                        await orchestrator.execute_2n_plus_1_loop("Test goal", team_config)
                        
                        # Verify EXECUTION_MODE_SELECTED event was emitted
                        calls = mock_redis.publish_execution_trace.call_args_list
                        mode_events = [
                            call for call in calls
                            if len(call.kwargs) > 0 and call.kwargs.get('event_data', {}).get('type') == 'EXECUTION_MODE_SELECTED'
                        ]
                        
                        assert len(mode_events) == 1
                        mode_event = mode_events[0].kwargs['event_data']
                        assert 'mode' in mode_event
                        assert mode_event['mode'] in ['sequential', 'parallel']
                        assert 'reason' in mode_event
                        assert 'confidence' in mode_event


@pytest.mark.asyncio
async def test_checklist_mode_disabled():
    """Test that checklists are not created when ENABLE_CHECKLIST_MODE=false."""
    orchestrator = TeamOrchestrator(
        team_id="test_team",
        tenant_id=1,
        user_id=1
    )
    
    team_config = {
        'job_id': 'test_job_123',
        'approved_tools': [],
        'specialist_agents': [{'agent_id': 'specialist_1', 'name': 'Specialist One'}],
        'max_iterations': 2
    }
    
    with patch.dict('os.environ', {'ENABLE_CHECKLIST_MODE': 'false'}):
        with patch('src.services.team_orchestrator.get_agent_loader') as mock_loader:
            with patch('src.services.team_orchestrator.core_redis') as mock_redis:
                with patch('src.services.team_orchestrator.log_security_event', new_callable=AsyncMock):
                    with patch('src.services.team_orchestrator.build_runtime_from_config') as mock_runtime:
                        # Setup mocks
                        mock_loader.return_value.load_agent_team = AsyncMock(return_value=None)
                        mock_loader.return_value.create_agent_executor = Mock(return_value=None)
                        mock_redis.publish_execution_trace = AsyncMock()
                        mock_redis.is_job_cancelled = AsyncMock(return_value=True)
                        
                        mock_runtime_instance = Mock()
                        mock_runtime_instance.ainvoke = AsyncMock(return_value={"output": '{"actions": [{"type": "finish"}]}'})
                        mock_runtime.return_value = mock_runtime_instance
                        
                        # Execute
                        await orchestrator.execute_2n_plus_1_loop("Test goal", team_config)
                        
                        # Verify checklists were NOT created
                        assert orchestrator.global_checklist is None
                        assert len(orchestrator.specialist_checklists) == 0
                        
                        # Verify no CHECKLIST_CREATED events
                        calls = mock_redis.publish_execution_trace.call_args_list
                        checklist_events = [
                            call for call in calls
                            if len(call.kwargs) > 0 and call.kwargs.get('event_data', {}).get('type') == 'CHECKLIST_CREATED'
                        ]
                        assert len(checklist_events) == 0
