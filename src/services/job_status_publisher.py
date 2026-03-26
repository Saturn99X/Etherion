import asyncio
import json
from typing import Dict, Any
from datetime import datetime
from src.core.redis import get_redis_client
from src.database.db import get_session
from src.database.models import Job, Tenant
from sqlalchemy import text
from src.utils.logging_utils import logger

async def publish_job_status(job_id: str, status_data: Dict[str, Any]) -> None:
    """
    Publish job status update to Redis Pub/Sub channel.
    On completion, increment tenant's cumulative_active_seconds based on job duration.
    """
    try:
        redis = get_redis_client()
        channel = f"job_status_{job_id}"
        status_data['timestamp'] = datetime.utcnow().isoformat()
        if 'status' in status_data and isinstance(status_data['status'], str):
            status_data['status'] = status_data['status'].upper()
        message = json.dumps(status_data)
        
        await redis.publish(channel, message)
        logger.info(f"Published status for job {job_id}: {status_data['status']}")
        
        # If completion, update active seconds
        if status_data.get('status') == 'COMPLETED':
            await _increment_active_seconds(job_id)
            
    except Exception as e:
        logger.error(f"Failed to publish job status for {job_id}: {e}")

async def _increment_active_seconds(job_id: str) -> None:
    """Increment tenant's cumulative_active_seconds by job duration."""
    with get_session() as session:
        job = session.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.warning(f"Job {job_id} not found for active seconds update")
            return
        
        # Calculate duration in seconds
        if job.started_at and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds()
            duration = min(duration, 3600)
            
            # Atomic DB update
            try:
                session.execute(
                    text("UPDATE tenant SET cumulative_active_seconds = cumulative_active_seconds + :inc WHERE id = :tid"),
                    {"inc": duration, "tid": job.tenant_id}
                )
                session.commit()
                logger.info(f"Incremented active seconds for tenant {job.tenant_id}: +{duration}s")
            except Exception as e:
                session.rollback()
                logger.error(f"Atomic increment failed for tenant {job.tenant_id}: {e}")
        else:
            logger.warning(f"Job {job_id} missing timestamps for duration calculation")

# JobStatusPublisher class for compatibility
class JobStatusPublisher:
    """Wrapper class for job status publishing functionality."""

    @staticmethod
    async def publish_status(job_id: str, status_data: Dict[str, Any]) -> None:
        """Publish job status update."""
        await publish_job_status(job_id, status_data)

    @staticmethod
    def sync_publish_status(job_id: str, status_data: Dict[str, Any]) -> None:
        """Sync wrapper for publishing job status."""
        sync_publish_job_status(job_id, status_data)

# Legacy sync compatibility
def sync_publish_job_status(job_id: str, status_data: Dict[str, Any]) -> None:
    """Sync wrapper for publish_job_status."""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(publish_job_status(job_id, status_data))

# Factory function for getting the publisher
def get_job_status_publisher() -> JobStatusPublisher:
    """Get a JobStatusPublisher instance."""
    return JobStatusPublisher()
