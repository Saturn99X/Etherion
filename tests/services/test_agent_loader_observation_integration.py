import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json

from src.services.agent_loader import AgentLoader
from src.services.user_observation_service import UserObservationService
from src.database.models import UserObservation, CustomAgentDefinition, AgentTeam
from tests.conftest import TestDatabaseSession


class TestAgentLoaderObservationIntegration:
    """Test suite for AgentLoader observation integration"""

    @pytest.fixture
    def db_session(self):
        """Provide a test database session"""
        with TestDatabaseSession() as session:
            yield session

    @pytest.fixture
    def agent_loader(self):
        """Provide an AgentLoader instance"""
        return AgentLoader()

    @pytest.fixture
    def observation_service(self):
        """Provide a UserObservationService instance"""
        return UserObservationService()

    @pytest.fixture
    def sample_user(self, db_session):
        """Create a sample user"""
        from src.database.models import User, Tenant

        tenant = Tenant(
            id=1,
            name="Test Tenant",
            domain="test.com",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(tenant)
        db_session.commit()

        user = User(
            user_id="test_user_123",
            email="test@example.com",
            name="Test User",
            provider="test",
            tenant_id=1,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    @pytest.fixture
    def sample_agent_team(self, db_session, sample_user):
        """Create a sample agent team"""
        team = AgentTeam(
            agent_team_id="test_team_123",
            tenant_id=1,
            name="Test Team",
            description="A test team",
            version=1,
            is_active=True,
            is_latest_version=True,
            is_system_agent=False
        )
        db_session.add(team)
        db_session.commit()
        db_session.refresh(team)
        return team

    @pytest.fixture
    def sample_custom_agent(self, db_session, sample_agent_team):
        """Create a sample custom agent"""
        agent = CustomAgentDefinition(
            custom_agent_id="test_agent_123",
            tenant_id=1,
            name="Test Agent",
            description="A test agent",
            system_prompt="You are a helpful assistant.",
            model_name="gemini-2.5-pro",
            version=1,
            is_active=True,
            is_latest_version=True,
            is_system_agent=False,
            max_iterations=10,
            timeout_seconds=300,
            temperature=0.7
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)
        return agent

    def test_load_user_context_with_observations(self, agent_loader, sample_user, db_session):
        """Test loading user context when observations exist"""
        # Create user observations first
        observation = UserObservation(
            user_id=sample_user.id,
            tenant_id=1,
            preferred_tone="formal",
            response_length_preference="detailed",
            technical_level="expert",
            formality_level="high",
            successful_tools=json.dumps(["api_tool", "analysis_tool"]),
            successful_approaches=json.dumps(["systematic", "analytical"]),
            observation_count=5,
            confidence_score=0.8,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(observation)
        db_session.commit()

        # Load user context
        context = agent_loader.load_user_context(sample_user.id, 1)

        assert isinstance(context, str)
        assert len(context) > 0
        assert "formal" in context.lower()
        assert "detailed" in context.lower()
        assert "expert" in context.lower()

    def test_load_user_context_without_observations(self, agent_loader, sample_user):
        """Test loading user context when no observations exist"""
        context = agent_loader.load_user_context(sample_user.id, 1)

        # Should return empty string when no observations
        assert context == ""

    def test_load_user_context_with_invalid_user(self, agent_loader):
        """Test loading user context with invalid user ID"""
        context = agent_loader.load_user_context(999999, 1)

        # Should return empty string for invalid user
        assert context == ""

    def test_load_agent_team_with_user_context(self, agent_loader, sample_user, sample_agent_team, sample_custom_agent, db_session):
        """Test loading agent team includes user context"""
        # Set up agent team with custom agent
        sample_agent_team.set_custom_agent_ids([sample_custom_agent.custom_agent_id])
        sample_agent_team.set_pre_approved_tool_names(["test_tool"])
        db_session.commit()

        # Create user observations
        observation = UserObservation(
            user_id=sample_user.id,
            tenant_id=1,
            preferred_tone="casual",
            response_length_preference="concise",
            technical_level="intermediate",
            formality_level="medium",
            successful_tools=json.dumps(["user_tool"]),
            successful_approaches=json.dumps(["quick_solution"]),
            observation_count=3,
            confidence_score=0.6,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(observation)
        db_session.commit()

        # Load agent team with user context
        team_config = agent_loader.load_agent_team(
            sample_agent_team.agent_team_id,
            1,
            "test_job_123",
            user_id=sample_user.id
        )

        assert team_config is not None
        assert team_config['team_id'] == sample_agent_team.agent_team_id

        # Check that custom agents include user context in system prompt
        custom_agents = team_config.get('custom_agents', [])
        assert len(custom_agents) > 0

        for agent in custom_agents:
            system_prompt = agent.get('system_prompt', '')
            assert isinstance(system_prompt, str)

            # User context should be appended to system prompt
            assert "casual" in system_prompt.lower() or "concise" in system_prompt.lower()

    def test_load_agent_team_without_user_context(self, agent_loader, sample_agent_team, sample_custom_agent, db_session):
        """Test loading agent team without user context"""
        # Set up agent team with custom agent
        sample_agent_team.set_custom_agent_ids([sample_custom_agent.custom_agent_id])
        db_session.commit()

        # Load agent team without user context
        team_config = agent_loader.load_agent_team(
            sample_agent_team.agent_team_id,
            1,
            "test_job_123",
            user_id=None
        )

        assert team_config is not None
        assert team_config['team_id'] == sample_agent_team.agent_team_id

        # Check that custom agents don't have user context
        custom_agents = team_config.get('custom_agents', [])
        assert len(custom_agents) > 0

        for agent in custom_agents:
            system_prompt = agent.get('system_prompt', '')
            assert isinstance(system_prompt, str)
            # Should not have user personalization context
            assert "USER PERSONALIZATION CONTEXT" not in system_prompt

    def test_load_custom_agent_with_user_context(self, agent_loader, sample_user, sample_custom_agent, db_session):
        """Test loading custom agent with user context enhancement"""
        # Create user observations
        observation = UserObservation(
            user_id=sample_user.id,
            tenant_id=1,
            preferred_tone="friendly",
            response_length_preference="comprehensive",
            technical_level="beginner",
            formality_level="low",
            successful_tools=json.dumps(["friendly_tool"]),
            successful_approaches=json.dumps(["friendly_approach"]),
            observation_count=2,
            confidence_score=0.4,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(observation)
        db_session.commit()

        with TestDatabaseSession() as session:
            # Load custom agent with user context
            agent_config = agent_loader._load_custom_agent(
                session, sample_custom_agent.custom_agent_id, 1, sample_user.id
            )

            assert agent_config is not None
            assert agent_config['agent_id'] == sample_custom_agent.custom_agent_id

            system_prompt = agent_config['system_prompt']
            assert isinstance(system_prompt, str)
            assert len(system_prompt) > 0

            # Should include user context
            assert "friendly" in system_prompt.lower()
            assert "comprehensive" in system_prompt.lower()

    def test_load_custom_agent_without_user_context(self, agent_loader, sample_custom_agent):
        """Test loading custom agent without user context enhancement"""
        with TestDatabaseSession() as session:
            # Load custom agent without user context
            agent_config = agent_loader._load_custom_agent(
                session, sample_custom_agent.custom_agent_id, 1, None
            )

            assert agent_config is not None
            assert agent_config['agent_id'] == sample_custom_agent.custom_agent_id

            system_prompt = agent_config['system_prompt']
            assert isinstance(system_prompt, str)
            assert len(system_prompt) > 0

            # Should not include user context
            assert "USER PERSONALIZATION CONTEXT" not in system_prompt

    def test_load_system_agents_with_user_context(self, agent_loader, sample_user, db_session):
        """Test loading system agents with user context"""
        # Create system agent
        system_agent = CustomAgentDefinition(
            custom_agent_id="system_agent_123",
            tenant_id=0,  # System tenant
            name="System Agent",
            description="A system agent",
            system_prompt="You are a system assistant.",
            model_name="gemini-2.5-pro",
            version=1,
            is_active=True,
            is_latest_version=True,
            is_system_agent=True,
            max_iterations=10,
            timeout_seconds=300,
            temperature=0.7
        )
        db_session.add(system_agent)

        # Create user observations
        observation = UserObservation(
            user_id=sample_user.id,
            tenant_id=1,
            preferred_tone="professional",
            response_length_preference="balanced",
            technical_level="intermediate",
            formality_level="medium",
            successful_tools=json.dumps(["system_tool"]),
            successful_approaches=json.dumps(["professional_approach"]),
            observation_count=4,
            confidence_score=0.7,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(observation)
        db_session.commit()

        # Load system agents with user context
        system_agents = agent_loader.load_system_agents(tenant_id=1, user_id=sample_user.id)

        assert isinstance(system_agents, list)
        assert len(system_agents) > 0

        # Check that system agents include user context
        for agent in system_agents:
            system_prompt = agent.get('system_prompt', '')
            assert isinstance(system_prompt, str)

            # Should include user context
            assert "professional" in system_prompt.lower() or "balanced" in system_prompt.lower()

    def test_load_system_agents_without_user_context(self, agent_loader, db_session):
        """Test loading system agents without user context"""
        # Create system agent
        system_agent = CustomAgentDefinition(
            custom_agent_id="system_agent_456",
            tenant_id=0,  # System tenant
            name="System Agent 2",
            description="Another system agent",
            system_prompt="You are another system assistant.",
            model_name="gemini-2.5-pro",
            version=1,
            is_active=True,
            is_latest_version=True,
            is_system_agent=True,
            max_iterations=10,
            timeout_seconds=300,
            temperature=0.7
        )
        db_session.add(system_agent)
        db_session.commit()

        # Load system agents without user context
        system_agents = agent_loader.load_system_agents(tenant_id=1, user_id=None)

        assert isinstance(system_agents, list)
        assert len(system_agents) > 0

        # Check that system agents don't have user context
        for agent in system_agents:
            system_prompt = agent.get('system_prompt', '')
            assert isinstance(system_prompt, str)
            assert "USER PERSONALIZATION CONTEXT" not in system_prompt

    def test_user_context_generation_error_handling(self, agent_loader, sample_user):
        """Test error handling in user context generation"""
        with patch.object(agent_loader.observation_service, 'generate_system_instructions',
                         side_effect=Exception("Database error")):
            # Should handle error gracefully
            context = agent_loader.load_user_context(sample_user.id, 1)
            assert context == ""

    def test_agent_enhancement_error_handling(self, agent_loader, sample_user, sample_custom_agent):
        """Test error handling in agent enhancement"""
        with patch.object(agent_loader.observation_service, 'generate_system_instructions',
                         side_effect=Exception("Service unavailable")):
            with TestDatabaseSession() as session:
                # Should handle error gracefully and return basic agent config
                agent_config = agent_loader._load_custom_agent(
                    session, sample_custom_agent.custom_agent_id, 1, sample_user.id
                )

                assert agent_config is not None
                assert agent_config['agent_id'] == sample_custom_agent.custom_agent_id
                # Should still have original system prompt
                assert sample_custom_agent.system_prompt in agent_config['system_prompt']

    def test_performance_impact_assessment(self, agent_loader, sample_user, sample_custom_agent):
        """Test that user context loading doesn't significantly impact performance"""
        import time

        # Create comprehensive user observations
        observation = UserObservation(
            user_id=sample_user.id,
            tenant_id=1,
            preferred_tone="technical",
            response_length_preference="comprehensive",
            technical_level="expert",
            formality_level="high",
            successful_tools=json.dumps(["tool1", "tool2", "tool3", "tool4", "tool5"]),
            successful_approaches=json.dumps(["approach1", "approach2", "approach3"]),
            failed_approaches=json.dumps(["bad_approach1", "bad_approach2"]),
            complexity_level="complex",
            example_requirements="extensive",
            visual_vs_text="balanced",
            observation_count=10,
            confidence_score=0.9,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        with TestDatabaseSession() as session:
            session.add(observation)
            session.commit()

            # Time the agent loading with user context
            start_time = time.time()
            agent_config = agent_loader._load_custom_agent(
                session, sample_custom_agent.custom_agent_id, 1, sample_user.id
            )
            end_time = time.time()

            # Should complete in reasonable time (< 100ms)
            duration = (end_time - start_time) * 1000
            assert duration < 100, f"Agent loading took {duration:.2f}ms, should be < 100ms"

            assert agent_config is not None
            system_prompt = agent_config['system_prompt']
            assert len(system_prompt) > len(sample_custom_agent.system_prompt)  # Should be enhanced
