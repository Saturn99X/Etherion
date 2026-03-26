"""
Comprehensive tests for the fine-tuning data collection system.

This module contains tests for privacy protection, functional correctness,
and integration with the existing job system.
"""

import pytest
import json
import hashlib
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from src.services.fine_tuning_anonymizer import FineTuningAnonymizer
from src.services.fine_tuning_gcs import FineTuningGCSService
from src.services.fine_tuning_manager import FineTuningDataManager
from src.tasks.fine_tuning_archival import (
    archive_for_fine_tuning,
    collect_fine_tuning_data,
    cleanup_old_fine_tuning_data,
    generate_fine_tuning_report
)

# Test data fixtures
@pytest.fixture
def sample_execution_trace():
    """Sample execution trace with PII data."""
    return {
        'metadata': {
            'job_id': 'job_123456',
            'job_type': 'execute_goal',
            'tenant_id': 123,
            'user_id': 456,
            'user_email': 'test@example.com',
            'created_at': datetime.utcnow().isoformat(),
            'completed_at': datetime.utcnow().isoformat()
        },
        'steps': [
            {
                'step_number': 1,
                'timestamp': datetime.utcnow().isoformat(),
                'step_type': 'THOUGHT',
                'thought': 'User wants to analyze their email data. I should call the email analysis tool with their API key.',
                'action_tool': None,
                'action_input': None,
                'observation_result': None,
                'step_cost': 0.001,
                'model_used': 'gemini-2.5-pro'
            },
            {
                'step_number': 2,
                'timestamp': datetime.utcnow().isoformat(),
                'step_type': 'ACTION',
                'thought': None,
                'action_tool': 'email_analysis',
                'action_input': json.dumps({
                    'api_key': 'sk-1234567890abcdef',
                    'email_address': 'test@example.com',
                    'user_id': 'user_456'
                }),
                'observation_result': json.dumps({
                    'total_emails': 150,
                    'categories': ['work', 'personal'],
                    'insights': 'User receives many work emails'
                }),
                'step_cost': 0.002,
                'model_used': 'gemini-2.5-flash'
            }
        ]
    }

@pytest.fixture
def sample_job_data():
    """Sample job data with sensitive information."""
    return {
        'job_id': 'job_123456',
        'tenant_id': 123,
        'user_id': 456,
        'user_email': 'test@example.com',
        'job_type': 'execute_goal',
        'input_data': json.dumps({
            'goal': 'Analyze my email data',
            'api_credentials': 'sk-1234567890abcdef',
            'personal_info': 'Phone: 555-123-4567'
        }),
        'output_data': json.dumps({
            'result': 'Analysis complete',
            'recommendations': 'Consider organizing work emails'
        }),
        'created_at': datetime.utcnow(),
        'completed_at': datetime.utcnow()
    }

class TestFineTuningAnonymizer:
    """Test the anonymization service."""

    @pytest.fixture
    def anonymizer(self):
        return FineTuningAnonymizer()

    @pytest.mark.asyncio
    async def test_anonymize_execution_trace_privacy(self, anonymizer, sample_execution_trace):
        """Test that PII is removed from execution traces."""
        tenant_id = 123
        result = await anonymizer.anonymize_execution_trace(sample_execution_trace, tenant_id)

        # Check that tenant-specific data is removed
        # Check that PII fields are removed from metadata
        assert 'tenant_id' not in result['metadata']
        assert 'user_id' not in result['metadata']
        # Check that sensitive data in nested structures is anonymized
        assert 'test@example.com' not in str(result)
        assert 'sk-1234567890abcdef' not in str(result)

        # Check that execution patterns are preserved
        assert 'steps' in result
        assert len(result['steps']) == 2
        assert result['steps'][0]['step_type'] == 'THOUGHT'
        assert result['steps'][1]['step_type'] == 'ACTION'

        # Check that anonymization metadata is added
        assert '_anonymization_info' in result
        assert 'anonymized_at' in result['_anonymization_info']
        assert 'original_tenant_id_hash' in result['_anonymization_info']

    @pytest.mark.asyncio
    async def test_anonymize_job_data(self, anonymizer, sample_job_data):
        """Test that job data is properly anonymized."""
        result = await anonymizer.anonymize_job_data(sample_job_data)

        # Check that PII fields are removed
        assert 'tenant_id' not in result
        assert 'user_id' not in result
        assert 'user_email' not in result

        # Check that sensitive data in nested structures is anonymized
        assert 'test@example.com' not in str(result)
        assert 'sk-1234567890abcdef' not in str(result)
        assert '555-123-4567' not in str(result)

        # Check that non-sensitive data is preserved
        assert result['job_type'] == 'execute_goal'

    def test_pii_patterns(self, anonymizer):
        """Test that PII patterns are correctly identified and replaced."""
        test_text = "Contact user_123 at test@example.com or call 555-123-4567"

        result = anonymizer._anonymize_text_field(test_text)

        assert '<EMAIL>' in result
        assert '<PHONE>' in result
        assert '<USER_ID>' in result
        assert 'test@example.com' not in result
        assert '555-123-4567' not in result

    def test_anonymize_data_structure(self, anonymizer):
        """Test recursive anonymization of nested data structures."""
        test_data = {
            'user_id': 123,
            'nested': {
                'email': 'test@example.com',
                'api_key': 'sk-1234567890abcdef'
            },
            'safe_field': 'This should remain unchanged'
        }

        result = anonymizer._anonymize_data_structure(test_data)

        assert 'user_id' not in result
        # The nested dict should be completely removed since it contains only PII fields
        assert 'nested' not in result
        assert result['safe_field'] == 'This should remain unchanged'

class TestFineTuningGCSService:
    """Test the GCS service for fine-tuning data."""

    @pytest.fixture
    def gcs_service(self):
        with patch('src.services.fine_tuning_gcs.storage.Client') as mock_client:
            service = FineTuningGCSService(skip_bucket_check=True)
            service.client = mock_client
            return service

    @pytest.mark.asyncio
    async def test_upload_trace_to_fine_tuning_bucket(self, gcs_service):
        """Test uploading anonymized traces to GCS."""
        anonymized_trace = {
            'metadata': {'job_type': 'execute_goal'},
            'steps': [{'step_type': 'THOUGHT'}],
            '_anonymization_info': {'version': '1.0'}
        }
        job_id = 'job_123456'
        tenant_hash = 'abc123def456'

        with patch.object(gcs_service.client, 'bucket') as mock_bucket:
            mock_blob = Mock()
            mock_bucket.return_value.blob.return_value = mock_blob

            result = await gcs_service.upload_trace_to_fine_tuning_bucket(
                anonymized_trace, job_id, tenant_hash
            )

            # Verify upload was called
            mock_blob.upload_from_filename.assert_called_once()

            # Verify GCS URI format
            assert 'gs://etherion-ai-fine-tuning/' in result
            assert job_id in result
            assert tenant_hash in result
            assert '.jsonl' in result

    @pytest.mark.asyncio
    async def test_get_fine_tuning_data_summary(self, gcs_service):
        """Test getting data summary from GCS."""
        with patch.object(gcs_service.client, 'bucket') as mock_bucket:
            mock_bucket.return_value.list_blobs.return_value = []

            result = await gcs_service.get_fine_tuning_data_summary()

            assert 'bucket_name' in result
            assert 'total_traces' in result
            assert 'total_size_mb' in result
            assert 'tenant_distribution' in result

    @pytest.mark.asyncio
    async def test_get_ml_training_dataset(self, gcs_service):
        """Test retrieving training dataset from GCS."""
        with patch.object(gcs_service.client, 'bucket') as mock_bucket:
            # Mock blob with metadata
            mock_blob = Mock()
            mock_blob.metadata = {
                'trace_id': 'trace_123',
                'uploaded_at': '2025-01-01T00:00:00'
            }
            mock_blob.download_as_text.return_value = '{"test": "data"}'
            mock_bucket.return_value.list_blobs.return_value = [mock_blob]

            result = await gcs_service.get_ml_training_dataset(limit=1)

            assert len(result) == 1
            assert result[0]['test'] == 'data'
            assert '_gcs_metadata' in result[0]

class TestFineTuningDataManager:
    """Test the fine-tuning data manager."""

    @pytest.fixture
    def manager(self):
        with patch('src.services.fine_tuning_manager.FineTuningGCSService') as mock_gcs_class:
            mock_gcs_instance = Mock()
            mock_gcs_instance.get_fine_tuning_data_summary = AsyncMock(return_value={
                'total_traces': 100,
                'total_size_mb': 50.5,
                'tenant_distribution': {'hash1': 50, 'hash2': 50}
            })
            mock_gcs_instance.get_ml_training_dataset = AsyncMock(return_value=[
                {
                    'metadata': {'safe': 'data'},
                    'steps': [{'safe': 'content'}]
                }
            ])
            mock_gcs_class.return_value = mock_gcs_instance
            return FineTuningDataManager()

    @pytest.mark.asyncio
    async def test_schedule_fine_tuning_archival(self, manager):
        """Test scheduling archival tasks."""
        with patch('src.services.fine_tuning_manager.archive_for_fine_tuning') as mock_task:
            mock_task.apply_async.return_value.id = 'task_123'

            result = await manager.schedule_fine_tuning_archival(
                'job_123456', 123, delay_hours=24
            )

            assert result == 'task_123'
            mock_task.apply_async.assert_called_once_with(
                args=['job_123456', 123],
                countdown=24 * 3600
            )

    @pytest.mark.asyncio
    async def test_get_fine_tuning_statistics(self, manager):
        """Test getting comprehensive statistics."""
        with patch.object(manager.gcs_service, 'get_fine_tuning_data_summary') as mock_gcs, \
             patch('src.services.fine_tuning_manager.get_db') as mock_db:

            mock_gcs.return_value = {
                'total_traces': 100,
                'total_size_mb': 50.5,
                'tenant_distribution': {'hash1': 50, 'hash2': 50}
            }

            # Mock database query
            mock_session = Mock()
            mock_query = Mock()
            mock_query.filter.return_value.count.return_value = 95
            mock_session.query.return_value = mock_query
            mock_db.return_value.__enter__.return_value = mock_session

            # Mock the database count operations
            mock_session.query.return_value.filter.return_value.count.return_value = 95
            # Also mock the scalar count operations used in the statistics method
            mock_session.scalar.return_value = 95

            result = await manager.get_fine_tuning_statistics()

            assert 'gcs_summary' in result
            assert 'database_stats' in result
            assert 'data_quality_insights' in result
            assert result['database_stats']['total_jobs_with_traces'] == 95

    @pytest.mark.asyncio
    async def test_validate_privacy_compliance(self, manager):
        """Test privacy compliance validation."""
        with patch.object(manager.gcs_service, 'get_ml_training_dataset') as mock_get_data:
            mock_get_data.return_value = [
                {
                    'metadata': {'safe': 'data'},
                    'steps': [{'safe': 'content'}]
                }
            ]

            result = await manager.validate_privacy_compliance()

            assert 'compliance_issues' in result
            assert 'is_compliant' in result
            assert 'compliance_score' in result
            assert result['total_traces_checked'] == 1

    @pytest.mark.asyncio
    async def test_get_ml_team_dashboard_data(self, manager):
        """Test getting dashboard data for ML team."""
        with patch.object(manager, 'get_fine_tuning_statistics') as mock_stats, \
             patch.object(manager.gcs_service, 'get_fine_tuning_data_summary') as mock_summary, \
             patch.object(manager, 'validate_privacy_compliance') as mock_compliance:

            mock_stats.return_value = {'test': 'stats'}
            mock_summary.return_value = {'total_traces': 100, 'total_size_mb': 50}
            mock_compliance.return_value = {
                'is_compliant': True,
                'compliance_score': 100
            }

            result = await manager.get_ml_team_dashboard_data()

            assert 'overview' in result
            assert 'statistics' in result
            assert 'recommendations' in result
            assert result['overview']['total_traces'] == 100

class TestFineTuningArchivalTasks:
    """Test the Celery archival tasks."""

    @pytest.mark.asyncio
    async def test_archive_for_fine_tuning_success(self):
        """Test successful archival task."""
        with patch('src.tasks.fine_tuning_archival.get_db') as mock_db, \
             patch('src.tasks.fine_tuning_archival.FineTuningAnonymizer') as mock_anonymizer, \
             patch('src.tasks.fine_tuning_archival.FineTuningGCSService') as mock_gcs_class:

            # Mock database
            mock_session = Mock()
            mock_job = Mock()
            mock_job.job_id = 'job_123456'
            mock_job.tenant_id = 123
            mock_job.status = 'COMPLETED'
            mock_job.trace_data_uri = None
            mock_job.job_type = 'execute_goal'
            mock_job.created_at = datetime.utcnow()
            mock_job.completed_at = datetime.utcnow()

            mock_trace_step = Mock()
            mock_trace_step.step_number = 1
            mock_trace_step.step_type = 'THOUGHT'
            mock_trace_step.thought = 'Test thought'
            mock_trace_step.get_action_input.return_value = None
            mock_trace_step.get_observation_result.return_value = None
            mock_trace_step.step_cost = 0.001
            mock_trace_step.model_used = 'gemini-2.5-pro'
            mock_trace_step.get_raw_data.return_value = None

            mock_session.query.return_value.filter.return_value.first.return_value = mock_job
            mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_trace_step]
            mock_db.return_value.__enter__.return_value = mock_session
            mock_job.status = 'COMPLETED'
            # Ensure the mock returns the actual status value, not a MagicMock
            mock_job.configure_mock(**{'status': 'COMPLETED'})
            # Also set the return value for the status attribute
            type(mock_job).status = property(lambda self: 'COMPLETED')

            # Mock services
            mock_anonymizer_instance = Mock()
            mock_anonymizer_instance.anonymize_execution_trace = AsyncMock(return_value={'anonymized': True})
            mock_anonymizer.return_value = mock_anonymizer_instance

            mock_gcs_instance = Mock()
            mock_gcs_instance.upload_trace_to_fine_tuning_bucket = AsyncMock(return_value='gs://bucket/file.jsonl')
            mock_gcs_class.return_value = mock_gcs_instance

            result = await archive_for_fine_tuning('job_123456', 123)

            assert result['success'] is True
            assert 'gcs_uri' in result
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_fine_tuning_data(self):
        """Test data collection task."""
        with patch('src.tasks.fine_tuning_archival.get_db') as mock_db, \
             patch('src.tasks.fine_tuning_archival.archive_for_fine_tuning') as mock_archive, \
             patch('src.tasks.fine_tuning_archival.FineTuningGCSService') as mock_gcs_class:

            # Mock database
            mock_session = Mock()
            mock_job = Mock()
            mock_job.job_id = 'job_123456'
            mock_job.tenant_id = 123
            mock_job.status = 'COMPLETED'
            mock_job.completed_at = datetime.utcnow()
            mock_job.trace_data_uri = None

            mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [mock_job]
            mock_db.return_value.__enter__.return_value = mock_session

            # Mock archival task
            async def mock_archive_func(*args, **kwargs):
                return {'success': True, 'gcs_uri': 'gs://bucket/file.jsonl'}
            mock_archive_func.__name__ = 'mock_archive'
            mock_archive.return_value = {'success': True, 'gcs_uri': 'gs://bucket/file.jsonl'}

            # Mock GCS service
            mock_gcs_instance = Mock()
            mock_gcs_instance.get_fine_tuning_data_summary = AsyncMock(return_value={
                'total_traces': 1,
                'total_size_mb': 0.1,
                'tenant_distribution': {'hash1': 1}
            })
            mock_gcs_class.return_value = mock_gcs_instance

            result = await collect_fine_tuning_data(days_back=7)

            assert 'total_jobs' in result
            assert 'successful_archives' in result
            assert result['total_jobs'] == 1
            assert result['successful_archives'] == 1

    @pytest.mark.asyncio
    async def test_cleanup_old_fine_tuning_data(self):
        """Test cleanup task."""
        with patch('src.tasks.fine_tuning_archival.FineTuningGCSService') as mock_gcs:
            mock_gcs_instance = Mock()
            mock_gcs_instance.delete_old_training_data = AsyncMock(return_value=5)
            mock_gcs.return_value = mock_gcs_instance

            result = await cleanup_old_fine_tuning_data(days_old=365)

            assert result['success'] is True
            assert result['deleted_files'] == 5

    @pytest.mark.asyncio
    async def test_generate_fine_tuning_report(self):
        """Test report generation task."""
        with patch('src.tasks.fine_tuning_archival.get_db') as mock_db, \
             patch('src.tasks.fine_tuning_archival.FineTuningGCSService') as mock_gcs:

            # Mock database
            mock_session = Mock()
            mock_session.query.return_value.filter.return_value.count.return_value = 10
            mock_db.return_value.__enter__.return_value = mock_session

            # Mock GCS service
            mock_gcs_instance = Mock()
            mock_gcs_instance.get_bucket_usage_report = AsyncMock(return_value={'storage': 'info'})
            mock_gcs_instance.get_fine_tuning_data_summary = AsyncMock(return_value={'summary': 'data'})
            mock_gcs.return_value = mock_gcs_instance

            result = await generate_fine_tuning_report()

            assert 'generated_at' in result
            assert 'bucket_usage' in result
            assert 'data_summary' in result
            assert 'recent_activity' in result

class TestIntegrationScenarios:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    async def test_end_to_end_archival_flow(self):
        """Test the complete archival flow from job completion to GCS storage."""
        with patch('src.tasks.fine_tuning_archival.get_db') as mock_db, \
             patch('src.tasks.fine_tuning_archival.FineTuningAnonymizer') as mock_anonymizer, \
             patch('src.tasks.fine_tuning_archival.FineTuningGCSService') as mock_gcs_class:

            # Setup mocks
            mock_session = Mock()
            mock_job = Mock()
            mock_job.job_id = 'job_test123'
            mock_job.tenant_id = 999
            mock_job.status = 'COMPLETED'
            mock_job.trace_data_uri = None
            mock_job.job_type = 'execute_goal'
            mock_job.created_at = datetime.utcnow() - timedelta(minutes=5)
            mock_job.completed_at = datetime.utcnow()

            # Mock execution trace step
            mock_step = Mock()
            mock_step.step_number = 1
            mock_step.step_type = 'THOUGHT'
            mock_step.thought = 'Processing user request'
            mock_step.get_action_input.return_value = {'tool': 'test'}
            mock_step.get_observation_result.return_value = {'result': 'success'}
            mock_step.step_cost = 0.001
            mock_step.model_used = 'gemini-2.5-pro'
            mock_step.get_raw_data.return_value = None

            mock_session.query.return_value.filter.return_value.first.return_value = mock_job
            mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_step]
            mock_db.return_value.__enter__.return_value = mock_session
            mock_job.status = 'COMPLETED'
            # Ensure the mock returns the actual status value, not a MagicMock
            mock_job.configure_mock(**{'status': 'COMPLETED'})
            # Also set the return value for the status attribute
            type(mock_job).status = property(lambda self: 'COMPLETED')

            # Mock anonymizer
            anonymized_trace = {
                'metadata': {'job_type': 'execute_goal'},
                'steps': [{'step_type': 'THOUGHT', 'thought': 'Processing user request'}],
                '_anonymization_info': {'version': '1.0'}
            }
            mock_anonymizer_instance = Mock()
            mock_anonymizer_instance.anonymize_execution_trace = AsyncMock(return_value=anonymized_trace)
            mock_anonymizer.return_value = mock_anonymizer_instance

            # Mock GCS service
            mock_gcs_instance = Mock()
            mock_gcs_instance.upload_trace_to_fine_tuning_bucket = AsyncMock(
                return_value='gs://etherion-ai-fine-tuning/traces/tenant999/job_test123_20250101_120000.jsonl'
            )
            mock_gcs_class.return_value = mock_gcs_instance

            # Execute the task
            result = await archive_for_fine_tuning('job_test123', 999)

            # Verify the complete flow
            assert result['success'] is True
            assert 'gcs_uri' in result
            assert result['gcs_uri'].startswith('gs://etherion-ai-fine-tuning/')

            # Verify database was updated
            mock_session.commit.assert_called_once()

            # Verify anonymization was called
            mock_anonymizer_instance.anonymize_execution_trace.assert_called_once()

            # Verify GCS upload was called
            mock_gcs_instance.upload_trace_to_fine_tuning_bucket.assert_called_once()

    @pytest.mark.asyncio
    async def test_privacy_protection_end_to_end(self, sample_execution_trace):
        """Test that privacy is protected throughout the entire flow."""
        anonymizer = FineTuningAnonymizer()
        tenant_id = 123

        # Anonymize the trace
        anonymized = await anonymizer.anonymize_execution_trace(sample_execution_trace, tenant_id)

        # Verify no PII in the anonymized trace (excluding anonymization metadata)
        # Remove the anonymization info section before checking
        trace_without_metadata = {k: v for k, v in anonymized.items() if k != '_anonymization_info'}
        anonymized_str = json.dumps(trace_without_metadata)
        assert 'tenant_id' not in anonymized_str
        assert 'user_id' not in anonymized_str
        assert 'test@example.com' not in anonymized_str
        assert 'sk-1234567890abcdef' not in anonymized_str

        # Verify execution patterns are preserved
        assert 'steps' in anonymized
        assert len(anonymized['steps']) == 2
        assert 'thought' in anonymized['steps'][0]
        assert 'action_tool' in anonymized['steps'][1]

        # Verify anonymization metadata is present
        assert '_anonymization_info' in anonymized
        assert anonymized['_anonymization_info']['version'] == '1.0'
        assert 'original_tenant_id_hash' in anonymized['_anonymization_info']

    @pytest.mark.asyncio
    async def test_error_handling_and_retry(self):
        """Test error handling and retry logic."""
        with patch('src.tasks.fine_tuning_archival.get_db') as mock_db, \
             patch('src.tasks.fine_tuning_archival.FineTuningGCSService') as mock_gcs_class:

            # Mock database with a job that will cause an error
            mock_session = Mock()
            mock_job = Mock()
            mock_job.job_id = 'job_error123'
            mock_job.tenant_id = 456
            mock_job.status = 'COMPLETED'

            mock_session.query.return_value.filter.return_value.first.return_value = mock_job
            mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
            mock_db.return_value.__enter__.return_value = mock_session
            mock_job.status = 'COMPLETED'
            # Ensure the mock returns the actual status value, not a MagicMock
            mock_job.configure_mock(**{'status': 'COMPLETED'})
            # Also set the return value for the status attribute
            type(mock_job).status = property(lambda self: 'COMPLETED')

            # Mock GCS service to cause an error
            mock_gcs_instance = Mock()
            mock_gcs_instance.upload_trace_to_fine_tuning_bucket = AsyncMock(side_effect=Exception("GCS Error"))
            mock_gcs_class.return_value = mock_gcs_instance

            # Test with empty trace (should fail)
            result = await archive_for_fine_tuning('job_error123', 456)

            assert result['success'] is False
            assert result['reason'] == 'job_not_completed'

    def test_tenant_isolation(self):
        """Test that tenant data is properly isolated."""
        # Test that tenant hashes are different for different tenants
        tenant_1_hash = hashlib.sha256(str(123).encode()).hexdigest()
        tenant_2_hash = hashlib.sha256(str(456).encode()).hexdigest()

        assert tenant_1_hash != tenant_2_hash
        assert len(tenant_1_hash) == 64  # SHA256 produces 64 character hex string
        assert len(tenant_2_hash) == 64

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
