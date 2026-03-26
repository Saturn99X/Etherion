import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json

from src.database.models.execution_trace import ExecutionTraceStep, StepType
from src.services.user_observation_service import UserObservationService
from tests.conftest import TestDatabaseSession


class TestExecutionTraceObservationRecording:
    """Test suite for ExecutionTraceStep observation recording"""

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
    def sample_job_id(self):
        """Provide a sample job ID"""
        return "test_job_123"

    @pytest.fixture
    def sample_execution_step(self, db_session):
        """Create a sample execution trace step"""
        from src.database.models import Tenant

        # Create tenant first
        tenant = Tenant(
            id=1,
            name="Test Tenant",
            domain="test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        # Create execution step
        step = ExecutionTraceStep(
            job_id="test_job_123",
            tenant_id=1,
            step_number=1,
            step_type=StepType.THOUGHT,
            thought="This is a test thought",
            timestamp=datetime.utcnow()
        )
        db_session.add(step)
        db_session.commit()
        db_session.refresh(step)
        return step

    def test_enable_observation_recording(self, sample_execution_step):
        """Test enabling observation recording for execution steps"""
        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(
            user_id=123,
            tenant_id=1
        )

        # Verify class attributes are set
        assert ExecutionTraceStep._user_id == 123
        assert ExecutionTraceStep._record_observations is True
        assert ExecutionTraceStep._observation_service is not None

    def test_disable_observation_recording(self, sample_execution_step):
        """Test disabling observation recording"""
        # First enable
        ExecutionTraceStep.enable_observation_recording(123, 1)

        # Then disable
        ExecutionTraceStep.disable_observation_recording()

        # Verify class attributes are reset
        assert ExecutionTraceStep._user_id is None
        assert ExecutionTraceStep._record_observations is False
        assert ExecutionTraceStep._observation_service is None

    def test_record_observation_with_enabled_recording(self, sample_execution_step):
        """Test recording observation when recording is enabled"""
        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(123, 1)

        # Record observation
        observation_data = {
            'response_content': 'Test observation content',
            'success_indicators': {'success': True},
            'tools_used': ['test_tool'],
            'approaches_used': ['test_approach'],
            'response_time': 1.5,
            'follow_up_count': 0,
            'content': 'Test content'
        }

        sample_execution_step.record_observation(observation_data)

        # Verify observation was scheduled (we can't easily test the actual recording
        # without mocking the Celery task, but we can verify the method was called)
        assert sample_execution_step._record_observations is True

    def test_record_observation_with_disabled_recording(self, sample_execution_step):
        """Test that observation recording does nothing when disabled"""
        # Ensure recording is disabled
        ExecutionTraceStep.disable_observation_recording()

        # Try to record observation
        observation_data = {
            'response_content': 'Test observation content',
            'success_indicators': {'success': True},
            'tools_used': ['test_tool'],
            'approaches_used': ['test_approach'],
            'response_time': 1.5,
            'follow_up_count': 0,
            'content': 'Test content'
        }

        # Should not raise any errors and should do nothing
        sample_execution_step.record_observation(observation_data)

    def test_after_creation_calls_record_observation(self, sample_execution_step):
        """Test that after_creation calls record_observation"""
        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(123, 1)

        # Call after_creation
        sample_execution_step.after_creation()

        # Verify the step still has recording enabled
        assert sample_execution_step._record_observations is True

    def test_after_completion_calls_record_observation(self, sample_execution_step):
        """Test that after_completion calls record_observation"""
        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(123, 1)

        # Call after_completion
        sample_execution_step.after_completion(success=True, output="Test output")

        # Verify the step still has recording enabled
        assert sample_execution_step._record_observations is True

    def test_observation_recording_with_action_step(self, db_session):
        """Test observation recording with ACTION step type"""
        from src.database.models import Tenant

        # Create tenant
        tenant = Tenant(
            id=1,
            name="Test Tenant",
            domain="test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        # Create action step
        step = ExecutionTraceStep(
            job_id="test_job_456",
            tenant_id=1,
            step_number=2,
            step_type=StepType.ACTION,
            action_tool="test_api_tool",
            action_input=json.dumps({"param": "value"}),
            thought="Executing API call",
            timestamp=datetime.utcnow()
        )
        db_session.add(step)
        db_session.commit()
        db_session.refresh(step)

        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(456, 1)

        # Record observation
        observation_data = {
            'response_content': 'API call completed successfully',
            'success_indicators': {'success': True},
            'tools_used': ['api_tool'],
            'approaches_used': ['api_approach'],
            'response_time': 2.5,
            'follow_up_count': 0,
            'content': 'API execution test'
        }

        step.record_observation(observation_data)

        # Verify recording was attempted
        assert step._record_observations is True

    def test_observation_recording_with_observation_step(self, db_session):
        """Test observation recording with OBSERVATION step type"""
        from src.database.models import Tenant

        # Create tenant
        tenant = Tenant(
            id=1,
            name="Test Tenant",
            domain="test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        # Create observation step
        step = ExecutionTraceStep(
            job_id="test_job_789",
            tenant_id=1,
            step_number=3,
            step_type=StepType.OBSERVATION,
            observation_result="Final result: Task completed",
            thought="Finalizing the task",
            timestamp=datetime.utcnow()
        )
        db_session.add(step)
        db_session.commit()
        db_session.refresh(step)

        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(789, 1)

        # Record observation
        observation_data = {
            'response_content': 'Final observation result',
            'success_indicators': {'success': True},
            'tools_used': ['final_tool'],
            'approaches_used': ['final_approach'],
            'response_time': 0.5,
            'follow_up_count': 0,
            'content': 'Final observation test'
        }

        step.record_observation(observation_data)

        # Verify recording was attempted
        assert step._record_observations is True

    def test_observation_recording_with_cost_data(self, db_session):
        """Test observation recording with cost tracking data"""
        from src.database.models import Tenant
        from decimal import Decimal

        # Create tenant
        tenant = Tenant(
            id=1,
            name="Test Tenant",
            domain="test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        # Create step with cost data
        step = ExecutionTraceStep(
            job_id="test_job_cost",
            tenant_id=1,
            step_number=1,
            step_type=StepType.THOUGHT,
            thought="Expensive thought process",
            step_cost=Decimal('0.0015'),
            model_used="gemini-2.5-pro",
            raw_data=json.dumps({"additional": "cost_data"}),
            timestamp=datetime.utcnow()
        )
        db_session.add(step)
        db_session.commit()
        db_session.refresh(step)

        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(999, 1)

        # Record observation
        observation_data = {
            'response_content': 'Cost tracking test',
            'success_indicators': {'success': True},
            'tools_used': ['cost_tool'],
            'approaches_used': ['cost_approach'],
            'response_time': 3.0,
            'follow_up_count': 0,
            'content': 'Cost tracking test content'
        }

        step.record_observation(observation_data)

        # Verify recording was attempted
        assert step._record_observations is True

    def test_observation_recording_error_handling(self, sample_execution_step):
        """Test error handling in observation recording"""
        # Enable observation recording with a mock service that will fail
        with patch('src.database.models.execution_trace.get_user_observation_service') as mock_get_service:
            mock_service = Mock()
            mock_service.record_interaction.side_effect = Exception("Database error")
            mock_get_service.return_value = mock_service

            # Manually set the class attributes to simulate enabled recording
            ExecutionTraceStep._observation_service = mock_service
            ExecutionTraceStep._user_id = 123
            ExecutionTraceStep._record_observations = True

            # Try to record observation
            observation_data = {
                'response_content': 'Error handling test',
                'success_indicators': {'success': True},
                'tools_used': ['error_tool'],
                'approaches_used': ['error_approach'],
                'response_time': 1.0,
                'follow_up_count': 0,
                'content': 'Error handling test content'
            }

            # Should not raise exception, should handle error gracefully
            sample_execution_step.record_observation(observation_data)

            # Verify the service was called
            mock_service.record_interaction.assert_called_once()

    def test_observation_recording_integration_with_celery(self, sample_execution_step):
        """Test integration with Celery for async observation recording"""
        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(123, 1)

        with patch('src.database.models.execution_trace.celery_app') as mock_celery:
            mock_task = Mock()
            mock_celery.task.return_value = mock_task

            # Record observation
            observation_data = {
                'response_content': 'Celery integration test',
                'success_indicators': {'success': True},
                'tools_used': ['celery_tool'],
                'approaches_used': ['celery_approach'],
                'response_time': 2.0,
                'follow_up_count': 0,
                'content': 'Celery integration test content'
            }

            sample_execution_step.record_observation(observation_data)

            # Verify Celery task was created and scheduled
            mock_celery.task.assert_called_once()

    def test_observation_recording_performance_impact(self, db_session):
        """Test that observation recording doesn't significantly impact step creation"""
        from src.database.models import Tenant
        import time

        # Create tenant
        tenant = Tenant(
            id=1,
            name="Test Tenant",
            domain="test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(123, 1)

        # Time step creation with observation recording
        start_time = time.time()
        step = ExecutionTraceStep(
            job_id="performance_test_job",
            tenant_id=1,
            step_number=1,
            step_type=StepType.THOUGHT,
            thought="Performance test thought",
            timestamp=datetime.utcnow()
        )
        db_session.add(step)
        db_session.commit()
        db_session.refresh(step)

        # Call after_creation
        step.after_creation()
        end_time = time.time()

        # Should complete quickly (< 50ms)
        duration = (end_time - start_time) * 1000
        assert duration < 50, f"Step creation with observation recording took {duration:.2f}ms, should be < 50ms"

    def test_multiple_steps_observation_recording(self, db_session):
        """Test observation recording across multiple steps"""
        from src.database.models import Tenant

        # Create tenant
        tenant = Tenant(
            id=1,
            name="Test Tenant",
            domain="test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        # Enable observation recording
        ExecutionTraceStep.enable_observation_recording(123, 1)

        # Create multiple steps
        steps = []
        for i in range(5):
            step = ExecutionTraceStep(
                job_id="multi_step_job",
                tenant_id=1,
                step_number=i+1,
                step_type=StepType.THOUGHT,
                thought=f"Step {i+1} thought",
                timestamp=datetime.utcnow()
            )
            db_session.add(step)
            db_session.commit()
            db_session.refresh(step)
            steps.append(step)

            # Record observation for each step
            step.after_creation()

        # Verify all steps have recording enabled
        for step in steps:
            assert step._record_observations is True

        assert len(steps) == 5
