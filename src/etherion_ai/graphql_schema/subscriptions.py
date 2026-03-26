import strawberry
import asyncio
import logging
from typing import AsyncGenerator, Optional
from strawberry.types import Info

from src.core.redis import get_redis_client, subscribe_to_job_status, subscribe_to_execution_trace, subscribe_to_ui_events
from src.etherion_ai.graphql_schema.output_types import JobStatusUpdate
from src.database.db import session_scope
from src.database.models import Job
from src.etherion_ai.middleware.auth_context import resolve_current_user_from_headers
from src.utils.rls_utils import set_session_tenant_context

logger = logging.getLogger(__name__)


async def _get_current_user_from_ws_or_headers(info: Info):
    request = info.context.get("request")
    auth_context = None
    try:
        auth_context = getattr(request.state, "auth_context", None)
    except Exception:
        auth_context = None

    if auth_context and auth_context.get("current_user"):
        return auth_context.get("current_user")

    connection_params = info.context.get("connection_params") or {}
    headers = connection_params.get("headers") or {}
    if isinstance(headers, dict):
        auth_value = headers.get("Authorization") or headers.get("authorization")
        if auth_value:
            current_user, tenant_id = await resolve_current_user_from_headers({"Authorization": auth_value})
            if current_user:
                try:
                    request.state.auth_context = {
                        "current_user": current_user,
                        "db_session": None,
                        "tenant_id": tenant_id,
                    }
                except Exception:
                    pass
                return current_user

    try:
        if request:
            current_user, _ = await resolve_current_user_from_headers(request.headers)
            if current_user:
                try:
                    request.state.auth_context = {
                        "current_user": current_user,
                        "db_session": None,
                        "tenant_id": current_user.tenant_id,
                    }
                except Exception:
                    pass
                return current_user
    except Exception:
        pass

    return None

@strawberry.type
class Subscription:
    """GraphQL subscriptions for real-time updates."""

    @strawberry.subscription
    async def subscribeToJobStatus(
        self,
        info: Info,
        job_id: str
    ) -> AsyncGenerator[JobStatusUpdate, None]:
        """
        Subscribe to real-time status updates for a specific job.

        Args:
            job_id: The job ID to subscribe to

        Yields:
            JobStatusUpdate: Real-time status updates for the job

        Example usage:
        ```
        subscription {
          subscribeToJobStatus(job_id: "job_abc123xyz") {
            job_id
            status
            timestamp
            message
            progress_percentage
            current_step_description
            error_message
            additional_data
          }
        }
        ```
        """
        # Get authentication context
        try:
            current_user = await _get_current_user_from_ws_or_headers(info)
            if not current_user:
                logger.warning(f"Unauthenticated subscription attempt for job {job_id}")
                yield JobStatusUpdate(
                    job_id=job_id,
                    status="ERROR",
                    timestamp="",
                    message="Authentication required",
                    error_message="User must be authenticated to subscribe to job status",
                )
                return
        except Exception as e:
            logger.error(f"Error getting auth context for job subscription {job_id}: {e}")
            yield JobStatusUpdate(
                job_id=job_id,
                status="ERROR",
                timestamp="",
                message="Authentication error",
                error_message="Failed to verify user authentication",
            )
            return

        # Verify the job exists and belongs to the user
        try:
            with session_scope() as session:
                job = session.query(Job).filter(Job.job_id == job_id).first()
                if not job:
                    logger.warning(f"Job not found: {job_id}")
                    yield JobStatusUpdate(
                        job_id=job_id,
                        status="ERROR",
                        timestamp="",
                        message="Job not found",
                        error_message=f"Job with ID {job_id} does not exist"
                    )
                    return

                # Check if user has access to this job (user-level isolation)
                if job.user_id != current_user.id or job.tenant_id != current_user.tenant_id:
                    logger.warning(f"Unauthorized access attempt to job {job_id} by user {current_user.user_id}")
                    yield JobStatusUpdate(
                        job_id=job_id,
                        status="ERROR",
                        timestamp="",
                        message="Access denied",
                        error_message="You do not have permission to access this job"
                    )
                    return
        except Exception as e:
            logger.error(f"Database error during job verification {job_id}: {e}")
            yield JobStatusUpdate(
                job_id=job_id,
                status="ERROR",
                timestamp="",
                message="Database error",
                error_message="Failed to verify job access"
            )
            return

        logger.info(f"Starting job status subscription for {job_id} by user {current_user.user_id}")

        try:
            # Subscribe to Redis updates for this job
            redis_client = get_redis_client()

            async for update_data in subscribe_to_job_status(job_id):
                try:
                    # Convert Redis message to GraphQL type
                    job_status_update = JobStatusUpdate(
                        job_id=update_data.get("job_id", job_id),
                        status=update_data.get("status", "UNKNOWN"),
                        timestamp=update_data.get("timestamp", ""),
                        message=update_data.get("message"),
                        progress_percentage=update_data.get("progress_percentage"),
                        current_step_description=update_data.get("current_step_description"),
                        error_message=update_data.get("error_message"),
                        additional_data=update_data.get("additional_data")
                    )

                    yield job_status_update

                    # Break the loop if job is in a terminal state
                    if update_data.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
                        logger.info(f"Job {job_id} reached terminal state: {update_data.get('status')}")
                        break

                except Exception as e:
                    logger.error(f"Error processing job status update for {job_id}: {e}")
                    yield JobStatusUpdate(
                        job_id=job_id,
                        status="ERROR",
                        timestamp="",
                        message="Processing error",
                        error_message=f"Error processing status update: {str(e)}"
                    )

        except asyncio.CancelledError:
            logger.info(f"Job status subscription cancelled for {job_id}")
            raise
        except Exception as e:
            logger.error(f"Error in job status subscription for {job_id}: {e}")
            yield JobStatusUpdate(
                job_id=job_id,
                status="ERROR",
                timestamp="",
                message="Subscription error",
                error_message=f"Subscription failed: {str(e)}"
            )
        finally:
            logger.info(f"Job status subscription ended for {job_id}")

    @strawberry.subscription
    async def subscribeToExecutionTrace(
        self,
        info: Info,
        job_id: str
    ) -> AsyncGenerator[JobStatusUpdate, None]:
        """Subscribe to execution trace UI events for a job."""
        # Auth context (require same-tenant)
        try:
            current_user = await _get_current_user_from_ws_or_headers(info)
            if not current_user:
                logger.warning(f"Unauthenticated trace subscription attempt for job {job_id}")
                yield JobStatusUpdate(
                    job_id=job_id,
                    status="ERROR",
                    timestamp="",
                    message="Authentication required",
                    error_message="User must be authenticated to subscribe to execution trace",
                )
                return
        except Exception as e:
            logger.error(f"Error getting auth context for trace subscription {job_id}: {e}")
            yield JobStatusUpdate(
                job_id=job_id,
                status="ERROR",
                timestamp="",
                message="Authentication error",
                error_message="Failed to verify user authentication",
            )
            return

        # Verify job ownership (user-level isolation)
        try:
            with session_scope() as session:
                # Explicitly set tenant context for RLS safety in WebSocket context
                set_session_tenant_context(session, current_user.tenant_id)
                job = session.query(Job).filter(Job.job_id == job_id).first()
                if not job or job.user_id != current_user.id or job.tenant_id != current_user.tenant_id:
                    logger.warning(f"Unauthorized trace subscription attempt to job {job_id} by user {current_user.user_id}")
                    yield JobStatusUpdate(
                        job_id=job_id,
                        status="ERROR",
                        timestamp="",
                        message="Access denied",
                        error_message="You do not have permission to access this job",
                    )
                    return
        except Exception as e:
            logger.error(f"Database error during trace job verification {job_id}: {e}")
            yield JobStatusUpdate(
                job_id=job_id,
                status="ERROR",
                timestamp="",
                message="Database error",
                error_message="Failed to verify job access",
            )
            return
        # WS connection + message throttling using async RedisClient wrapper
        redis = get_redis_client()
        ip = info.context.get("request").client.host if info.context.get("request").client else "unknown"
        msg_limit = 60
        conn_limit = 10
        conn_key = f"wsconn:exec:{ip}"
        try:
            active = await redis.incr(conn_key)
            if active == 1:
                await redis.expire(conn_key, 3600)
            if active > conn_limit:
                await redis.decr(conn_key)
                raise Exception("Too many websocket connections from this IP")

            window_key = f"wsrate:exec:{ip}:{job_id}:{int(asyncio.get_event_loop().time()//60)}"
            async for evt in subscribe_to_execution_trace(job_id):
                try:
                    count = await redis.incr(window_key)
                    if count == 1:
                        await redis.expire(window_key, 70)
                    if count > msg_limit:
                        continue  # drop burst messages
                except Exception:
                    pass
                yield JobStatusUpdate(
                    job_id=evt.get("job_id", job_id),
                    status=evt.get("type", "TRACE"),
                    timestamp=evt.get("timestamp", ""),
                    message=evt.get("step_description"),
                    progress_percentage=evt.get("progress"),
                    current_step_description=evt.get("step_description"),
                    additional_data=evt,
                )
        finally:
            try:
                await redis.decr(conn_key)
            except Exception:
                pass

    @strawberry.subscription
    async def subscribeToUIEvents(
        self,
        info: Info,
        tenant_id: int
    ) -> AsyncGenerator[JobStatusUpdate, None]:
        """Subscribe to tenant-scoped UI events."""
        try:
            auth_context = info.context.get("request").state.auth_context
            current_user = auth_context.get("current_user")
            if not current_user or current_user.tenant_id != tenant_id:
                logger.warning(f"Access denied for tenant UI events: tenant_id={tenant_id}")
                # Emit a single error payload, then end stream gracefully
                yield JobStatusUpdate(
                    job_id="",
                    status="ERROR",
                    timestamp="",
                    message="Access denied",
                    error_message="You do not have permission to subscribe to these UI events",
                )
                return
        except Exception as e:
            logger.error(f"Auth context error for UI events subscription tenant_id={tenant_id}: {e}")
            yield JobStatusUpdate(
                job_id="",
                status="ERROR",
                timestamp="",
                message="Authentication error",
                error_message="Failed to verify user authentication",
            )
            return
        # WS connection + message throttling using async RedisClient wrapper
        redis = get_redis_client()
        ip = info.context.get("request").client.host if info.context.get("request").client else "unknown"
        msg_limit = 60
        conn_limit = 10
        conn_key = f"wsconn:ui:{ip}"
        try:
            active = await redis.incr(conn_key)
            if active == 1:
                await redis.expire(conn_key, 3600)
            if active > conn_limit:
                await redis.decr(conn_key)
                raise Exception("Too many websocket connections from this IP")

            window_key = f"wsrate:ui:{ip}:{tenant_id}:{int(asyncio.get_event_loop().time()//60)}"
            async for evt in subscribe_to_ui_events(tenant_id):
                try:
                    count = await redis.incr(window_key)
                    if count == 1:
                        await redis.expire(window_key, 70)
                    if count > msg_limit:
                        continue
                except Exception:
                    pass
                yield JobStatusUpdate(
                    job_id=evt.get("job_id", ""),
                    status=evt.get("type", "UI"),
                    timestamp=evt.get("timestamp", ""),
                    message=evt.get("message"),
                    additional_data=evt,
                )
        finally:
            try:
                await redis.decr(conn_key)
            except Exception:
                pass

    @strawberry.subscription
    async def subscribeToJobUpdates(
        self,
        info: Info,
        tenant_id: Optional[int] = None
    ) -> AsyncGenerator[JobStatusUpdate, None]:
        """
        Subscribe to job status updates for all jobs in a tenant.
        Useful for dashboard monitoring.

        Args:
            tenant_id: Optional tenant ID filter. If not provided, uses current user's tenant.

        Yields:
            JobStatusUpdate: Status updates for all jobs in the tenant

        Example usage:
        ```
        subscription {
          subscribeToJobUpdates(tenant_id: 123) {
            job_id
            status
            timestamp
            message
            progress_percentage
          }
        }
        ```
        """
        # Get authentication context
        try:
            auth_context = info.context.get("request").state.auth_context
            current_user = auth_context.get("current_user")

            if not current_user:
                logger.warning("Unauthenticated subscription attempt for job updates")
                return

            # Use provided tenant_id or default to user's tenant
            target_tenant_id = tenant_id or current_user.tenant_id

            # Verify user has access to the tenant
            if current_user.tenant_id != target_tenant_id:
                logger.warning(f"User {current_user.user_id} attempted to access tenant {target_tenant_id}")
                return

        except Exception as e:
            logger.error(f"Error getting auth context for tenant job updates: {e}")
            return

        logger.info(f"Starting tenant job updates subscription for tenant {target_tenant_id} by user {current_user.user_id}")

        try:
            redis_client = get_redis_client()

            # Subscribe to a tenant-wide job updates channel
            tenant_channel = f"tenant_jobs_{target_tenant_id}"

            async for update_data in redis_client.subscribe(tenant_channel):
                try:
                    job_status_update = JobStatusUpdate(
                        job_id=update_data.get("job_id", ""),
                        status=update_data.get("status", "UNKNOWN"),
                        timestamp=update_data.get("timestamp", ""),
                        message=update_data.get("message"),
                        progress_percentage=update_data.get("progress_percentage"),
                        current_step_description=update_data.get("current_step_description"),
                        error_message=update_data.get("error_message"),
                        additional_data=update_data.get("additional_data")
                    )

                    yield job_status_update

                except Exception as e:
                    logger.error(f"Error processing tenant job update for tenant {target_tenant_id}: {e}")
                    continue

        except asyncio.CancelledError:
            logger.info(f"Tenant job updates subscription cancelled for tenant {target_tenant_id}")
            raise
        except Exception as e:
            logger.error(f"Error in tenant job updates subscription for tenant {target_tenant_id}: {e}")
        finally:
            logger.info(f"Tenant job updates subscription ended for tenant {target_tenant_id}")
