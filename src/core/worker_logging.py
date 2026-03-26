"""
Worker logging configuration for Cloud Logging integration.

This module configures structured logging for Celery workers to ensure
all worker-side events are captured in Cloud Logging.
"""

import logging
import sys
from typing import Optional

try:
    from google.cloud import logging as cloud_logging
    CLOUD_LOGGING_AVAILABLE = True
except ImportError:
    CLOUD_LOGGING_AVAILABLE = False


def configure_worker_logging(
    enable_cloud_logging: bool = True,
    log_level: int = logging.INFO
) -> logging.Logger:
    """
    Configure logging for Celery workers.
    
    This function sets up structured logging that sends logs to both stdout
    and Google Cloud Logging (if enabled and available).
    
    Args:
        enable_cloud_logging: If True, attempt to send logs to Cloud Logging
        log_level: Logging level (default: logging.INFO)
    
    Returns:
        Configured root logger
    
    Example:
        # In worker startup (e.g., celery.py or worker entrypoint)
        from src.core.worker_logging import configure_worker_logging
        
        logger = configure_worker_logging(enable_cloud_logging=True)
        logger.info("Worker started successfully")
    """
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Add stdout handler (always enabled)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    
    # Use structured format for easy parsing
    formatter = logging.Formatter(
        '[%(levelname)s] %(asctime)s %(name)s | %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)
    
    # Add Cloud Logging handler if enabled and available
    if enable_cloud_logging:
        if not CLOUD_LOGGING_AVAILABLE:
            logger.warning(
                "Cloud Logging requested but google-cloud-logging not installed. "
                "Install with: pip install google-cloud-logging"
            )
        else:
            try:
                client = cloud_logging.Client()
                cloud_handler = client.get_default_handler()
                cloud_handler.setLevel(log_level)
                logger.addHandler(cloud_handler)
                logger.info("✓ Cloud Logging enabled for worker")
            except Exception as e:
                logger.warning(
                    f"Could not enable Cloud Logging: {e}. "
                    f"Logs will only appear in stdout."
                )
    
    return logger


def get_worker_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance for worker code.
    
    Args:
        name: Logger name (default: None for root logger)
    
    Returns:
        Logger instance
    
    Example:
        from src.core.worker_logging import get_worker_logger
        
        logger = get_worker_logger(__name__)
        logger.info("Processing job", extra={"job_id": "job_123"})
    """
    return logging.getLogger(name)
