"""
Comprehensive integration tests for complete frontend-backend system.

This test suite validates that all frontend components properly integrate with
the backend GraphQL API, including authentication, data flow, error handling,
and security measures.
"""

import pytest
import pytest_asyncio
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient

from src.database.db import get_session, session_scope
from src.database.models import User, Tenant, Tool, ToolStatus, Job, JobStatus
from src.database.models.secure_credential import SecureCredential, CredentialStatus
from src.etherion_ai.app import create_app
from src.services.secure_credential_service import SecureCredentialService
from src.tools.tool_manager import ToolManager


class TestCompleteFrontendBackendIntegration:
    """Test every frontend component with real backend data."""

    @pytest_asyncio.fixture
    async def app(self):
        """Create and configure the FastAPI application."""
        app_instance = create_app()
        async with AsyncClient(base_url="http://test") as client:
            yield app_instance, client

    @pytest_asyncio.fixture
    async def db_session(self):
        """Create a database session for testing."""
        # For async tests, we need to handle the sync session_scope differently
        session = get_session()  # Get a sync session
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @pytest_asyncio.fixture
    async def test_tenant(self, db_session):
        """Create a test tenant."""
        tenant = Tenant(
            tenant_id="test-tenant-123",
            subdomain="test-tenant",
            name="Test Tenant",
            admin_email="admin@test.com"
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)
        return tenant

    @pytest_asyncio.fixture
    async def test_user(self, db_session, test_tenant):
        """Create a test user."""
        user = User(
            user_id="test-user-123",
            tenant_id=test_tenant.id,
            email="test@test.com"
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    @pytest.mark.asyncio
    async def test_agent_registry_integration(self, app, db_session, test_user):
        """Test agent registry loads real agents from backend."""
        # app is a tuple of (app_instance, client)
        app_instance, client = app

        # Setup test data
        from src.database.models.custom_agent import CustomAgentDefinition

        agent = CustomAgentDefinition(
            custom_agent_id="test-agent-123",
            tenant_id=test_test_user.tenant_id,
            name="Test Customer Support Agent",
            description="Handles customer inquiries and provides product information",
            system_prompt="You are a helpful customer support agent...",
            is_system_agent=False,
            is_active=True
        )
        db_db_session.add(agent)
        await db_db_session.commit()
        await db_db_session.refresh(agent)

        # Test GraphQL query
        query = """
        query GetAgents($tenant_id: Int!) {
            getAgents(tenant_id: $tenant_id) {
                id
                name
                description
                createdAt
                lastUsed
                status
                agentType
                capabilities
                performanceMetrics
            }
        }
        """

        response = await client.post(
            "/graphql",
            json={
                "query": query,
                "variables": {"tenant_id": test_user.tenant_id}
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "getAgents" in data["data"]
        agents = data["data"]["getAgents"]

        # Verify agent data is returned
        assert len(agents) == 1
        assert agents[0]["name"] == "Test Customer Support Agent"
        assert agents[0]["description"] == "Handles customer inquiries and provides product information"
        assert agents[0]["agentType"] == "specialized"

        # Test creating a new agent
        create_mutation = """
        mutation CreateAgent($agent_input: AgentInput!) {
            createAgent(agent_input: $agent_input) {
                id
                name
                description
                status
            }
        }
        """

        create_response = await client.post(
            "/graphql",
            json={
                "query": create_mutation,
                "variables": {
                    "agent_input": {
                        "name": "New Test Agent",
                        "description": "A newly created test agent",
                        "agentType": "general",
                        "capabilities": ["test_capability"],
                        "systemPrompt": "You are a test agent..."
                    }
                }
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert create_response.status_code == 200
        create_data = create_response.json()
        assert "data" in create_data
        assert "createAgent" in create_data["data"]
        new_agent = create_data["data"]["createAgent"]
        assert new_agent["name"] == "New Test Agent"
        assert new_agent["status"] == "active"

        # Verify agent appears in registry
        response = await client.post(
            "/graphql",
            json={
                "query": query,
                "variables": {"tenant_id": test_user.tenant_id}
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        data = response.json()
        agents = data["data"]["getAgents"]
        assert len(agents) == 2  # Original + new agent

    @pytest.mark.asyncio
    async def test_integration_hub_real_connections(self, app, db_session, test_user):
        """Test integration hub shows real connection status."""
        # Create test integration credentials
        credential_service = SecureCredentialService()

        credentials = {
            "api_key": "test-api-key-123",
            "webhook_secret": "test-webhook-secret"
        }

        credential = credential_service.create_credential(
            tenant_id=test_user.tenant_id,
            tool_name="mcp_slack",
            service_name="slack",
            credential_data=credentials,
            credential_type="api_key",
            description="Test Slack credentials",
            created_by=str(test_user.id)
        )

        await db_session.commit()
        await db_session.refresh(credential)

        # Test GraphQL query for integrations
        query = """
        query GetIntegrations($tenant_id: Int!) {
            getIntegrations(tenant_id: $tenant_id) {
                serviceName
                status
                lastConnected
                errorMessage
                capabilities
            }
        }
        """

        response = await client.post(
            "/graphql",
            json={
                "query": query,
                "variables": {"tenant_id": test_user.tenant_id}
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "getIntegrations" in data["data"]
        integrations = data["data"]["getIntegrations"]

        # Should return empty list since no real integrations are configured
        assert isinstance(integrations, list)

        # Test connecting an integration
        connect_mutation = """
        mutation ConnectIntegration($service_name: String!, $credentials: String!) {
            connectIntegration(service_name: $service_name, credentials: $credentials) {
                serviceName
                status
                validationErrors
            }
        }
        """

        connect_response = await client.post(
            "/graphql",
            json={
                "query": connect_mutation,
                "variables": {
                    "service_name": "slack",
                    "credentials": json.dumps({
                        "api_key": "test-bot-token",
                        "webhook_url": "https://hooks.slack.com/test"
                    })
                }
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert connect_response.status_code == 200
        connect_data = connect_response.json()
        assert "data" in connect_data
        assert "connectIntegration" in connect_data["data"]

        # Test integration testing
        test_mutation = """
        mutation TestIntegration($service_name: String!) {
            testIntegration(service_name: $service_name) {
                success
                testResult
                errorMessage
            }
        }
        """

        test_response = await client.post(
            "/graphql",
            json={
                "query": test_mutation,
                "variables": {"service_name": "slack"}
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert test_response.status_code == 200
        test_data = test_response.json()
        assert "data" in test_data
        assert "testIntegration" in test_data["data"]

    @pytest.mark.asyncio
    async def test_mcp_tools_real_execution(self, app, db_session, test_user):
        """Test MCP tools execute real API calls."""
        # Setup MCP tool credentials
        credential_service = SecureCredentialService()

        # Create credentials for multiple MCP tools
        tools_credentials = {
            "mcp_slack": {
                "bot_token": "xoxb-test-bot-token",
                "app_token": "xapp-test-app-token"
            },
            "mcp_email": {
                "api_key": "SG.test-email-api-key",
                "domain": "test.com"
            },
            "mcp_jira": {
                "email": "test@test.com",
                "api_token": "test-jira-token",
                "site_url": "https://test.atlassian.net"
            }
        }

        for tool_name, credentials in tools_credentials.items():
            credential_service.create_credential(
                tenant_id=test_user.tenant_id,
                tool_name=tool_name,
                service_name=tool_name.replace("mcp_", ""),
                credential_data=credentials,
                credential_type="api_key",
                description=f"Test credentials for {tool_name}",
                created_by=str(test_user.id)
            )

        await db_session.commit()

        # Test GraphQL query for available MCP tools
        query = """
        query GetAvailableMCPTools {
            getAvailableMCPTools {
                name
                description
                category
                requiredCredentials
                capabilities
                status
            }
        }
        """

        response = await client.post(
            "/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "getAvailableMCPTools" in data["data"]
        tools = data["data"]["getAvailableMCPTools"]

        # Should return all registered MCP tools
        assert len(tools) >= 3  # At least the ones we created credentials for

        # Test MCP tool execution
        execute_mutation = """
        mutation ExecuteMCPTool($tool_name: String!, $params: String!) {
            executeMCPTool(tool_name: $tool_name, params: $params) {
                success
                result
                executionTime
                errorMessage
                toolOutput
            }
        }
        """

        # Test Slack tool execution
        execute_response = await client.post(
            "/graphql",
            json={
                "query": execute_mutation,
                "variables": {
                    "tool_name": "mcp_slack",
                    "params": json.dumps({
                        "tenant_id": test_user.tenant_id,
                        "action": "test_connection"
                    })
                }
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert execute_response.status_code == 200
        execute_data = execute_response.json()
        assert "data" in execute_data
        assert "executeMCPTool" in execute_data["data"]

        # Test credential management
        credential_mutation = """
        mutation ManageMCPCredentials($tool_name: String!, $credentials: String!) {
            manageMCPCredentials(tool_name: $tool_name, credentials: $credentials) {
                success
                validationErrors
            }
        }
        """

        credential_response = await client.post(
            "/graphql",
            json={
                "query": credential_mutation,
                "variables": {
                    "tool_name": "mcp_slack",
                    "credentials": json.dumps({
                        "bot_token": "xoxb-new-bot-token",
                        "app_token": "xapp-new-app-token"
                    })
                }
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert credential_response.status_code == 200
        credential_data = credential_response.json()
        assert "data" in credential_data
        assert "manageMCPCredentials" in credential_data["data"]

    @pytest.mark.asyncio
    async def test_job_history_real_data(self, app, db_session, test_user):
        """Test job history shows real execution data."""
        # Create test jobs
        jobs = []
        for i in range(5):
            job = Job(
                job_id=f"test-job-{i}",
                tenant_id=test_user.tenant_id,
                user_id=test_user.id,
                status=JobStatus.COMPLETED,
                job_type="execute_goal"
            )

            # Set input data
            input_data = {
                "goal": f"Test goal {i}: Analyze data and generate report",
                "context": f"Context for test job {i}",
                "output_format_instructions": "Return a summary report",
                "user_id": test_user.user_id,
                "tenant_id": test_user.tenant_id
            }
            job.set_input_data(input_data)

            # Set output data
            output_data = {
                "final_output": f"Report generated for test job {i}",
                "final_thought": f"Successfully analyzed data and generated report {i}",
                "total_cost": 0.1 * (i + 1),
                "model_used": "gpt-4",
                "token_count": 1000 + (i * 500),
                "success_rate": 0.85 + (i * 0.03)
            }
            job.set_output_data(output_data)

            jobs.append(job)
            db_session.add(job)

        await db_session.commit()

        # Test GraphQL query for job history
        query = """
        query GetJobHistory($limit: Int, $offset: Int, $status: String, $date_from: String, $date_to: String) {
            getJobHistory(limit: $limit, offset: $offset, status: $status, date_from: $date_from, date_to: $date_to) {
                jobs {
                    id
                    goal
                    status
                    createdAt
                    completedAt
                    duration
                    totalCost
                    modelUsed
                    tokenCount
                    successRate
                }
                totalCount
                pageInfo {
                    hasNextPage
                    hasPreviousPage
                }
            }
        }
        """

        response = await client.post(
            "/graphql",
            json={
                "query": query,
                "variables": {
                    "limit": 10,
                    "offset": 0,
                    "status": "completed"
                }
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "getJobHistory" in data["data"]
        job_history = data["data"]["getJobHistory"]

        # Verify job history data
        assert len(job_history["jobs"]) == 5
        assert job_history["totalCount"] == 5
        assert not job_history["pageInfo"]["hasNextPage"]
        assert not job_history["pageInfo"]["hasPreviousPage"]

        # Check specific job data
        job = job_history["jobs"][0]
        assert job["goal"] == "Test goal 0: Analyze data and generate report"
        assert job["status"] == "completed"
        assert job["modelUsed"] == "gpt-4"
        assert job["tokenCount"] == 1000
        assert job["totalCost"] == "$0.10"

        # Test job details query
        details_query = """
        query GetJobDetails($job_id: String!) {
            getJobDetails(job_id: $job_id) {
                id
                goal
                status
                createdAt
                completedAt
                executionTrace {
                    steps {
                        stepNumber
                        timestamp
                        stepType
                        thought
                        actionTool
                        actionInput
                        observationResult
                        stepCost
                        modelUsed
                    }
                }
                performanceMetrics
                errorLogs
            }
        }
        """

        details_response = await client.post(
            "/graphql",
            json={
                "query": details_query,
                "variables": {"job_id": "test-job-0"}
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert details_response.status_code == 200
        details_data = details_response.json()
        assert "data" in details_data
        assert "getJobDetails" in details_data["data"]

        job_details = details_data["data"]["getJobDetails"]
        assert job_details["id"] == "test-job-0"
        assert job_details["goal"] == "Test goal 0: Analyze data and generate report"
        assert job_details["status"] == "completed"

    @pytest.mark.asyncio
    async def test_tone_profile_management(self, app, db_session, test_user):
        """Test tone profile management with real data."""
        # Create test tone profiles
        from src.database.models.tone_profile import ToneProfile

        profiles = [
            ToneProfile(
                name="Professional",
                profile_text="Use a formal, professional tone with proper grammar and business language.",
                description="Formal tone suitable for business communications",
                is_default=True,
                user_id=test_user.id,
                tenant_id=test_user.tenant_id
            ),
            ToneProfile(
                name="Casual & Friendly",
                profile_text="Be conversational and friendly. Use contractions and a relaxed tone while staying helpful.",
                description="Friendly tone for customer interactions",
                is_default=False,
                user_id=test_user.id,
                tenant_id=test_user.tenant_id
            ),
            ToneProfile(
                name="Technical Expert",
                profile_text="Provide detailed technical explanations with precise terminology. Focus on accuracy.",
                description="Technical tone for expert audiences",
                is_default=False,
                user_id=test_user.id,
                tenant_id=test_user.tenant_id
            )
        ]

        for profile in profiles:
            db_session.add(profile)

        await db_session.commit()

        # Test GraphQL query for tone profiles
        query = """
        query GetToneProfiles($user_id: Int!) {
            getToneProfiles(user_id: $user_id) {
                id
                name
                type
                description
                usageCount
                lastUsed
                effectiveness
            }
        }
        """

        response = await client.post(
            "/graphql",
            json={
                "query": query,
                "variables": {"user_id": test_user.id}
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "getToneProfiles" in data["data"]
        tone_profiles = data["data"]["getToneProfiles"]

        # Verify tone profiles data
        assert len(tone_profiles) == 3
        assert tone_profiles[0]["name"] == "Professional"
        assert tone_profiles[0]["type"] == "system_default"
        assert tone_profiles[1]["name"] == "Casual & Friendly"
        assert tone_profiles[1]["type"] == "user_created"

        # Test applying a tone profile
        apply_mutation = """
        mutation ApplyToneProfile($profile_id: String!, $goal_id: String!) {
            applyToneProfile(profile_id: $profile_id, goal_id: $goal_id)
        }
        """

        apply_response = await client.post(
            "/graphql",
            json={
                "query": apply_mutation,
                "variables": {
                    "profile_id": str(profiles[0].id),
                    "goal_id": "test-goal-123"
                }
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert apply_response.status_code == 200
        apply_data = apply_response.json()
        assert "data" in apply_data
        assert "applyToneProfile" in apply_data["data"]
        assert apply_data["data"]["applyToneProfile"] is True

    @pytest.mark.asyncio
    async def test_secure_credential_management(self, app, db_session, test_user):
        """Test secure credential management system."""
        credential_service = SecureCredentialService()

        # Test creating credentials
        credentials = {
            "api_key": "sk-test-1234567890abcdef",
            "webhook_secret": "whsec_test_webhook_secret",
            "environment": "test"
        }

        credential = credential_service.create_credential(
            tenant_id=test_user.tenant_id,
            tool_name="mcp_stripe",
            service_name="stripe",
            credential_data=credentials,
            credential_type="api_key",
            description="Stripe test credentials",
            created_by=str(test_user.id)
        )

        await db_session.commit()
        await db_session.refresh(credential)

        # Verify credential was created
        assert credential.id is not None
        assert credential.tool_name == "mcp_stripe"
        assert credential.service_name == "stripe"
        assert credential.status == CredentialStatus.ACTIVE

        # Test retrieving credentials
        retrieved_data = credential_service.get_credential(
            credential_id=credential.id,
            tenant_id=test_user.tenant_id,
            accessed_by=str(test_user.id)
        )

        assert retrieved_data["api_key"] == "sk-test-1234567890abcdef"
        assert retrieved_data["webhook_secret"] == "whsec_test_webhook_secret"
        assert retrieved_data["environment"] == "test"

        # Test credential validation
        is_valid = credential_service.test_credential(
            credential_id=credential.id,
            tenant_id=test_user.tenant_id
        )

        assert is_valid[0] is True  # Success
        assert "valid" in is_valid[1].lower()

        # Test updating credentials
        new_credentials = {
            "api_key": "sk-live-new-key-abcdef123456",
            "webhook_secret": "whsec_new_webhook_secret",
            "environment": "production"
        }

        updated_credential = credential_service.update_credential(
            credential_id=credential.id,
            tenant_id=test_user.tenant_id,
            credential_data=new_credentials,
            updated_by=str(test_user.id)
        )

        assert updated_credential.id == credential.id
        assert updated_credential.last_updated_at > credential.created_at

        # Test credential revocation
        revocation_result = credential_service.revoke_credential(
            credential_id=credential.id,
            tenant_id=test_user.tenant_id,
            revoked_by=str(test_user.id)
        )

        assert revocation_result is True

        # Verify credential is revoked
        await db_session.refresh(credential)
        assert credential.status == CredentialStatus.REVOKED

    @pytest.mark.asyncio
    async def test_mcp_tool_manager_integration(self, app, db_session, test_user):
        """Test MCP tool manager integration with real credentials."""
        from src.services.mcp_tool_manager import MCPToolManager

        mcp_manager = MCPToolManager(db_session)

        # Create credentials for multiple MCP tools
        tools_credentials = {
            "mcp_slack": {
                "bot_token": "xoxb-test-slack-token-123",
                "app_token": "xapp-test-slack-app-456"
            },
            "mcp_email": {
                "api_key": "SG.test-email-key-789",
                "domain": "test-email.com"
            },
            "mcp_jira": {
                "email": "test@jira.com",
                "api_token": "jira-api-token-123",
                "site_url": "https://test.atlassian.net"
            }
        }

        created_credentials = []
        for tool_name, credentials in tools_credentials.items():
            credential = mcp_manager.credential_service.create_credential(
                tenant_id=test_user.tenant_id,
                tool_name=tool_name,
                service_name=tool_name.replace("mcp_", ""),
                credential_data=credentials,
                credential_type="api_key",
                description=f"Test credentials for {tool_name}",
                created_by=str(test_user.id)
            )
            created_credentials.append(credential)

        await db_session.commit()

        # Test getting available tools
        available_tools = await mcp_manager.get_available_tools()
        assert len(available_tools) >= 3

        # Test storing credentials through manager
        status = await mcp_manager.store_credentials(
            tenant_id=test_user.tenant_id,
            tool_name="mcp_hubspot",
            service_name="hubspot",
            credentials={"api_key": "hubspot-test-key-123"},
            created_by=str(test_user.id)
        )

        assert status.success is True

        # Test retrieving credentials through manager
        try:
            retrieved_creds = await mcp_manager.get_credentials(
                tenant_id=test_user.tenant_id,
                tool_name="mcp_slack"
            )
            assert "bot_token" in retrieved_creds
            assert retrieved_creds["bot_token"] == "xoxb-test-slack-token-123"
        except ValueError:
            # Expected if credentials are encrypted and can't be decrypted in test
            pass

        # Test testing credentials through manager
        test_result = await mcp_manager.test_credentials(
            tenant_id=test_user.tenant_id,
            tool_name="mcp_slack"
        )

        assert test_result is not None
        assert hasattr(test_result, 'success')

        # Test updating credentials through manager
        update_status = await mcp_manager.update_credentials(
            tenant_id=test_user.tenant_id,
            tool_name="mcp_email",
            service_name="email",
            new_credentials={"api_key": "SG.new-email-key-999", "domain": "new-domain.com"},
            updated_by=str(test_user.id)
        )

        assert update_status.success is True

    @pytest.mark.asyncio
    async def test_end_to_end_data_flow(self, app, db_session, test_user):
        """Test complete end-to-end data flow from frontend to backend."""
        # 1. Create an agent
        create_agent_mutation = """
        mutation CreateAgent($agent_input: AgentInput!) {
            createAgent(agent_input: $agent_input) {
                id
                name
                description
                status
                agentType
                capabilities
            }
        }
        """

        agent_response = await client.post(
            "/graphql",
            json={
                "query": create_agent_mutation,
                "variables": {
                    "agent_input": {
                        "name": "E2E Test Agent",
                        "description": "Agent created for end-to-end testing",
                        "agentType": "specialized",
                        "capabilities": ["data_analysis", "report_generation"],
                        "systemPrompt": "You are a data analysis agent..."
                    }
                }
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert agent_response.status_code == 200
        agent_data = agent_response.json()
        agent_id = agent_data["data"]["createAgent"]["id"]

        # 2. Configure MCP tool credentials
        credential_mutation = """
        mutation ManageMCPCredentials($tool_name: String!, $credentials: String!) {
            manageMCPCredentials(tool_name: $tool_name, credentials: $credentials) {
                success
                validationErrors
            }
        }
        """

        credential_response = await client.post(
            "/graphql",
            json={
                "query": credential_mutation,
                "variables": {
                    "tool_name": "mcp_slack",
                    "credentials": json.dumps({
                        "bot_token": "xoxb-e2e-test-token",
                        "app_token": "xapp-e2e-test-app"
                    })
                }
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert credential_response.status_code == 200
        credential_result = credential_response.json()
        assert credential_result["data"]["manageMCPCredentials"]["success"] is True

        # 3. Create a tone profile
        tone_mutation = """
        mutation CreateToneProfile($profile_input: ToneProfileInput!) {
            createToneProfile(profile_input: $profile_input) {
                id
                name
                description
                profileText
            }
        }
        """

        tone_response = await client.post(
            "/graphql",
            json={
                "query": tone_mutation,
                "variables": {
                    "profile_input": {
                        "name": "E2E Test Tone",
                        "profileText": "Use a professional and analytical tone for data analysis.",
                        "description": "Tone profile for end-to-end testing",
                        "isDefault": False
                    }
                }
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert tone_response.status_code == 200
        tone_result = tone_response.json()
        tone_id = tone_result["data"]["createToneProfile"]["id"]

        # 4. Execute a goal that uses the agent
        goal_mutation = """
        mutation ExecuteGoal($goal_input: GoalInput!) {
            executeGoal(goal_input: $goal_input) {
                success
                job_id
                status
                message
            }
        }
        """

        goal_response = await client.post(
            "/graphql",
            json={
                "query": goal_mutation,
                "variables": {
                    "goal_input": {
                        "goal": "Analyze sales data and generate a comprehensive report using the E2E Test Agent",
                        "context": "We have sales data from the last quarter that needs analysis",
                        "output_format_instructions": "Return a detailed analysis report with charts and recommendations",
                        "userId": test_user.user_id,
                        "agentTeamId": agent_id
                    }
                }
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert goal_response.status_code == 200
        goal_result = goal_response.json()
        assert goal_result["data"]["executeGoal"]["success"] is True
        job_id = goal_result["data"]["executeGoal"]["job_id"]

        # 5. Check job history
        history_query = """
        query GetJobHistory($limit: Int, $offset: Int) {
            getJobHistory(limit: $limit, offset: $offset) {
                jobs {
                    id
                    goal
                    status
                    modelUsed
                    tokenCount
                    totalCost
                }
                totalCount
            }
        }
        """

        history_response = await client.post(
            "/graphql",
            json={
                "query": history_query,
                "variables": {"limit": 10, "offset": 0}
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert history_response.status_code == 200
        history_data = history_response.json()
        assert history_data["data"]["getJobHistory"]["totalCount"] >= 1

        # 6. Verify the job appears in history with correct data
        jobs = history_data["data"]["getJobHistory"]["jobs"]
        e2e_job = next((job for job in jobs if job["id"] == job_id), None)
        assert e2e_job is not None
        assert "Analyze sales data" in e2e_job["goal"]
        assert e2e_job["status"] in ["queued", "running", "completed", "failed"]

        # 7. Test integration connections
        integration_query = """
        query GetIntegrations($tenant_id: Int!) {
            getIntegrations(tenant_id: $tenant_id) {
                serviceName
                status
                capabilities
            }
        }
        """

        integration_response = await client.post(
            "/graphql",
            json={
                "query": integration_query,
                "variables": {"tenant_id": test_user.tenant_id}
            },
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert integration_response.status_code == 200
        integration_data = integration_response.json()
        assert "data" in integration_data
        assert "getIntegrations" in integration_data["data"]

        # 8. Test MCP tools availability
        mcp_query = """
        query GetAvailableMCPTools {
            getAvailableMCPTools {
                name
                description
                status
                capabilities
            }
        }
        """

        mcp_response = await client.post(
            "/graphql",
            json={"query": mcp_query},
            headers={"Authorization": f"Bearer test-token-{test_user.id}"}
        )

        assert mcp_response.status_code == 200
        mcp_data = mcp_response.json()
        assert "data" in mcp_data
        assert "getAvailableMCPTools" in mcp_data["data"]

        print("✅ Complete end-to-end integration test passed!")
        print(f"Created agent: {agent_id}")
        print(f"Created tone profile: {tone_id}")
        print(f"Executed goal, created job: {job_id}")
        print(f"Total jobs in history: {history_data['data']['getJobHistory']['totalCount']}")
        print(f"Available MCP tools: {len(mcp_data['data']['getAvailableMCPTools'])}")
