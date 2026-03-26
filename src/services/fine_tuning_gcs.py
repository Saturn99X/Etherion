"""
Fine-Tuning GCS Service

This module provides GCS operations specifically for fine-tuning data,
with a dedicated bucket separate from user data for ML team access.
"""

import logging
import json
import tempfile
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from src.core.gcs_client import GCSClient

logger = logging.getLogger(__name__)

class FineTuningGCSService:
    """
    GCS service for fine-tuning data operations.

    This service manages a dedicated fine-tuning bucket separate from
    user data buckets to ensure ML team access without compromising
    user privacy.
    """

    def __init__(self, skip_bucket_check: bool = False):
        """
        Initialize the fine-tuning GCS service.

        Args:
            skip_bucket_check: If True, skip bucket existence check (for testing)
        """
        self._client = None
        self.fine_tuning_bucket_name = self._get_fine_tuning_bucket_name()

        # Ensure bucket exists (unless skipped for testing)
        if not skip_bucket_check:
            self._ensure_bucket_exists()

    @property
    def client(self):
        if self._client is None:
            self._client = self._initialize_client()
        return self._client

    def _initialize_client(self) -> Any:
        """
        Initialize GCS client with appropriate authentication.

        Returns:
            storage.Client: Authenticated GCS client
        """
        from google.cloud import storage
        from google.oauth2 import service_account
        import google.auth
        try:
            # Try service account key first (for production)
            service_account_path = os.getenv('GCP_SERVICE_ACCOUNT_KEY_PATH')
            if service_account_path and os.path.exists(service_account_path):
                credentials = service_account.Credentials.from_service_account_file(
                    service_account_path
                )
                return storage.Client(credentials=credentials)

            # Fall back to default credentials (for development)
            credentials, project = google.auth.default()
            return storage.Client(credentials=credentials, project=project)

        except Exception as e:
            logger.error(f"Failed to initialize GCS client for fine-tuning: {e}")
            raise

    def _get_fine_tuning_bucket_name(self) -> str:
        """
        Get the dedicated fine-tuning bucket name.

        Returns:
            str: Fine-tuning bucket name
        """
        base_bucket = os.getenv('GCS_FINE_TUNING_BUCKET', 'etherion-ai-fine-tuning')
        return base_bucket

    def _ensure_bucket_exists(self) -> None:
        """
        Ensure the fine-tuning bucket exists and is properly configured.
        """
        try:
            bucket = self.client.bucket(self.fine_tuning_bucket_name)

            if not bucket.exists():
                # Create the bucket with proper configuration
                bucket = self.client.create_bucket(
                    self.fine_tuning_bucket_name,
                    location='us-central1'  # Default location
                )

                # Set bucket labels for identification
                bucket.labels = {
                    'purpose': 'fine-tuning-data',
                    'environment': os.getenv('ENVIRONMENT', 'development'),
                    'created_by': 'etherion-ai-system'
                }
                bucket.patch()

                # Set lifecycle policy for automatic cleanup
                lifecycle_rule = {
                    'action': {'type': 'Delete'},
                    'condition': {'age': 365}  # Delete after 1 year
                }

                bucket.lifecycle_rules = [lifecycle_rule]
                bucket.patch()

                logger.info(f"Created fine-tuning bucket: {self.fine_tuning_bucket_name}")

            else:
                logger.info(f"Fine-tuning bucket already exists: {self.fine_tuning_bucket_name}")

        except Exception as e:
            logger.error(f"Failed to ensure fine-tuning bucket exists: {e}")
            raise

    async def upload_trace_to_fine_tuning_bucket(
        self,
        anonymized_trace: Dict[str, Any],
        job_id: str,
        tenant_hash: str
    ) -> str:
        """
        Upload anonymized trace to fine-tuning GCS bucket.

        Args:
            anonymized_trace: Anonymized execution trace
            job_id: Job identifier
            tenant_hash: Hashed tenant ID for categorization

        Returns:
            str: GCS URI of the uploaded trace
        """
        try:
            # Create a unique trace ID for the fine-tuning dataset
            trace_id = f"{tenant_hash}_{job_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

            # Create GCS key for the trace
            gcs_key = f"traces/{tenant_hash}/{trace_id}.jsonl"

            # Convert trace to JSONL format (one JSON object per line)
            jsonl_content = json.dumps(anonymized_trace, separators=(',', ':')) + '\n'

            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
                f.write(jsonl_content)
                temp_file_path = f.name

            try:
                # Upload to fine-tuning bucket
                bucket = self.client.bucket(self.fine_tuning_bucket_name)
                blob = bucket.blob(gcs_key)

                # Set metadata for ML team
                blob.metadata = {
                    'trace_id': trace_id,
                    'job_id': job_id,
                    'tenant_hash': tenant_hash,
                    'uploaded_at': datetime.utcnow().isoformat(),
                    'format': 'jsonl',
                    'version': '1.0',
                    'data_type': 'execution_trace'
                }

                # Upload the file
                blob.upload_from_filename(temp_file_path)

                gcs_uri = f"gs://{self.fine_tuning_bucket_name}/{gcs_key}"
                logger.info(f"Successfully uploaded anonymized trace to {gcs_uri}")

                return gcs_uri

            finally:
                # Clean up temporary file
                os.unlink(temp_file_path)

        except Exception as e:
            logger.error(f"Failed to upload trace to fine-tuning bucket: {e}")
            raise

    async def get_fine_tuning_data_summary(self) -> Dict[str, Any]:
        """
        Get summary of fine-tuning data available in the bucket.

        Returns:
            Dict[str, Any]: Summary statistics for ML team
        """
        try:
            bucket = self.client.bucket(self.fine_tuning_bucket_name)

            # Get all blobs in the bucket
            blobs = list(bucket.list_blobs())

            # Calculate statistics
            total_traces = len(blobs)
            total_size_bytes = sum(blob.size for blob in blobs if blob.size)

            # Group by tenant hash
            tenant_stats = {}
            date_stats = {}

            for blob in blobs:
                if blob.metadata:
                    tenant_hash = blob.metadata.get('tenant_hash', 'unknown')
                    upload_date = blob.metadata.get('uploaded_at', '')[:10]  # YYYY-MM-DD

                    # Update tenant stats
                    if tenant_hash not in tenant_stats:
                        tenant_stats[tenant_hash] = {'count': 0, 'size': 0}
                    tenant_stats[tenant_hash]['count'] += 1
                    tenant_stats[tenant_hash]['size'] += blob.size

                    # Update date stats
                    if upload_date not in date_stats:
                        date_stats[upload_date] = {'count': 0, 'size': 0}
                    date_stats[upload_date]['count'] += 1
                    date_stats[upload_date]['size'] += blob.size

            # Get oldest and newest traces
            sorted_blobs = sorted(blobs, key=lambda x: x.metadata.get('uploaded_at', '') if x.metadata else '')
            oldest_trace = sorted_blobs[0].metadata.get('uploaded_at', 'unknown') if sorted_blobs else 'unknown'
            newest_trace = sorted_blobs[-1].metadata.get('uploaded_at', 'unknown') if sorted_blobs else 'unknown'

            summary = {
                'bucket_name': self.fine_tuning_bucket_name,
                'total_traces': total_traces,
                'total_size_bytes': total_size_bytes,
                'total_size_mb': round(total_size_bytes / (1024 * 1024), 2),
                'tenant_distribution': tenant_stats,
                'daily_distribution': date_stats,
                'oldest_trace': oldest_trace,
                'newest_trace': newest_trace,
                'generated_at': datetime.utcnow().isoformat()
            }

            logger.info(f"Generated fine-tuning data summary: {total_traces} traces, {summary['total_size_mb']} MB")
            return summary

        except Exception as e:
            logger.error(f"Failed to get fine-tuning data summary: {e}")
            raise

    async def get_ml_training_dataset(
        self,
        date_range: Optional[tuple] = None,
        tenant_hashes: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get anonymized training dataset for ML team.

        Args:
            date_range: Tuple of (start_date, end_date) in YYYY-MM-DD format
            tenant_hashes: List of tenant hashes to include
            limit: Maximum number of traces to return

        Returns:
            List[Dict[str, Any]]: List of anonymized traces for training
        """
        try:
            bucket = self.client.bucket(self.fine_tuning_bucket_name)
            blobs = list(bucket.list_blobs())

            # Filter by date range if provided
            if date_range:
                start_date, end_date = date_range
                blobs = [
                    blob for blob in blobs
                    if blob.metadata
                    and blob.metadata.get('uploaded_at', '')[:10] >= start_date
                    and blob.metadata.get('uploaded_at', '')[:10] <= end_date
                ]

            # Filter by tenant hashes if provided
            if tenant_hashes:
                blobs = [
                    blob for blob in blobs
                    if blob.metadata and blob.metadata.get('tenant_hash') in tenant_hashes
                ]

            # Sort by upload date (newest first)
            blobs = sorted(
                blobs,
                key=lambda x: x.metadata.get('uploaded_at', '') if x.metadata else '',
                reverse=True
            )

            # Apply limit
            if limit:
                blobs = blobs[:limit]

            # Download and parse traces
            training_data = []

            for blob in blobs:
                try:
                    # Download trace content
                    content = blob.download_as_text()

                    # Parse JSONL
                    trace_data = json.loads(content.strip())

                    # Add metadata for training context
                    trace_data['_gcs_metadata'] = blob.metadata

                    training_data.append(trace_data)

                except Exception as e:
                    logger.warning(f"Failed to parse trace {blob.name}: {e}")
                    continue

            logger.info(f"Retrieved {len(training_data)} traces for ML training")
            return training_data

        except Exception as e:
            logger.error(f"Failed to get ML training dataset: {e}")
            raise

    async def delete_old_training_data(self, days_old: int = 365) -> int:
        """
        Delete training data older than specified days.

        Args:
            days_old: Number of days after which data should be deleted

        Returns:
            int: Number of files deleted
        """
        try:
            bucket = self.client.bucket(self.fine_tuning_bucket_name)
            blobs = list(bucket.list_blobs())

            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            deleted_count = 0

            for blob in blobs:
                if blob.metadata:
                    upload_date_str = blob.metadata.get('uploaded_at', '')
                    if upload_date_str:
                        try:
                            upload_date = datetime.fromisoformat(upload_date_str.replace('Z', '+00:00'))
                            if upload_date < cutoff_date:
                                blob.delete()
                                deleted_count += 1
                        except ValueError:
                            logger.warning(f"Invalid date format in metadata: {upload_date_str}")

            logger.info(f"Deleted {deleted_count} old training data files")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to delete old training data: {e}")
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
            bucket = self.client.bucket(self.fine_tuning_bucket_name)
            signed_urls = {}

            for trace_id in trace_ids:
                # Find blob by trace_id in metadata
                blobs = list(bucket.list_blobs())

                for blob in blobs:
                    if blob.metadata and blob.metadata.get('trace_id') == trace_id:
                        # Generate signed URL
                        signed_url = blob.generate_signed_url(
                            expiration=timedelta(hours=expiration_hours),
                            method='GET'
                        )

                        signed_urls[trace_id] = signed_url
                        break

            logger.info(f"Generated signed URLs for {len(signed_urls)} traces")
            return signed_urls

        except Exception as e:
            logger.error(f"Failed to generate signed URLs: {e}")
            raise

    async def get_bucket_usage_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive usage report for the fine-tuning bucket.

        Returns:
            Dict[str, Any]: Usage statistics and recommendations
        """
        try:
            bucket = self.client.bucket(self.fine_tuning_bucket_name)

            # Get bucket info
            bucket.reload()

            # Get all blobs
            blobs = list(bucket.list_blobs())

            # Calculate statistics
            total_size = sum(blob.size for blob in blobs)
            total_files = len(blobs)

            # Storage class distribution
            storage_classes = {}
            for blob in blobs:
                storage_class = blob.storage_class
                storage_classes[storage_class] = storage_classes.get(storage_class, 0) + 1

            # Generate recommendations
            recommendations = []

            if total_size > 100 * 1024 * 1024:  # 100 MB
                recommendations.append("Consider archiving older data to reduce storage costs")

            if storage_classes.get('STANDARD', 0) / total_files > 0.8:
                recommendations.append("Consider using Nearline or Coldline storage for older traces")

            report = {
                'bucket_name': self.fine_tuning_bucket_name,
                'created_date': bucket.time_created.isoformat() if bucket.time_created else None,
                'location': bucket.location,
                'storage_class': bucket.storage_class,
                'total_files': total_files,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'storage_class_distribution': storage_classes,
                'recommendations': recommendations,
                'generated_at': datetime.utcnow().isoformat()
            }

            logger.info(f"Generated bucket usage report: {total_size} bytes, {total_files} files")
            return report

        except Exception as e:
            logger.error(f"Failed to generate bucket usage report: {e}")
            raise

    async def upload_dataset_jsonl(self, jsonl_path: str, dataset_key: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Upload a prepared training-ready JSONL dataset to the fine-tuning bucket.

        Args:
            jsonl_path: Local path to the JSONL file
            dataset_key: Object key under the bucket (e.g., 'sft_datasets/alpaca/dataset_20251004.jsonl')
            metadata: Optional GCS metadata

        Returns:
            GCS URI of the uploaded dataset
        """
        bucket = self.client.bucket(self.fine_tuning_bucket_name)
        blob = bucket.blob(dataset_key)

        if metadata:
            blob.metadata = metadata

        blob.upload_from_filename(jsonl_path)
        gcs_uri = f"gs://{self.fine_tuning_bucket_name}/{dataset_key}"
        logger.info(f"Uploaded dataset JSONL to {gcs_uri}")
        return gcs_uri

    async def get_traces_by_ids(self, trace_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch anonymized traces by exact trace_id metadata.

        Args:
            trace_ids: List of trace_id values to retrieve

        Returns:
            List of anonymized traces
        """
        if not trace_ids:
            return []

        bucket = self.client.bucket(self.fine_tuning_bucket_name)
        blobs = list(bucket.list_blobs())

        wanted = set(trace_ids)
        results: List[Dict[str, Any]] = []
        for blob in blobs:
            if not blob.metadata:
                continue
            if blob.metadata.get('trace_id') in wanted:
                try:
                    content = blob.download_as_text()
                    results.append(json.loads(content.strip()))
                except Exception as e:
                    logger.warning(f"Failed to parse trace {blob.name}: {e}")
                    continue
        return results
