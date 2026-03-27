import os
import logging
from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure, worker_ready
from kombu import Queue
from typing import Dict, Any

# Configure worker logging with Cloud Logging support
try:
    from src.core.worker_logging import configure_worker_logging
    logger = configure_worker_logging(enable_cloud_logging=True)
except Exception as e:
    # Fallback to basic logging if worker_logging fails
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.warning(f"Could not configure worker logging: {e}")

# Broker/result configuration
REDIS_URL = os.getenv("ETHERION_REDIS_URL") or os.getenv("REDIS_URL")
if not REDIS_URL:
    if os.getenv("ENVIRONMENT") == "production":
        raise ValueError("REDIS_URL environment variable is required for production deployment")
    REDIS_URL = "redis://localhost:6379/0"

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
_env_result_backend = os.getenv("CELERY_RESULT_BACKEND")

# In production we do not depend on Celery task results. If the result backend is
# configured to the same Redis instance as the broker, Celery's redis backend
# reconnect logic can cause API requests (send_task) to fail. Default to
# disabling the result backend unless explicitly forced.
_force_result_backend = (os.getenv("CELERY_FORCE_RESULT_BACKEND") or "").lower() == "true"

# Detect in-memory test configuration where broker/results are process-local
_inmemory_transport = CELERY_BROKER_URL.startswith("memory://")
_effective_backend_for_celery = _env_result_backend
CELERY_BACKEND_FOR_APP = _env_result_backend
if not _force_result_backend and not _inmemory_transport:
    _effective_backend_for_celery = "disabled://"
    CELERY_BACKEND_FOR_APP = _effective_backend_for_celery
    os.environ.pop("CELERY_RESULT_BACKEND", None)
    CELERY_RESULT_BACKEND = None
elif _effective_backend_for_celery is None and _inmemory_transport:
    _effective_backend_for_celery = "cache+memory://"
    CELERY_BACKEND_FOR_APP = _effective_backend_for_celery
    CELERY_RESULT_BACKEND = _effective_backend_for_celery
else:
    CELERY_RESULT_BACKEND = _effective_backend_for_celery

logger.warning(
    "Celery config: broker=%r result_backend=%r forced_result_backend=%s effective_backend_for_celery=%r",
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    _force_result_backend,
    _effective_backend_for_celery,
)
_inmemory_backend = bool(CELERY_RESULT_BACKEND) and CELERY_RESULT_BACKEND.startswith("cache+memory://")
_auto_eager_for_inmemory = _inmemory_transport and _inmemory_backend

# Respect explicit env override; only auto-enable eager for in-memory when env is unset
_env_always_eager_raw = os.getenv("CELERY_ALWAYS_EAGER")
if _env_always_eager_raw is not None:
    _task_always_eager = _env_always_eager_raw.lower() == "true"
else:
    _task_always_eager = _auto_eager_for_inmemory
    if _auto_eager_for_inmemory:
        logging.getLogger(__name__).info("Celery: using eager mode for in-memory broker/result backend (env unset)")

# Create Celery application
_celery_kwargs: Dict[str, Any] = {
    "broker": CELERY_BROKER_URL,
    "include": [
        "src.services.goal_orchestrator",
        "src.services.orchestrator_security",
        "src.services.orchestrator_error_handler",
        "src.core.tasks",
        "src.services.pricing.reconciliation",
        "src.tasks.drive_worker",
        "src.tasks.vendor_kb_sync",
    ],
}
if CELERY_BACKEND_FOR_APP:
    _celery_kwargs["backend"] = CELERY_BACKEND_FOR_APP

celery_app = Celery("etherion_tasks", **_celery_kwargs)

# Celery configuration
celery_app.conf.update(
    # Task routing and queues
    task_default_queue="worker-agents",
    task_queues=(
        Queue("worker-agents", routing_key="worker-agents"),
        Queue("worker-artifacts", routing_key="worker-artifacts"),
        Queue("etherion_tasks", routing_key="etherion_tasks"),
        Queue("high_priority", routing_key="high_priority"),
        Queue("low_priority", routing_key="low_priority"),
    ),
    task_default_routing_key="worker-agents",

    # Route heavy ingestion / maintenance tasks onto the artifacts worker.
    # Agent/orchestrator jobs (and anything unspecified) lands on worker-agents.
    task_routes={
        "core.admin_ingest_gcs_uri": {"queue": "worker-artifacts", "routing_key": "worker-artifacts"},
        "core.cleanup_completed_jobs": {"queue": "worker-artifacts", "routing_key": "worker-artifacts"},
        "core.monitor_job_health": {"queue": "worker-artifacts", "routing_key": "worker-artifacts"},
        "core.periodic_cleanup": {"queue": "worker-artifacts", "routing_key": "worker-artifacts"},
        "core.archive_execution_trace": {"queue": "worker-artifacts", "routing_key": "worker-artifacts"},
        "worker.drive_stage_file": {"queue": "worker-artifacts", "routing_key": "worker-artifacts"},
        "src.services.pricing.reconciliation.run_reconciliation": {"queue": "worker-artifacts", "routing_key": "worker-artifacts"},
        "goal_orchestrator.execute_goal": {"queue": "worker-agents", "routing_key": "worker-agents"},
    },

    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_shutdown=True,

    # Retry configuration with exponential backoff
    task_default_retry_delay=60,  # 1 minute
    task_max_retry_delay=3600,    # 1 hour max
    task_default_max_retries=3,
    task_retry_backoff=True,
    task_retry_backoff_max=3600,  # 1 hour max backoff
    task_retry_jitter=True,

    # Worker configuration
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,

    # Serialization
    task_serializer="json",
    accept_content=["json"],

    # Time zone
    timezone="UTC",
    enable_utc=True,

    # Monitoring
    task_send_sent_event=True,
    task_track_started=True,

    # Execution mode
    task_always_eager=_task_always_eager,
    task_eager_propagates=True,
)

if CELERY_RESULT_BACKEND:
    celery_app.conf.update(
        # Result backend settings
        result_expires=3600,  # 1 hour
        result_persistent=False if _inmemory_backend else True,
        result_serializer="json",
    )

# Beat schedule (reconciliation at 00:00 UTC)
celery_app.conf.beat_schedule = {
    "pricing-reconciliation-nightly": {
        "task": "src.services.pricing.reconciliation.run_reconciliation",
        "schedule": {
            "type": "crontab",
            "minute": 0,
            "hour": 0,
        },
    }
}

# Task signal handlers for logging and monitoring
@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Log worker startup with Cloud Logging enabled."""
    logger.info("✓ Celery worker started with Cloud Logging enabled")

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Log task start."""
    logger.info(f"Task {task.name} ({task_id}) starting with args: {args}, kwargs: {kwargs}")

@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
    """Log task completion."""
    logger.info(f"Task {task.name} ({task_id}) completed with state: {state}")

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """Log task failure."""
    logger.error(f"Task {sender.name} ({task_id}) failed: {exception}")
    logger.error(f"Traceback: {traceback}")

# Basic test task for health checks
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def health_check_task(self) -> Dict[str, Any]:
    """Basic health check task for testing Celery setup."""
    try:
        logger.info(f"Health check task executed successfully - Task ID: {self.request.id}")
        return {
            "status": "healthy",
            "task_id": self.request.id,
            "message": "Celery is working correctly"
        }
    except Exception as exc:
        logger.error(f"Health check task failed: {exc}")
        raise self.retry(exc=exc)

# Utility functions
def get_celery_app() -> Celery:
    """Get the Celery application instance."""
    return celery_app

def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get the status of a Celery task."""
    if not CELERY_RESULT_BACKEND:
        return {
            "task_id": task_id,
            "status": "UNKNOWN",
            "result": None,
            "traceback": None,
            "ready": False,
            "successful": False,
            "failed": False,
        }
    result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result,
        "traceback": result.traceback,
        "ready": result.ready(),
        "successful": result.successful(),
        "failed": result.failed(),
    }

# Export the celery app for use by workers
__all__ = ["celery_app", "get_celery_app", "get_task_status", "health_check_task"]

# Best-effort revoke helpers (used by STOP semantics). These are safe no-ops if
# Celery is running in eager mode or if the job id doesn't correspond to a task.

def safe_revoke_job(job_id: str, terminate: bool = True) -> bool:
    """Attempt to revoke a Celery task matching the job_id.

    Returns True if the revoke command was issued without raising; False otherwise.
    Note: In our current architecture, executeGoal often runs in-process (async),
    so this is best-effort for future long-running workers.
    """
    try:
        celery_app.control.revoke(job_id, terminate=terminate)
        return True
    except Exception:
        return False

def safe_revoke_group(group_id: str, terminate: bool = True) -> bool:
    """Attempt to revoke a Celery group id (if tasks were grouped per job)."""
    try:
        celery_app.control.revoke(group_id, terminate=terminate)
        return True
    except Exception:
        return False
