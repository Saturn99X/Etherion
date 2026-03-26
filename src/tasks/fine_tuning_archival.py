"""
Fine-Tuning Archival Tasks

This module contains Celery tasks for archiving execution traces to GCS
for fine-tuning purposes, ensuring data privacy and PII removal.
"""

import logging
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from src.core.celery import celery_app
from src.database.db import get_db
from src.database.models import Job, ExecutionTraceStep
from src.services.fine_tuning_anonymizer import FineTuningAnonymizer
from src.services.fine_tuning_gcs import FineTuningGCSService

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
async def archive_for_fine_tuning(self, job_id: str, tenant_id: int) -> Dict[str, Any]:
    """
    Archive execution trace for fine-tuning purposes.

    This task retrieves the execution trace from the database, anonymizes
    sensitive data, uploads it to the fine-tuning GCS bucket, and updates
    the Job.trace_data_uri field.

    Args:
        job_id: Job identifier
        tenant_id: Tenant ID

    Returns:
        Dict[str, Any]: Task result with GCS URI and metadata
    """
    try:
        logger.info(f"Starting fine-tuning archival for job {job_id}, tenant {tenant_id}")

        # Initialize services
        anonymizer = FineTuningAnonymizer()
        gcs_service = FineTuningGCSService()

        # Get database session
        db = next(get_db())

        # Retrieve job and execution trace
        job = db.query(Job).filter(
            Job.job_id == job_id,
            Job.tenant_id == tenant_id
        ).first()

        if not job:
            raise ValueError(f"Job {job_id} not found for tenant {tenant_id}")

        # Check if job is completed
        if job.status not in ['COMPLETED', 'FAILED']:
            logger.warning(f"Job {job_id} is not completed (status: {job.status}), skipping archival")
            return {
                'success': False,
                'reason': 'job_not_completed',
                'job_status': job.status
            }

        # Check if already archived
        if job.trace_data_uri:
            logger.info(f"Job {job_id} already has trace archived at {job.trace_data_uri}")
            return {
                'success': True,
                'gcs_uri': job.trace_data_uri,
                'reason': 'already_archived'
            }

        # Retrieve execution trace steps
        trace_steps = db.query(ExecutionTraceStep).filter(
            ExecutionTraceStep.job_id == job_id,
            ExecutionTraceStep.tenant_id == tenant_id
        ).order_by(ExecutionTraceStep.step_number).all()

        if not trace_steps:
            logger.warning(f"No execution trace steps found for job {job_id}")
            return {
                'success': False,
                'reason': 'no_trace_data'
            }

        # Build execution trace structure
        execution_trace = {
            'metadata': {
                'job_id': job_id,
                'job_type': job.job_type,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'status': job.status,
                'total_steps': len(trace_steps),
                'execution_time_seconds': None
            },
            'steps': []
        }

        # Calculate execution time if completed
        if job.created_at and job.completed_at:
            execution_time = job.completed_at - job.created_at
            execution_trace['metadata']['execution_time_seconds'] = execution_time.total_seconds()

        # Build steps data
        for step in trace_steps:
            step_data = {
                'step_number': step.step_number,
                'timestamp': step.timestamp.isoformat(),
                'step_type': step.step_type,
                'thought': step.thought,
                'action_tool': step.action_tool,
                'action_input': step.get_action_input(),
                'observation_result': step.get_observation_result(),
                'step_cost': float(step.step_cost) if step.step_cost else None,
                'model_used': step.model_used,
                'raw_data': step.get_raw_data()
            }
            execution_trace['steps'].append(step_data)

        # Anonymize the execution trace
        tenant_hash = hashlib.sha256(str(tenant_id).encode()).hexdigest()
        anonymized_trace = await anonymizer.anonymize_execution_trace(execution_trace, tenant_id)

        # Upload to fine-tuning bucket
        gcs_uri = await gcs_service.upload_trace_to_fine_tuning_bucket(
            anonymized_trace,
            job_id,
            tenant_hash
        )

        # Update job with trace URI
        job.trace_data_uri = gcs_uri
        db.commit()

        logger.info(f"Successfully archived job {job_id} to {gcs_uri}")

        return {
            'success': True,
            'gcs_uri': gcs_uri,
            'trace_id': anonymized_trace.get('_anonymization_info', {}).get('trace_id'),
            'tenant_hash': tenant_hash,
            'steps_archived': len(trace_steps),
            'archived_at': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to archive job {job_id} for fine-tuning: {e}")

        # Retry logic for transient failures
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying archival for job {job_id} (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60 * (2 ** self.request.retries))  # Exponential backoff

        # Update job with error status
        try:
            db = next(get_db())
            job = db.query(Job).filter(
                Job.job_id == job_id,
                Job.tenant_id == tenant_id
            ).first()

            if job:
                job.error_message = f"Fine-tuning archival failed: {str(e)}"
                db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update job error status: {db_error}")

        return {
            'success': False,
            'error': str(e),
            'retry_count': self.request.retries
        }

@celery_app.task
async def collect_fine_tuning_data(days_back: int = 30) -> Dict[str, Any]:
    """
    Collect fine-tuning data from recent completed jobs.

    This task finds completed jobs that haven't been archived yet,
    anonymizes their execution traces, and uploads them to the
    fine-tuning bucket.

    Args:
        days_back: Number of days to look back for jobs

    Returns:
        Dict[str, Any]: Collection summary
    """
    try:
        logger.info(f"Starting fine-tuning data collection for last {days_back} days")

        # Initialize services
        anonymizer = FineTuningAnonymizer()
        gcs_service = FineTuningGCSService()

        # Get database session
        db = next(get_db())

        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)

        # Find completed jobs without trace_data_uri
        jobs = db.query(Job).filter(
            Job.status.in_(['COMPLETED', 'FAILED']),
            Job.completed_at >= cutoff_date,
            Job.trace_data_uri.is_(None)
        ).limit(100).all()  # Process in batches

        logger.info(f"Found {len(jobs)} jobs to archive")

        results = {
            'total_jobs': len(jobs),
            'successful_archives': 0,
            'failed_archives': 0,
            'errors': []
        }

        for job in jobs:
            try:
                # Archive individual job
                archive_result = await archive_for_fine_tuning(
                    job.job_id,
                    job.tenant_id
                )

                if archive_result.get('success'):
                    results['successful_archives'] += 1
                else:
                    results['failed_archives'] += 1
                    if 'error' in archive_result:
                        results['errors'].append({
                            'job_id': job.job_id,
                            'error': archive_result['error']
                        })

            except Exception as e:
                results['failed_archives'] += 1
                results['errors'].append({
                    'job_id': job.job_id,
                    'error': str(e)
                })
                logger.error(f"Failed to archive job {job.job_id}: {e}")

        # Generate summary report
        summary = await gcs_service.get_fine_tuning_data_summary()

        results['bucket_summary'] = summary
        results['collected_at'] = datetime.utcnow().isoformat()

        logger.info(f"Fine-tuning data collection completed: {results['successful_archives']} successful, {results['failed_archives']} failed")

        return results

    except Exception as e:
        logger.error(f"Fine-tuning data collection failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'collected_at': datetime.utcnow().isoformat()
        }

@celery_app.task
async def cleanup_old_fine_tuning_data(days_old: int = 365) -> Dict[str, Any]:
    """
    Clean up old fine-tuning data to manage storage costs.

    Args:
        days_old: Delete data older than this many days

    Returns:
        Dict[str, Any]: Cleanup results
    """
    try:
        logger.info(f"Starting cleanup of fine-tuning data older than {days_old} days")

        gcs_service = FineTuningGCSService()
        deleted_count = await gcs_service.delete_old_training_data(days_old)

        result = {
            'success': True,
            'deleted_files': deleted_count,
            'days_threshold': days_old,
            'cleaned_at': datetime.utcnow().isoformat()
        }

        logger.info(f"Cleanup completed: deleted {deleted_count} files")
        return result

    except Exception as e:
        logger.error(f"Fine-tuning data cleanup failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'cleaned_at': datetime.utcnow().isoformat()
        }

@celery_app.task
async def generate_fine_tuning_report() -> Dict[str, Any]:
    """
    Generate a comprehensive report on fine-tuning data status.

    Returns:
        Dict[str, Any]: Comprehensive report
    """
    try:
        logger.info("Generating fine-tuning data report")

        gcs_service = FineTuningGCSService()
        bucket_report = await gcs_service.get_bucket_usage_report()
        data_summary = await gcs_service.get_fine_tuning_data_summary()

        # Get recent archival activity from database
        db = next(get_db())
        recent_cutoff = datetime.utcnow() - timedelta(days=7)

        recent_jobs = db.query(Job).filter(
            Job.trace_data_uri.isnot(None),
            Job.completed_at >= recent_cutoff
        ).count()

        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'bucket_usage': bucket_report,
            'data_summary': data_summary,
            'recent_activity': {
                'jobs_archived_last_7_days': recent_jobs,
                'average_daily_archives': recent_jobs / 7
            },
            'recommendations': []
        }

        # Generate recommendations
        total_size_mb = data_summary.get('total_size_mb', 0)
        if total_size_mb > 1000:  # 1GB
            report['recommendations'].append("Consider implementing data sampling for ML training")

        if bucket_report.get('storage_class_distribution', {}).get('STANDARD', 0) > 0:
            report['recommendations'].append("Consider moving older data to Nearline/Coldline storage")

        logger.info(f"Generated fine-tuning report: {total_size_mb} MB total data")
        return report

    except Exception as e:
        logger.error(f"Failed to generate fine-tuning report: {e}")
        return {
            'success': False,
            'error': str(e),
            'generated_at': datetime.utcnow().isoformat()
        }
