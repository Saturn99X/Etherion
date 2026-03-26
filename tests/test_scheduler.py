# tests/test_scheduler.py
import pytest
from datetime import datetime, timedelta
from sqlmodel import Session, select
from src.scheduler.models import ScheduledTask
from src.scheduler.service import SchedulerService
from src.database.models import Tenant, User, Project
from src.database.db import engine


class TestScheduler:
    """Test cases for the scheduler functionality."""

    def test_create_scheduled_task(self):
        """Test creating a scheduled task."""
        # Create test data
        with Session(engine) as session:
            # Create a tenant
            tenant = Tenant(
                tenant_id="test_tenant_123",
                subdomain="test",
                name="Test Tenant",
                admin_email="admin@test.com"
            )
            session.add(tenant)
            session.commit()
            session.refresh(tenant)

            # Create a user
            user = User(
                user_id="test_user_123",
                email="user@test.com",
                name="Test User",
                tenant_id=tenant.id
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            # Create a project
            project = Project(
                name="Test Project",
                description="A test project",
                user_id=user.id,
                tenant_id=tenant.id
            )
            session.add(project)
            session.commit()
            session.refresh(project)

        # Test creating a scheduled task
        goal_input = {
            "goal": "Create a blog post about AI",
            "context": "Focus on practical applications",
            "userId": "test_user_123"
        }
        
        scheduled_at = datetime.utcnow() + timedelta(hours=1)
        
        task = SchedulerService.create_scheduled_task(
            tenant_id=tenant.id,
            user_id=user.id,
            project_id=project.id,
            goal_input=goal_input,
            scheduled_at=scheduled_at
        )

        # Verify the task was created correctly
        assert task.tenant_id == tenant.id
        assert task.user_id == user.id
        assert task.project_id == project.id
        assert task.status == "pending"
        assert task.scheduled_at == scheduled_at

        # Clean up
        with Session(engine) as session:
            session.delete(task)
            session.delete(project)
            session.delete(user)
            session.delete(tenant)
            session.commit()

    def test_get_scheduled_tasks_by_tenant(self):
        """Test retrieving scheduled tasks by tenant."""
        # Create test data
        with Session(engine) as session:
            # Create a tenant
            tenant = Tenant(
                tenant_id="test_tenant_456",
                subdomain="test2",
                name="Test Tenant 2",
                admin_email="admin2@test.com"
            )
            session.add(tenant)
            session.commit()
            session.refresh(tenant)

            # Create a user
            user = User(
                user_id="test_user_456",
                email="user2@test.com",
                name="Test User 2",
                tenant_id=tenant.id
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            # Create a project
            project = Project(
                name="Test Project 2",
                description="Another test project",
                user_id=user.id,
                tenant_id=tenant.id
            )
            session.add(project)
            session.commit()
            session.refresh(project)

            # Create scheduled tasks
            goal_input = {
                "goal": "Create a blog post about AI",
                "context": "Focus on practical applications",
                "userId": "test_user_456"
            }
            
            scheduled_at = datetime.utcnow() + timedelta(hours=1)
            
            task1 = ScheduledTask(
                tenant_id=tenant.id,
                user_id=user.id,
                project_id=project.id,
                goal_input=str(goal_input),
                scheduled_at=scheduled_at,
                status="pending"
            )
            
            task2 = ScheduledTask(
                tenant_id=tenant.id,
                user_id=user.id,
                project_id=project.id,
                goal_input=str(goal_input),
                scheduled_at=scheduled_at,
                status="pending"
            )
            
            session.add(task1)
            session.add(task2)
            session.commit()
            session.refresh(task1)
            session.refresh(task2)

        # Test retrieving tasks by tenant
        tasks = SchedulerService.get_scheduled_tasks_by_tenant(tenant.id)
        
        # Verify we got the correct tasks
        assert len(tasks) == 2
        task_ids = [task.id for task in tasks]
        assert task1.id in task_ids
        assert task2.id in task_ids

        # Clean up
        with Session(engine) as session:
            session.delete(task1)
            session.delete(task2)
            session.delete(project)
            session.delete(user)
            session.delete(tenant)
            session.commit()