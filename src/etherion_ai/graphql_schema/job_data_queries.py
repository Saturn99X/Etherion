"""
GraphQL queries for retrieving job trace and output data from GCS.
"""

import strawberry
from typing import Optional
from strawberry.types import Info

from src.core.gcs_client import GCSClient
from src.database.db import get_session
from src.database.models import Job
import logging

logger = logging.getLogger(__name__)

@strawberry.type
class JobDataResponse:
    """Response type for job data queries."""
    success: bool
    data: Optional[str] = None
    error_message: Optional[str] = None

@strawberry.type
class Query:
    """GraphQL queries for job data retrieval."""

    @strawberry.field
    async def get_job_trace(
        self,
        info: Info,
        job_id: str,
        tenant_id: int
    ) -> JobDataResponse:
        """
        Retrieve job execution trace from GCS.

        Args:
            job_id: The job identifier
            tenant_id: The tenant identifier

        Returns:
            JobDataResponse with trace data or error
        """
        try:
            # Get database context from GraphQL info
            # This assumes you have user authentication context
            user_tenant_id = getattr(info.context, 'tenant_id', None)
            if user_tenant_id != tenant_id:
                return JobDataResponse(
                    success=False,
                    error_message="Unauthorized access to job data"
                )

            # Query job from database
            with get_session() as session:
                job = session.query(Job).filter(
                    Job.job_id == job_id,
                    Job.tenant_id == tenant_id
                ).first()

                if not job:
                    return JobDataResponse(
                        success=False,
                        error_message=f"Job not found: {job_id}"
                    )

                if not hasattr(job, 'trace_data_uri') or not job.trace_data_uri:
                    return JobDataResponse(
                        success=False,
                        error_message="Trace data not available for this job"
                    )

                # Extract GCS key from URI
                # URI format: gs://bucket/key
                if not job.trace_data_uri.startswith('gs://'):
                    return JobDataResponse(
                        success=False,
                        error_message="Invalid trace data URI format"
                    )

                gcs_parts = job.trace_data_uri.replace('gs://', '').split('/', 1)
                if len(gcs_parts) != 2:
                    return JobDataResponse(
                        success=False,
                        error_message="Invalid GCS URI format"
                    )

                bucket_name, gcs_key = gcs_parts

                # Initialize GCS client and retrieve data
                gcs_client = GCSClient(tenant_id=str(tenant_id))
                trace_data = gcs_client.stream_file_content(gcs_key)

                return JobDataResponse(
                    success=True,
                    data=trace_data
                )

        except Exception as e:
            logger.error(f"Failed to retrieve job trace for {job_id}: {e}")
            return JobDataResponse(
                success=False,
                error_message=f"Failed to retrieve trace data: {str(e)}"
            )

    @strawberry.field
    async def get_job_output(
        self,
        info: Info,
        job_id: str,
        tenant_id: int
    ) -> JobDataResponse:
        """
        Retrieve job output data from GCS.

        Args:
            job_id: The job identifier
            tenant_id: The tenant identifier

        Returns:
            JobDataResponse with output data or error
        """
        try:
            # Get database context from GraphQL info
            user_tenant_id = getattr(info.context, 'tenant_id', None)
            if user_tenant_id != tenant_id:
                return JobDataResponse(
                    success=False,
                    error_message="Unauthorized access to job data"
                )

            # Query job from database
            with get_session() as session:
                job = session.query(Job).filter(
                    Job.job_id == job_id,
                    Job.tenant_id == tenant_id
                ).first()

                if not job:
                    return JobDataResponse(
                        success=False,
                        error_message=f"Job not found: {job_id}"
                    )

                if not hasattr(job, 'output_data_uri') or not job.output_data_uri:
                    return JobDataResponse(
                        success=False,
                        error_message="Output data not available for this job"
                    )

                # Extract GCS key from URI
                if not job.output_data_uri.startswith('gs://'):
                    return JobDataResponse(
                        success=False,
                        error_message="Invalid output data URI format"
                    )

                gcs_parts = job.output_data_uri.replace('gs://', '').split('/', 1)
                if len(gcs_parts) != 2:
                    return JobDataResponse(
                        success=False,
                        error_message="Invalid GCS URI format"
                    )

                bucket_name, gcs_key = gcs_parts

                # Initialize GCS client and retrieve data
                gcs_client = GCSClient(tenant_id=str(tenant_id))
                output_data = gcs_client.stream_file_content(gcs_key)

                return JobDataResponse(
                    success=True,
                    data=output_data
                )

        except Exception as e:
            logger.error(f"Failed to retrieve job output for {job_id}: {e}")
            return JobDataResponse(
                success=False,
                error_message=f"Failed to retrieve output data: {str(e)}"
            )

    @strawberry.field
    async def get_job_data_status(
        self,
        info: Info,
        job_id: str,
        tenant_id: int
    ) -> "JobDataStatusResponse":
        """
        Get the availability status of job trace and output data.

        Args:
            job_id: The job identifier
            tenant_id: The tenant identifier

        Returns:
            JobDataStatusResponse with availability information
        """
        try:
            # Get database context from GraphQL info
            user_tenant_id = getattr(info.context, 'tenant_id', None)
            if user_tenant_id != tenant_id:
                return JobDataStatusResponse(
                    success=False,
                    error_message="Unauthorized access to job data"
                )

            # Query job from database
            with get_session() as session:
                job = session.query(Job).filter(
                    Job.job_id == job_id,
                    Job.tenant_id == tenant_id
                ).first()

                if not job:
                    return JobDataStatusResponse(
                        success=False,
                        error_message=f"Job not found: {job_id}",
                        trace_available=False,
                        output_available=False
                    )

                trace_available = (
                    hasattr(job, 'trace_data_uri') and
                    job.trace_data_uri is not None and
                    len(job.trace_data_uri.strip()) > 0
                )

                output_available = (
                    hasattr(job, 'output_data_uri') and
                    job.output_data_uri is not None and
                    len(job.output_data_uri.strip()) > 0
                )

                return JobDataStatusResponse(
                    success=True,
                    trace_available=trace_available,
                    output_available=output_available,
                    trace_uri=job.trace_data_uri if trace_available else None,
                    output_uri=job.output_data_uri if output_available else None
                )

        except Exception as e:
            logger.error(f"Failed to get job data status for {job_id}: {e}")
            return JobDataStatusResponse(
                success=False,
                error_message=f"Failed to get data status: {str(e)}",
                trace_available=False,
                output_available=False
            )

@strawberry.type
class JobDataStatusResponse:
    """Response type for job data status queries."""
    success: bool
    trace_available: bool = False
    output_available: bool = False
    trace_uri: Optional[str] = None
    output_uri: Optional[str] = None
    error_message: Optional[str] = None
