# src/scheduler/tasks.py
from celery import Celery
import redis
import json
from datetime import datetime
from sqlmodel import Session, select
from src.database.db import sync_engine as engine
from src.scheduler.models import ScheduledTask
from src.database.models import Tenant, User, Project
from src.etherion_ai.graphql_schema.input_types import GoalInput
from src.utils.llm_loader import get_gemini_llm
from src.services.orchestrator_runtime import create_named_orchestrator_runtime
from src.services.user_observation_service import get_user_observation_service
import asyncio
import uuid

# Initialize Celery
celery_app = Celery('scheduler', broker='redis://localhost:6379/0')

# Connect to Redis for Pub/Sub
redis_client = redis.Redis(decode_responses=True)

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def execute_scheduled_goal(self, tenant_id: int, user_id: int, project_id: int, goal_input: dict, scheduled_task_id: int):
    """Execute a scheduled goal task."""
    try:
        # Update task status to running
        with Session(engine) as session:
            task = session.get(ScheduledTask, scheduled_task_id)
            if task:
                task.status = "running"
                task.celery_task_id = self.request.id
                session.add(task)
                session.commit()

        # Execute the goal using the existing orchestrator
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(_execute_goal(tenant_id, user_id, project_id, goal_input))

        # Update task status to completed
        with Session(engine) as session:
            task = session.get(ScheduledTask, scheduled_task_id)
            if task:
                task.status = "completed"
                task.last_execution_result = json.dumps(result)
                task.updated_at = datetime.utcnow()
                session.add(task)
                session.commit()

    except Exception as exc:
        # Update task status to failed
        with Session(engine) as session:
            task = session.get(ScheduledTask, scheduled_task_id)
            if task:
                task.status = "failed"
                task.execution_log = str(exc)
                task.updated_at = datetime.utcnow()
                session.add(task)
                session.commit()
        raise self.retry(exc=exc)

async def _execute_goal(tenant_id: int, user_id: int, project_id: int, goal_input: dict):
    """Execute a goal using the orchestrator agent."""
    # Get tenant, user, and project information
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        user = session.get(User, user_id)
        project = session.get(Project, project_id)

    # Create the orchestrator agent
    llm_pro = get_gemini_llm(model_tier='pro')
    director_agent_obj = create_named_orchestrator_runtime(profile_name="team_orchestrator", llm=llm_pro)

    # Prepare the goal with context
    observation_service = get_user_observation_service()
    feedback_history = await observation_service.generate_system_instructions(
        user_id=user_id,
        tenant_id=tenant_id
    )

    comprehensive_goal = (
        f"**User Past Feedback Analysis:**\n{feedback_history}\n\n"
        f"**Current User Goal:**\n{goal_input.get('goal', '')}\n\n"
        f"**Additional Context & Constraints:**\n{goal_input.get('context', 'None provided.')}\n\n"
        f"**Required Final Output Format:**\n{goal_input.get('output_format_instructions', 'A clear, final text answer.')}"
    )

    # Execute the goal
    job_id = f"scheduled:{uuid.uuid4()}"
    result = await director_agent_obj.ainvoke({"input": comprehensive_goal, "metadata": {"job_id": job_id}})

    return result