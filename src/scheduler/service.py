# src/scheduler/service.py
from datetime import datetime
from sqlmodel import Session, select
from src.database.db import sync_engine as engine
from src.scheduler.models import ScheduledTask
from src.scheduler.tasks import execute_scheduled_goal
from src.database.models import Tenant, User, Project
from src.etherion_ai.graphql_schema.input_types import GoalInput
import json


class SchedulerService:
    @staticmethod
    def create_scheduled_task(tenant_id: int, user_id: int, project_id: int, goal_input: GoalInput, scheduled_at: datetime) -> ScheduledTask:
        """Create a new scheduled task."""
        with Session(engine) as session:
            # Verify that the project belongs to the tenant
            project = session.get(Project, project_id)
            if not project or project.tenant_id != tenant_id:
                raise Exception("Project not found or access denied.")
            
            # Create the scheduled task
            task = ScheduledTask(
                tenant_id=tenant_id,
                user_id=user_id,
                project_id=project_id,
                goal_input=goal_input.json() if hasattr(goal_input, 'json') else json.dumps(goal_input.__dict__),
                scheduled_at=scheduled_at
            )
            
            session.add(task)
            session.commit()
            session.refresh(task)
            
            # Schedule the task with Celery
            execute_scheduled_goal.apply_async(
                args=[tenant_id, user_id, project_id, goal_input.__dict__, task.id],
                eta=scheduled_at
            )
            
            return task
    
    @staticmethod
    def update_scheduled_task(task_id: int, tenant_id: int, user_id: int, project_id: int, goal_input: GoalInput, scheduled_at: datetime) -> ScheduledTask:
        """Update an existing scheduled task."""
        with Session(engine) as session:
            # Verify that the task belongs to the tenant
            task = session.get(ScheduledTask, task_id)
            if not task or task.tenant_id != tenant_id:
                raise Exception("Scheduled task not found or access denied.")
            
            # Verify that the project belongs to the tenant
            project = session.get(Project, project_id)
            if not project or project.tenant_id != tenant_id:
                raise Exception("Project not found or access denied.")
            
            # Update the task
            task.user_id = user_id
            task.project_id = project_id
            task.goal_input = goal_input.json() if hasattr(goal_input, 'json') else json.dumps(goal_input.__dict__)
            task.scheduled_at = scheduled_at
            task.updated_at = datetime.utcnow()
            
            session.add(task)
            session.commit()
            session.refresh(task)
            
            # Reschedule the task with Celery if it's still pending
            if task.status == "pending":
                # Revoke the existing task if it exists
                if task.celery_task_id:
                    from src.scheduler.tasks import celery_app
                    celery_app.control.revoke(task.celery_task_id)
                
                # Schedule the updated task
                execute_scheduled_goal.apply_async(
                    args=[tenant_id, user_id, project_id, goal_input.__dict__, task.id],
                    eta=scheduled_at
                )
            
            return task
    
    @staticmethod
    def delete_scheduled_task(task_id: int, tenant_id: int) -> bool:
        """Delete a scheduled task."""
        with Session(engine) as session:
            # Verify that the task belongs to the tenant
            task = session.get(ScheduledTask, task_id)
            if not task or task.tenant_id != tenant_id:
                raise Exception("Scheduled task not found or access denied.")
            
            # Revoke the task if it's still pending
            if task.status == "pending" and task.celery_task_id:
                from src.scheduler.tasks import celery_app
                celery_app.control.revoke(task.celery_task_id)
            
            session.delete(task)
            session.commit()
            
            return True
    
    @staticmethod
    def get_scheduled_tasks_by_tenant(tenant_id: int) -> list[ScheduledTask]:
        """Get all scheduled tasks for a tenant."""
        with Session(engine) as session:
            statement = select(ScheduledTask).where(ScheduledTask.tenant_id == tenant_id)
            tasks = session.exec(statement).all()
            return tasks
    
    @staticmethod
    def get_scheduled_task_by_id(task_id: int, tenant_id: int) -> ScheduledTask:
        """Get a specific scheduled task by ID."""
        with Session(engine) as session:
            task = session.get(ScheduledTask, task_id)
            if not task or task.tenant_id != tenant_id:
                raise Exception("Scheduled task not found or access denied.")
            return task