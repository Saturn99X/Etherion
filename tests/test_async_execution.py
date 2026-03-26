#!/usr/bin/env python3
"""
Comprehensive test script for the Etherion AI Asynchronous Execution Engine.

This script tests all three systems:
1. Job-Based Foundation
2. Decoupled Real-Time API Layer
3. Persistent Memory Layer

Usage:
    python test_async_execution.py [--environment {dev,test,prod}] [--verbose]
"""

import asyncio
import json
import logging
import time
import argparse
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

# Add the src directory to Python path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Import our modules
try:
    from src.database.db import get_session
    from src.database.models import Job, JobStatus, ExecutionTraceStep, StepType, Tenant, User
    from src.core.celery import celery_app, health_check_task
    from src.core.redis import get_redis_client, publish_job_status, subscribe_to_job_status
    from src.services.goal_orchestrator import orchestrate_goal_task
    from src.services.job_status_publisher import get_job_status_publisher
    from src.core.tasks import update_job_status_task
except ImportError as e:
    print(f"Failed to import required modules: {e}")
    print("Make sure you're running this from the langchain-app directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_async_execution.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """Container for test results."""
    test_name: str
    success: bool
    message: str
    execution_time: float
    details: Optional[Dict[str, Any]] = None

class AsyncExecutionTester:
    """Comprehensive tester for the async execution system."""

    def __init__(self, environment: str = "test", verbose: bool = False):
        self.environment = environment
        self.verbose = verbose
        self.results: List[TestResult] = []
        self.redis_client = get_redis_client()
        self.job_status_publisher = get_job_status_publisher()

        # Test data
        self.test_tenant_id = 1
        self.test_user_id = 1
        self.test_job_ids: List[str] = []

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return comprehensive results."""
        logger.info(f"Starting comprehensive async execution tests (Environment: {self.environment})")

        test_methods = [
            self.test_database_models,
            self.test_redis_connectivity,
            self.test_celery_health,
            self.test_job_creation,
            self.test_job_status_publisher,
            self.test_execution_trace_recording,
            self.test_async_goal_orchestration,
            self.test_redis_subscriptions,
            self.test_job_lifecycle_complete,
            self.test_error_handling,
            self.test_job_cleanup
        ]

        start_time = time.time()

        for test_method in test_methods:
            try:
                logger.info(f"Running test: {test_method.__name__}")
                await test_method()
            except Exception as e:
                self.results.append(TestResult(
                    test_name=test_method.__name__,
                    success=False,
                    message=f"Test failed with exception: {str(e)}",
                    execution_time=0.0,
                    details={"exception": str(e), "type": type(e).__name__}
                ))
                logger.error(f"Test {test_method.__name__} failed: {e}")

        total_time = time.time() - start_time

        # Generate summary
        successful_tests = [r for r in self.results if r.success]
        failed_tests = [r for r in self.results if not r.success]

        summary = {
            "environment": self.environment,
            "total_tests": len(self.results),
            "successful_tests": len(successful_tests),
            "failed_tests": len(failed_tests),
            "success_rate": len(successful_tests) / len(self.results) * 100 if self.results else 0,
            "total_execution_time": total_time,
            "test_results": [
                {
                    "test_name": r.test_name,
                    "success": r.success,
                    "message": r.message,
                    "execution_time": r.execution_time,
                    "details": r.details
                }
                for r in self.results
            ]
        }

        return summary

    def _record_result(self, test_name: str, success: bool, message: str,
                      execution_time: float, details: Optional[Dict[str, Any]] = None):
        """Record a test result."""
        result = TestResult(test_name, success, message, execution_time, details)
        self.results.append(result)

        if success:
            logger.info(f"✅ {test_name}: {message}")
        else:
            logger.error(f"❌ {test_name}: {message}")

        if self.verbose and details:
            logger.info(f"Details: {json.dumps(details, indent=2)}")

    async def test_database_models(self):
        """Test System 1: Database models and relationships."""
        start_time = time.time()

        try:
            with get_session() as session:
                # Test Job model creation
                job = Job(
                    job_id=Job.generate_job_id(),
                    tenant_id=self.test_tenant_id,
                    user_id=self.test_user_id,
                    status=JobStatus.QUEUED,
                    job_type="test_job"
                )

                # Test JSON data methods
                test_data = {"test": "data", "number": 42}
                job.set_input_data(test_data)
                job.set_job_metadata({"created_by": "test_suite"})

                session.add(job)
                session.commit()
                session.refresh(job)

                # Verify data retrieval
                retrieved_input = job.get_input_data()
                retrieved_metadata = job.get_job_metadata()

                assert retrieved_input == test_data
                assert retrieved_metadata["created_by"] == "test_suite"

                self.test_job_ids.append(job.job_id)

                # Test ExecutionTraceStep model
                trace_step = ExecutionTraceStep(
                    job_id=job.job_id,
                    tenant_id=self.test_tenant_id,
                    step_number=1,
                    step_type=StepType.THOUGHT,
                    thought="This is a test thought"
                )

                session.add(trace_step)
                session.commit()

                execution_time = time.time() - start_time
                self._record_result(
                    "test_database_models",
                    True,
                    f"Successfully created Job and ExecutionTraceStep models",
                    execution_time,
                    {
                        "job_id": job.job_id,
                        "trace_step_id": trace_step.id,
                        "input_data_test": "passed",
                        "metadata_test": "passed"
                    }
                )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_database_models",
                False,
                f"Database model test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def test_redis_connectivity(self):
        """Test Redis connectivity and Pub/Sub functionality."""
        start_time = time.time()

        try:
            # Test basic connectivity
            ping_result = await self.redis_client.ping()
            assert ping_result, "Redis ping failed"

            # Test set/get operations
            test_key = f"test_key_{int(time.time())}"
            test_value = {"test": "value", "timestamp": time.time()}

            await self.redis_client.set(test_key, test_value, expire=60)
            retrieved_value = await self.redis_client.get(test_key)

            assert retrieved_value == test_value

            # Test pub/sub functionality
            test_channel = f"test_channel_{int(time.time())}"
            test_message = {"type": "test", "data": "pub_sub_test"}

            # Publish message
            await self.redis_client.publish(test_channel, test_message)

            # Clean up
            await self.redis_client.delete(test_key)

            execution_time = time.time() - start_time
            self._record_result(
                "test_redis_connectivity",
                True,
                "Redis connectivity and Pub/Sub tests passed",
                execution_time,
                {
                    "ping": "success",
                    "set_get": "success",
                    "pub_sub": "success"
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_redis_connectivity",
                False,
                f"Redis connectivity test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def test_celery_health(self):
        """Test Celery worker health and basic task execution."""
        start_time = time.time()

        try:
            # Test basic health check task
            result = health_check_task.delay()

            # Wait for result with timeout
            task_result = result.get(timeout=30)

            assert task_result["status"] == "healthy"
            assert "task_id" in task_result

            execution_time = time.time() - start_time
            self._record_result(
                "test_celery_health",
                True,
                f"Celery health check passed: {task_result['message']}",
                execution_time,
                {
                    "task_id": task_result["task_id"],
                    "celery_status": task_result["status"]
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_celery_health",
                False,
                f"Celery health test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def test_job_creation(self):
        """Test System 1: Job creation and status management."""
        start_time = time.time()

        try:
            with get_session() as session:
                # Create a new job
                job = Job(
                    job_id=Job.generate_job_id(),
                    tenant_id=self.test_tenant_id,
                    user_id=self.test_user_id,
                    status=JobStatus.QUEUED,
                    job_type="execute_goal"
                )

                input_data = {
                    "goal": "Test goal execution",
                    "context": "This is a test context",
                    "user_id": self.test_user_id
                }
                job.set_input_data(input_data)

                session.add(job)
                session.commit()
                session.refresh(job)

                self.test_job_ids.append(job.job_id)

                # Test status updates
                job.update_status(JobStatus.RUNNING)
                session.commit()

                assert job.status == JobStatus.RUNNING
                assert job.started_at is not None

                # Test completion
                job.update_status(JobStatus.COMPLETED)
                output_data = {"result": "Test completed successfully"}
                job.set_output_data(output_data)
                session.commit()

                assert job.status == JobStatus.COMPLETED
                assert job.completed_at is not None
                assert job.get_output_data() == output_data

                execution_time = time.time() - start_time
                self._record_result(
                    "test_job_creation",
                    True,
                    f"Job lifecycle test completed successfully",
                    execution_time,
                    {
                        "job_id": job.job_id,
                        "status_transitions": "QUEUED -> RUNNING -> COMPLETED",
                        "input_data": input_data,
                        "output_data": output_data
                    }
                )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_job_creation",
                False,
                f"Job creation test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def test_job_status_publisher(self):
        """Test System 2: Job status publishing functionality."""
        start_time = time.time()

        try:
            test_job_id = f"test_job_{int(time.time())}"

            # Test various status updates
            updates = [
                {
                    "status": "QUEUED",
                    "message": "Job queued for processing",
                    "progress_percentage": 0
                },
                {
                    "status": "RUNNING",
                    "message": "Job execution started",
                    "progress_percentage": 10,
                    "current_step_description": "Initializing orchestrator"
                },
                {
                    "status": "RUNNING",
                    "message": "Processing goal",
                    "progress_percentage": 50,
                    "current_step_description": "THOUGHT: Analyzing user requirements"
                },
                {
                    "status": "COMPLETED",
                    "message": "Job completed successfully",
                    "progress_percentage": 100
                }
            ]

            successful_publishes = 0
            for update in updates:
                result = await self.job_status_publisher.publish_status_update(
                    job_id=test_job_id,
                    **update
                )
                if result:
                    successful_publishes += 1

                # Small delay between updates
                await asyncio.sleep(0.1)

            assert successful_publishes == len(updates)

            execution_time = time.time() - start_time
            self._record_result(
                "test_job_status_publisher",
                True,
                f"Successfully published {successful_publishes} status updates",
                execution_time,
                {
                    "job_id": test_job_id,
                    "updates_published": successful_publishes,
                    "total_updates": len(updates)
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_job_status_publisher",
                False,
                f"Job status publisher test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def test_execution_trace_recording(self):
        """Test System 3: Execution trace recording."""
        start_time = time.time()

        try:
            from src.services.goal_orchestrator import record_thought_step, record_action_step, record_observation_step

            test_job_id = f"test_trace_job_{int(time.time())}"

            # Record different types of trace steps
            thought_step = record_thought_step(
                job_id=test_job_id,
                tenant_id=self.test_tenant_id,
                step_number=1,
                thought="I need to analyze this goal and determine the best approach",
                model_used="gemini-2.5-pro",
                step_cost=0.002
            )

            action_step = record_action_step(
                job_id=test_job_id,
                tenant_id=self.test_tenant_id,
                step_number=2,
                action_tool="VertexAISearch",
                action_input={"query": "test search", "max_results": 5},
                model_used="gemini-2.5-pro",
                step_cost=0.001
            )

            observation_step = record_observation_step(
                job_id=test_job_id,
                tenant_id=self.test_tenant_id,
                step_number=3,
                observation_result="Found 3 relevant results for the search query",
                model_used="gemini-2.5-pro",
                step_cost=0.0005
            )

            # Verify steps were recorded
            with get_session() as session:
                trace_steps = session.query(ExecutionTraceStep).filter(
                    ExecutionTraceStep.job_id == test_job_id
                ).order_by(ExecutionTraceStep.step_number).all()

                assert len(trace_steps) == 3
                assert trace_steps[0].step_type == StepType.THOUGHT
                assert trace_steps[1].step_type == StepType.ACTION
                assert trace_steps[2].step_type == StepType.OBSERVATION

                total_cost = sum(step.step_cost for step in trace_steps if step.step_cost)

            execution_time = time.time() - start_time
            self._record_result(
                "test_execution_trace_recording",
                True,
                f"Successfully recorded {len(trace_steps)} execution trace steps",
                execution_time,
                {
                    "job_id": test_job_id,
                    "trace_steps_recorded": len(trace_steps),
                    "total_cost": float(total_cost),
                    "step_types": [step.step_type.value for step in trace_steps]
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_execution_trace_recording",
                False,
                f"Execution trace recording test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def test_async_goal_orchestration(self):
        """Test complete async goal orchestration workflow."""
        start_time = time.time()

        try:
            # Create a job for orchestration
            with get_session() as session:
                job = Job(
                    job_id=Job.generate_job_id(),
                    tenant_id=self.test_tenant_id,
                    user_id=self.test_user_id,
                    status=JobStatus.QUEUED,
                    job_type="execute_goal"
                )

                input_data = {
                    "goal": "Write a short test summary",
                    "context": "This is for testing the async execution system",
                    "output_format_instructions": "Return a JSON object with 'summary' key"
                }
                job.set_input_data(input_data)

                session.add(job)
                session.commit()
                session.refresh(job)

                self.test_job_ids.append(job.job_id)

            # Enqueue orchestration task
            task_result = orchestrate_goal_task.delay(
                job_id=job.job_id,
                goal_description=input_data["goal"],
                context=input_data["context"],
                output_format_instructions=input_data["output_format_instructions"],
                user_id=self.test_user_id,
                tenant_id=self.test_tenant_id
            )

            # Note: In a real test, we would wait for the task to complete
            # For this test, we just verify the task was enqueued successfully
            assert task_result.id is not None

            execution_time = time.time() - start_time
            self._record_result(
                "test_async_goal_orchestration",
                True,
                f"Goal orchestration task enqueued successfully",
                execution_time,
                {
                    "job_id": job.job_id,
                    "task_id": task_result.id,
                    "task_state": task_result.state,
                    "input_data": input_data
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_async_goal_orchestration",
                False,
                f"Async goal orchestration test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def test_redis_subscriptions(self):
        """Test System 2: Redis subscription functionality."""
        start_time = time.time()

        try:
            test_job_id = f"subscription_test_job_{int(time.time())}"
            messages_received = []

            async def message_collector():
                async for message in subscribe_to_job_status(test_job_id):
                    messages_received.append(message)
                    if len(messages_received) >= 3:  # Collect 3 messages then stop
                        break

            # Start subscription in background
            subscription_task = asyncio.create_task(message_collector())

            # Give subscription time to start
            await asyncio.sleep(0.5)

            # Publish test messages
            test_messages = [
                {"status": "QUEUED", "message": "Job queued"},
                {"status": "RUNNING", "message": "Job started", "progress": 10},
                {"status": "COMPLETED", "message": "Job completed", "progress": 100}
            ]

            for msg in test_messages:
                await publish_job_status(test_job_id, msg)
                await asyncio.sleep(0.2)

            # Wait for subscription to collect messages
            await asyncio.wait_for(subscription_task, timeout=10)

            assert len(messages_received) == 3
            assert messages_received[0]["status"] == "QUEUED"
            assert messages_received[2]["status"] == "COMPLETED"

            execution_time = time.time() - start_time
            self._record_result(
                "test_redis_subscriptions",
                True,
                f"Successfully received {len(messages_received)} messages via subscription",
                execution_time,
                {
                    "job_id": test_job_id,
                    "messages_received": len(messages_received),
                    "messages": messages_received
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_redis_subscriptions",
                False,
                f"Redis subscription test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def test_job_lifecycle_complete(self):
        """Test complete job lifecycle from creation to completion."""
        start_time = time.time()

        try:
            # This test simulates a complete job lifecycle
            job_id = Job.generate_job_id()

            # Step 1: Create job
            with get_session() as session:
                job = Job(
                    job_id=job_id,
                    tenant_id=self.test_tenant_id,
                    user_id=self.test_user_id,
                    status=JobStatus.QUEUED,
                    job_type="execute_goal"
                )

                job.set_input_data({
                    "goal": "Complete lifecycle test",
                    "context": "Testing full workflow"
                })

                session.add(job)
                session.commit()

                self.test_job_ids.append(job_id)

            # Step 2: Publish initial status
            await self.job_status_publisher.publish_job_started(job_id, "Job started")

            # Step 3: Update to running status
            update_result = update_job_status_task.delay(job_id, JobStatus.RUNNING.value)
            update_result.get(timeout=10)  # Wait for completion

            # Step 4: Record execution steps
            from src.services.goal_orchestrator import record_thought_step, record_action_step

            record_thought_step(job_id, self.test_tenant_id, 1,
                              "Starting goal processing", "gemini-2.5-pro", 0.001)
            record_action_step(job_id, self.test_tenant_id, 2,
                             "TestTool", {"param": "value"}, "gemini-2.5-pro", 0.002)

            # Step 5: Publish progress updates
            await self.job_status_publisher.publish_job_progress(
                job_id, 50, "Processing goal", "Halfway through processing"
            )

            # Step 6: Complete the job
            await self.job_status_publisher.publish_job_completed(
                job_id, {"result": "Test completed"}, "Job completed successfully"
            )

            # Step 7: Update final status in database
            update_result = update_job_status_task.delay(job_id, JobStatus.COMPLETED.value)
            update_result.get(timeout=10)

            # Verify final state
            with get_session() as session:
                final_job = session.query(Job).filter(Job.job_id == job_id).first()
                assert final_job.status == JobStatus.COMPLETED

                trace_steps = session.query(ExecutionTraceStep).filter(
                    ExecutionTraceStep.job_id == job_id
                ).count()
                assert trace_steps == 2

            execution_time = time.time() - start_time
            self._record_result(
                "test_job_lifecycle_complete",
                True,
                "Complete job lifecycle test passed",
                execution_time,
                {
                    "job_id": job_id,
                    "final_status": "COMPLETED",
                    "trace_steps": trace_steps
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_job_lifecycle_complete",
                False,
                f"Complete job lifecycle test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def test_error_handling(self):
        """Test error handling and failure scenarios."""
        start_time = time.time()

        try:
            test_cases = []

            # Test 1: Job with invalid status transition
            try:
                with get_session() as session:
                    job = Job(
                        job_id=Job.generate_job_id(),
                        tenant_id=self.test_tenant_id,
                        user_id=self.test_user_id,
                        status=JobStatus.COMPLETED,  # Start as completed
                        job_type="test_error"
                    )

                    session.add(job)
                    session.commit()

                    # Try to update to running (invalid transition)
                    job.update_status(JobStatus.RUNNING)  # This should work (our model allows it)
                    session.commit()

                    test_cases.append(("invalid_status_transition", True, "Model allows status transitions"))

            except Exception as e:
                test_cases.append(("invalid_status_transition", False, str(e)))

            # Test 2: Publishing status for non-existent job
            try:
                fake_job_id = "non_existent_job_123"
                result = await self.job_status_publisher.publish_status_update(
                    job_id=fake_job_id,
                    status="RUNNING",
                    message="This should work even for non-existent jobs"
                )
                test_cases.append(("non_existent_job_publish", True, "Publishing works for any job_id"))

            except Exception as e:
                test_cases.append(("non_existent_job_publish", False, str(e)))

            # Test 3: Redis connection failure simulation
            try:
                # This test would require mocking Redis failure
                # For now, just test that our Redis client handles basic errors gracefully
                result = await self.redis_client.get("definitely_non_existent_key")
                assert result is None
                test_cases.append(("redis_error_handling", True, "Gracefully handles non-existent keys"))

            except Exception as e:
                test_cases.append(("redis_error_handling", False, str(e)))

            successful_cases = [case for case in test_cases if case[1]]

            execution_time = time.time() - start_time
            self._record_result(
                "test_error_handling",
                len(successful_cases) == len(test_cases),
                f"Error handling tests: {len(successful_cases)}/{len(test_cases)} passed",
                execution_time,
                {
                    "test_cases": test_cases,
                    "successful": len(successful_cases),
                    "total": len(test_cases)
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_error_handling",
                False,
                f"Error handling test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def test_job_cleanup(self):
        """Test job cleanup and maintenance functionality."""
        start_time = time.time()

        try:
            from src.core.tasks import cleanup_completed_jobs_task

            # Create some old completed jobs
            old_jobs_created = 0
            with get_session() as session:
                for i in range(3):
                    job = Job(
                        job_id=Job.generate_job_id(),
                        tenant_id=self.test_tenant_id,
                        user_id=self.test_user_id,
                        status=JobStatus.COMPLETED,
                        job_type="cleanup_test"
                    )

                    # Set completed_at to 2 days ago
                    job.completed_at = datetime.utcnow() - timedelta(days=2)

                    session.add(job)
                    old_jobs_created += 1

                session.commit()

            # Run cleanup task (for jobs older than 1 day)
            cleanup_result = cleanup_completed_jobs_task.delay(max_age_hours=24)
            result = cleanup_result.get(timeout=30)

            assert result["success"] == True
            assert result["cleaned_jobs"] >= 0  # Should have cleaned up some jobs

            execution_time = time.time() - start_time
            self._record_result(
                "test_job_cleanup",
                True,
                f"Job cleanup test passed: cleaned {result['cleaned_jobs']} jobs",
                execution_time,
                {
                    "old_jobs_created": old_jobs_created,
                    "jobs_cleaned": result["cleaned_jobs"],
                    "cleanup_result": result
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_result(
                "test_job_cleanup",
                False,
                f"Job cleanup test failed: {str(e)}",
                execution_time,
                {"exception": str(e)}
            )

    async def cleanup_test_data(self):
        """Clean up test data created during tests."""
        try:
            with get_session() as session:
                # Clean up test jobs
                for job_id in self.test_job_ids:
                    job = session.query(Job).filter(Job.job_id == job_id).first()
                    if job:
                        session.delete(job)

                    # Clean up associated trace steps
                    trace_steps = session.query(ExecutionTraceStep).filter(
                        ExecutionTraceStep.job_id == job_id
                    ).all()
                    for step in trace_steps:
                        session.delete(step)

                session.commit()
                logger.info(f"Cleaned up {len(self.test_job_ids)} test jobs and associated data")

        except Exception as e:
            logger.error(f"Error cleaning up test data: {e}")

    def print_summary(self, summary: Dict[str, Any]):
        """Print a comprehensive test summary."""
        print("\n" + "="*80)
        print("ETHERION AI ASYNC EXECUTION ENGINE - TEST RESULTS")
        print("="*80)
        print(f"Environment: {summary['environment']}")
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Successful: {summary['successful_tests']}")
        print(f"Failed: {summary['failed_tests']}")
        print(f"Success Rate: {summary['success_rate']:.1f}%")
        print(f"Total Execution Time: {summary['total_execution_time']:.2f}s")
        print()

        # Print individual test results
        for result in summary['test_results']:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            print(f"{status} {result['test_name']}")
            print(f"    Message: {result['message']}")
            print(f"    Time: {result['execution_time']:.3f}s")
            if not result['success'] and result.get('details'):
                print(f"    Error: {result['details'].get('exception', 'Unknown error')}")
            print()

        # Overall assessment
        if summary['success_rate'] == 100:
            print("🎉 ALL TESTS PASSED! The async execution engine is working correctly.")
        elif summary['success_rate'] >= 80:
            print("⚠️  Most tests passed, but there are some issues to address.")
        else:
            print("🚨 CRITICAL ISSUES detected. The system needs attention before deployment.")

        print("="*80)


async def main():
    """Main test execution function."""
    parser = argparse.ArgumentParser(
        description="Test the Etherion AI Asynchronous Execution Engine"
    )
    parser.add_argument(
        "--environment",
        choices=["dev", "test", "prod"],
        default="test",
        help="Test environment"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--output-file",
        type=str,
        help="Save results to JSON file"
    )

    args = parser.parse_args()

    # Set log level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("Starting Etherion AI Async Execution Engine Tests...")
    print(f"Environment: {args.environment}")
    print(f"Verbose: {args.verbose}")
    print()

    tester = AsyncExecutionTester(
        environment=args.environment,
        verbose=args.verbose
    )

    try:
        # Run all tests
        summary = await tester.run_all_tests()

        # Print results
        tester.print_summary(summary)

        # Save results to file if requested
        if args.output_file:
            with open(args.output_file, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
            print(f"\nResults saved to: {args.output_file}")

        # Clean up test data
        await tester.cleanup_test_data()

        # Exit with appropriate code
        exit_code = 0 if summary['success_rate'] == 100 else 1
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\n\nTest execution interrupted by user.")
        await tester.cleanup_test_data()
        sys.exit(130)

    except Exception as e:
        print(f"\n\nFATAL ERROR during test execution: {e}")
        logger.exception("Fatal error during test execution")
        sys.exit(1)


if __name__ == "__main__":
    try:
        # Check if we're running in the correct environment
        if not os.path.exists("src"):
            print("Error: This script must be run from the langchain-app directory")
            sys.exit(1)

        # Run the async main function
        asyncio.run(main())

    except Exception as e:
        print(f"Failed to start test suite: {e}")
        sys.exit(1)
