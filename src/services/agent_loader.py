"""
Database-driven agent loading service.
Replaces hardcoded agent registry with dynamic database loading.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from src.database.db import session_scope
from src.database.models import CustomAgentDefinition, AgentTeam
from src.services.user_observation_service import UserObservationService, get_user_observation_service
from src.tools.tool_manager import get_tool_manager

logger = logging.getLogger(__name__)


class AgentLoader:
    """Service for loading agents and teams from the database with user observation integration."""

    def __init__(self):
        self.tool_manager = get_tool_manager()
        self.observation_service = get_user_observation_service()

    async def load_user_context(self, user_id: int, tenant_id: int) -> str:
        """
        Load user observation context for agent execution.

        Args:
            user_id: User ID for personalization
            tenant_id: Tenant ID for security

        Returns:
            User context string for system instructions
        """
        if not user_id:
            return ""

        try:
            user_context = await self.observation_service.generate_system_instructions(user_id, tenant_id)
            if user_context:
                return f"\n**USER PERSONALIZATION CONTEXT:**\n{user_context}"
            return ""
        except Exception as e:
            logger.warning(f"Failed to load user context for user {user_id}: {e}")
            return ""

    async def load_agent_team(self, agent_team_id: str, tenant_id: int, job_id: str, user_id: int = None) -> Optional[Dict[str, Any]]:
        """
        Load an agent team from the database with all its agents and tools.
        
        Args:
            agent_team_id: ID of the agent team to load
            tenant_id: Tenant ID for security
            job_id: Job ID for tracing
            
        Returns:
            Dict with team configuration and loaded agents, or None if not found
        """
        try:
            with session_scope() as session:
                # Load the agent team
                agent_team = session.query(AgentTeam).filter(
                    AgentTeam.agent_team_id == agent_team_id,
                    AgentTeam.tenant_id == tenant_id,
                    AgentTeam.is_active == True,
                    AgentTeam.is_latest_version == True
                ).first()
                
                if not agent_team:
                    logger.error(f"Agent team not found or inactive: {agent_team_id}")
                    return None
                
                # Load user context for personalization (async)
                user_context = await self.load_user_context(user_id, tenant_id) if user_id else ""

                # Load all custom agents in the team
                custom_agents = []
                for custom_agent_id in agent_team.get_custom_agent_ids():
                    agent = await self._load_custom_agent(session, custom_agent_id, tenant_id, user_id)
                    if agent:
                        # Add user context to agent system prompt
                        if agent['system_prompt'] and user_context:
                            agent['system_prompt'] += user_context
                        custom_agents.append(agent)
                
                # Load pre-approved tools
                pre_approved_tools = []
                for tool_name in agent_team.get_pre_approved_tool_names():
                    try:
                        tool_instance = self.tool_manager.get_tool_instance(
                            tool_name=tool_name,
                            tenant_id=tenant_id,
                            job_id=job_id
                        )
                        pre_approved_tools.append({
                            'name': tool_name,
                            'instance': tool_instance,
                            'type': 'standard_tool'
                        })
                    except Exception as e:
                        logger.error(f"Failed to load pre-approved tool {tool_name}: {e}")
                        continue
                
                # Build team configuration
                team_config = {
                    'team_id': agent_team.agent_team_id,
                    'name': agent_team.name,
                    'description': agent_team.description,
                    'version': agent_team.version,
                    'is_system_agent': agent_team.is_system_agent,
                    'custom_agents': custom_agents,
                    'pre_approved_tools': pre_approved_tools,
                    'max_concurrent_executions': agent_team.max_concurrent_executions,
                    'default_timeout_seconds': agent_team.default_timeout_seconds,
                    'team_metadata': agent_team.get_team_metadata()
                }
                
                logger.info(f"Loaded agent team '{agent_team.name}' with {len(custom_agents)} agents and {len(pre_approved_tools)} tools")
                return team_config
                
        except Exception as e:
            logger.error(f"Failed to load agent team {agent_team_id}: {e}")
            return None
    
    async def _load_custom_agent(self, session: Session, custom_agent_id: str, tenant_id: int, user_id: int = None) -> Optional[Dict[str, Any]]:
        """
        Load a custom agent from the database.
        
        Args:
            session: Database session
            custom_agent_id: ID of the custom agent
            tenant_id: Tenant ID for security
            
        Returns:
            Dict with agent configuration, or None if not found
        """
        try:
            agent = session.query(CustomAgentDefinition).filter(
                CustomAgentDefinition.custom_agent_id == custom_agent_id,
                CustomAgentDefinition.tenant_id == tenant_id,
                CustomAgentDefinition.is_active == True,
                CustomAgentDefinition.is_latest_version == True
            ).first()
            
            if not agent:
                logger.error(f"Custom agent not found or inactive: {custom_agent_id}")
                return None
            
            # Enhance system prompt with user context if provided
            enhanced_system_prompt = agent.system_prompt
            if user_id:
                user_context = await self.load_user_context(user_id, tenant_id)
                if user_context:
                    enhanced_system_prompt = f"{agent.system_prompt}\n{user_context}"

            # Create agent configuration
            agent_config = {
                'agent_id': agent.custom_agent_id,
                'name': agent.name,
                'description': agent.description,
                'system_prompt': enhanced_system_prompt,
                'tool_names': agent.get_tool_names(),
                'model_name': agent.model_name,
                'version': agent.version,
                'is_system_agent': agent.is_system_agent,
                'max_iterations': agent.max_iterations,
                'timeout_seconds': agent.timeout_seconds,
                'temperature': agent.temperature,
                'custom_metadata': agent.get_custom_metadata()
            }
            
            return agent_config
            
        except Exception as e:
            logger.error(f"Failed to load custom agent {custom_agent_id}: {e}")
            return None
    
    async def load_system_agents(self, tenant_id: int = 0, user_id: int = None) -> List[Dict[str, Any]]:
        """
        Load all system agents for a tenant.
        
        Args:
            tenant_id: Tenant ID (default 0 for platform tenant)
            
        Returns:
            List of system agent configurations
        """
        try:
            with session_scope() as session:
                system_agents = session.query(CustomAgentDefinition).filter(
                    CustomAgentDefinition.tenant_id == tenant_id,
                    CustomAgentDefinition.is_system_agent == True,
                    CustomAgentDefinition.is_active == True,
                    CustomAgentDefinition.is_latest_version == True
                ).all()
                
                agents = []
                for agent in system_agents:
                    agent_config = await self._load_custom_agent(session, agent.custom_agent_id, tenant_id, user_id)
                    if agent_config:
                        agents.append(agent_config)
                
                logger.info(f"Loaded {len(agents)} system agents for tenant {tenant_id}")
                return agents
                
        except Exception as e:
            logger.error(f"Failed to load system agents for tenant {tenant_id}: {e}")
            return []
    
    async def load_system_teams(self, tenant_id: int = 0) -> List[Dict[str, Any]]:
        """
        Load all system teams for a tenant.
        
        Args:
            tenant_id: Tenant ID (default 0 for platform tenant)
            
        Returns:
            List of system team configurations
        """
        try:
            with session_scope() as session:
                system_teams = session.query(AgentTeam).filter(
                    AgentTeam.tenant_id == tenant_id,
                    AgentTeam.is_system_agent == True,
                    AgentTeam.is_active == True,
                    AgentTeam.is_latest_version == True
                ).all()
                
                teams = []
                for team in system_teams:
                    team_config = await self.load_agent_team(team.agent_team_id, tenant_id, "system_loading")
                    if team_config:
                        teams.append(team_config)
                
                logger.info(f"Loaded {len(teams)} system teams for tenant {tenant_id}")
                return teams
                
        except Exception as e:
            logger.error(f"Failed to load system teams for tenant {tenant_id}: {e}")
            return []
    
    async def get_available_agents_for_tenant(self, tenant_id: int) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all available agents and teams for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dict with 'custom_agents' and 'teams' lists
        """
        try:
            with session_scope() as session:
                # Get custom agents
                custom_agents = session.query(CustomAgentDefinition).filter(
                    CustomAgentDefinition.tenant_id == tenant_id,
                    CustomAgentDefinition.is_active == True,
                    CustomAgentDefinition.is_latest_version == True
                ).all()
                
                # Get agent teams
                agent_teams = session.query(AgentTeam).filter(
                    AgentTeam.tenant_id == tenant_id,
                    AgentTeam.is_active == True,
                    AgentTeam.is_latest_version == True
                ).all()
                
                # Convert to configurations
                agents = []
                for agent in custom_agents:
                    agent_config = await self._load_custom_agent(session, agent.custom_agent_id, tenant_id)
                    if agent_config:
                        agents.append(agent_config)
                
                teams = []
                for team in agent_teams:
                    team_config = await self.load_agent_team(team.agent_team_id, tenant_id, "tenant_loading")
                    if team_config:
                        teams.append(team_config)
                
                return {
                    'custom_agents': agents,
                    'teams': teams
                }
                
        except Exception as e:
            logger.error(f"Failed to get available agents for tenant {tenant_id}: {e}")
            return {'custom_agents': [], 'teams': []}
    
    def create_agent_executor(self, agent_config: Dict[str, Any], tenant_id: int, job_id: str) -> Optional[Any]:
        """
        Create a specialist agent executor that uses the configured model and system prompt.

        The executor:
        - Honors STOP via Redis before/after execution
        - Publishes simple trace events
        - Uses get_gemini_llm to run a minimal prompt composed of system + user instruction
        """
        try:
            from langchain_core.prompts import ChatPromptTemplate
            from src.utils.llm_loader import get_gemini_llm
            from src.core.redis import is_job_cancelled, publish_execution_trace

            system_prompt = agent_config.get('system_prompt') or ''
            model_name = agent_config.get('model_name') or 'gemini-2.5-flash'
            temperature = float(agent_config.get('temperature') or 0.7)

            # Inject mandatory KB paradigm and tool instructions into specialist system prompt
            try:
                from src.prompts.kb_paradigm_instructions import MANDATORY_KB_PARADIGM_INSTRUCTIONS, get_mandatory_tool_instructions
                tool_names = agent_config.get('tool_names', [])
                if isinstance(tool_names, str):
                    try:
                        import json as _json
                        tool_names = _json.loads(tool_names)
                    except Exception:
                        tool_names = []
                system_prompt = system_prompt + "\n\n" + MANDATORY_KB_PARADIGM_INSTRUCTIONS
                system_prompt += get_mandatory_tool_instructions(tool_names)
            except Exception:
                pass

            class SpecialistAgentExecutor:
                def __init__(self, agent_id: str, tenant_id: int, job_id: str):
                    self.agent_id = agent_id
                    self.tenant_id = tenant_id
                    self.job_id = job_id
                    # Create a lightweight chain per executor
                    self.llm = get_gemini_llm(model_tier='flash')
                    self.prompt = ChatPromptTemplate.from_messages([
                        ("system", system_prompt),
                        ("human", "{instruction}")
                    ])
                    self.chain = self.prompt | self.llm

                async def execute(self, instruction: str) -> Dict[str, Any]:
                    try:
                        if self.job_id:
                            try:
                                if await is_job_cancelled(self.job_id):
                                    return {"agent_id": self.agent_id, "output": "CANCELLED", "success": False, "code": "CANCELLED"}
                            except Exception:
                                pass
                            try:
                                await publish_execution_trace(self.job_id, {"type": "SPECIALIST_INVOKE", "agent_id": self.agent_id})
                            except Exception:
                                pass

                        resp = await self.chain.ainvoke({"instruction": instruction})
                        output_text = resp if isinstance(resp, str) else getattr(resp, 'content', str(resp))

                        if self.job_id:
                            try:
                                if await is_job_cancelled(self.job_id):
                                    return {"agent_id": self.agent_id, "output": "CANCELLED", "success": False, "code": "CANCELLED"}
                            except Exception:
                                pass

                        return {"agent_id": self.agent_id, "output": output_text, "success": True}
                    except Exception as e:
                        return {"agent_id": self.agent_id, "output": str(e), "success": False}

            return SpecialistAgentExecutor(
                agent_id=agent_config['agent_id'],
                tenant_id=tenant_id,
                job_id=job_id,
            )

        except Exception as e:
            logger.error(f"Failed to create agent executor for {agent_config.get('agent_id')}: {e}")
            return None
    
    async def load_agents_by_team(self, team_name: str, tenant_id: int = 0) -> List[Dict[str, Any]]:
        """
        Load all agents for a specific team.
        
        Args:
            team_name: Name of the team
            tenant_id: Tenant ID (default 0 for system teams)
            
        Returns:
            List of agent configurations
        """
        try:
            with session_scope() as session:
                # Get team
                team = session.query(AgentTeam).filter(
                    AgentTeam.team_name == team_name,
                    AgentTeam.tenant_id == tenant_id,
                    AgentTeam.is_active == True,
                    AgentTeam.is_latest_version == True
                ).first()
                
                if not team:
                    logger.warning(f"Team {team_name} not found")
                    return []
                
                # Get agents for this team
                agents = session.query(CustomAgentDefinition).filter(
                    CustomAgentDefinition.tenant_id == tenant_id,
                    CustomAgentDefinition.is_active == True,
                    CustomAgentDefinition.is_latest_version == True,
                    CustomAgentDefinition.agent_metadata['team_name'].astext == team_name
                ).all()
                
                agent_configs = []
                for agent in agents:
                    config = await self._load_custom_agent(session, agent.custom_agent_id, tenant_id, None)
                    if config:
                        agent_configs.append(config)
                
                return agent_configs
                
        except Exception as e:
            logger.error(f"Failed to load agents for team {team_name}: {e}")
            return []
    
    async def load_all_system_agents(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load all system agents organized by team.
        
        Returns:
            Dict with team_name -> list of agent configs
        """
        try:
            with session_scope() as session:
                # Get all system teams
                teams = session.query(AgentTeam).filter(
                    AgentTeam.tenant_id == 0,
                    AgentTeam.is_system_team == True,
                    AgentTeam.is_active == True,
                    AgentTeam.is_latest_version == True
                ).all()
                
                result = {}
                for team in teams:
                    agents = await self.load_agents_by_team(team.team_name, tenant_id=0)
                    result[team.team_name] = agents
                
                return result
                
        except Exception as e:
            logger.error(f"Failed to load all system agents: {e}")
            return {}
    
    async def get_agent_teams_hierarchy(self, tenant_id: int = 0) -> Dict[str, Any]:
        """
        Get the complete agent teams hierarchy.
        
        Args:
            tenant_id: Tenant ID (default 0 for system teams)
            
        Returns:
            Dict with team hierarchy and metadata
        """
        try:
            with session_scope() as session:
                teams = session.query(AgentTeam).filter(
                    AgentTeam.tenant_id == tenant_id,
                    AgentTeam.is_active == True,
                    AgentTeam.is_latest_version == True
                ).all()
                
                hierarchy = {}
                for team in teams:
                    agents = await self.load_agents_by_team(team.team_name, tenant_id)
                    hierarchy[team.team_name] = {
                        'team_id': team.agent_team_id,
                        'description': team.team_description,
                        'agent_count': len(agents),
                        'agents': [agent['name'] for agent in agents],
                        'metadata': team.team_metadata
                    }
                
                return hierarchy
                
        except Exception as e:
            logger.error(f"Failed to get agent teams hierarchy: {e}")
            return {}


# Global agent loader instance
_agent_loader: Optional[AgentLoader] = None


def get_agent_loader() -> AgentLoader:
    """Get the global agent loader instance."""
    global _agent_loader
    if _agent_loader is None:
        _agent_loader = AgentLoader()
    return _agent_loader
