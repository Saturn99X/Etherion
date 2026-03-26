import logging
from typing import Dict, Any, Optional, List
from celery import current_task
from datetime import datetime
import time
import tempfile
import json
import os
import uuid
import concurrent.futures
import threading

from src.core.celery import celery_app
from src.core.gcs_client import GCSClient
from src.database.models import ExecutionTraceStep, Job, JobStatus
from src.core.redis import get_redis_client, publish_job_status
from src.database.db import get_session
from src.core.tenant_tasks import tenant_task, tenant_scoped_session

logger = logging.getLogger(__name__)

_mm_ingest_lock = threading.Lock()
_mm_ingest_service = None

_status_redis_lock = threading.Lock()
_status_redis_client = None


def _get_status_redis_client():
    global _status_redis_client
    if _status_redis_client is not None:
        return _status_redis_client
    with _status_redis_lock:
        if _status_redis_client is not None:
            return _status_redis_client
        import redis as _redis
        _redis_url = os.getenv("ETHERION_REDIS_URL") or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
        _is_tls = _redis_url.lower().startswith("rediss://")
        _ssl_kwargs = {}
        if _is_tls:
            import ssl as _ssl
            _ssl_kwargs["ssl_cert_reqs"] = _ssl.CERT_NONE
        _status_redis_client = _redis.from_url(
            _redis_url,
            decode_responses=True,
            socket_timeout=10,
            **_ssl_kwargs,
        )
        return _status_redis_client


def _get_mm_ingest_service():
    global _mm_ingest_service
    if _mm_ingest_service is not None:
        return _mm_ingest_service
    with _mm_ingest_lock:
        if _mm_ingest_service is None:
            from src.services.multimodal_ingestion_service import MultimodalIngestionService
            _mm_ingest_service = MultimodalIngestionService(project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
    return _mm_ingest_service


def _download_blob_bytes(blob: Any, *, timeout_s: float) -> bytes:
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(blob.download_as_bytes, timeout=timeout_s)
    try:
        return fut.result(timeout=timeout_s)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def _reload_blob(blob: Any, *, timeout_s: float) -> None:
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(blob.reload, timeout=timeout_s)
    try:
        fut.result(timeout=timeout_s)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

@tenant_task(bind=True, name="core.update_job_status")
def update_job_status_task(self, job_id: str, status: str, error_message: Optional[str] = None, tenant_id: Optional[int] = None) -> Dict[str, Any]:
    try:
        if tenant_id is None:
            from src.database.db import get_db
            session = get_db()
            try:
                job = session.query(Job).filter(Job.job_id == job_id).first()
                if not job:
                    raise ValueError(f"Job not found: {job_id}")
                tenant_id = job.tenant_id
            finally:
                session.close()
        
        with tenant_scoped_session(tenant_id) as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            old_status = job.status
            job.update_status(JobStatus(status))

            if error_message:
                job.error_message = error_message

            session.commit()

            logger.info(f"Job {job_id} status updated: {old_status} -> {status}")

            status_data = {
                "job_id": job_id,
                "status": (status or "").upper(),
                "timestamp": datetime.utcnow().isoformat(),
                "error_message": error_message,
                "tenant_id": tenant_id
            }

            import asyncio
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(publish_job_status(job_id, status_data))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(publish_job_status(job_id, status_data))
                finally:
                    loop.close()

            if status.lower() == JobStatus.COMPLETED.value.lower():
                try:
                    archive_execution_trace_task.apply_async(
                        args=[job_id], 
                        kwargs={"tenant_id": tenant_id},
                    )
                except Exception as _e:
                    logger.warning(f"Failed to enqueue archival for job {job_id}: {_e}")

            return {
                "success": True,
                "job_id": job_id,
                "tenant_id": tenant_id,
                "old_status": old_status.value,
                "new_status": status,
                "updated_at": job.last_updated_at.isoformat()
            }

    except Exception as exc:
        logger.error(f"Failed to update job status for {job_id}: {exc}")
        raise self.retry(exc=exc, countdown=60, max_retries=3)


@celery_app.task(bind=True, name="core.admin_ingest_gcs_uri", ignore_result=True)
def admin_ingest_gcs_uri_task(
    self,
    *,
    tenant_id: str,
    gcs_uri: str,
    filename: str,
    mime_type: str,
    size_bytes: int,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    import asyncio

    def _now_iso() -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _merge_status(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(base)
        out.update(updates)
        out["updated_at"] = _now_iso()
        return out

    task_id = getattr(getattr(self, "request", None), "id", None) or f"ingest:{uuid.uuid4().hex}"
    redis_key = f"admin_ingest:{task_id}"

    # Reuse a process-wide Redis client so each task doesn't pay TLS handshake cost.
    _redis_client = _get_status_redis_client()
    logger.info(f"[PERF] Redis client ready")

    def _set_status_sync(payload: Dict[str, Any]) -> None:
        """Synchronously write status to Redis using reused client."""
        try:
            _redis_client.set(redis_key, json.dumps(payload), ex=3600)
        except Exception as e:
            logger.error(f"[PERF] _set_status_sync FAILED: {e}")
            raise

    t0 = time.time()
    base_payload: Dict[str, Any] = {
        "job_id": task_id,
        "status": "RUNNING",
        "tenant_id": str(tenant_id),
        "gcs_uri": str(gcs_uri),
        "filename": str(filename),
        "mime_type": str(mime_type),
        "size_bytes": int(size_bytes),
        "project_id": str(project_id) if project_id else None,
        "error": None,
        "stage": "INIT",
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    logger.info(f"[PERF] Task {task_id} starting: {gcs_uri}, size={size_bytes}B")

    # Write initial status ONCE
    _set_status_sync(base_payload)

    last_progress_t = time.time()
    last_progress_stage: Optional[str] = None

    try:
        # ALL files go through multimodal pipeline - deterministic parsing (PyMuPDF) + multimodal embedding
        t_import = time.time()
        svc = _get_mm_ingest_service()
        logger.info(f"[PERF] Service get: {(time.time() - t_import)*1000:.0f}ms")
        
        t_gcs = time.time()
        logger.info(f"[PERF] GCS download starting: {gcs_uri}")
        _set_status_sync(_merge_status(base_payload, {"stage": "GCS_DOWNLOAD"}))
        from src.core.gcs_client import download_blob_to_bytes
        content = download_blob_to_bytes(
            gcs_uri,
            timeout=30,
            job_id=task_id,
            tenant_id=str(tenant_id),
        )
        logger.info(f"[PERF] GCS download: {(time.time() - t_gcs)*1000:.0f}ms, size={len(content)} bytes")

        def _progress(stage: str, meta: Dict[str, Any]) -> None:
            nonlocal last_progress_t, last_progress_stage
            try:
                now = time.time()
                if stage != last_progress_stage or (now - last_progress_t) >= 2.0:
                    last_progress_t = now
                    last_progress_stage = stage
                    _set_status_sync(_merge_status(base_payload, {"stage": stage, **(meta or {})}))
            except Exception as _e:
                logger.info(f"[PERF] Progress write failed: {_e}")

        t_ingest = time.time()
        logger.info(f"[PERF] Calling _ingest_with_content for {filename}")
        result = svc._ingest_with_content(
            tenant_id=str(tenant_id),
            gcs_uri=str(gcs_uri),
            content=content,
            filename=str(filename),
            mime_type=str(mime_type),
            size_bytes=int(len(content)),
            project_id=str(project_id) if project_id else None,
            job_id=task_id,
            progress=_progress,
        )
        logger.info(f"[PERF] _ingest_with_content returned: docs={len(result.doc_ids)}, errors={len(result.errors)}")
        logger.info(f"[PERF] Ingestion total: {(time.time() - t_ingest)*1000:.0f}ms")

        logger.info(f"[PERF] Building final payload...")
        payload = {
            "job_id": task_id,
            "status": "COMPLETED",
            "tenant_id": result.tenant_id,
            "gcs_uri": result.gcs_uri,
            "filename": result.filename,
            "mime_type": result.mime_type,
            "size_bytes": int(result.size_bytes),
            "doc_ids": result.doc_ids,
            "image_ids": result.image_ids,
            "chapter_count": int(result.chapter_count),
            "part_count": int(result.part_count),
            "total_tokens": int(result.total_tokens),
            "errors": result.errors,
            "error": None,
            "stage": "COMPLETED",
            "started_at": base_payload.get("started_at"),
            "updated_at": _now_iso(),
            "elapsed_s": round(time.time() - t0, 3),
        }
        t_final = time.time()
        logger.info(f"[PERF] Writing final status to Redis...")
        _set_status_sync(payload)
        logger.info(f"[PERF] Final status write: {(time.time() - t_final)*1000:.0f}ms")
        logger.info(f"[PERF] TOTAL task time: {(time.time() - t0)*1000:.0f}ms")
        return payload
    except Exception as exc:
        payload = {
            "job_id": task_id,
            "status": "FAILED",
            "tenant_id": str(tenant_id),
            "gcs_uri": str(gcs_uri),
            "filename": str(filename),
            "mime_type": str(mime_type),
            "size_bytes": int(size_bytes),
            "error": str(exc),
            "stage": "FAILED",
            "started_at": base_payload.get("started_at") if "base_payload" in locals() else None,
            "updated_at": _now_iso(),
            "elapsed_s": round(time.time() - t0, 3) if "t0" in locals() else None,
        }
        _set_status_sync(payload)
        raise

@celery_app.task(bind=True, name="core.cleanup_completed_jobs")
def cleanup_completed_jobs_task(self, max_age_hours: int = 24) -> Dict[str, Any]:
    try:
        from datetime import timedelta
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        with get_session() as session:
            old_jobs = session.query(Job).filter(
                Job.status.in_([JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]),
                Job.completed_at < cutoff_time
            ).all()
            job_count = len(old_jobs)
            for job in old_jobs:
                session.delete(job)
            session.commit()
            logger.info(f"Cleaned up {job_count} old completed jobs")
            return {
                "success": True,
                "cleaned_jobs": job_count,
                "cutoff_time": cutoff_time.isoformat()
            }
    except Exception as exc:
        logger.error(f"Failed to cleanup completed jobs: {exc}")
        raise self.retry(exc=exc, countdown=300, max_retries=2)

@celery_app.task(bind=True, name="core.monitor_job_health")
def monitor_job_health_task(self, job_id: str, timeout_minutes: int = 60) -> Dict[str, Any]:
    try:
        from datetime import timedelta
        with get_session() as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                return {"success": False, "error": f"Job not found: {job_id}"}
            if job.status == JobStatus.RUNNING:
                started_at = job.started_at or job.created_at
                timeout_time = started_at + timedelta(minutes=timeout_minutes)
                if datetime.utcnow() > timeout_time:
                    job.update_status(JobStatus.FAILED)
                    job.error_message = f"Job timed out after {timeout_minutes} minutes"
                    session.commit()
                    status_data = {
                        "job_id": job_id,
                        "status": JobStatus.FAILED.value,
                        "timestamp": datetime.utcnow().isoformat(),
                        "error_message": job.error_message
                    }
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    loop.run_until_complete(publish_job_status(job_id, status_data))
                    logger.warning(f"Job {job_id} marked as failed due to timeout")
                    return {
                        "success": True,
                        "action": "timeout",
                        "job_id": job_id,
                        "timeout_minutes": timeout_minutes
                    }
            return {
                "success": True,
                "action": "no_action",
                "job_id": job_id,
                "status": job.status.value
            }
    except Exception as exc:
        logger.error(f"Failed to monitor job health for {job_id}: {exc}")
        raise self.retry(exc=exc, countdown=60, max_retries=2)

@celery_app.task(name="core.periodic_cleanup")
def periodic_cleanup_task():
    return cleanup_completed_jobs_task.delay(max_age_hours=48)


@tenant_task(bind=True, name="core.archive_execution_trace", autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 120})
def archive_execution_trace_task(self, job_id: str, tenant_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Archive ExecutionTraceStep records for a completed job to GCS as JSONL and Markdown.
    Registers the transcript as an AI Asset in BigQuery with vector indexing.
    """
    try:
        if tenant_id is None:
            with tenant_scoped_session() as session:
                job = session.query(Job).filter(Job.job_id == job_id).first()
                if not job:
                    return {"success": False, "error": f"Job not found: {job_id}"}
                tenant_id = job.tenant_id

        with tenant_scoped_session(tenant_id) as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                return {"success": False, "error": f"Job not found: {job_id}"}

            steps = session.query(ExecutionTraceStep).filter(ExecutionTraceStep.job_id == job_id).order_by(ExecutionTraceStep.step_number.asc()).all()

            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.jsonl') as tmp:
                temp_path = tmp.name
                serialized_steps = []
                for s in steps:
                    record = {
                        "job_id": s.job_id,
                        "tenant_id": s.tenant_id,
                        "step_number": s.step_number,
                        "timestamp": s.timestamp.isoformat(),
                        "step_type": s.step_type.value if hasattr(s.step_type, 'value') else str(s.step_type),
                        "thought": s.thought,
                        "action_tool": s.action_tool,
                        "action_input": s.get_action_input(),
                        "observation_result": s.observation_result,
                        "step_cost": float(s.step_cost) if s.step_cost is not None else None,
                        "model_used": s.model_used,
                        "raw_data": s.get_raw_data(),
                        "actor": getattr(s, "actor", "orchestrator"),
                        "event_type": getattr(s, "event_type", "unknown"),
                    }
                    serialized_steps.append(record)
                    tmp.write(json.dumps(record, ensure_ascii=False) + "\n")

            from src.utils.transcript_utils import generate_markdown_transcript
            transcript_md = generate_markdown_transcript(serialized_steps)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.md') as md_tmp:
                md_temp_path = md_tmp.name
                md_tmp.write(transcript_md)

            gcs = GCSClient(tenant_id=str(tenant_id))
            jsonl_key = f"ai/{job_id}/replay_trace.jsonl"
            jsonl_uri = gcs.upload_file(temp_path, jsonl_key, metadata={"job_id": job_id, "origin": "ai", "kb_type": "ai_replay"})
            md_key = f"ai/{job_id}/replay_transcript.md"
            md_uri = gcs.upload_file(md_temp_path, md_key, metadata={"job_id": job_id, "origin": "ai", "kb_type": "ai_replay"})

            job.trace_data_uri = jsonl_uri

            from src.services.bigquery_service import BigQueryService
            from src.services.embedding_service import EmbeddingService
            
            bq_inst = BigQueryService(project_id=os.getenv("GOOGLE_CLOUD_PROJECT", "fabled-decker-476913-v9"))
            embedder = EmbeddingService(project_id=bq_inst.project_id)
            
            try:
                dataset_id = f"tnt_{tenant_id}"
                vector = embedder.embed_texts([transcript_md[:15000]])[0]
                asset_row = {
                    "asset_id": f"replay_{job_id}",
                    "job_id": job_id,
                    "tenant_id": str(tenant_id),
                    "created_at": datetime.utcnow().isoformat(),
                    "gcs_uri": md_uri,
                    "content_type": "text/markdown",
                    "filename": "replay_transcript.md",
                    "size_bytes": len(transcript_md.encode('utf-8')),
                    "text_extract": transcript_md[:10000],
                    "vector_embedding": vector,
                    "metadata": json.dumps({
                        "origin": "ai",
                        "kb_type": "ai_replay",
                        "thread_id": getattr(job, "thread_id", None) or (job.get_job_metadata() or {}).get("thread_id"),
                        "jsonl_uri": jsonl_uri,
                    })
                }
                bq_inst.insert_rows_json(dataset_id, "assets", [asset_row])
            except Exception as bq_err:
                logger.warning(f"Failed to register replay asset in BigQuery: {bq_err}")

            final_thought = None
            if steps:
                for s in reversed(steps):
                    if s.thought:
                        final_thought = s.thought
                        break

            existing_output: Dict[str, Any] = {}
            try:
                existing_output = (job.get_output_data() or {}) if hasattr(job, "get_output_data") else {}
            except Exception:
                existing_output = {}

            final_output = None
            try:
                if isinstance(existing_output, dict):
                    final_output = (
                        existing_output.get("output")
                        or existing_output.get("final_output")
                        or existing_output.get("result")
                        or existing_output.get("response")
                    )
            except Exception:
                final_output = None

            summary = {
                "final_output": final_output,
                "final_thought": final_thought,
            }
            try:
                if isinstance(existing_output, dict):
                    merged = dict(existing_output)
                    merged.update(summary)
                    job.set_output_data(merged)
                else:
                    job.set_output_data(summary)
            except Exception:
                pass

            session.commit()

            try:
                from src.services.user_observation_service import UserObservationService
                import asyncio
                observation_service = UserObservationService()
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.create_task(observation_service.process_execution_trace_for_observations(job_id, job.user_id, tenant_id))
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(observation_service.process_execution_trace_for_observations(job_id, job.user_id, tenant_id))
                    finally:
                        loop.close()
            except Exception as obs_error:
                logger.warning(f"Failed to process user observations: {obs_error}")

            return {"success": True, "job_id": job_id, "tenant_id": tenant_id, "trace_uri": jsonl_uri, "transcript_uri": md_uri}

    except Exception as exc:
        logger.error(f"Failed to archive execution trace: {exc}")
        raise self.retry(exc=exc)
