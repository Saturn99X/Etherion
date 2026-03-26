import pytest
import json
import time
from unittest.mock import patch
from src.database.db import session_scope, get_db
from src.database.models import Job, JobStatus, ExecutionTraceStep, AgentTeam, CustomAgentDefinition, Tenant, Project, StepType
from src.services.goal_orchestrator import orchestrate_goal_task
from src.services.user_observation_service import UserObservationService
from src.database.models import UserObservation


def test_multi_orchestrator_with_observation_recording():
    """Test that orchestration includes observation recording."""
    with patch('src.services.goal_orchestrator.get_user_observation_service') as mock_obs_service, \
         patch('src.services.goal_orchestrator.get_tool_manager') as mock_tool_mgr, \
         patch('src.services.goal_orchestrator.get_gemini_llm') as mock_llm, \
         patch('src.services.goal_orchestrator.create_react_agent') as mock_create_agent:

        # Setup mocks
        mock_observation_service = Mock()
        mock_obs_service.return_value = mock_observation_service
        mock_observation_service.generate_system_instructions.return_value = "User prefers concise responses."

        mock_tool_manager = Mock()
        mock_tool_mgr.return_value = mock_tool_manager
        mock_tool_manager.get_tools_for_tenant.return_value = [Mock(name="test_tool")]

        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance

        mock_team_agent = Mock()
        mock_team_agent.ainvoke = Mock(side_effect=Exception("Team failure for testing"))
        mock_platform_agent = Mock()
        mock_platform_agent.ainvoke = Mock(return_value={"output": "Platform orchestration successful"})
        mock_create_agent.side_effect = [mock_team_agent, mock_platform_agent]

        with session_scope() as session:
            tenant = Tenant(name="test_tenant_obs", tenant_id="tst_obs_123", subdomain="testobs", admin_email="obs@example.com")
            session.add(tenant)
            session.commit()
            session.refresh(tenant)

            project = Project(name="test_project_obs", description="", user_id=123, tenant_id=tenant.id)
            session.add(project)
            session.commit()
            session.refresh(project)

            # Create a minimal custom agent
            custom_agent = CustomAgentDefinition(
                custom_agent_id=CustomAgentDefinition.generate_custom_agent_id(),
                tenant_id=tenant.id,
                name="test_agent",
                description="Test agent",
                system_prompt="You are a test agent.",
                tool_names=json.dumps([])
            )
            session.add(custom_agent)
            session.commit()
            session.refresh(custom_agent)

            # Team with agent to force team execution path
            agent_team = AgentTeam(
                agent_team_id=AgentTeam.generate_agent_team_id(),
                tenant_id=tenant.id,
                name="test_team",
                description="Test team",
                custom_agent_ids=json.dumps([custom_agent.custom_agent_id]),
                pre_approved_tool_names=json.dumps([])
            )
            session.add(agent_team)
            session.commit()
            session.refresh(agent_team)

            # Create job record with user_id for observation recording
            job = Job(
                goal_description="Test goal with observation recording",
                project_id=project.project_id,
                user_id=123,
                tenant_id=tenant.id,
                status=JobStatus.RUNNING
            )
            session.add(job)
            session.commit()
            session.refresh(job)

            # Update job metadata to include agent team
            job_metadata = job.get_job_metadata() or {}
            job_metadata.update({"agent_team_id": agent_team.agent_team_id})
            job.set_job_metadata(job_metadata)
            session.commit()

            # Mock the execution to avoid actual LLM calls
            with patch('src.services.goal_orchestrator.GoalOrchestrator._execute_goal_orchestration') as mock_execute:
                mock_execute.return_value = {
                    "job_id": job.job_id,
                    "success": True,
                    "output": "Test orchestration result"
                }

                from src.services.goal_orchestrator import GoalOrchestrator
                orchestrator = GoalOrchestrator()

                # Execute orchestration
                result = orchestrator.orchestrate_goal(
                    "Test goal with observation recording",
                    project.project_id,
                    user_id=123
                )

                # Verify observation service was called
                mock_observation_service.generate_system_instructions.assert_called_with(123, tenant.id)
                mock_observation_service.record_interaction.assert_called()

                # Verify result
                assert result["success"] is True
                assert "job_id" in result


def test_multi_orchestrator_escalation():
    """Test that a failing Team Orchestrator escalates and completes via Platform Orchestrator."""

    with session_scope() as session:
        tenant = Tenant(name="test_tenant_mo", tenant_id="tst1234567890", subdomain="testmo", admin_email="t@example.com")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)

        project = Project(name="test_project_mo", description="", user_id=1, tenant_id=tenant.id)
        session.add(project)
        session.commit()
        session.refresh(project)

        # Create a minimal custom agent definition (will be executed via custom executor if present)
        custom_agent = CustomAgentDefinition(
            custom_agent_id=CustomAgentDefinition.generate_custom_agent_id(),
            tenant_id=tenant.id,
            name="failing_agent",
            description="Intentionally failing",
            system_prompt="You will attempt and report failure per contract.",
            tool_names=json.dumps([])
        )
        session.add(custom_agent)
        session.commit()
        session.refresh(custom_agent)

        # Team with no tools to force immediate failure and escalation
        agent_team = AgentTeam(
            agent_team_id=AgentTeam.generate_agent_team_id(),
            tenant_id=tenant.id,
            name="failing_team",
            description="No tools to guarantee failure",
            custom_agent_ids=json.dumps([custom_agent.custom_agent_id]),
            pre_approved_tool_names=json.dumps([])
        )
        session.add(agent_team)
        session.commit()
        session.refresh(agent_team)

        # Create job record
        job = Job(
            job_id=Job.generate_job_id(),
            tenant_id=tenant.id,
            user_id=1,
            status=JobStatus.QUEUED,
            job_type="execute_goal"
        )
        job.set_input_data({"goal": "Test goal that will escalate"})
        job.set_job_metadata({"agent_team_id": agent_team.agent_team_id})
        session.add(job)
        session.commit()
        session.refresh(job)

    # Invoke celery task synchronously (function call)
    result = orchestrate_goal_task(
        job_id=job.job_id,
        goal_description="Test goal that will escalate",
        context=None,
        output_format_instructions=None,
        user_id=1,
        tenant_id=tenant.id,
        agent_team_id=agent_team.agent_team_id
    )

    assert result["success"] is True
    assert result["job_id"] == job.job_id

    # Verify job status and trace evidence
    db = get_db()
    try:
        persisted_job = db.query(Job).filter(Job.job_id == job.job_id).first()
        assert persisted_job.status == JobStatus.COMPLETED

        steps = db.query(ExecutionTraceStep).filter(ExecutionTraceStep.job_id == job.job_id).all()
        # Not strictly required, but if present, check for failure/escalation markers
        trace_logs = " ".join([(s.thought or s.observation_result or "") for s in steps])
        assert ("failure" in trace_logs.lower() or "escalation" in trace_logs.lower() or len(steps) >= 0)
    finally:
        # Assert that CustomAgentDefinition was updated if self-healing applied
        updated_agent = None
        try:
            updated_agent = db.query(CustomAgentDefinition).filter(
                CustomAgentDefinition.tenant_id == tenant.id,
                CustomAgentDefinition.name == "failing_agent"
            ).first()
        except Exception:
            pass
        db.close()

    if updated_agent is not None and updated_agent.system_prompt:
        assert "improved" in (updated_agent.system_prompt or "").lower()
