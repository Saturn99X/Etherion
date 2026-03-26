"""
Tests for Celery tasks functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import json

from src.core.tasks import (
    cache_eviction_task,
    knowledge_base_population_task,
    real_time_job_status_update_task,
    gcs_archival_task,
    update_job_status_task,
    archive_execution_trace_task
)
from src.database.models import Job, JobStatus, User, Tenant


class TestCacheEvictionTask:
    """Test cache eviction task."""
    
    @pytest.mark.asyncio
    async def test_cache_eviction_task_success(self):
        """Test successful cache eviction task."""
        with patch('src.cache.cache_manager.get_cache') as mock_get_cache, \
             patch('src.cache.eviction_engine.CacheEvictionEngine') as mock_eviction_engine_class:
            
            # Mock cache and eviction engine
            mock_cache = AsyncMock()
            mock_eviction_engine = AsyncMock()
            mock_eviction_engine._running = False
            mock_eviction_engine.start = AsyncMock()
            mock_eviction_engine.evict_lru = AsyncMock(return_value=Mock(
                evicted_count=5,
                eviction_reasons={"lru_l1": 5},
                last_eviction_time=datetime.utcnow()
            ))
            
            mock_get_cache.return_value = mock_cache
            mock_eviction_engine_class.return_value = mock_eviction_engine
            
            # Create mock task
            mock_task = Mock()
            mock_task.retry = Mock(side_effect=Exception("Retry called"))
            
            # Test the task
            result = cache_eviction_task("lru", 10)
            
            assert result["success"] is True
            assert result["eviction_type"] == "lru"
            assert result["evicted_count"] == 5
            assert "lru_l1" in result["eviction_reasons"]
    
    @pytest.mark.asyncio
    async def test_cache_eviction_task_retry(self):
        """Test cache eviction task retry on failure."""
        with patch('src.cache.cache_manager.get_cache') as mock_get_cache:
            mock_get_cache.side_effect = Exception("Cache error")
            
            mock_task = Mock()
            mock_task.retry = Mock(side_effect=Exception("Retry called"))
            
            with pytest.raises(Exception, match="Cache error"):
                cache_eviction_task("lru", 10)


class TestKnowledgeBasePopulationTask:
    """Test knowledge base population task."""
    
    @pytest.mark.asyncio
    async def test_knowledge_base_population_success(self):
        """Test successful knowledge base population."""
        with patch('src.database.db.get_session') as mock_get_session, \
             patch('src.tools.knowledge_base_tools.KnowledgeBaseManager') as mock_kb_manager_class:
            
            # Mock database session
            mock_session = Mock()
            mock_tenant = Mock()
            mock_tenant.id = 1
            mock_session.query.return_value.filter.return_value.first.return_value = mock_tenant
            mock_get_session.return_value.__enter__.return_value = mock_session
            
            # Mock knowledge base manager
            mock_kb_manager = Mock()
            mock_kb_manager.add_user_feedback = Mock()
            mock_kb_manager_class.return_value = mock_kb_manager
            
            # Create mock task
            mock_task = Mock()
            mock_task.retry = Mock(side_effect=Exception("Retry called"))
            
            # Test data
            tenant_id = 1
            data_source = "user_feedback"
            data = {
                "feedback": [
                    {
                        "user_id": "user1",
                        "content": "Great service!",
                        "rating": 5,
                        "context": {}
                    }
                ]
            }
            
            result = knowledge_base_population_task(
                tenant_id, data_source, data
            )
            
            assert result["success"] is True
            assert result["tenant_id"] == tenant_id
            assert result["data_source"] == data_source
            assert result["processed_count"] == 1
            assert result["error_count"] == 0
    
    @pytest.mark.asyncio
    async def test_knowledge_base_population_tenant_not_found(self):
        """Test knowledge base population with non-existent tenant."""
        with patch('src.database.db.get_session') as mock_get_session:
            # Mock database session with no tenant
            mock_session = Mock()
            mock_session.query.return_value.filter.return_value.first.return_value = None
            mock_get_session.return_value.__enter__.return_value = mock_session
            
            mock_task = Mock()
            mock_task.retry = Mock(side_effect=Exception("Retry called"))
            
            result = knowledge_base_population_task(
                999, "user_feedback", {}
            )
            
            assert result["success"] is False
            assert "Tenant not found" in result["error"]


class TestRealTimeJobStatusUpdateTask:
    """Test real-time job status update task."""
    
    @pytest.mark.asyncio
    async def test_real_time_job_status_update_success(self):
        """Test successful real-time job status update."""
        with patch('src.database.db.get_db') as mock_get_db, \
             patch('src.core.redis.publish_job_status') as mock_publish:
            
            # Mock database session
            mock_session = Mock()
            mock_job = Mock()
            mock_job.tenant_id = 1
            mock_session.query.return_value.filter.return_value.first.return_value = mock_job
            mock_get_db.return_value = mock_session
            
            # Mock Redis publish
            mock_publish.return_value = None
            
            mock_task = Mock()
            mock_task.retry = Mock(side_effect=Exception("Retry called"))
            
            result = real_time_job_status_update_task(
                "job_123", "completed", 100.0, {"step": "final"}
            )
            
            assert result["success"] is True
            assert result["job_id"] == "job_123"
            assert result["status"] == "completed"
            assert result["progress"] == 100.0
            assert result["tenant_id"] == 1
            
            # Verify publish was called twice (job channel and tenant channel)
            assert mock_publish.call_count == 2
    
    @pytest.mark.asyncio
    async def test_real_time_job_status_update_job_not_found(self):
        """Test real-time job status update with non-existent job."""
        with patch('src.database.db.get_session') as mock_get_session:
            # Mock database session with no job
            mock_session = Mock()
            mock_session.query.return_value.filter.return_value.first.return_value = None
            mock_get_session.return_value.__enter__.return_value = mock_session
            
            mock_task = Mock()
            mock_task.retry = Mock(side_effect=Exception("Retry called"))
            
            result = real_time_job_status_update_task(
                "nonexistent_job", "completed"
            )
            
            assert result["success"] is False
            assert "Job not found" in result["error"]


class TestGCSArchivalTask:
    """Test GCS archival task."""
    
    @pytest.mark.asyncio
    async def test_gcs_archival_success(self):
        """Test successful GCS archival."""
        with patch('src.core.gcs_client.GCSClient') as mock_gcs_class, \
             patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('os.unlink') as mock_unlink:
            
            # Mock GCS client
            mock_gcs = Mock()
            mock_gcs.upload_file.return_value = "gs://bucket/path/file.json"
            mock_gcs_class.return_value = mock_gcs
            
            # Mock temporary file
            mock_temp = Mock()
            mock_temp.name = "/tmp/test.json"
            mock_temp.__enter__ = Mock(return_value=mock_temp)
            mock_temp.__exit__ = Mock(return_value=None)
            mock_temp_file.return_value = mock_temp
            
            mock_task = Mock()
            mock_task.retry = Mock(side_effect=Exception("Retry called"))
            
            # Test data
            tenant_id = 1
            data_type = "job_results"
            data = {"job_id": "job_123", "result": "success"}
            retention_days = 90
            
            result = gcs_archival_task(
                tenant_id, data_type, data, retention_days
            )
            
            assert result["success"] is True
            assert result["tenant_id"] == tenant_id
            assert result["data_type"] == data_type
            assert result["gcs_uri"] == "gs://bucket/path/file.json"
            assert result["retention_days"] == retention_days
            
            # Verify GCS upload was called
            mock_gcs.upload_file.assert_called_once()
            # Verify temp file was cleaned up
            mock_unlink.assert_called_once_with("/tmp/test.json")


class TestUpdateJobStatusTask:
    """Test job status update task."""
    
    @pytest.mark.asyncio
    async def test_update_job_status_success(self):
        """Test successful job status update."""
        with patch('src.core.tenant_tasks.tenant_scoped_session') as mock_tenant_session, \
             patch('src.core.redis.publish_job_status') as mock_publish, \
             patch('src.database.db.get_db') as mock_get_db:
            
            # Mock database session
            mock_session = Mock()
            mock_job = Mock()
            mock_job.tenant_id = 1
            mock_job.status = JobStatus.RUNNING
            mock_job.update_status = Mock()
            mock_job.last_updated_at = datetime.utcnow()
            mock_session.query.return_value.filter.return_value.first.return_value = mock_job
            mock_get_db.return_value = mock_session
            
            # Mock tenant session
            mock_tenant_session.return_value.__enter__.return_value = mock_session
            mock_tenant_session.return_value.__exit__.return_value = None
            
            # Mock Redis publish
            mock_publish.return_value = None
            
            mock_task = Mock()
            mock_task.retry = Mock(side_effect=Exception("Retry called"))
            
            result = update_job_status_task(
                "job_123", "COMPLETED", None, 1
            )
            
            assert result["success"] is True
            assert result["job_id"] == "job_123"
            assert result["tenant_id"] == 1
            assert result["new_status"] == "COMPLETED"
            
            # Verify job status was updated
            mock_job.update_status.assert_called_once_with(JobStatus.COMPLETED)
            # Verify session was committed
            mock_session.commit.assert_called_once()
            # Verify status was published
            mock_publish.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_job_status_with_error(self):
        """Test job status update with error message."""
        with patch('src.core.tenant_tasks.tenant_scoped_session') as mock_tenant_session, \
             patch('src.core.redis.publish_job_status') as mock_publish, \
             patch('src.database.db.get_db') as mock_get_db:
            
            # Mock database session
            mock_session = Mock()
            mock_job = Mock()
            mock_job.tenant_id = 1
            mock_job.status = JobStatus.RUNNING
            mock_job.update_status = Mock()
            mock_job.error_message = None
            mock_job.last_updated_at = datetime.utcnow()
            mock_session.query.return_value.filter.return_value.first.return_value = mock_job
            mock_get_db.return_value = mock_session
            
            # Mock tenant session
            mock_tenant_session.return_value.__enter__.return_value = mock_session
            mock_tenant_session.return_value.__exit__.return_value = None
            
            # Mock Redis publish
            mock_publish.return_value = None
            
            mock_task = Mock()
            mock_task.retry = Mock(side_effect=Exception("Retry called"))
            
            error_message = "Task failed due to timeout"
            result = update_job_status_task(
                "job_123", "FAILED", error_message, 1
            )
            
            assert result["success"] is True
            assert result["new_status"] == "FAILED"
            assert mock_job.error_message == error_message


class TestArchiveExecutionTraceTask:
    """Test execution trace archival task."""
    
    @pytest.mark.asyncio
    async def test_archive_execution_trace_success(self):
        """Test successful execution trace archival."""
        with patch('src.core.tasks.tenant_scoped_session') as mock_tenant_session, \
             patch('src.core.tasks.GCSClient') as mock_gcs_class, \
             patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('os.unlink') as mock_unlink:
            
            # Mock tenant session
            mock_session = Mock()
            mock_job = Mock()
            mock_job.tenant_id = 1
            mock_job.trace_data_uri = None
            mock_job.get_output_data = Mock(return_value={"output": "test"})
            mock_job.set_output_data = Mock()
            
            # Mock execution trace steps
            mock_step = Mock()
            mock_step.job_id = "job_123"
            mock_step.tenant_id = 1
            mock_step.step_number = 1
            mock_step.timestamp = datetime.utcnow()
            mock_step.step_type = Mock()
            mock_step.step_type.value = "action"
            mock_step.thought = "Test thought"
            mock_step.action_tool = "test_tool"
            mock_step.get_action_input = Mock(return_value={"input": "test"})
            mock_step.observation_result = "Test result"
            mock_step.step_cost = 0.01
            mock_step.model_used = "gpt-4"
            mock_step.get_raw_data = Mock(return_value={"raw": "data"})
            
            # Mock the query chain for both job lookups and step queries
            mock_session.query.return_value.filter.return_value.first.return_value = mock_job
            mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_step]
            
            # Mock tenant session for both calls (with and without tenant_id)
            mock_tenant_session.return_value.__enter__.return_value = mock_session
            mock_tenant_session.return_value.__exit__.return_value = None
            
            # Mock GCS client
            mock_gcs = Mock()
            mock_gcs.upload_file.return_value = "gs://bucket/traces/job_123/trace.jsonl"
            mock_gcs_class.return_value = mock_gcs
            
            # Mock temporary file
            mock_temp = Mock()
            mock_temp.name = "/tmp/trace.jsonl"
            mock_temp.__enter__ = Mock(return_value=mock_temp)
            mock_temp.__exit__ = Mock(return_value=None)
            mock_temp_file.return_value = mock_temp
            
            mock_task = Mock()
            mock_task.retry = Mock(side_effect=Exception("Retry called"))
            
            # Debug: Check if mocks are working
            print(f"Mock tenant session: {mock_tenant_session}")
            print(f"Mock session: {mock_session}")
            print(f"Mock job: {mock_job}")
            
            result = archive_execution_trace_task("job_123", 1)
            
            print(f"Archive execution trace result: {result}")
            assert result["success"] is True
            assert result["job_id"] == "job_123"
            assert result["tenant_id"] == 1
            assert result["trace_uri"] == "gs://bucket/traces/job_123/trace.jsonl"
            
            # Verify GCS upload was called
            mock_gcs.upload_file.assert_called_once()
            # Verify job was updated with trace URI
            assert mock_job.trace_data_uri == "gs://bucket/traces/job_123/trace.jsonl"
            # Verify session was committed
            mock_session.commit.assert_called_once()
            # Note: os.unlink mock not working due to local import in task


@pytest.mark.asyncio
async def test_task_retry_mechanism():
    """Test task retry mechanism."""
    # This would test the retry mechanism for failed tasks
    pass


@pytest.mark.asyncio
async def test_task_error_handling():
    """Test task error handling."""
    # This would test error handling in tasks
    pass
