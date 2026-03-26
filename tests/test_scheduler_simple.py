# tests/test_scheduler_simple.py
import pytest
from src.scheduler.models import ScheduledTask
from src.scheduler.service import SchedulerService


class TestSchedulerSimple:
    """Simple test cases for the scheduler functionality."""

    def test_scheduled_task_model_exists(self):
        """Test that the ScheduledTask model exists."""
        # This test just verifies that the model can be imported
        assert ScheduledTask.__name__ == "ScheduledTask"

    def test_scheduler_service_exists(self):
        """Test that the SchedulerService exists."""
        # This test just verifies that the service can be imported
        assert hasattr(SchedulerService, "create_scheduled_task")
        assert hasattr(SchedulerService, "update_scheduled_task")
        assert hasattr(SchedulerService, "delete_scheduled_task")
        assert hasattr(SchedulerService, "get_scheduled_tasks_by_tenant")
        assert hasattr(SchedulerService, "get_scheduled_task_by_id")