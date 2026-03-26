"""
Temporary File Manager for local buffering of execution traces and outputs.

This module provides utilities for creating, managing, and cleaning up temporary files
used for buffering execution traces and job outputs before uploading to GCS.
"""

import logging
import os
import json
import tempfile
import uuid
from typing import Optional, Dict, Any, List
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class TempFileManager:
    """
    Manager for temporary files used in execution trace buffering.

    Provides context managers and utilities for creating, writing to, and cleaning up
    temporary files used during job execution.
    """

    def __init__(self, tenant_id: str, job_id: str, base_temp_dir: Optional[str] = None):
        """
        Initialize temp file manager for a specific job.

        Args:
            tenant_id: Tenant identifier for isolation
            job_id: Job identifier for file naming
            base_temp_dir: Base directory for temp files (defaults to system temp dir)
        """
        self.tenant_id = tenant_id
        self.job_id = job_id
        self.base_temp_dir = base_temp_dir or tempfile.gettempdir()

        # Create tenant-specific temp directory
        self.tenant_temp_dir = Path(self.base_temp_dir) / f"etherion-{tenant_id}"
        self.tenant_temp_dir.mkdir(exist_ok=True, parents=True)

        # Job-specific temp directory
        self.job_temp_dir = self.tenant_temp_dir / f"job-{job_id}"
        self.job_temp_dir.mkdir(exist_ok=True, parents=True)

        # File paths
        self.trace_file_path = self.job_temp_dir / f"trace-{job_id}.jsonl"
        self.output_file_path = self.job_temp_dir / f"output-{job_id}.txt"

        logger.info(f"Initialized temp file manager for job {job_id}, tenant {tenant_id}")

    @contextmanager
    def trace_file_writer(self):
        """
        Context manager for writing to the trace file.

        Yields:
            function: Function to append trace steps to the file
        """
        trace_steps = []

        def append_trace_step(step_data: Dict[str, Any]) -> None:
            """Append a trace step to the buffer."""
            trace_steps.append(step_data)

        try:
            yield append_trace_step
        finally:
            # Write all buffered steps to file on exit
            self._write_trace_steps_to_file(trace_steps)

    def append_trace_step(self, step_data: Dict[str, Any]) -> None:
        """
        Append a single trace step to the trace file.

        Args:
            step_data: Trace step data to append
        """
        try:
            with open(self.trace_file_path, 'a', encoding='utf-8') as f:
                json.dump(step_data, f, ensure_ascii=False)
                f.write('\n')
        except Exception as e:
            logger.error(f"Failed to append trace step to file: {e}")
            raise

    def write_job_output(self, output_data: str) -> None:
        """
        Write job output to the output file.

        Args:
            output_data: Final job output to write
        """
        try:
            with open(self.output_file_path, 'w', encoding='utf-8') as f:
                f.write(output_data)
        except Exception as e:
            logger.error(f"Failed to write job output to file: {e}")
            raise

    def _write_trace_steps_to_file(self, trace_steps: List[Dict[str, Any]]) -> None:
        """
        Write buffered trace steps to the file.

        Args:
            trace_steps: List of trace steps to write
        """
        if not trace_steps:
            return

        try:
            with open(self.trace_file_path, 'a', encoding='utf-8') as f:
                for step in trace_steps:
                    json.dump(step, f, ensure_ascii=False)
                    f.write('\n')
        except Exception as e:
            logger.error(f"Failed to write trace steps to file: {e}")
            raise

    def get_trace_file_path(self) -> str:
        """
        Get the path to the trace file.

        Returns:
            str: Path to the trace file
        """
        return str(self.trace_file_path)

    def get_output_file_path(self) -> str:
        """
        Get the path to the output file.

        Returns:
            str: Path to the output file
        """
        return str(self.output_file_path)

    def trace_file_exists(self) -> bool:
        """
        Check if the trace file exists.

        Returns:
            bool: True if trace file exists
        """
        return self.trace_file_path.exists()

    def output_file_exists(self) -> bool:
        """
        Check if the output file exists.

        Returns:
            bool: True if output file exists
        """
        return self.output_file_path.exists()

    def get_trace_file_size(self) -> int:
        """
        Get the size of the trace file in bytes.

        Returns:
            int: File size in bytes
        """
        if not self.trace_file_exists():
            return 0
        return self.trace_file_path.stat().st_size

    def cleanup(self) -> None:
        """
        Clean up temporary files and directories.
        """
        try:
            # Remove job-specific temp directory and all its contents
            if self.job_temp_dir.exists():
                import shutil
                shutil.rmtree(self.job_temp_dir)
                logger.info(f"Cleaned up temp directory: {self.job_temp_dir}")

            # Check if tenant temp directory is empty and remove if so
            if self.tenant_temp_dir.exists() and not any(self.tenant_temp_dir.iterdir()):
                self.tenant_temp_dir.rmdir()
                logger.info(f"Cleaned up empty tenant temp directory: {self.tenant_temp_dir}")

        except Exception as e:
            logger.error(f"Failed to cleanup temp files: {e}")

    def read_trace_file_content(self) -> str:
        """
        Read the entire trace file content.

        Returns:
            str: Trace file content
        """
        if not self.trace_file_exists():
            return ""

        try:
            with open(self.trace_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read trace file content: {e}")
            return ""

    def read_output_file_content(self) -> str:
        """
        Read the entire output file content.

        Returns:
            str: Output file content
        """
        if not self.output_file_exists():
            return ""

        try:
            with open(self.output_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read output file content: {e}")
            return ""

    @classmethod
    def cleanup_stale_temp_files(cls, max_age_hours: int = 24) -> None:
        """
        Clean up stale temporary files older than specified hours.

        Args:
            max_age_hours: Maximum age of temp files to keep
        """
        import time

        try:
            temp_base = Path(tempfile.gettempdir())
            etherion_temp_dirs = temp_base.glob("etherion-*")

            current_time = time.time()
            max_age_seconds = max_age_hours * 3600

            for tenant_dir in etherion_temp_dirs:
                if not tenant_dir.is_dir():
                    continue

                # Check each job directory
                for job_dir in tenant_dir.glob("job-*"):
                    if not job_dir.is_dir():
                        continue

                    # Check if directory is older than max age
                    dir_mtime = job_dir.stat().st_mtime
                    if current_time - dir_mtime > max_age_seconds:
                        try:
                            import shutil
                            shutil.rmtree(job_dir)
                            logger.info(f"Cleaned up stale temp directory: {job_dir}")
                        except Exception as e:
                            logger.error(f"Failed to cleanup stale directory {job_dir}: {e}")

                # Clean up empty tenant directories
                if not any(tenant_dir.iterdir()):
                    try:
                        tenant_dir.rmdir()
                        logger.info(f"Cleaned up empty tenant temp directory: {tenant_dir}")
                    except Exception as e:
                        logger.error(f"Failed to cleanup empty tenant directory {tenant_dir}: {e}")

        except Exception as e:
            logger.error(f"Failed to cleanup stale temp files: {e}")
