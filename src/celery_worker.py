#!/usr/bin/env python3
"""
Celery Worker Entry Point for Etherion AI Platform
This script serves as the entry point for Celery workers running in Cloud Run.
"""

import os
import sys
import logging
from pathlib import Path

# Add the src directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def main():
    """Main entry point for Celery worker."""
    try:
        # Import Celery app after setting up path
        from src.core.celery import celery_app
        
        # Import task modules to ensure they are registered with the Celery app
        try:
            import src.services.goal_orchestrator  # noqa
            import src.services.pricing.reconciliation  # noqa
            logger.info("Successfully imported task modules")
        except ImportError as e:
            logger.error(f"Failed to import task modules: {e}", exc_info=True)
            raise

        # Log startup information
        logger.info("Starting Etherion AI Celery Worker")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Worker PID: {os.getpid()}")
        logger.info(f"REDIS_URL: {os.getenv('REDIS_URL', 'not set')}")
        logger.info(f"CELERY_BROKER_URL: {os.getenv('CELERY_BROKER_URL', 'not set')}")

        # Configure worker arguments
        # NOTE: Do NOT pass --app here. When calling celery_app.start(), the app
        # is already known. --app is only for CLI invocation (celery -A <app> worker).
        # Concurrency from env var, default 8 for multi-user support
        concurrency = os.getenv("CELERY_CONCURRENCY", "8")
        worker_args = [
            "worker",
            "--loglevel=info",
            f"--concurrency={concurrency}",
            "--max-tasks-per-child=100",
            "--prefetch-multiplier=1",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            "--pool=threads"
        ]

        # Add queue specification if provided
        queue = os.getenv("CELERY_QUEUE", "etherion_tasks")
        worker_args.extend(["--queues", queue])

        # Start the worker
        logger.info(f"Starting Celery worker with args: {' '.join(worker_args[1:])}")
        celery_app.start(worker_args)

    except KeyboardInterrupt:
        logger.info("Celery worker interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to start Celery worker: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
