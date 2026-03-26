"""
Fine-Tuning Data Manager

This module provides high-level management and coordination for the fine-tuning
data collection system, including scheduling, ML team access, and data governance.
"""

import logging
import hashlib
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

from src.core.celery import celery_app
from src.database.db import get_db
from src.database.models import Job, ExecutionTraceStep
from src.services.fine_tuning_anonymizer import FineTuningAnonymizer
from src.services.fine_tuning_gcs import FineTuningGCSService
from src.tasks.fine_tuning_archival import (
    archive_for_fine_tuning,
    collect_fine_tuning_data,
    cleanup_old_fine_tuning_data,
    generate_fine_tuning_report
)

logger = logging.getLogger(__name__)

class FineTuningDataManager:
    """
    Manages fine-tuning data collection and ML team access.

    This class provides high-level coordination for the fine-tuning system,
    including scheduling archival tasks, providing ML team access, and
    ensuring data governance compliance.
    """

    def __init__(self):
        """Initialize the fine-tuning data manager."""
        self.anonymizer = FineTuningAnonymizer()
        self.gcs_service = FineTuningGCSService()

    async def schedule_fine_tuning_archival(
        self,
        job_id: str,
        tenant_id: int,
        delay_hours: int = 24
    ) -> str:
        """
        Schedule fine-tuning archival for a completed job.

        Args:
            job_id: Job identifier
            tenant_id: Tenant ID
            delay_hours: Hours to delay archival (default: 24)

        Returns:
            str: Task ID of the scheduled archival task
        """
        try:
            logger.info(f"Scheduling fine-tuning archival for job {job_id} in {delay_hours} hours")

            # Schedule the archival task with delay
            task = archive_for_fine_tuning.apply_async(
                args=[job_id, tenant_id],
                countdown=delay_hours * 3600  # Convert hours to seconds
            )

            logger.info(f"Scheduled archival task {task.id} for job {job_id}")
            return task.id

        except Exception as e:
            logger.error(f"Failed to schedule fine-tuning archival for job {job_id}: {e}")
            raise

    async def collect_fine_tuning_data(
        self,
        days_back: int = 30,
        batch_size: int = 50
    ) -> Dict[str, Any]:
        """
        Collect fine-tuning data from recent jobs.

        Args:
            days_back: Number of days to look back for jobs
            batch_size: Number of jobs to process in each batch

        Returns:
            Dict[str, Any]: Collection summary
        """
        try:
            logger.info(f"Starting fine-tuning data collection for last {days_back} days")

            # Schedule the collection task
            task = collect_fine_tuning_data.apply_async(
                args=[days_back]
            )

            logger.info(f"Scheduled collection task {task.id}")
            return {
                'task_id': task.id,
                'status': 'scheduled',
                'days_back': days_back,
                'scheduled_at': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to start fine-tuning data collection: {e}")
            raise

    async def get_ml_training_dataset(
        self,
        date_range: Optional[Tuple[str, str]] = None,
        tenant_hashes: Optional[List[str]] = None,
        limit: Optional[int] = None,
        include_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Get anonymized training dataset for ML team.

        Args:
            date_range: Tuple of (start_date, end_date) in YYYY-MM-DD format
            tenant_hashes: List of tenant hashes to include
            limit: Maximum number of traces to return
            include_metadata: Whether to include GCS metadata

        Returns:
            Dict[str, Any]: Training dataset with metadata
        """
        try:
            logger.info("Retrieving ML training dataset")

            # Get training data from GCS
            traces = await self.gcs_service.get_ml_training_dataset(
                date_range=date_range,
                tenant_hashes=tenant_hashes,
                limit=limit
            )

            # Get summary statistics
            summary = await self.gcs_service.get_fine_tuning_data_summary()

            result = {
                'dataset': traces,
                'summary': summary,
                'filters_applied': {
                    'date_range': date_range,
                    'tenant_hashes': tenant_hashes,
                    'limit': limit
                },
                'generated_at': datetime.utcnow().isoformat(),
                'total_traces': len(traces)
            }

            logger.info(f"Retrieved {len(traces)} traces for ML training")
            return result

        except Exception as e:
            logger.error(f"Failed to get ML training dataset: {e}")
            raise

    async def generate_signed_urls_for_ml_access(
        self,
        trace_ids: List[str],
        expiration_hours: int = 24
    ) -> Dict[str, str]:
        """
        Generate signed URLs for ML team to access specific traces.

        Args:
            trace_ids: List of trace IDs to generate URLs for
            expiration_hours: URL expiration time in hours

        Returns:
            Dict[str, str]: Mapping of trace_id to signed URL
        """
        try:
            logger.info(f"Generating signed URLs for {len(trace_ids)} traces")

            signed_urls = await self.gcs_service.generate_signed_urls_for_ml_access(
                trace_ids,
                expiration_hours
            )

            logger.info(f"Generated signed URLs for {len(signed_urls)} traces")
            return signed_urls

        except Exception as e:
            logger.error(f"Failed to generate signed URLs: {e}")
            raise

    async def get_fine_tuning_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about the fine-tuning data collection.

        Returns:
            Dict[str, Any]: Statistics and insights
        """
        try:
            logger.info("Generating fine-tuning statistics")

            # Get GCS summary
            gcs_summary = await self.gcs_service.get_fine_tuning_data_summary()

            # Get database statistics
            db = next(get_db())

            # Jobs with traces
            jobs_with_traces = db.query(Job).filter(
                Job.trace_data_uri.isnot(None)
            ).count()

            # Recent archival activity (last 7 days)
            recent_cutoff = datetime.utcnow() - timedelta(days=7)
            recent_archives = db.query(Job).filter(
                Job.trace_data_uri.isnot(None),
                Job.completed_at >= recent_cutoff
            ).count()

            # Failed archival attempts
            failed_archives = db.query(Job).filter(
                Job.error_message.like('%Fine-tuning archival failed%')
            ).count()

            # Calculate success rate
            total_processed = jobs_with_traces + failed_archives
            success_rate = (jobs_with_traces / total_processed * 100) if total_processed > 0 else 0

            statistics = {
                'gcs_summary': gcs_summary,
                'database_stats': {
                    'total_jobs_with_traces': jobs_with_traces,
                    'recent_archives_7_days': recent_archives,
                    'failed_archives': failed_archives,
                    'success_rate_percent': round(success_rate, 2),
                    'average_daily_archives': round(recent_archives / 7, 2)
                },
                'data_quality_insights': {
                    'traces_per_tenant_distribution': gcs_summary.get('tenant_distribution', {}),
                    'daily_archive_trends': gcs_summary.get('daily_distribution', {}),
                    'oldest_trace_age_days': self._calculate_age_days(
                        gcs_summary.get('oldest_trace', '')
                    ),
                    'newest_trace_age_days': self._calculate_age_days(
                        gcs_summary.get('newest_trace', '')
                    )
                },
                'generated_at': datetime.utcnow().isoformat()
            }

            logger.info(f"Generated statistics: {jobs_with_traces} archived jobs, {success_rate:.1f}% success rate")
            return statistics

        except Exception as e:
            logger.error(f"Failed to get fine-tuning statistics: {e}")
            raise

    async def schedule_data_collection_campaign(
        self,
        campaign_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Schedule a comprehensive data collection campaign.

        Args:
            campaign_config: Configuration for the collection campaign

        Returns:
            Dict[str, Any]: Campaign scheduling results
        """
        try:
            logger.info(f"Scheduling data collection campaign: {campaign_config}")

            # Extract campaign parameters
            days_back = campaign_config.get('days_back', 30)
            batch_size = campaign_config.get('batch_size', 50)
            cleanup_old_data = campaign_config.get('cleanup_old_data', True)
            cleanup_threshold_days = campaign_config.get('cleanup_threshold_days', 365)
            generate_report = campaign_config.get('generate_report', True)

            # Schedule collection task
            collection_task = collect_fine_tuning_data.apply_async(
                args=[days_back]
            )

            # Schedule cleanup if requested
            cleanup_task_id = None
            if cleanup_old_data:
                cleanup_task = cleanup_old_fine_tuning_data.apply_async(
                    args=[cleanup_threshold_days]
                )
                cleanup_task_id = cleanup_task.id

            # Schedule report generation if requested
            report_task_id = None
            if generate_report:
                report_task = generate_fine_tuning_report.apply_async()
                report_task_id = report_task.id

            result = {
                'campaign_id': f"campaign_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                'status': 'scheduled',
                'tasks_scheduled': {
                    'collection': collection_task.id,
                    'cleanup': cleanup_task_id,
                    'report': report_task_id
                },
                'configuration': campaign_config,
                'scheduled_at': datetime.utcnow().isoformat()
            }

            logger.info(f"Scheduled data collection campaign with {len([t for t in result['tasks_scheduled'].values() if t])} tasks")
            return result

        except Exception as e:
            logger.error(f"Failed to schedule data collection campaign: {e}")
            raise

    async def validate_privacy_compliance(self) -> Dict[str, Any]:
        """
        Validate that all archived data complies with privacy requirements.

        Returns:
            Dict[str, Any]: Privacy compliance report
        """
        try:
            logger.info("Validating privacy compliance for fine-tuning data")

            # Get sample of traces to check for PII
            sample_traces = await self.gcs_service.get_ml_training_dataset(limit=10)

            compliance_issues = []
            pii_patterns_found = []

            # Common PII patterns to check for
            pii_patterns = {
                'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
                'api_key': r'\b[A-Za-z0-9]{20,}\b',
                'tenant_id': r'\btenant_\d+\b',
                'user_id': r'\buser_\d+\b'
            }

            for i, trace in enumerate(sample_traces):
                trace_issues = []

                # Check metadata
                if 'metadata' in trace:
                    metadata_str = str(trace['metadata'])
                    for pattern_name, pattern in pii_patterns.items():
                        if re.search(pattern, metadata_str):
                            trace_issues.append(f"PII pattern '{pattern_name}' found in metadata")

                # Check steps
                for j, step in enumerate(trace.get('steps', [])):
                    step_str = str(step)
                    for pattern_name, pattern in pii_patterns.items():
                        if re.search(pattern, step_str):
                            trace_issues.append(f"PII pattern '{pattern_name}' found in step {j}")

                if trace_issues:
                    compliance_issues.append({
                        'trace_index': i,
                        'issues': trace_issues
                    })

            compliance_report = {
                'total_traces_checked': len(sample_traces),
                'compliance_issues': compliance_issues,
                'is_compliant': len(compliance_issues) == 0,
                'compliance_score': (1 - len(compliance_issues) / len(sample_traces)) * 100 if sample_traces else 100,
                'validated_at': datetime.utcnow().isoformat()
            }

            logger.info(f"Privacy compliance validation completed: {compliance_report['compliance_score']:.1f}% compliant")
            return compliance_report

        except Exception as e:
            logger.error(f"Failed to validate privacy compliance: {e}")
            raise

    async def get_ml_team_dashboard_data(self) -> Dict[str, Any]:
        """
        Get comprehensive data for the ML team dashboard.

        Returns:
            Dict[str, Any]: Dashboard data including statistics and recommendations
        """
        try:
            logger.info("Generating ML team dashboard data")

            # Get all statistics
            statistics = await self.get_fine_tuning_statistics()

            # Get recent activity
            gcs_summary = await self.gcs_service.get_fine_tuning_data_summary()

            # Generate recommendations
            recommendations = []

            # Data volume recommendations
            total_size_mb = gcs_summary.get('total_size_mb', 0)
            if total_size_mb > 10000:  # 10GB
                recommendations.append({
                    'type': 'storage',
                    'priority': 'high',
                    'message': 'Consider implementing data sampling or archival strategies for storage cost optimization',
                    'action': 'Review storage costs and implement data retention policies'
                })

            # Data quality recommendations
            tenant_count = len(gcs_summary.get('tenant_distribution', {}))
            if tenant_count < 5:
                recommendations.append({
                    'type': 'data_quality',
                    'priority': 'medium',
                    'message': 'Limited tenant diversity may affect model generalization',
                    'action': 'Consider collecting data from more diverse sources or implementing data augmentation'
                })

            # Privacy compliance recommendations
            compliance_report = await self.validate_privacy_compliance()
            if not compliance_report.get('is_compliant', True):
                recommendations.append({
                    'type': 'privacy',
                    'priority': 'high',
                    'message': 'Privacy compliance issues detected in training data',
                    'action': 'Review and fix anonymization process for affected traces'
                })

            dashboard_data = {
                'overview': {
                    'total_traces': gcs_summary.get('total_traces', 0),
                    'total_size_mb': total_size_mb,
                    'active_tenants': tenant_count,
                    'compliance_score': compliance_report.get('compliance_score', 100)
                },
                'statistics': statistics,
                'recommendations': recommendations,
                'generated_at': datetime.utcnow().isoformat()
            }

            logger.info("Generated ML team dashboard data")
            return dashboard_data

        except Exception as e:
            logger.error(f"Failed to get ML team dashboard data: {e}")
            raise

    def _calculate_age_days(self, date_string: str) -> Optional[int]:
        """
        Calculate age in days from a date string.

        Args:
            date_string: ISO date string

        Returns:
            Optional[int]: Age in days or None if invalid
        """
        try:
            if not date_string or date_string == 'unknown':
                return None

            date = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
            age = datetime.utcnow() - date
            return age.days
        except (ValueError, AttributeError):
            return None
