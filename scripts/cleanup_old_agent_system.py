#!/usr/bin/env python3
"""
Cleanup script to remove old agent system after successful migration.

This script:
1. Verifies migration was successful
2. Removes src/agents directory
3. Cleans up any remaining references
4. Runs verification tests

Usage:
    python scripts/cleanup_old_agent_system.py
"""

import os
import sys
import shutil
from pathlib import Path
from typing import List

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.db import session_scope
from src.database.models import CustomAgentDefinition, AgentTeam
from src.services.agent_loader import get_agent_loader

logger = logging.getLogger(__name__)

class AgentSystemCleanup:
    """Handles cleanup of old agent system."""
    
    def __init__(self):
        self.project_root = PROJECT_ROOT
        self.agents_dir = self.project_root / "src" / "agents"
        
    def verify_migration_success(self) -> bool:
        """Verify that migration was successful."""
        print("Verifying migration success...")
        
        try:
            with session_scope() as session:
                # Check for system teams
                teams = session.query(AgentTeam).filter(
                    AgentTeam.tenant_id == 0,
                    AgentTeam.is_system_team == True,
                    AgentTeam.is_active == True
                ).count()
                
                # Check for system agents
                agents = session.query(CustomAgentDefinition).filter(
                    CustomAgentDefinition.tenant_id == 0,
                    CustomAgentDefinition.is_system_agent == True,
                    CustomAgentDefinition.is_active == True
                ).count()
                
                print(f"Found {teams} system teams and {agents} system agents in database")
                
                if teams == 0 or agents == 0:
                    print("❌ Migration verification failed: No teams or agents found")
                    return False
                
                # Test agent loader
                agent_loader = get_agent_loader()
                system_agents = agent_loader.load_all_system_agents()
                
                if not system_agents:
                    print("❌ Migration verification failed: Agent loader returned no agents")
                    return False
                
                print(f"✅ Migration verification successful: {len(system_agents)} teams loaded")
                return True
                
        except Exception as e:
            print(f"❌ Migration verification failed: {e}")
            return False
    
    def find_remaining_references(self) -> List[str]:
        """Find remaining references to old agent system."""
        print("Scanning for remaining references to old agent system...")
        
        references = []
        
        # Search for imports
        for py_file in self.project_root.rglob("*.py"):
            if "src/agents" in str(py_file):
                continue  # Skip files in src/agents itself
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                if "from src.agents" in content or "import src.agents" in content:
                    references.append(str(py_file.relative_to(self.project_root)))
                    
            except Exception:
                continue
        
        return references
    
    def backup_agents_directory(self):
        """Create backup of agents directory before deletion."""
        if not self.agents_dir.exists():
            print("No agents directory to backup")
            return
        
        backup_dir = self.project_root / "backup_agents_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"Creating backup at: {backup_dir}")
        
        try:
            shutil.copytree(self.agents_dir, backup_dir)
            print(f"✅ Backup created successfully")
        except Exception as e:
            print(f"❌ Failed to create backup: {e}")
            raise
    
    def remove_agents_directory(self):
        """Remove the src/agents directory."""
        if not self.agents_dir.exists():
            print("No agents directory to remove")
            return
        
        print(f"Removing agents directory: {self.agents_dir}")
        
        try:
            shutil.rmtree(self.agents_dir)
            print("✅ Agents directory removed successfully")
        except Exception as e:
            print(f"❌ Failed to remove agents directory: {e}")
            raise
    
    def run_verification_tests(self) -> bool:
        """Run verification tests to ensure system still works."""
        print("Running verification tests...")
        
        try:
            # Test agent loader
            agent_loader = get_agent_loader()
            system_agents = agent_loader.load_all_system_agents()
            
            if not system_agents:
                print("❌ Verification failed: No system agents loaded")
                return False
            
            # Test creating a few agent executors
            test_count = 0
            for team_name, team_agents in system_agents.items():
                for agent_config in team_agents[:1]:  # Test one agent per team
                    try:
                        executor = agent_loader.create_agent_executor(
                            agent_config, 
                            tenant_id=0, 
                            job_id="cleanup_verification"
                        )
                        if executor:
                            test_count += 1
                    except Exception as e:
                        print(f"Warning: Failed to create executor for {agent_config['name']}: {e}")
                
                if test_count >= 3:  # Test at least 3 agents
                    break
            
            if test_count == 0:
                print("❌ Verification failed: No agent executors could be created")
                return False
            
            print(f"✅ Verification successful: {test_count} agent executors created")
            return True
            
        except Exception as e:
            print(f"❌ Verification failed: {e}")
            return False
    
    def cleanup(self):
        """Perform complete cleanup."""
        print("=" * 60)
        print("AGENT SYSTEM CLEANUP")
        print("=" * 60)
        
        # Step 1: Verify migration
        if not self.verify_migration_success():
            print("❌ Cannot proceed with cleanup: Migration verification failed")
            return False
        
        # Step 2: Check for remaining references
        references = self.find_remaining_references()
        if references:
            print("⚠️  Found remaining references to old agent system:")
            for ref in references:
                print(f"  - {ref}")
            print("Please update these files before proceeding with cleanup.")
            return False
        
        # Step 3: Create backup
        self.backup_agents_directory()
        
        # Step 4: Remove agents directory
        self.remove_agents_directory()
        
        # Step 5: Run verification tests
        if not self.run_verification_tests():
            print("❌ Cleanup verification failed. Please restore from backup if needed.")
            return False
        
        print("=" * 60)
        print("✅ CLEANUP COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print("The old agent system has been removed and the new database-driven")
        print("system is working correctly.")
        print()
        print("Next steps:")
        print("1. Run full test suite to ensure everything works")
        print("2. Update documentation if needed")
        print("3. Commit changes to version control")
        
        return True

def main():
    """Main cleanup function."""
    import logging
    from datetime import datetime
    logging.basicConfig(level=logging.INFO)
    
    cleanup = AgentSystemCleanup()
    success = cleanup.cleanup()
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()



