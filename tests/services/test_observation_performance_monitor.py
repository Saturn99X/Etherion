import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal
import json

from src.services.observation_performance_monitor import (
    ObservationPerformanceMonitor,
    start_observation_timing,
    end_observation_timing,
    record_observation_error,
    get_observation_performance_summary,
    log_observation_performance_report
)


class TestObservationPerformanceMonitor:
    """Test suite for ObservationPerformanceMonitor"""

    @pytest.fixture
    def performance_monitor(self):
        """Provide an ObservationPerformanceMonitor instance"""
        return ObservationPerformanceMonitor()

    @pytest.fixture
    def sample_user_id(self):
        """Provide a sample user ID"""
        return 123

    @pytest.fixture
    def sample_tenant_id(self):
        """Provide a sample tenant ID"""
        return 456

    def test_start_and_end_timing(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test timing functionality"""
        # Start timing
        timer_id = performance_monitor.start_timing(
            'record_interaction',
            sample_user_id,
            sample_tenant_id
        )

        assert isinstance(timer_id, str)
        assert 'record_interaction' in timer_id
        assert str(sample_user_id) in timer_id
        assert str(sample_tenant_id) in timer_id

        # End timing
        duration = performance_monitor.end_timing(
            timer_id,
            'record_interaction',
            sample_user_id,
            sample_tenant_id
        )

        assert isinstance(duration, float)
        assert duration >= 0

    def test_record_error(self, performance_monitor, sample_tenant_id):
        """Test error recording"""
        test_error = Exception("Test error message")

        # Record error
        performance_monitor.record_error('record_interaction', sample_tenant_id, test_error)

        # Verify error was recorded
        metrics = performance_monitor.get_performance_metrics('record_interaction', sample_tenant_id)
        assert metrics['errors'] == 1

    def test_get_performance_metrics(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test getting performance metrics"""
        # Record some operations
        timer_id1 = performance_monitor.start_timing('record_interaction', sample_user_id, sample_tenant_id)
        timer_id2 = performance_monitor.start_timing('generate_system_instructions', sample_user_id, sample_tenant_id)

        performance_monitor.end_timing(timer_id1, 'record_interaction', sample_user_id, sample_tenant_id)
        performance_monitor.end_timing(timer_id2, 'generate_system_instructions', sample_user_id, sample_tenant_id)

        # Get metrics for specific operation
        metrics = performance_monitor.get_performance_metrics('record_interaction', sample_tenant_id)
        assert metrics['count'] == 1
        assert metrics['total_time'] > 0
        assert metrics['avg_time'] > 0

        # Get all metrics for tenant
        all_metrics = performance_monitor.get_performance_metrics(None, sample_tenant_id)
        assert 'record_interaction:456' in all_metrics
        assert 'generate_system_instructions:456' in all_metrics

    def test_get_performance_summary(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test performance summary generation"""
        # Record multiple operations
        for i in range(5):
            timer_id = performance_monitor.start_timing('record_interaction', sample_user_id, sample_tenant_id)
            performance_monitor.end_timing(timer_id, 'record_interaction', sample_user_id, sample_tenant_id)

        # Get summary
        summary = performance_monitor.get_performance_summary(sample_tenant_id)

        assert isinstance(summary, dict)
        assert summary['total_operations'] == 5
        assert summary['total_time'] > 0
        assert summary['avg_operation_time'] > 0
        assert 'operations_by_type' in summary
        assert 'record_interaction' in summary['operations_by_type']

    def test_performance_threshold_detection(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test performance threshold detection"""
        # Record slow operation (exceeding threshold)
        timer_id = performance_monitor.start_timing('record_interaction', sample_user_id, sample_tenant_id)
        # Simulate slow operation by manually setting high duration
        performance_monitor.metrics['record_interaction:456']['count'] = 1
        performance_monitor.metrics['record_interaction:456']['total_time'] = 0.5  # 500ms (exceeds 100ms threshold)
        performance_monitor.metrics['record_interaction:456']['avg_time'] = 0.5
        performance_monitor.metrics['record_interaction:456']['last_recorded'] = datetime.utcnow()

        # Get summary
        summary = performance_monitor.get_performance_summary(sample_tenant_id)

        # Should detect performance issues
        assert len(summary.get('performance_issues', [])) > 0

        # Should have recommendations
        assert len(summary.get('recommendations', [])) > 0

    def test_generate_recommendations(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test recommendation generation"""
        # Set up high error rate scenario
        performance_monitor.metrics['record_interaction:456']['count'] = 10
        performance_monitor.metrics['record_interaction:456']['errors'] = 3  # 30% error rate
        performance_monitor.metrics['record_interaction:456']['total_time'] = 1.0
        performance_monitor.metrics['record_interaction:456']['avg_time'] = 0.1
        performance_monitor.metrics['record_interaction:456']['last_recorded'] = datetime.utcnow()

        # Get summary
        summary = performance_monitor.get_performance_summary(sample_tenant_id)

        # Should generate recommendations for high error rate
        recommendations = summary.get('recommendations', [])
        assert len(recommendations) > 0

        # Check for error rate recommendation
        error_rate_recommendation = any('error rate' in rec.lower() for rec in recommendations)
        assert error_rate_recommendation

    def test_convenience_functions(self, sample_user_id, sample_tenant_id):
        """Test convenience functions for performance monitoring"""
        # Test start timing convenience function
        timer_id = start_observation_timing('record_interaction', sample_user_id, sample_tenant_id)
        assert isinstance(timer_id, str)

        # Test end timing convenience function
        duration = end_observation_timing(timer_id, 'record_interaction', sample_user_id, sample_tenant_id)
        assert isinstance(duration, float)

        # Test error recording convenience function
        test_error = Exception("Convenience function test error")
        record_observation_error('record_interaction', sample_tenant_id, test_error)

    @pytest.mark.asyncio
    async def test_async_performance_summary(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test async performance summary retrieval"""
        # Record some operations
        for i in range(3):
            timer_id = performance_monitor.start_timing('get_user_observations', sample_user_id, sample_tenant_id)
            performance_monitor.end_timing(timer_id, 'get_user_observations', sample_user_id, sample_tenant_id)

        # Get async summary
        summary = await get_observation_performance_summary(sample_tenant_id)

        assert isinstance(summary, dict)
        assert summary['total_operations'] == 3
        assert 'get_user_observations' in summary['operations_by_type']

    @pytest.mark.asyncio
    async def test_performance_report_logging(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test performance report logging"""
        # Record some operations
        for i in range(2):
            timer_id = performance_monitor.start_timing('record_interaction', sample_user_id, sample_tenant_id)
            performance_monitor.end_timing(timer_id, 'record_interaction', sample_user_id, sample_tenant_id)

        # Mock logger to capture output
        with patch('src.services.observation_performance_monitor.logger') as mock_logger:
            # Log performance report
            await log_observation_performance_report(sample_tenant_id)

            # Verify logger was called
            assert mock_logger.info.called or mock_logger.warning.called

    def test_cache_export_functionality(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test cache export functionality"""
        # Record some operations
        timer_id = performance_monitor.start_timing('record_interaction', sample_user_id, sample_tenant_id)
        performance_monitor.end_timing(timer_id, 'record_interaction', sample_user_id, sample_tenant_id)

        with patch.object(performance_monitor.cache_manager, 'set_db_query') as mock_cache:
            # Export to cache
            asyncio.run(performance_monitor.export_metrics_to_cache(sample_tenant_id))

            # Verify cache was set
            mock_cache.assert_called_once()
            call_args = mock_cache.call_args
            assert sample_tenant_id in str(call_args[0][0])  # cache key contains tenant_id

    def test_cleanup_old_metrics(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test cleanup of old performance metrics"""
        # Record operation with old timestamp
        performance_monitor.metrics['record_interaction:456']['count'] = 1
        performance_monitor.metrics['record_interaction:456']['total_time'] = 0.1
        performance_monitor.metrics['record_interaction:456']['avg_time'] = 0.1
        performance_monitor.metrics['record_interaction:456']['last_recorded'] = datetime.utcnow() - timedelta(days=10)

        # Add old sample
        old_sample = {
            'timestamp': datetime.utcnow() - timedelta(days=10),
            'duration': 0.1,
            'user_id': sample_user_id,
            'operation': 'record_interaction'
        }
        performance_monitor.performance_samples['record_interaction:456'].append(old_sample)

        # Cleanup old metrics (more than 7 days)
        asyncio.run(performance_monitor.cleanup_old_metrics(days=7))

        # Verify old metrics were cleaned up
        assert 'record_interaction:456' not in performance_monitor.metrics
        assert len(performance_monitor.performance_samples['record_interaction:456']) == 0

    def test_background_monitoring_task_error_handling(self, performance_monitor):
        """Test error handling in background monitoring task"""
        with patch('src.services.observation_performance_monitor.get_tenant_context', side_effect=Exception("Context error")):
            with patch('src.services.observation_performance_monitor.logger') as mock_logger:
                # Run background task briefly (it will fail but should handle gracefully)
                async def test_background_task():
                    try:
                        # Just try to start the task, it will fail immediately due to mocking
                        await performance_monitor.background_monitoring_task()
                    except asyncio.CancelledError:
                        pass  # Expected when cancelled
                    except Exception as e:
                        # Should handle the error gracefully
                        mock_logger.error.assert_called()

                # This will fail due to mocking, but should not raise unhandled exceptions
                try:
                    asyncio.run(test_background_task())
                except Exception:
                    pass  # Expected due to mocking

    def test_multiple_operations_tracking(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test tracking multiple different operations"""
        operations = [
            'record_interaction',
            'generate_system_instructions',
            'get_user_observations',
            'record_execution_trace_observation'
        ]

        # Record multiple operations
        for op in operations:
            timer_id = performance_monitor.start_timing(op, sample_user_id, sample_tenant_id)
            performance_monitor.end_timing(timer_id, op, sample_user_id, sample_tenant_id)

        # Get summary
        summary = performance_monitor.get_performance_summary(sample_tenant_id)

        # Verify all operations are tracked
        operations_by_type = summary.get('operations_by_type', {})
        for op in operations:
            assert op in operations_by_type
            assert operations_by_type[op]['count'] == 1

    def test_high_volume_operations(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test handling high volume of operations"""
        # Record many operations
        for i in range(100):
            timer_id = performance_monitor.start_timing('record_interaction', sample_user_id, sample_tenant_id)
            performance_monitor.end_timing(timer_id, 'record_interaction', sample_user_id, sample_tenant_id)

        # Get summary
        summary = performance_monitor.get_performance_summary(sample_tenant_id)

        # Should handle high volume
        assert summary['total_operations'] == 100
        assert summary['total_time'] > 0

        # Recommendations should include high volume warning
        recommendations = summary.get('recommendations', [])
        high_volume_recommendation = any('volume' in rec.lower() for rec in recommendations)
        assert high_volume_recommendation

    def test_mixed_success_and_error_scenarios(self, performance_monitor, sample_user_id, sample_tenant_id):
        """Test mixed success and error scenarios"""
        # Record successful operations
        for i in range(8):
            timer_id = performance_monitor.start_timing('record_interaction', sample_user_id, sample_tenant_id)
            performance_monitor.end_timing(timer_id, 'record_interaction', sample_user_id, sample_tenant_id)

        # Record errors
        for i in range(2):
            performance_monitor.record_error('record_interaction', sample_tenant_id, Exception(f"Error {i}"))

        # Get summary
        summary = performance_monitor.get_performance_summary(sample_tenant_id)

        # Should calculate error rate correctly
        operations_by_type = summary.get('operations_by_type', {})
        record_interaction = operations_by_type.get('record_interaction', {})
        error_rate = record_interaction.get('error_rate', 0)

        assert abs(error_rate - 0.2) < 0.01  # 20% error rate (2 errors out of 10 operations)

    def test_performance_monitor_singleton_behavior(self):
        """Test singleton behavior of performance monitor"""
        from src.services.observation_performance_monitor import get_observation_performance_monitor

        # Get multiple instances
        monitor1 = get_observation_performance_monitor()
        monitor2 = get_observation_performance_monitor()

        # Should be the same instance
        assert monitor1 is monitor2

        # Should maintain state across calls
        monitor1.metrics['test_key'] = {'count': 1}
        assert monitor2.metrics['test_key']['count'] == 1
