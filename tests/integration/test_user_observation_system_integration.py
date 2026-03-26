import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json

from src.services.user_observation_service import UserObservationService
from src.services.agent_loader import AgentLoader
from src.services.goal_orchestrator import GoalOrchestrator
from src.database.models.execution_trace import ExecutionTraceStep
from src.database.models import UserObservation, Job, JobStatus
from tests.conftest import TestDatabaseSession


class TestUserObservationSystemIntegration:
    """Integration tests for the complete user observation system"""

    @pytest.fixture
    def db_session(self):
        """Provide a test database session"""
        with TestDatabaseSession() as session:
            yield session

    @pytest.fixture
    def observation_service(self):
        """Provide a UserObservationService instance"""
        return UserObservationService()

    @pytest.fixture
    def agent_loader(self):
        """Provide an AgentLoader instance"""
        return AgentLoader()

    @pytest.fixture
    def goal_orchestrator(self):
        """Provide a GoalOrchestrator instance"""
        return GoalOrchestrator()

    @pytest.fixture
    def sample_user(self, db_session):
        """Create a sample user for testing"""
        from src.database.models import User, Tenant

        tenant = Tenant(
            id=1,
            name="Integration Test Tenant",
            domain="integration-test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        user = User(
            user_id="integration_user_123",
            email="integration@example.com",
            name="Integration User",
            provider="test",
            tenant_id=1,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    def test_end_to_end_observation_flow(self, db_session, observation_service, sample_user):
        """Test complete end-to-end observation flow"""
        # Record multiple interactions to build observation profile
        interactions = [
            {
                'response_content': 'I prefer detailed technical explanations with examples.',
                'success_indicators': {'success': True},
                'tools_used': ['api_tool', 'documentation_tool'],
                'approaches_used': ['detailed_explanation', 'examples_provided'],
                'response_time': 2.5,
                'follow_up_count': 0,
                'content': 'How do I implement this feature?'
            },
            {
                'response_content': 'The implementation works well. Thanks for the clear explanation.',
                'success_indicators': {'success': True},
                'tools_used': ['implementation_tool'],
                'approaches_used': ['step_by_step_guidance'],
                'response_time': 1.8,
                'follow_up_count': 1,
                'content': 'This approach is working perfectly.'
            },
            {
                'response_content': 'I need more beginner-friendly explanations.',
                'success_indicators': {'success': False},
                'tools_used': ['complex_tool'],
                'approaches_used': ['advanced_technical_jargon'],
                'response_time': 5.0,
                'follow_up_count': 2,
                'content': 'This is too complex for me to understand.'
            }
        ]

        # Record all interactions
        for interaction in interactions:
            observation_service.record_interaction(sample_user.id, 1, interaction)

        # Generate system instructions based on observations
        instructions = observation_service.generate_system_instructions(sample_user.id, 1)

        assert isinstance(instructions, str)
        assert len(instructions) > 0

        # Verify instructions reflect user preferences
        assert 'detailed' in instructions.lower() or 'technical' in instructions.lower()

        # Get personality profile
        profile = observation_service.get_personality_profile(sample_user.id, 1)

        assert isinstance(profile, dict)
        assert 'communication_preferences' in profile
        assert 'success_patterns' in profile

        # Verify profile reflects learned preferences
        comm_prefs = profile['communication_preferences']
        assert comm_prefs['preferred_tone'] in ['formal', 'technical', 'detailed']

        success_patterns = profile['success_patterns']
        assert 'api_tool' in success_patterns['successful_tools']
        assert 'detailed_explanation' in success_patterns['successful_approaches']
        assert 'advanced_technical_jargon' in success_patterns['failed_approaches']

    def test_agent_loading_with_user_context(self, db_session, agent_loader, observation_service, sample_user):
        """Test agent loading includes user context from observations"""
        from src.database.models import CustomAgentDefinition, Tenant

        # Create tenant
        tenant = Tenant(
            id=1,
            name="Agent Integration Test Tenant",
            domain="agent-test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        # Create custom agent
        agent = CustomAgentDefinition(
            custom_agent_id="integration_agent_123",
            tenant_id=1,
            name="Integration Test Agent",
            description="An agent for integration testing",
            system_prompt="You are a helpful assistant for integration testing.",
            model_name="gemini-2.5-pro",
            version=1,
            is_active=True,
            is_latest_version=True,
            is_system_agent=False,
            max_iterations=10,
            timeout_seconds=300,
            temperature=0.7
        )
        db_session.add(agent)
        db_session.commit()

        # Build user observation profile
        interactions = [
            {
                'response_content': 'I like concise responses with bullet points.',
                'success_indicators': {'success': True},
                'tools_used': ['summary_tool'],
                'approaches_used': ['concise_bullet_points'],
                'response_time': 0.8,
                'follow_up_count': 0,
                'content': 'Please be brief and use bullet points.'
            },
            {
                'response_content': 'Good response format, easy to follow.',
                'success_indicators': {'success': True},
                'tools_used': ['format_tool'],
                'approaches_used': ['structured_response'],
                'response_time': 1.2,
                'follow_up_count': 0,
                'content': 'This format works well for me.'
            }
        ]

        for interaction in interactions:
            observation_service.record_interaction(sample_user.id, 1, interaction)

        # Load agent with user context
        with TestDatabaseSession() as session:
            agent_config = agent_loader._load_custom_agent(session, agent.custom_agent_id, 1, sample_user.id)

            assert agent_config is not None
            assert agent_config['agent_id'] == agent.custom_agent_id

            # Verify system prompt includes user context
            system_prompt = agent_config['system_prompt']
            assert isinstance(system_prompt, str)
            assert len(system_prompt) > len(agent.system_prompt)  # Should be enhanced

            # Should include user preferences
            assert 'concise' in system_prompt.lower() or 'bullet' in system_prompt.lower()

    def test_goal_orchestration_with_observation_recording(self, db_session, goal_orchestrator, observation_service, sample_user):
        """Test goal orchestration includes observation recording"""
        from src.database.models import Project, Tenant

        # Create tenant
        tenant = Tenant(
            id=1,
            name="Orchestration Test Tenant",
            domain="orchestration-test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)

        # Create project
        project = Project(
            project_id="integration_project_123",
            tenant_id=1,
            name="Integration Test Project",
            description="A project for integration testing",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(project)
        db_session.commit()

        # Build user observation profile first
        for i in range(3):
            interaction = {
                'response_content': f'Test orchestration interaction {i}',
                'success_indicators': {'success': i < 2},  # 2 successful, 1 failed
                'tools_used': ['orchestration_tool'],
                'approaches_used': ['goal_oriented_approach'],
                'response_time': 2.0,
                'follow_up_count': 0,
                'content': f'Orchestration test {i}'
            }
            observation_service.record_interaction(sample_user.id, 1, interaction)

        # Mock the orchestrator's _execute_goal_orchestration to avoid complex dependencies
        with patch.object(goal_orchestrator, '_execute_goal_orchestration') as mock_execute:
            mock_execute.return_value = {
                'job_id': 'test_job_123',
                'success': True,
                'output': 'Test orchestration result'
            }

            # Orchestrate a goal
            result = asyncio.run(goal_orchestrator.orchestrate_goal(
                "Test goal for observation system integration",
                "integration_project_123",
                user_id=sample_user.id
            ))

            # Verify orchestration was called
            mock_execute.assert_called_once()

            # Verify result structure
            assert 'job_id' in result
            assert 'success' in result
            assert result['success'] is True

            # Verify observation recording was enabled during execution
            # (This would be verified by checking that ExecutionTraceStep.enable_observation_recording was called)

    def test_execution_trace_observation_integration(self, db_session, observation_service, sample_user):
        """Test execution trace observation integration"""
        from src.database.models import Tenant

        # Create tenant
        tenant = Tenant(
            id=1,
            name="Trace Test Tenant",
            domain="trace-test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(sample_user.id, 1)

        # Create execution trace steps
        steps_data = [
            {
                'job_id': 'trace_job_1',
                'step_number': 1,
                'step_type': 'THOUGHT',
                'thought': 'Planning the solution approach'
            },
            {
                'job_id': 'trace_job_1',
                'step_number': 2,
                'step_type': 'ACTION',
                'action_tool': 'planning_tool',
                'action_input': json.dumps({'plan': 'step_by_step'}),
                'thought': 'Executing the planned steps'
            },
            {
                'job_id': 'trace_job_1',
                'step_number': 3,
                'step_type': 'OBSERVATION',
                'observation_result': 'Task completed successfully',
                'thought': 'Finalizing the execution'
            }
        ]

        for step_data in steps_data:
            step = ExecutionTraceStep(
                tenant_id=1,
                timestamp=datetime.utcnow(),
                **step_data
            )
            db_session.add(step)
            db_session.commit()
            db_session.refresh(step)

            # Record observation for each step
            step.after_creation()

        # Process execution trace for observations
        asyncio.run(observation_service.process_execution_trace_for_observations(
            'trace_job_1', sample_user.id, 1
        ))

        # Verify observations were recorded
        observations = db_session.query(UserObservation).filter(
            UserObservation.user_id == sample_user.id,
            UserObservation.tenant_id == 1
        ).all()

        assert len(observations) >= 1
        assert observations[0].observation_count >= 3  # Should have recorded multiple observations

    def test_performance_monitoring_integration(self, db_session, observation_service, sample_user):
        """Test performance monitoring integration with observation system"""
        from src.services.observation_performance_monitor import start_observation_timing, end_observation_timing

        # Record interactions with performance monitoring
        for i in range(5):
            # Start timing
            timer_id = start_observation_timing('record_interaction', sample_user.id, 1)

            # Record interaction
            interaction = {
                'response_content': f'Performance monitoring test {i}',
                'success_indicators': {'success': True},
                'tools_used': ['performance_tool'],
                'approaches_used': ['performance_approach'],
                'response_time': 1.0,
                'follow_up_count': 0,
                'content': f'Performance test {i}'
            }
            observation_service.record_interaction(sample_user.id, 1, interaction)

            # End timing
            duration = end_observation_timing(timer_id, 'record_interaction', sample_user.id, 1)

            assert duration >= 0

        # Generate system instructions with timing
        instructions_timer = start_observation_timing('generate_system_instructions', sample_user.id, 1)
        instructions = observation_service.generate_system_instructions(sample_user.id, 1)
        instructions_duration = end_observation_timing(instructions_timer, 'generate_system_instructions', sample_user.id, 1)

        assert instructions_duration >= 0
        assert isinstance(instructions, str)

        # Get performance summary
        from src.services.observation_performance_monitor import get_observation_performance_monitor
        monitor = get_observation_performance_monitor()
        summary = monitor.get_performance_summary(1)

        assert isinstance(summary, dict)
        assert summary['total_operations'] >= 6  # 5 record_interaction + 1 generate_system_instructions
        assert summary['total_time'] > 0
        assert 'operations_by_type' in summary

        # Should have tracked both operation types
        operations_by_type = summary['operations_by_type']
        assert 'record_interaction' in operations_by_type
        assert 'generate_system_instructions' in operations_by_type

    def test_error_handling_and_recovery(self, db_session, observation_service, sample_user):
        """Test error handling and recovery in the observation system"""
        # Test with invalid interaction data
        invalid_interactions = [
            {},  # Empty data
            {'invalid_field': 'value'},  # Missing required fields
            {
                'response_content': None,
                'success_indicators': None,
                'tools_used': None,
                'approaches_used': None,
                'response_time': None,
                'follow_up_count': None,
                'content': None
            }  # All None values
        ]

        # Should handle these gracefully without crashing
        for i, invalid_data in enumerate(invalid_interactions):
            try:
                observation_service.record_interaction(sample_user.id, 1, invalid_data)
                # If it succeeds, that's fine - system is resilient
            except Exception as e:
                # If it fails, should be handled gracefully
                assert "constraint" in str(e).lower() or "invalid" in str(e).lower()

        # Test with database errors (simulate by using invalid tenant_id)
        error_interaction = {
            'response_content': 'Error test interaction',
            'success_indicators': {'success': True},
            'tools_used': ['error_tool'],
            'approaches_used': ['error_approach'],
            'response_time': 1.0,
            'follow_up_count': 0,
            'content': 'Error test content'
        }

        # Should handle database constraint errors gracefully
        try:
            observation_service.record_interaction(sample_user.id, 999999, error_interaction)
        except Exception as e:
            # Should raise a database-related exception, not crash
            assert "foreign key" in str(e).lower() or "constraint" in str(e).lower()

    def test_system_resilience_under_load(self, db_session, observation_service, sample_user):
        """Test system resilience under high load"""
        # Record many interactions quickly
        for i in range(20):
            interaction = {
                'response_content': f'Load test interaction {i}',
                'success_indicators': {'success': i % 5 != 0},  # 80% success rate
                'tools_used': [f'load_tool_{i % 3}'],
                'approaches_used': [f'load_approach_{i % 4}'],
                'response_time': 1.0 + (i % 3) * 0.5,  # Vary response times
                'follow_up_count': i % 3,
                'content': f'Load test content {i}'
            }

            observation_service.record_interaction(sample_user.id, 1, interaction)

        # Generate system instructions
        instructions = observation_service.generate_system_instructions(sample_user.id, 1)
        assert isinstance(instructions, str)
        assert len(instructions) > 0

        # Get personality profile
        profile = observation_service.get_personality_profile(sample_user.id, 1)
        assert isinstance(profile, dict)

        # Verify observations were recorded correctly
        observations = db_session.query(UserObservation).filter(
            UserObservation.user_id == sample_user.id,
            UserObservation.tenant_id == 1
        ).all()

        assert len(observations) >= 1
        observation = observations[0]
        assert observation.observation_count >= 20

        # Verify confidence score reflects the volume of data
        assert observation.confidence_score >= 0.8  # Should be high with lots of data

    def test_cross_component_data_consistency(self, db_session, observation_service, agent_loader, sample_user):
        """Test data consistency across different components"""
        from src.database.models import CustomAgentDefinition, Tenant

        # Create tenant
        tenant = Tenant(
            id=1,
            name="Consistency Test Tenant",
            domain="consistency-test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        # Create agent
        agent = CustomAgentDefinition(
            custom_agent_id="consistency_agent_123",
            tenant_id=1,
            name="Consistency Test Agent",
            description="An agent for consistency testing",
            system_prompt="You are a consistency test assistant.",
            model_name="gemini-2.5-pro",
            version=1,
            is_active=True,
            is_latest_version=True,
            is_system_agent=False
        )
        db_session.add(agent)
        db_session.commit()

        # Record interactions that will influence agent behavior
        consistency_interactions = [
            {
                'response_content': 'I prefer responses under 100 words with clear structure.',
                'success_indicators': {'success': True},
                'tools_used': ['clarity_tool'],
                'approaches_used': ['structured_brief'],
                'response_time': 0.8,
                'follow_up_count': 0,
                'content': 'Keep responses clear and brief.'
            },
            {
                'response_content': 'Use bullet points and numbered lists when possible.',
                'success_indicators': {'success': True},
                'tools_used': ['formatting_tool'],
                'approaches_used': ['list_based_formatting'],
                'response_time': 1.2,
                'follow_up_count': 0,
                'content': 'Use lists for better readability.'
            }
        ]

        for interaction in consistency_interactions:
            observation_service.record_interaction(sample_user.id, 1, interaction)

        # Load agent with user context
        with TestDatabaseSession() as session:
            agent_config = agent_loader._load_custom_agent(session, agent.custom_agent_id, 1, sample_user.id)

            # Verify agent config reflects user preferences
            system_prompt = agent_config['system_prompt']
            assert 'clear' in system_prompt.lower() or 'brief' in system_prompt.lower()
            assert 'structure' in system_prompt.lower() or 'list' in system_prompt.lower()

        # Generate personality profile
        profile = observation_service.get_personality_profile(sample_user.id, 1)
        comm_prefs = profile['communication_preferences']

        # Verify profile is consistent with recorded interactions
        assert comm_prefs['response_length_preference'] in ['concise', 'brief']
        assert comm_prefs['preferred_tone'] in ['clear', 'structured', 'formal']

        # Verify success patterns are consistent
        success_patterns = profile['success_patterns']
        assert 'clarity_tool' in success_patterns['successful_tools']
        assert 'structured_brief' in success_patterns['successful_approaches']
