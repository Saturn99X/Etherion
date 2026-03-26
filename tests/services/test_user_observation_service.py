import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal
import json

from src.services.user_observation_service import UserObservationService
from src.database.models import UserObservation, User, Tenant
from src.database.db import get_db
from tests.conftest import TestDatabaseSession


class TestUserObservationService:
    """Test suite for UserObservationService"""

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
    def sample_user(self, db_session):
        """Create a sample user for testing"""
        user = User(
            user_id="test_user_123",
            email="test@example.com",
            name="Test User",
            provider="test",
            tenant_id=1,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    @pytest.fixture
    def sample_tenant(self, db_session):
        """Create a sample tenant for testing"""
        tenant = Tenant(
            id=1,
            name="Test Tenant",
            domain="test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()
        return tenant

    def test_record_interaction_creates_new_observation(self, observation_service, sample_user, sample_tenant):
        """Test that recording an interaction creates a new observation record"""
        interaction_data = {
            'response_content': 'This is a test response',
            'success_indicators': {'success': True},
            'tools_used': ['test_tool'],
            'approaches_used': ['test_approach'],
            'response_time': 1.5,
            'follow_up_count': 0,
            'content': 'Test content'
        }

        # Record the interaction
        observation_service.record_interaction(sample_user.id, sample_tenant.id, interaction_data)

        # Verify observation was created
        with TestDatabaseSession() as session:
            observation = session.query(UserObservation).filter(
                UserObservation.user_id == sample_user.id,
                UserObservation.tenant_id == sample_tenant.id
            ).first()

            assert observation is not None
            assert observation.observation_count == 1
            assert observation.last_observation_at is not None
            assert observation.confidence_score > 0

    def test_record_interaction_updates_existing_observation(self, observation_service, sample_user, sample_tenant):
        """Test that recording multiple interactions updates existing observation"""
        # Record first interaction
        interaction_data1 = {
            'response_content': 'First response',
            'success_indicators': {'success': True},
            'tools_used': ['tool1'],
            'approaches_used': ['approach1'],
            'response_time': 1.0,
            'follow_up_count': 0,
            'content': 'First content'
        }
        observation_service.record_interaction(sample_user.id, sample_tenant.id, interaction_data1)

        # Record second interaction
        interaction_data2 = {
            'response_content': 'Second response',
            'success_indicators': {'success': True},
            'tools_used': ['tool2'],
            'approaches_used': ['approach2'],
            'response_time': 2.0,
            'follow_up_count': 1,
            'content': 'Second content'
        }
        observation_service.record_interaction(sample_user.id, sample_tenant.id, interaction_data2)

        # Verify observation was updated
        with TestDatabaseSession() as session:
            observation = session.query(UserObservation).filter(
                UserObservation.user_id == sample_user.id,
                UserObservation.tenant_id == sample_tenant.id
            ).first()

            assert observation is not None
            assert observation.observation_count == 2
            assert observation.confidence_score > 0.5  # Should be higher with more data

    def test_analyze_communication_style(self, observation_service, sample_user, sample_tenant):
        """Test communication style analysis"""
        # Record interaction with specific communication patterns
        interaction_data = {
            'response_content': 'I would recommend using the API endpoint for this implementation. ' +
                              'Moreover, please ensure proper error handling. ' +
                              'Thank you for your attention to this matter.',
            'success_indicators': {'success': True},
            'tools_used': [],
            'approaches_used': [],
            'response_time': 0.5,
            'follow_up_count': 0,
            'content': 'Technical implementation question'
        }

        observation_service.record_interaction(sample_user.id, sample_tenant.id, interaction_data)

        # Verify communication style was analyzed
        with TestDatabaseSession() as session:
            observation = session.query(UserObservation).filter(
                UserObservation.user_id == sample_user.id,
                UserObservation.tenant_id == sample_tenant.id
            ).first()

            assert observation is not None
            assert observation.preferred_tone in ['formal', 'technical']
            assert observation.formality_level == 'high'

    def test_analyze_success_patterns(self, observation_service, sample_user, sample_tenant):
        """Test success pattern analysis"""
        # Record successful interaction
        success_data = {
            'response_content': 'Successfully completed the task',
            'success_indicators': {'success': True},
            'tools_used': ['api_tool', 'database_tool'],
            'approaches_used': ['systematic_approach', 'data_driven'],
            'response_time': 2.0,
            'follow_up_count': 0,
            'content': 'Complex data processing task'
        }

        # Record failed interaction
        failure_data = {
            'response_content': 'Failed due to timeout',
            'success_indicators': {'success': False},
            'tools_used': ['timeout_tool'],
            'approaches_used': ['rushed_approach'],
            'response_time': 30.0,
            'follow_up_count': 2,
            'content': 'Time-sensitive task'
        }

        observation_service.record_interaction(sample_user.id, sample_tenant.id, success_data)
        observation_service.record_interaction(sample_user.id, sample_tenant.id, failure_data)

        # Verify success patterns were recorded
        with TestDatabaseSession() as session:
            observation = session.query(UserObservation).filter(
                UserObservation.user_id == sample_user.id,
                UserObservation.tenant_id == sample_tenant.id
            ).first()

            assert observation is not None
            assert 'api_tool' in json.loads(observation.successful_tools)
            assert 'database_tool' in json.loads(observation.successful_tools)
            assert 'systematic_approach' in json.loads(observation.successful_approaches)
            assert 'rushed_approach' in json.loads(observation.failed_approaches)

    def test_generate_system_instructions(self, observation_service, sample_user, sample_tenant):
        """Test system instruction generation"""
        # Record some interactions first
        for i in range(3):
            interaction_data = {
                'response_content': f'Test response {i}',
                'success_indicators': {'success': True},
                'tools_used': ['test_tool'],
                'approaches_used': ['test_approach'],
                'response_time': 1.0,
                'follow_up_count': 0,
                'content': f'Test content {i}'
            }
            observation_service.record_interaction(sample_user.id, sample_tenant.id, interaction_data)

        # Generate system instructions
        instructions = observation_service.generate_system_instructions(sample_user.id, sample_tenant.id)

        assert isinstance(instructions, str)
        assert len(instructions) > 0
        assert 'test_tool' in instructions or 'test_approach' in instructions

    def test_get_user_observations_caching(self, observation_service, sample_user, sample_tenant):
        """Test that user observations are properly cached"""
        # Record an interaction
        interaction_data = {
            'response_content': 'Cached test response',
            'success_indicators': {'success': True},
            'tools_used': [],
            'approaches_used': [],
            'response_time': 0.5,
            'follow_up_count': 0,
            'content': 'Cache test content'
        }
        observation_service.record_interaction(sample_user.id, sample_tenant.id, interaction_data)

        # Get observations (should cache)
        observation1 = observation_service.get_user_observations(sample_user.id, sample_tenant.id)
        observation2 = observation_service.get_user_observations(sample_user.id, sample_tenant.id)

        assert observation1 is not None
        assert observation2 is not None
        assert observation1.id == observation2.id

    def test_personality_profile_generation(self, observation_service, sample_user, sample_tenant):
        """Test personality profile generation"""
        # Record multiple interactions to build a profile
        for i in range(5):
            interaction_data = {
                'response_content': f'Detailed response {i} with lots of technical details and examples',
                'success_indicators': {'success': i < 4},  # 80% success rate
                'tools_used': ['api_tool', 'analysis_tool'],
                'approaches_used': ['analytical', 'methodical'],
                'response_time': 2.0 + i * 0.5,
                'follow_up_count': 0,
                'content': f'Technical question {i}'
            }
            observation_service.record_interaction(sample_user.id, sample_tenant.id, interaction_data)

        # Generate personality profile
        profile = observation_service.get_personality_profile(sample_user.id, sample_tenant.id)

        assert isinstance(profile, dict)
        assert 'communication_preferences' in profile
        assert 'personality_traits' in profile
        assert 'success_patterns' in profile
        assert 'behavioral_patterns' in profile
        assert 'content_preferences' in profile
        assert 'metadata' in profile

        # Verify specific values
        assert profile['communication_preferences']['preferred_tone'] in ['formal', 'technical']
        assert profile['personality_traits']['detail_orientation'] in ['high', 'medium']
        assert 'api_tool' in profile['success_patterns']['successful_tools']

    def test_error_handling(self, observation_service, sample_user, sample_tenant):
        """Test error handling in the observation service"""
        # Test with invalid user ID
        interaction_data = {
            'response_content': 'Test response',
            'success_indicators': {'success': True},
            'tools_used': [],
            'approaches_used': [],
            'response_time': 1.0,
            'follow_up_count': 0,
            'content': 'Test content'
        }

        # Should handle gracefully (may create new user observation or log warning)
        try:
            observation_service.record_interaction(999999, sample_tenant.id, interaction_data)
            # If no exception, that's fine - it might create a new user
        except Exception as e:
            # If it raises an exception, that's also acceptable for invalid user
            assert "foreign key" in str(e).lower() or "constraint" in str(e).lower()

    @pytest.mark.asyncio
    async def test_async_observation_processing(self, observation_service, sample_user, sample_tenant):
        """Test asynchronous observation processing"""
        # Record execution trace observation
        execution_data = {
            'trace_steps': [
                {'step_type': 'THOUGHT', 'thought': 'Planning the solution'},
                {'step_type': 'ACTION', 'action_tool': 'api_tool', 'action_input': {'param': 'value'}},
                {'step_type': 'OBSERVATION', 'observation_result': 'Success'}
            ],
            'success': True,
            'tools_used': ['api_tool'],
            'execution_time': 3.5,
            'goal_description': 'Test goal execution'
        }

        await observation_service.record_execution_trace_observation(
            'test_job_123', sample_user.id, sample_tenant.id, execution_data
        )

        # Verify observation was recorded
        with TestDatabaseSession() as session:
            observation = session.query(UserObservation).filter(
                UserObservation.user_id == sample_user.id,
                UserObservation.tenant_id == sample_tenant.id
            ).first()

            assert observation is not None
            assert observation.observation_count >= 1

    def test_background_observation_processing(self, observation_service, sample_user, sample_tenant):
        """Test background observation processing"""
        # Record many interactions to trigger background processing
        for i in range(10):
            interaction_data = {
                'response_content': f'Background test {i}',
                'success_indicators': {'success': i % 2 == 0},  # Alternating success/failure
                'tools_used': ['background_tool'],
                'approaches_used': ['background_approach'],
                'response_time': 1.0,
                'follow_up_count': 0,
                'content': f'Background content {i}'
            }
            observation_service.record_interaction(sample_user.id, sample_tenant.id, interaction_data)

        # Trigger background processing
        observation_service.background_observation_processing(sample_user.id, sample_tenant.id)

        # Verify observations were processed (personality traits updated)
        with TestDatabaseSession() as session:
            observation = session.query(UserObservation).filter(
                UserObservation.user_id == sample_user.id,
                UserObservation.tenant_id == sample_tenant.id
            ).first()

            assert observation is not None
            assert observation.patience_level in ['high', 'medium', 'low']
            assert observation.detail_orientation in ['high', 'medium', 'low']
            assert observation.risk_tolerance in ['conservative', 'balanced', 'aggressive']

    def test_integration_with_logging_system(self, observation_service, sample_user, sample_tenant):
        """Test integration with logging system"""
        # Test error log integration
        error_message = "Timeout occurred while executing tool: api_call_tool"
        log_level = "ERROR"

        observation_service.integrate_with_logging_system(
            sample_user.id, sample_tenant.id, error_message, log_level
        )

        # Verify observation was recorded for the error
        with TestDatabaseSession() as session:
            observation = session.query(UserObservation).filter(
                UserObservation.user_id == sample_user.id,
                UserObservation.tenant_id == sample_tenant.id
            ).first()

            assert observation is not None
            # Should have recorded the timeout failure
            failed_approaches = json.loads(getattr(observation, 'failed_approaches', '[]'))
            assert len(failed_approaches) > 0

    def test_performance_monitoring_integration(self, observation_service, sample_user, sample_tenant):
        """Test that performance monitoring is integrated"""
        with patch('src.services.user_observation_service.start_observation_timing') as mock_start, \
             patch('src.services.user_observation_service.end_observation_timing') as mock_end, \
             patch('src.services.user_observation_service.record_observation_error') as mock_error:

            mock_start.return_value = 'test_timer'
            mock_end.return_value = 0.05

            # Record an interaction
            interaction_data = {
                'response_content': 'Performance test',
                'success_indicators': {'success': True},
                'tools_used': [],
                'approaches_used': [],
                'response_time': 0.1,
                'follow_up_count': 0,
                'content': 'Performance test content'
            }

            observation_service.record_interaction(sample_user.id, sample_tenant.id, interaction_data)

            # Verify performance monitoring was called
            mock_start.assert_called_once()
            mock_end.assert_called_once()

    def test_edge_cases(self, observation_service, sample_user, sample_tenant):
        """Test edge cases and boundary conditions"""
        # Test with empty interaction data
        empty_data = {}
        observation_service.record_interaction(sample_user.id, sample_tenant.id, empty_data)

        # Test with very long content
        long_content = "A" * 10000
        long_data = {
            'response_content': long_content,
            'success_indicators': {'success': True},
            'tools_used': [],
            'approaches_used': [],
            'response_time': 5.0,
            'follow_up_count': 0,
            'content': long_content
        }
        observation_service.record_interaction(sample_user.id, sample_tenant.id, long_data)

        # Test with special characters
        special_data = {
            'response_content': 'Response with émojis 🎉 and spëcial chärs',
            'success_indicators': {'success': True},
            'tools_used': ['special_tool'],
            'approaches_used': ['special_approach'],
            'response_time': 1.0,
            'follow_up_count': 0,
            'content': 'Special content with ñoñó characters'
        }
        observation_service.record_interaction(sample_user.id, sample_tenant.id, special_data)

        # Verify all observations were recorded
        with TestDatabaseSession() as session:
            observations = session.query(UserObservation).filter(
                UserObservation.user_id == sample_user.id,
                UserObservation.tenant_id == sample_tenant.id
            ).all()

            assert len(observations) == 3  # All three interactions recorded
            assert all(obs.observation_count >= 1 for obs in observations)
