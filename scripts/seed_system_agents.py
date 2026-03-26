#!/usr/bin/env python3
"""
Idempotent seeding script for system agents and teams.
Run after migrations. Safe to run multiple times.

NOTE: This script now only handles basic system setup.
Agent teams and agents are created by the migration script.
"""

import json
from datetime import datetime
import sys
from pathlib import Path

# Ensure project root is on sys.path when executed directly from scripts/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.db import session_scope
from src.database.models import CustomAgentDefinition, AgentTeam


def main():
    """Main seeding function."""
    print("=" * 60)
    print("SYSTEM AGENTS SEEDING SCRIPT")
    print("=" * 60)
    print()
    
    # Basic system setup
    platform_tenant_id = 0  # System tenant
    
    print(f"Setting up system tenant: {platform_tenant_id}")
    
    # Create basic system agents if they don't exist
    with session_scope() as session:
        # Check if we have any system agents
        existing_agents = session.query(CustomAgentDefinition).filter(
            CustomAgentDefinition.tenant_id == platform_tenant_id,
            CustomAgentDefinition.is_system_agent == True
        ).count()
        
        if existing_agents == 0:
            print("No system agents found. Run the migration script first:")
            print("python scripts/migrate_agents_to_database.py")
        else:
            print(f"Found {existing_agents} system agents in database")
        
        # Check if we have any system teams
        existing_teams = session.query(AgentTeam).filter(
            AgentTeam.tenant_id == platform_tenant_id,
            AgentTeam.is_system_team == True
        ).count()
        
        if existing_teams == 0:
            print("No system teams found. Run the migration script first:")
            print("python scripts/migrate_agents_to_database.py")
        else:
            print(f"Found {existing_teams} system teams in database")
    
    print()
    print("=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print("1. Run agent migration: python scripts/migrate_agents_to_database.py")
    print("2. Verify migration: Check database for agents and teams")
    print("3. Test orchestrator: Ensure agents load from database")
    print("4. Remove old system: Delete src/agents directory")
    print("=" * 60)


if __name__ == "__main__":
    main()