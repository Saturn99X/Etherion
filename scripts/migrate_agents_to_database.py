#!/usr/bin/env python3
"""
Agent Migration Script: Migrates all agents from src/agents/ directories to database.

This script:
1. Scans all agent directories
2. Extracts agent metadata
3. Creates AgentTeam records for each directory
4. Creates CustomAgentDefinition records for each agent
5. Links agents to their teams
6. Sets is_system_agent=True for all migrated agents

Usage:
    python scripts/migrate_agents_to_database.py
"""

import os
import sys
import ast
import importlib.util
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.db import session_scope
from src.database.models import CustomAgentDefinition, AgentTeam

logger = logging.getLogger(__name__)

class AgentMigrator:
    """Handles migration of agents from directories to database."""
    
    def __init__(self):
        self.agents_dir = PROJECT_ROOT / "src" / "agents"
        self.migrated_teams = {}
        self.migrated_agents = {}
        
    def scan_agent_directories(self) -> Dict[str, List[str]]:
        """Scan agent directories and return team -> agents mapping."""
        teams = {}
        
        for team_dir in self.agents_dir.iterdir():
            if team_dir.is_dir() and not team_dir.name.startswith('__'):
                team_name = team_dir.name
                agents = []
                
                for agent_file in team_dir.glob("*.py"):
                    if not agent_file.name.startswith('__'):
                        agents.append(agent_file.stem)
                
                if agents:
                    teams[team_name] = agents
                    
        return teams
    
    def extract_agent_metadata(self, team_name: str, agent_name: str) -> Optional[Dict[str, Any]]:
        """Extract metadata from agent file."""
        agent_file = self.agents_dir / team_name / f"{agent_name}.py"
        
        if not agent_file.exists():
            return None
            
        try:
            # Read the file content
            with open(agent_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse the AST
            tree = ast.parse(content)
            
            # Extract metadata
            metadata = {
                'name': agent_name,
                'team_name': team_name,
                'file_path': str(agent_file.relative_to(PROJECT_ROOT)),
                'system_prompt': '',
                'description': '',
                'tools': [],
                'model_name': 'gemini-2.5-flash',
                'version': '1.0.0'
            }
            
            # Find the create function
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith('create_'):
                    # Extract system prompt from docstring or comments
                    if node.body and isinstance(node.body[0], ast.Expr):
                        if isinstance(node.body[0].value, ast.Constant):
                            docstring = node.body[0].value.value
                            if docstring:
                                metadata['description'] = docstring.split('\n')[0].strip()
                    
                    # Look for system prompt variable
                    for stmt in node.body:
                        if isinstance(stmt, ast.Assign):
                            for target in stmt.targets:
                                if isinstance(target, ast.Name) and 'SYSTEM_PROMPT' in target.id:
                                    if isinstance(stmt.value, ast.Constant):
                                        metadata['system_prompt'] = stmt.value.value
                                    break
                    
                    # Look for tools list
                    for stmt in node.body:
                        if isinstance(stmt, ast.Assign):
                            for target in stmt.targets:
                                if isinstance(target, ast.Name) and 'tools' in target.id.lower():
                                    if isinstance(stmt.value, ast.List):
                                        tools = []
                                        for elt in stmt.value.elts:
                                            if isinstance(elt, ast.Name):
                                                tools.append(elt.id)
                                        metadata['tools'] = tools
                                    break
                    
                    break
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to extract metadata from {agent_file}: {e}")
            return None
    
    def create_agent_team(self, session, team_name: str, agents: List[str]) -> AgentTeam:
        """Create or update AgentTeam record."""
        # Check if team already exists
        existing_team = session.query(AgentTeam).filter(
            AgentTeam.team_name == team_name,
            AgentTeam.tenant_id == 0,  # System teams are in tenant 0
            AgentTeam.is_system_team == True
        ).first()
        
        if existing_team:
            return existing_team
        
        # Create new team
        team = AgentTeam(
            team_name=team_name,
            team_description=f"System {team_name} team with {len(agents)} agents",
            tenant_id=0,  # System teams
            is_system_team=True,
            is_active=True,
            is_latest_version=True,
            version="1.0.0",
            created_by="system_migration",
            team_metadata={
                'migration_date': datetime.utcnow().isoformat(),
                'agent_count': len(agents),
                'source': 'directory_migration'
            }
        )
        
        session.add(team)
        session.flush()  # Get the ID
        
        logger.info(f"Created team: {team_name} with {len(agents)} agents")
        return team
    
    def create_agent_definition(self, session, metadata: Dict[str, Any], team: AgentTeam) -> CustomAgentDefinition:
        """Create CustomAgentDefinition record."""
        # Check if agent already exists
        existing_agent = session.query(CustomAgentDefinition).filter(
            CustomAgentDefinition.name == metadata['name'],
            CustomAgentDefinition.tenant_id == 0,
            CustomAgentDefinition.is_system_agent == True
        ).first()
        
        if existing_agent:
            return existing_agent
        
        # Create new agent
        agent = CustomAgentDefinition(
            name=metadata['name'],
            description=metadata['description'],
            system_prompt=metadata['system_prompt'],
            model_name=metadata['model_name'],
            tenant_id=0,  # System agents
            is_system_agent=True,
            is_active=True,
            is_latest_version=True,
            version=metadata['version'],
            created_by="system_migration",
            agent_metadata={
                'team_name': metadata['team_name'],
                'file_path': metadata['file_path'],
                'migration_date': datetime.utcnow().isoformat(),
                'source': 'directory_migration'
            }
        )
        
        # Set tools
        if metadata['tools']:
            agent.set_tool_names(metadata['tools'])
        
        session.add(agent)
        session.flush()  # Get the ID
        
        logger.info(f"Created agent: {metadata['name']} in team {metadata['team_name']}")
        return agent
    
    def migrate_all_agents(self):
        """Migrate all agents to database."""
        logger.info("Starting agent migration...")
        
        # Scan directories
        teams = self.scan_agent_directories()
        logger.info(f"Found {len(teams)} teams with agents")
        
        with session_scope() as session:
            for team_name, agents in teams.items():
                logger.info(f"Processing team: {team_name} with {len(agents)} agents")
                
                # Create team
                team = self.create_agent_team(session, team_name, agents)
                self.migrated_teams[team_name] = team
                
                # Create agents
                for agent_name in agents:
                    metadata = self.extract_agent_metadata(team_name, agent_name)
                    if metadata:
                        agent = self.create_agent_definition(session, metadata, team)
                        self.migrated_agents[agent_name] = agent
                    else:
                        logger.warning(f"Failed to extract metadata for {agent_name}")
                
                session.commit()
                logger.info(f"Completed team: {team_name}")
        
        logger.info(f"Migration complete! Migrated {len(self.migrated_teams)} teams and {len(self.migrated_agents)} agents")
        
        # Print summary
        print("\n" + "="*50)
        print("MIGRATION SUMMARY")
        print("="*50)
        print(f"Teams migrated: {len(self.migrated_teams)}")
        for team_name in self.migrated_teams.keys():
            print(f"  - {team_name}")
        
        print(f"\nAgents migrated: {len(self.migrated_agents)}")
        for agent_name in self.migrated_agents.keys():
            print(f"  - {agent_name}")
        
        print("\nNext steps:")
        print("1. Update orchestrator to use database loading")
        print("2. Update tests to use database agents")
        print("3. Remove src/agents directory")
        print("4. Run comprehensive tests")

def main():
    """Main migration function."""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    migrator = AgentMigrator()
    migrator.migrate_all_agents()

if __name__ == "__main__":
    main()



