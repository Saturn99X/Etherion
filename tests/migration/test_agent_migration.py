#!/usr/bin/env python3
"""
Test suite for agent migration from directories to database.
"""

import pytest
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.db import session_scope
from src.database.models import CustomAgentDefinition, AgentTeam
from src.services.agent_loader import get_agent_loader


class TestAgentMigration:
    """Test agent migration functionality."""
    
    def test_agent_teams_created(self):
        """Test that agent teams are created in database."""
        with session_scope() as session:
            teams = session.query(AgentTeam).filter(
                AgentTeam.tenant_id == 0,
                AgentTeam.is_system_team == True,
                AgentTeam.is_active == True
            ).all()
            
            assert len(teams) > 0, "No system teams found in database"
            
            # Check for expected teams
            team_names = [team.team_name for team in teams]
            expected_teams = ['Sales', 'Marketing', 'Support', 'Content', 'Analytics']
            
            for expected_team in expected_teams:
                assert expected_team in team_names, f"Expected team {expected_team} not found"
    
    def test_agents_created(self):
        """Test that agents are created in database."""
        with session_scope() as session:
            agents = session.query(CustomAgentDefinition).filter(
                CustomAgentDefinition.tenant_id == 0,
                CustomAgentDefinition.is_system_agent == True,
                CustomAgentDefinition.is_active == True
            ).all()
            
            assert len(agents) > 0, "No system agents found in database"
            
            # Check that agents have proper metadata
            for agent in agents:
                assert agent.name, f"Agent {agent.custom_agent_id} has no name"
                assert agent.description, f"Agent {agent.name} has no description"
                assert agent.system_prompt, f"Agent {agent.name} has no system prompt"
                assert agent.agent_metadata, f"Agent {agent.name} has no metadata"
                assert 'team_name' in agent.agent_metadata, f"Agent {agent.name} has no team_name in metadata"
    
    def test_agent_loader_functions(self):
        """Test that agent loader functions work correctly."""
        agent_loader = get_agent_loader()
        
        # Test load_all_system_agents
        system_agents = agent_loader.load_all_system_agents()
        assert isinstance(system_agents, dict), "load_all_system_agents should return dict"
        assert len(system_agents) > 0, "No system agents loaded"
        
        # Test load_agents_by_team
        for team_name in system_agents.keys():
            team_agents = agent_loader.load_agents_by_team(team_name)
            assert isinstance(team_agents, list), f"load_agents_by_team should return list for {team_name}"
            assert len(team_agents) > 0, f"No agents found for team {team_name}"
            
            # Check agent structure
            for agent_config in team_agents:
                assert 'name' in agent_config, f"Agent config missing name in team {team_name}"
                assert 'description' in agent_config, f"Agent config missing description in team {team_name}"
                assert 'agent_id' in agent_config, f"Agent config missing agent_id in team {team_name}"
        
        # Test get_agent_teams_hierarchy
        hierarchy = agent_loader.get_agent_teams_hierarchy()
        assert isinstance(hierarchy, dict), "get_agent_teams_hierarchy should return dict"
        assert len(hierarchy) > 0, "No teams in hierarchy"
        
        for team_name, team_info in hierarchy.items():
            assert 'team_id' in team_info, f"Team {team_name} missing team_id"
            assert 'description' in team_info, f"Team {team_name} missing description"
            assert 'agent_count' in team_info, f"Team {team_name} missing agent_count"
            assert 'agents' in team_info, f"Team {team_name} missing agents list"
    
    def test_agent_executor_creation(self):
        """Test that agent executors can be created."""
        agent_loader = get_agent_loader()
        system_agents = agent_loader.load_all_system_agents()
        
        # Test creating executors for a few agents
        test_count = 0
        for team_name, team_agents in system_agents.items():
            for agent_config in team_agents[:2]:  # Test first 2 agents per team
                try:
                    executor = agent_loader.create_agent_executor(
                        agent_config, 
                        tenant_id=0, 
                        job_id="test_migration"
                    )
                    assert executor is not None, f"Failed to create executor for {agent_config['name']}"
                    test_count += 1
                    
                    if test_count >= 5:  # Limit to 5 tests
                        break
                except Exception as e:
                    pytest.fail(f"Failed to create executor for {agent_config['name']}: {e}")
            
            if test_count >= 5:
                break
        
        assert test_count > 0, "No agent executors could be created"
    
    def test_team_agent_relationships(self):
        """Test that team-agent relationships are correct."""
        with session_scope() as session:
            teams = session.query(AgentTeam).filter(
                AgentTeam.tenant_id == 0,
                AgentTeam.is_system_team == True
            ).all()
            
            for team in teams:
                # Get agents for this team
                agents = session.query(CustomAgentDefinition).filter(
                    CustomAgentDefinition.tenant_id == 0,
                    CustomAgentDefinition.is_system_agent == True,
                    CustomAgentDefinition.agent_metadata['team_name'].astext == team.team_name
                ).all()
                
                assert len(agents) > 0, f"Team {team.team_name} has no agents"
                
                # Check that all agents have correct team_name in metadata
                for agent in agents:
                    assert agent.agent_metadata['team_name'] == team.team_name, \
                        f"Agent {agent.name} has wrong team_name in metadata"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



