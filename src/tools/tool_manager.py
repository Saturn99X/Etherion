import logging
import importlib
import pkgutil
import inspect
import os
from typing import Dict, Any, List, Optional, Type, Union
from langchain_core.tools import BaseTool

from src.database.db import get_session, session_scope
from src.database.models import Tool, ToolStatus, CustomAgentDefinition
from src.agents.specialists.custom_agent_runtime_executor import CustomAgentRuntimeExecutor

logger = logging.getLogger(__name__)


class InvalidToolStatusError(Exception):
    """Raised when attempting to use a tool that is not STABLE."""
    pass


class ToolNotFoundError(Exception):
    """Raised when a requested tool cannot be found."""
    pass


class ToolInstantiationError(Exception):
    """Raised when a tool cannot be instantiated."""
    pass


class ToolManager:
    """
    Centralized tool management system for dynamic tool resolution and security validation.

    This class provides the single source of truth for tool loading, ensuring that:
    - Only STABLE tools are used in production environments
    - Tools are properly instantiated with correct parameters
    - CustomAgentRuntimeExecutor is handled specially
    - All tool access is logged and validated
    """

    def __init__(self):
        self._tool_cache: Dict[str, Type[BaseTool]] = {}
        self._tool_registry: Dict[str, Dict[str, Any]] = {}
        self._initialize_tool_registry()

    def _initialize_tool_registry(self) -> None:
        """Initialize the tool registry with available tools."""
        try:
            # Standard tools registry
            self._tool_registry = {
                # Research and Information Tools
                "exa_search": {
                    "module": "src.tools.exa_search",
                    "class": "exa_search",
                    "type": "function",
                    "category": "research",
                    "description": "Search the web using Exa with ranking and snippet extraction"
                },
                "bigquery_vector_search": {
                    "module": "src.tools.bigquery_vector_tool",
                    "class": "bigquery_vector_search",
                    "type": "function",
                    "category": "research",
                    "description": "Semantic search via BigQuery VECTOR_SEARCH"
                },
                "unified_research_tool": {
                    "module": "src.tools.unified_research_tool",
                    "class": "unified_research_tool",
                    "type": "function",
                    "category": "research",
                    "description": "Unified research across web and images for consolidated results"
                },
                "orchestrator_research_tool": {
                    "module": "src.tools.orchestrator_research",
                    "class": "orchestrator_research_tool",
                    "type": "function",
                    "category": "research"
                },
                "image_search": {
                    "module": "src.tools.image_search",
                    "class": "image_search",
                    "type": "function",
                    "category": "research"
                },
                # File Generation (wrappers around FileGenerationService)
                "generate_pdf_file": {
                    "module": "src.tools.file_generation_tools",
                    "class": "generate_pdf_file",
                    "type": "function",
                    "category": "file_generation"
                },
                "generate_excel_file": {
                    "module": "src.tools.file_generation_tools",
                    "class": "generate_excel_file",
                    "type": "function",
                    "category": "file_generation"
                },
                "generate_presentation_file": {
                    "module": "src.tools.file_generation_tools",
                    "class": "generate_presentation_file",
                    "type": "function",
                    "category": "file_generation"
                },
                "generate_image_file": {
                    "module": "src.tools.file_generation_tools",
                    "class": "generate_image_file",
                    "type": "function",
                    "category": "file_generation"
                },

                # Communication Tools
                "MCPSlackTool": {
                    "module": "src.tools.mcp.mcp_slack",
                    "class": "MCPSlackTool",
                    "type": "class",
                    "category": "communication"
                },
                "MCPJiraTool": {
                    "module": "src.tools.mcp.mcp_jira",
                    "class": "MCPJiraTool",
                    "type": "class",
                    "category": "communication"
                },
                # Additional MCP Tools
                "MCPHubSpotTool": {
                    "module": "src.tools.mcp.mcp_hubspot",
                    "class": "MCPHubSpotTool",
                    "type": "class",
                    "category": "communication"
                },
                "MCPNotionTool": {
                    "module": "src.tools.mcp.mcp_notion",
                    "class": "MCPNotionTool",
                    "type": "class",
                    "category": "communication"
                },
                "MCPShopifyTool": {
                    "module": "src.tools.mcp.mcp_shopify",
                    "class": "MCPShopifyTool",
                    "type": "class",
                    "category": "communication"
                },
                "MCPTwitterTool": {
                    "module": "src.tools.mcp.mcp_twitter",
                    "class": "MCPTwitterTool",
                    "type": "class",
                    "category": "communication"
                },
                # Knowledge Base Tools
                "search_user_feedback_history": {
                    "module": "src.tools.knowledge_base_tools",
                    "class": "search_user_feedback_history",
                    "type": "function",
                    "category": "knowledge"
                },

                "kb_object_fetch_ingest": {
                    "module": "src.tools.kb_object_fetch_ingest_tool",
                    "class": "kb_object_fetch_ingest",
                    "type": "function",
                    "category": "knowledge",
                    "description": "Fetch a tenant-scoped GCS object (gs://...) and ingest it into BigQuery KB using the existing ingestion pipeline"
                },

                # Multimodal Knowledge Base Tools (1408-D embeddings, cross-modal search)
                "multimodal_kb_search": {
                    "module": "src.tools.multimodal_kb_tool",
                    "class": "multimodal_kb_search",
                    "type": "function",
                    "category": "knowledge",
                    "description": "Search multimodal KB using 1408-D embeddings - retrieves documents AND images with same query (cross-modal)"
                },
                "fetch_document_content": {
                    "module": "src.tools.multimodal_kb_tool",
                    "class": "fetch_document_content",
                    "type": "function",
                    "category": "knowledge",
                    "description": "Fetch full document content from GCS after multimodal search (on-demand retrieval)"
                },
                "image_search_by_image": {
                    "module": "src.tools.multimodal_kb_tool",
                    "class": "image_search_by_image",
                    "type": "function",
                    "category": "knowledge",
                    "description": "Reverse image search - find similar images AND related documents using image as query"
                },

                # Utility Tools
                "ConfirmActionTool": {
                    "module": "src.tools.confirm_action_tool",
                    "class": "ConfirmActionTool",
                    "type": "class",
                    "category": "utility"
                },

                "ui_action_tool": {
                    "module": "src.tools.ui_action_tool",
                    "class": "ui_action_tool",
                    "type": "function",
                    "category": "ui"
                },

                "tool_registry_tool": {
                    "module": "src.tools.tool_registry_tool",
                    "class": "tool_registry_tool",
                    "type": "function",
                    "category": "utility",
                    "description": "List/search available tools and their descriptions for the LLM"
                },
                "get_tool_usage_schema": {
                    "module": "src.tools.tool_registry_tool",
                    "class": "get_tool_usage_schema",
                    "type": "function",
                    "category": "utility",
                    "description": "Get detailed usage schema, input parameters, and examples for a specific tool"
                },

                # Special: Custom Agent Runtime Executor
                "custom_agent_runtime_executor": {
                    "module": "src.agents.specialists.custom_agent_runtime_executor",
                    "class": "CustomAgentRuntimeExecutor",
                    "type": "class",
                    "category": "runtime",
                    "is_custom_agent_executor": True
                }
            }

            # Optional heavy package scan (disabled by default): this imports many modules.
            # Keep off in production for cold-start performance; on-demand registration covers usage.
            enable_scan = os.getenv("ENABLE_TOOL_PACKAGE_SCAN", "0").lower() in ("1", "true", "yes")
            if enable_scan:
                # Dynamically discover MCP tools under src.tools.mcp and register them
                try:
                    mcp_pkg = importlib.import_module("src.tools.mcp")
                    if hasattr(mcp_pkg, "__path__"):
                        for finder, name, ispkg in pkgutil.iter_modules(mcp_pkg.__path__):
                            if name in ("__init__", "base_mcp_tool"):
                                continue
                            module_fq = f"src.tools.mcp.{name}"
                            try:
                                m = importlib.import_module(module_fq)
                                # Find EnhancedMCPTool subclasses
                                try:
                                    from src.tools.mcp.base_mcp_tool import EnhancedMCPTool
                                except Exception:
                                    EnhancedMCPTool = None  # type: ignore
                                for attr_name in dir(m):
                                    obj = getattr(m, attr_name)
                                    if (
                                        inspect.isclass(obj)
                                        and EnhancedMCPTool is not None
                                        and issubclass(obj, EnhancedMCPTool)
                                        and obj is not EnhancedMCPTool
                                    ):
                                        tool_name = obj.__name__
                                        # Register if not already present
                                        if tool_name not in self._tool_registry:
                                            self._tool_registry[tool_name] = {
                                                "module": module_fq,
                                                "class": tool_name,
                                                "type": "class",
                                                "category": "communication",
                                            }
                            except Exception as ie:
                                logger.warning(f"Failed to import MCP module {module_fq}: {ie}")
                except Exception as de:
                    logger.warning(f"MCP dynamic discovery failed: {de}")

                # Dynamically discover non-MCP @tool functions (BaseTool instances) under src.tools
                try:
                    tools_pkg = importlib.import_module("src.tools")
                    if hasattr(tools_pkg, "__path__"):
                        EXCLUDE_PACKAGES = {"mcp", "file_generation", "image_generation", "tracking"}
                        EXCLUDE_MODULES = {"save_to_gcs_tool", "vertex_ai_search"}  # exclude legacy Vertex tool
                        for finder, mod_name, ispkg in pkgutil.iter_modules(tools_pkg.__path__):
                            if mod_name in EXCLUDE_PACKAGES or mod_name in EXCLUDE_MODULES:
                                continue
                            module_fq = f"src.tools.{mod_name}"
                            try:
                                m = importlib.import_module(module_fq)
                            except Exception as ie:
                                logger.warning(f"Failed to import tools module {module_fq}: {ie}")
                                continue
                            # Inspect attributes for BaseTool instances created via @tool decorator
                            for attr_name in dir(m):
                                try:
                                    obj = getattr(m, attr_name)
                                except Exception:
                                    continue
                                try:
                                    from langchain_core.tools import BaseTool as _LCBaseTool
                                except Exception:
                                    _LCBaseTool = BaseTool  # fallback to imported BaseTool
                                if isinstance(obj, _LCBaseTool):
                                    # Determine canonical registry name
                                    registry_name = getattr(obj, "name", attr_name)
                                    # Skip if already present
                                    if registry_name in self._tool_registry:
                                        continue
                                    self._tool_registry[registry_name] = {
                                        "module": module_fq,
                                        "class": attr_name,
                                        "type": "function",  # return the object as-is in _instantiate_standard_tool
                                        "category": getattr(obj, "tags", ["utility"])[0] if hasattr(obj, "tags") else "utility",
                                    }
                except Exception as te:
                    logger.warning(f"Non-MCP tool discovery failed: {te}")

            logger.info(f"Initialized tool registry with {len(self._tool_registry)} tools")

        except Exception as e:
            logger.error(f"Failed to initialize tool registry: {e}")
            self._tool_registry = {}

    def get_tool_instance(
        self,
        tool_name: str,
        tenant_id: int,
        job_id: str,
        custom_agent_id: Optional[str] = None,
        force_stable_only: bool = True
    ) -> BaseTool:
        """
        Get a tool instance by name with security validation.

        Args:
            tool_name: Name of the tool to instantiate
            tenant_id: Tenant ID for security isolation
            job_id: Job ID for execution tracing
            custom_agent_id: Custom agent ID (required for CustomAgentRuntimeExecutor)
            force_stable_only: If True, only allow STABLE tools (default: True)

        Returns:
            BaseTool: Instantiated tool ready for use

        Raises:
            ToolNotFoundError: If tool is not found in database or registry
            InvalidToolStatusError: If tool status is not STABLE (when force_stable_only=True)
            ToolInstantiationError: If tool cannot be instantiated
        """

        try:
            # PRIORITY 1: If tool exists in in-memory registry, instantiate directly
            # DB lookup is optional enrichment, not a gate (tool_registry is authoritative)
            if tool_name in self._tool_registry or self._try_register_tool_on_demand(tool_name) is None and tool_name in self._tool_registry:
                return self._instantiate_standard_tool(tool_name, tenant_id, job_id)

            # PRIORITY 2: Check DB for special tool types (e.g., CustomAgentRuntimeExecutor)
            with session_scope() as session:
                tool_record = session.query(Tool).filter(Tool.name == tool_name).first()

                if tool_record:
                    # Enforce STABLE status requirement if DB record exists
                    if force_stable_only and tool_record.status != ToolStatus.STABLE:
                        raise InvalidToolStatusError(
                            f"Tool '{tool_name}' has status '{tool_record.status.value}', "
                            f"only STABLE tools are allowed"
                        )

                    # Special handling for CustomAgentRuntimeExecutor
                    if tool_record.is_custom_agent_executor:
                        if not custom_agent_id:
                            raise ToolInstantiationError(
                                "custom_agent_id is required for CustomAgentRuntimeExecutor"
                            )

                        return CustomAgentRuntimeExecutor(
                            tenant_id=tenant_id,
                            job_id=job_id,
                            custom_agent_id=custom_agent_id
                        )

                    # Load standard tool from DB record
                    return self._instantiate_standard_tool(tool_name, tenant_id, job_id)

            # PRIORITY 3: Try on-demand registration for tools not yet in registry
            self._try_register_tool_on_demand(tool_name)
            if tool_name in self._tool_registry:
                return self._instantiate_standard_tool(tool_name, tenant_id, job_id)

            # Tool not found anywhere
            raise ToolNotFoundError(f"Tool '{tool_name}' not found in registry or database")

        except (ToolNotFoundError, InvalidToolStatusError, ToolInstantiationError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting tool instance '{tool_name}': {e}")
            raise ToolInstantiationError(f"Failed to get tool instance: {str(e)}")

    def _instantiate_standard_tool(self, tool_name: str, tenant_id: int, job_id: str) -> BaseTool:
        """Instantiate a standard (non-custom-agent) tool."""

        # Check if tool is in our registry
        if tool_name not in self._tool_registry:
            self._try_register_tool_on_demand(tool_name)
        if tool_name not in self._tool_registry:
            raise ToolNotFoundError(f"Tool '{tool_name}' not found in tool registry")

        tool_config = self._tool_registry[tool_name]

        try:
            # Import the tool module
            module = importlib.import_module(tool_config["module"])

            if tool_config["type"] == "class":
                # Instantiate class-based tool
                tool_class = getattr(module, tool_config["class"])

                # Try to pass job_id and tenant_id if the constructor supports it
                # Prefer passing tenant_id and job_id if supported
                for ctor in (
                    lambda: tool_class(tenant_id=tenant_id, job_id=job_id),
                    lambda: tool_class(job_id=job_id),
                    lambda: tool_class(),
                ):
                    try:
                        tool_instance = ctor()
                        break
                    except TypeError:
                        tool_instance = None
                        continue
                if tool_instance is None:
                    raise ToolInstantiationError("Could not instantiate tool with available constructors")

                return tool_instance

            elif tool_config["type"] == "function":
                # For function-based tools, return them as-is
                tool_function = getattr(module, tool_config["class"])
                return tool_function

            else:
                raise ToolInstantiationError(f"Unknown tool type: {tool_config['type']}")

        except ImportError as e:
            logger.error(f"Failed to import tool module '{tool_config['module']}': {e}")
            raise ToolInstantiationError(f"Tool module import failed: {str(e)}")
        except AttributeError as e:
            logger.error(f"Tool class/function '{tool_config['class']}' not found in module: {e}")
            raise ToolInstantiationError(f"Tool class/function not found: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to instantiate tool '{tool_name}': {e}")
            raise ToolInstantiationError(f"Tool instantiation failed: {str(e)}")

    def _try_register_tool_on_demand(self, tool_name: str) -> None:
        """Best-effort on-demand registry fill.

        Goal: allow the LLM to request a tool by name (from the DB registry) and load
        it at the moment it is needed, without boot-time imports / scans.
        """

        if tool_name in self._tool_registry:
            return

        # 1) MCP class convention: MCPNotionTool -> src.tools.mcp.mcp_notion
        if tool_name.startswith("MCP") and tool_name.endswith("Tool"):
            try:
                core = tool_name[len("MCP") : -len("Tool")]
                if core:
                    snake = ""
                    for i, ch in enumerate(core):
                        if ch.isupper() and i != 0:
                            snake += "_"
                        snake += ch.lower()
                    module_fq = f"src.tools.mcp.mcp_{snake}"
                    module = importlib.import_module(module_fq)
                    if hasattr(module, tool_name) and inspect.isclass(getattr(module, tool_name)):
                        self._tool_registry[tool_name] = {
                            "module": module_fq,
                            "class": tool_name,
                            "type": "class",
                            "category": "communication",
                        }
                        return
            except Exception as e:
                logger.warning(f"On-demand MCP registration failed for {tool_name}: {e}")

        # 2) Try module name equal to tool_name (common for function tools)
        for module_fq in (f"src.tools.{tool_name}", f"src.tools.{self._camel_to_snake(tool_name)}"):
            try:
                module = importlib.import_module(module_fq)
            except Exception:
                continue

            # Direct attribute match
            if hasattr(module, tool_name):
                obj = getattr(module, tool_name)
                self._register_obj(module_fq, tool_name, obj)
                return

            # Otherwise, search module for BaseTool instance with matching .name
            try:
                from langchain_core.tools import BaseTool as _LCBaseTool
            except Exception:
                _LCBaseTool = BaseTool

            for attr_name in dir(module):
                try:
                    obj = getattr(module, attr_name)
                except Exception:
                    continue
                if isinstance(obj, _LCBaseTool) and getattr(obj, "name", None) == tool_name:
                    self._tool_registry[tool_name] = {
                        "module": module_fq,
                        "class": attr_name,
                        "type": "function",
                        "category": getattr(obj, "tags", ["utility"])[0] if hasattr(obj, "tags") else "utility",
                    }
                    return

    def _register_obj(self, module_fq: str, tool_name: str, obj: Any) -> None:
        if inspect.isclass(obj):
            self._tool_registry[tool_name] = {
                "module": module_fq,
                "class": tool_name,
                "type": "class",
                "category": "utility",
            }
            return
        self._tool_registry[tool_name] = {
            "module": module_fq,
            "class": tool_name,
            "type": "function",
            "category": "utility",
        }

    def _camel_to_snake(self, s: str) -> str:
        out = ""
        for i, ch in enumerate(s):
            if ch.isupper() and i != 0:
                out += "_"
            out += ch.lower()
        return out

    def get_available_tools(self, tenant_id: int, include_beta: bool = False) -> List[Dict[str, Any]]:
        """
        Get list of available tools for a tenant.

        Args:
            tenant_id: Tenant ID for filtering
            include_beta: Whether to include BETA status tools

        Returns:
            List of tool information dictionaries
        """
        try:
            with session_scope() as session:
                query = session.query(Tool)

                if include_beta:
                    query = query.filter(Tool.status.in_([ToolStatus.STABLE, ToolStatus.BETA]))
                else:
                    query = query.filter(Tool.status == ToolStatus.STABLE)

                tools = query.all()

                return [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "status": tool.status.value,
                        "category": tool.category,
                        "is_custom_agent_executor": tool.is_custom_agent_executor,
                        "version": tool.version,
                        "documentation_url": tool.documentation_url,
                        "requires_auth": tool.requires_auth,
                        "max_concurrent_calls": tool.max_concurrent_calls
                    }
                    for tool in tools
                ]

        except Exception as e:
            logger.error(f"Failed to get available tools: {e}")
            return []

    def validate_tool_names(self, tool_names: List[str], tenant_id: int, include_beta: bool = False) -> Dict[str, Any]:
        """
        Validate a list of tool names against database records.

        Args:
            tool_names: List of tool names to validate
            tenant_id: Tenant ID for context
            include_beta: Whether to allow BETA status tools

        Returns:
            Dict with validation results including valid/invalid/deprecated tools
        """
        validation_result = {
            "valid_tools": [],
            "invalid_tools": [],
            "deprecated_tools": [],
            "beta_tools": [],
            "not_found_tools": []
        }

        try:
            with session_scope() as session:
                for tool_name in tool_names:
                    tool_record = session.query(Tool).filter(Tool.name == tool_name).first()

                    if not tool_record:
                        validation_result["not_found_tools"].append(tool_name)
                        continue

                    if tool_record.status == ToolStatus.STABLE:
                        validation_result["valid_tools"].append(tool_name)
                    elif tool_record.status == ToolStatus.BETA:
                        if include_beta:
                            validation_result["valid_tools"].append(tool_name)
                        validation_result["beta_tools"].append(tool_name)
                    elif tool_record.status == ToolStatus.DEPRECATED:
                        validation_result["deprecated_tools"].append(tool_name)
                    else:
                        validation_result["invalid_tools"].append(tool_name)

        except Exception as e:
            logger.error(f"Failed to validate tool names: {e}")
            # Mark all tools as invalid if validation fails
            validation_result["invalid_tools"].extend(tool_names)

        return validation_result

    def register_tool_in_database(
        self,
        name: str,
        description: str,
        status: ToolStatus = ToolStatus.BETA,
        category: Optional[str] = None,
        version: Optional[str] = None,
        documentation_url: Optional[str] = None,
        requires_auth: bool = False,
        max_concurrent_calls: Optional[int] = None,
        is_custom_agent_executor: bool = False
    ) -> bool:
        """
        Register a tool in the database.

        Args:
            name: Unique tool name
            description: Tool description
            status: Tool status (default: BETA)
            category: Tool category
            version: Tool version
            documentation_url: Link to documentation
            requires_auth: Whether tool requires authentication
            max_concurrent_calls: Maximum concurrent calls allowed
            is_custom_agent_executor: Whether this is the CustomAgentRuntimeExecutor

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            with session_scope() as session:
                # Check if tool already exists
                existing_tool = session.query(Tool).filter(Tool.name == name).first()

                if existing_tool:
                    logger.warning(f"Tool '{name}' already exists in database")
                    return False

                # Create new tool record
                tool = Tool(
                    name=name,
                    description=description,
                    status=status,
                    category=category,
                    version=version,
                    documentation_url=documentation_url,
                    requires_auth=requires_auth,
                    max_concurrent_calls=max_concurrent_calls,
                    is_custom_agent_executor=is_custom_agent_executor
                )

                session.add(tool)
                session.commit()

                logger.info(f"Successfully registered tool '{name}' with status '{status.value}'")
                return True

        except Exception as e:
            logger.error(f"Failed to register tool '{name}': {e}")
            return False

    def update_tool_status(self, tool_name: str, new_status: ToolStatus) -> bool:
        """
        Update the status of a tool in the database.

        Args:
            tool_name: Name of the tool to update
            new_status: New status for the tool

        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            with session_scope() as session:
                tool = session.query(Tool).filter(Tool.name == tool_name).first()

                if not tool:
                    logger.error(f"Tool '{tool_name}' not found for status update")
                    return False

                old_status = tool.status
                tool.status = new_status
                tool.update_timestamp()

                session.commit()

                logger.info(f"Updated tool '{tool_name}' status: {old_status.value} -> {new_status.value}")
                return True

        except Exception as e:
            logger.error(f"Failed to update tool status for '{tool_name}': {e}")
            return False

    def get_tools_for_agent_team(self, agent_team_id: str, tenant_id: int, job_id: str) -> List[BaseTool]:
        """
        Get all validated tools for an AgentTeam.

        Args:
            agent_team_id: ID of the agent team
            tenant_id: Tenant ID for security
            job_id: Job ID for tracing

        Returns:
            List of validated tool instances
        """
        tools = []

        try:
            from src.database.models import AgentTeam

            with session_scope() as session:
                agent_team = session.query(AgentTeam).filter(
                    AgentTeam.agent_team_id == agent_team_id,
                    AgentTeam.tenant_id == tenant_id,
                    AgentTeam.is_active == True
                ).first()

                if not agent_team:
                    logger.error(f"Agent team not found or inactive: {agent_team_id}")
                    return []

                # Load CustomAgentRuntimeExecutor instances for each custom agent
                for custom_agent_id in agent_team.get_custom_agent_ids():
                    try:
                        custom_executor = self.get_tool_instance(
                            tool_name="custom_agent_runtime_executor",
                            tenant_id=tenant_id,
                            job_id=job_id,
                            custom_agent_id=custom_agent_id
                        )
                        tools.append(custom_executor)
                        logger.debug(f"Added custom agent executor for: {custom_agent_id}")

                    except Exception as e:
                        logger.error(f"Failed to load custom agent {custom_agent_id}: {e}")
                        continue

                # Load pre-approved standard tools
                for tool_name in agent_team.get_pre_approved_tool_names():
                    try:
                        tool_instance = self.get_tool_instance(
                            tool_name=tool_name,
                            tenant_id=tenant_id,
                            job_id=job_id
                        )
                        tools.append(tool_instance)
                        logger.debug(f"Added pre-approved tool: {tool_name}")

                    except Exception as e:
                        logger.error(f"Failed to load pre-approved tool {tool_name}: {e}")
                        continue

                logger.info(
                    f"Loaded {len(tools)} tools for agent team '{agent_team.name}' "
                    f"({len(agent_team.get_custom_agent_ids())} custom agents, "
                    f"{len(agent_team.get_pre_approved_tool_names())} pre-approved tools)"
                )

        except Exception as e:
            logger.error(f"Failed to get tools for agent team {agent_team_id}: {e}")

        return tools

    def get_default_stable_tools(self, tenant_id: int, job_id: str) -> List[BaseTool]:
        """
        Get default set of STABLE tools for the main Platform Orchestrator.

        Args:
            tenant_id: Tenant ID for security
            job_id: Job ID for tracing

        Returns:
            List of STABLE tool instances
        """
        tools = []

        try:
            with session_scope() as session:
                stable_tools = session.query(Tool).filter(
                    Tool.status == ToolStatus.STABLE,
                    Tool.is_custom_agent_executor == False  # Exclude custom agent executor
                ).all()

                for tool_record in stable_tools:
                    try:
                        tool_instance = self.get_tool_instance(
                            tool_name=tool_record.name,
                            tenant_id=tenant_id,
                            job_id=job_id,
                            force_stable_only=True
                        )
                        tools.append(tool_instance)

                    except Exception as e:
                        logger.error(f"Failed to load default tool {tool_record.name}: {e}")
                        continue

                logger.info(f"Loaded {len(tools)} default STABLE tools")

        except Exception as e:
            logger.error(f"Failed to get default stable tools: {e}")

        return tools

    def initialize_default_tools(self) -> bool:
        """
        Initialize the database with default tool records.
        This should be called during application startup or deployment.

        Returns:
{{ ... }}
            bool: True if initialization successful
        """
        default_tools = [
            {
                "name": "bigquery_vector_search",
                "description": "Semantic search using BigQuery VECTOR_SEARCH",
                "status": ToolStatus.STABLE,
                "category": "research",
                "version": "1.0"
            },
            {
                "name": "orchestrator_research_tool",
                "description": "Unified research tool for text and image searches",
                "status": ToolStatus.STABLE,
                "category": "research",
                "version": "1.0"
            },
            {
                "name": "image_search",
                "description": "Search for relevant images based on query",
                "status": ToolStatus.STABLE,
                "category": "research",
                "version": "1.0"
            },
            {
                "name": "generate_pdf_file",
                "description": "Generate a PDF using the FileGenerationService",
                "status": ToolStatus.BETA,
                "category": "file_generation",
                "version": "1.0"
            },
            {
                "name": "generate_excel_file",
                "description": "Generate an Excel workbook using the FileGenerationService",
                "status": ToolStatus.BETA,
                "category": "file_generation",
                "version": "1.0"
            },
            {
                "name": "generate_presentation_file",
                "description": "Generate a PowerPoint using the FileGenerationService",
                "status": ToolStatus.BETA,
                "category": "file_generation",
                "version": "1.0"
            },
            {
                "name": "generate_image_file",
                "description": "Generate an image via Vertex AI using the FileGenerationService",
                "status": ToolStatus.BETA,
                "category": "file_generation",
                "version": "1.0"
            },
            {
                "name": "MCPSlackTool",
                "description": "Interact with Slack for messaging and notifications",
                "status": ToolStatus.BETA,  # Start as BETA until fully tested
                "category": "communication",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "MCPJiraTool",
                "description": "Manage Jira tickets and project tracking",
                "status": ToolStatus.BETA,
                "category": "communication",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "MCPHubSpotTool",
                "description": "Manage HubSpot contacts, deals, and marketing campaigns",
                "status": ToolStatus.BETA,
                "category": "communication",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "MCPLinkedInTool",
                "description": "Access LinkedIn profiles, connections, and company data",
                "status": ToolStatus.BETA,
                "category": "communication",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "MCPNotionTool",
                "description": "Create, read, and update Notion pages and databases",
                "status": ToolStatus.BETA,
                "category": "communication",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "MCPResendTool",
                "description": "Send transactional emails through Resend API",
                "status": ToolStatus.BETA,
                "category": "communication",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "MCPShopifyTool",
                "description": "Access Shopify store data, orders, and products",
                "status": ToolStatus.BETA,
                "category": "communication",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "MCPTwitterTool",
                "description": "Access Twitter/X data and post updates",
                "status": ToolStatus.BETA,
                "category": "communication",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "MCPRedfinTool",
                "description": "Access real estate data from Redfin",
                "status": ToolStatus.BETA,
                "category": "communication",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "MCPZillowTool",
                "description": "Access real estate data from Zillow",
                "status": ToolStatus.BETA,
                "category": "communication",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "order_lookup_tool",
                "description": "Look up order status and details by order ID",
                "status": ToolStatus.STABLE,
                "category": "ecommerce",
                "version": "1.0"
            },
            {
                "name": "get_shopify_order_details",
                "description": "Get comprehensive Shopify order information",
                "status": ToolStatus.STABLE,
                "category": "ecommerce",
                "requires_auth": True,
                "version": "1.0"
            },
            {
                "name": "search_user_feedback_history",
                "description": "Search user's feedback history for preferences",
                "status": ToolStatus.STABLE,
                "category": "knowledge",
                "version": "1.0"
            },
            {
                "name": "save_to_document_tool",
                "description": "Save content to a document and return reference",
                "status": ToolStatus.STABLE,
                "category": "document",
                "version": "1.0"
            },
            {
                "name": "ConfirmActionTool",
                "description": "Request user confirmation for critical actions",
                "status": ToolStatus.STABLE,
                "category": "utility",
                "version": "1.0"
            },
            {
                "name": "ui_action_tool",
                "description": "Publish tenant-scoped UI events to trigger frontend components",
                "status": ToolStatus.STABLE,
                "category": "ui",
                "version": "1.0"
            },
            {
                "name": "custom_agent_runtime_executor",
                "description": "Execute user-defined custom agents with security validation",
                "status": ToolStatus.STABLE,
                "category": "runtime",
                "is_custom_agent_executor": True,
                "version": "1.0"
            }
        ]

        success_count = 0
        for tool_config in default_tools:
            if self.register_tool_in_database(**tool_config):
                success_count += 1

        logger.info(f"Initialized {success_count}/{len(default_tools)} default tools in database")
        return success_count == len(default_tools)

    def get_tool_registry_info(self) -> Dict[str, Any]:
        """Get information about the current tool registry."""
        return {
            "total_tools": len(self._tool_registry),
            "tool_names": list(self._tool_registry.keys()),
            "categories": list(set(
                tool_config.get("category", "unknown")
                for tool_config in self._tool_registry.values()
            )),
            "registry_status": "initialized" if self._tool_registry else "empty",
            # Expose full registry for downstream scripts to read descriptions/categories
            "registry": self._tool_registry,
        }


# Global tool manager instance
_tool_manager: Optional[ToolManager] = None


def get_tool_manager() -> ToolManager:
    """Get global tool manager instance."""
    global _tool_manager
    if _tool_manager is None:
        _tool_manager = ToolManager()
    return _tool_manager


# Convenience functions for common operations
def get_tool_instance(
    tool_name: str,
    tenant_id: int,
    job_id: str,
    custom_agent_id: Optional[str] = None
) -> BaseTool:
    """Convenience function to get a tool instance."""
    return get_tool_manager().get_tool_instance(
        tool_name=tool_name,
        tenant_id=tenant_id,
        job_id=job_id,
        custom_agent_id=custom_agent_id
    )


def validate_tool_names(tool_names: List[str], tenant_id: int) -> Dict[str, Any]:
    """Convenience function to validate tool names."""
    return get_tool_manager().validate_tool_names(tool_names, tenant_id)


def get_available_tools(tenant_id: int, include_beta: bool = False) -> List[Dict[str, Any]]:
    """Convenience function to get available tools."""
    return get_tool_manager().get_available_tools(tenant_id, include_beta)


def initialize_default_tools() -> bool:
    """Convenience function to initialize default tools."""
    return get_tool_manager().initialize_default_tools()
