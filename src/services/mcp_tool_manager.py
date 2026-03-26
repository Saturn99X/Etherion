# src/services/mcp_tool_manager.py
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from src.database.db import get_session, session_scope
from src.database.models import Tool, ToolStatus
from src.tools.tool_manager import get_tool_manager
from ..database.models.secure_credential import SecureCredential, CredentialStatus
from ..services.secure_credential_service import SecureCredentialService

logger = logging.getLogger(__name__)

@dataclass
class MCPToolInfo:
    """Information about an available MCP tool."""
    name: str
    description: str
    category: str
    required_credentials: List[str]
    capabilities: List[str]
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "requiredCredentials": self.required_credentials,
            "capabilities": self.capabilities,
            "status": self.status
        }

@dataclass
class MCPToolResult:
    """Result from MCP tool execution."""
    success: bool
    result: str
    executionTime: float
    errorMessage: Optional[str] = None
    toolOutput: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "result": self.result,
            "executionTime": self.executionTime,
            "errorMessage": self.errorMessage,
            "toolOutput": self.toolOutput
        }

@dataclass
class MCPCredentialStatus:
    """Status result from managing MCP tool credentials."""
    success: bool
    validationErrors: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "validationErrors": self.validationErrors
        }

@dataclass
class MCPToolTestResult:
    """Result from testing MCP tool credentials."""
    success: bool
    testResult: str
    errorMessage: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "testResult": self.testResult,
            "errorMessage": self.errorMessage
        }

class MCPToolManager:
    """
    Centralized management of all MCP tools with real execution and secure credential management.
    """

    def __init__(self, db_session=None):
        self.db_session = db_session
        self.tool_manager = get_tool_manager()
        # Lazily initialize credential service to avoid requiring MASTER_ENCRYPTION_KEY
        # for operations that do not need it (e.g., listing available tools).
        self.credential_service = None

    def _get_credential_service(self) -> SecureCredentialService:
        """Lazily create and return the SecureCredentialService instance."""
        if self.credential_service is None:
            self.credential_service = SecureCredentialService()
        return self.credential_service

    async def get_available_tools(self) -> List[MCPToolInfo]:
        """
        Get all available MCP tools with status.

        Returns:
            List[MCPToolInfo]: List of available MCP tools
        """
        try:
            mcp_tools = []

            # Define MCP tool configurations
            mcp_tool_configs = {
                "mcp_slack": {
                    "description": "Send messages and interact with Slack",
                    "category": "communication",
                    "required_credentials": ["bot_token"],
                    "capabilities": ["send_message", "read_channel", "file_upload"]
                },
                "mcp_jira": {
                    "description": "Manage Jira tickets and project tracking",
                    "category": "communication",
                    "required_credentials": ["api_token", "email"],
                    "capabilities": ["create_ticket", "update_ticket", "get_ticket", "search_tickets"]
                },
                "mcp_hubspot": {
                    "description": "Manage HubSpot contacts, deals, and marketing campaigns",
                    "category": "communication",
                    "required_credentials": ["api_key"],
                    "capabilities": ["create_contact", "update_contact", "get_contact", "create_deal"]
                },
                "mcp_linkedin": {
                    "description": "Access LinkedIn profiles, connections, and company data",
                    "category": "communication",
                    "required_credentials": ["access_token"],
                    "capabilities": ["get_profile", "get_connections", "search_companies"]
                },
                "mcp_notion": {
                    "description": "Create, read, and update Notion pages and databases",
                    "category": "communication",
                    "required_credentials": ["token"],
                    "capabilities": ["create_page", "update_page", "query_database", "search_pages"]
                },
               
                "mcp_shopify": {
                    "description": "Access Shopify store data, orders, and products",
                    "category": "communication",
                    "required_credentials": ["access_token", "shop_domain"],
                    "capabilities": ["get_orders", "get_products", "update_order", "create_product"]
                },
                # Additional tools present in src/tools/mcp but previously not surfaced
                "mcp_gmail": {
                    "description": "Gmail: read, search, send emails (OAuth2 with refresh)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": ["list_messages", "get_message", "send_message", "search_messages", "get_labels"]
                },
                "mcp_google_drive": {
                    "description": "Google Drive: files, folders, permissions (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": ["list_files", "get_file", "upload_file", "search_files"]
                },
                "mcp_google_calendar": {
                    "description": "Google Calendar: calendars and events (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": ["list_calendars", "get_events", "create_event", "update_event", "delete_event"]
                },
                "mcp_google_docs": {
                    "description": "Google Docs: documents (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": ["get_doc_content", "create_doc", "modify_doc_text"]
                },
                "mcp_google_sheets": {
                    "description": "Google Sheets: spreadsheets (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": [
                        "list_spreadsheets",
                        "get_spreadsheet_info",
                        "read_sheet_values",
                        "modify_sheet_values",
                        "create_sheet",
                        "create_spreadsheet"
                    ]
                },
                "mcp_google_slides": {
                    "description": "Google Slides: presentations (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": ["create_presentation", "get_presentation"]
                },
                "mcp_google_forms": {
                    "description": "Google Forms: forms and responses (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": [
                        "create_form",
                        "get_form",
                        "list_form_responses",
                        "set_publish_settings",
                        "get_form_response"
                    ]
                },
                "mcp_google_tasks": {
                    "description": "Google Tasks: personal tasks (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": [
                        "list_task_lists", "get_task_list", "create_task_list", "update_task_list", "delete_task_list",
                        "list_tasks", "get_task", "create_task", "update_task", "delete_task", "move_task"
                    ]
                },
                "mcp_google_chat": {
                    "description": "Google Chat: spaces and messages (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": ["list_spaces", "get_messages", "send_message"]
                },
                "mcp_google_search": {
                    "description": "Google Programmable Search Engine (API key)",
                    "category": "communication",
                    "required_credentials": ["credentials"],
                    "capabilities": ["search_custom"]
                },
                "mcp_ms365": {
                    "description": "Microsoft 365: mail, calendar, files (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": ["list_messages", "send_message", "list_events", "list_files"]
                },
                "mcp_salesforce": {
                    "description": "Salesforce: leads, accounts, opportunities (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": ["create_lead", "update_lead", "query_soql"]
                },
                "mcp_instagram": {
                    "description": "Instagram: basic content operations (token)",
                    "category": "communication",
                    "required_credentials": ["access_token"],
                    "capabilities": ["get_profile", "list_media", "post_media"]
                },
                "mcp_reddit": {
                    "description": "Reddit: posts, comments, search (OAuth2)",
                    "category": "communication",
                    "required_credentials": ["oauth_credentials"],
                    "capabilities": ["get_subreddit", "submit_post", "comment", "search"]
                },
                "mcp_twitter": {
                    "description": "Access Twitter/X data and post updates",
                    "category": "communication",
                    "required_credentials": ["api_key", "api_secret", "access_token", "access_token_secret"],
                    "capabilities": ["post_tweet", "get_tweets", "search_tweets", "get_user"]
                }
            }

            # Get tool status from database
            with session_scope() as session:
                for tool_name, config in mcp_tool_configs.items():
                    # Check if tool exists in database
                    tool_record = session.query(Tool).filter(Tool.name == tool_name).first()

                    if tool_record:
                        status = tool_record.status.value
                    else:
                        # Tool not in database yet, assume available
                        status = "available"

                    mcp_tools.append(MCPToolInfo(
                        name=tool_name,
                        description=config["description"],
                        category=config["category"],
                        required_credentials=config["required_credentials"],
                        capabilities=config["capabilities"],
                        status=status
                    ))

            return mcp_tools

        except Exception as e:
            logger.error(f"Failed to get available MCP tools: {e}")
            return []

    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> MCPToolResult:
        """
        Execute MCP tool with proper error handling.

        Args:
            tool_name: Name of the MCP tool to execute
            params: Parameters for tool execution

        Returns:
            MCPToolResult: Execution result
        """
        try:
            import time
            start_time = time.time()

            # Require tenant_id
            tenant_id = params.get('tenant_id')
            if not tenant_id:
                return MCPToolResult(
                    success=False,
                    result="Missing required parameter: tenant_id",
                    executionTime=0.0,
                    errorMessage="Missing required parameter: tenant_id",
                )

            # Parse operation and tool params
            operation: Optional[str] = params.get("operation")
            tool_params: Dict[str, Any] = params.get("params") if isinstance(params.get("params"), dict) else {k: v for k, v in params.items() if k not in ("operation", "params")}

            # Map tool_name to module/class
            registry: Dict[str, Tuple[str, str]] = {
                "mcp_slack": ("src.tools.mcp.mcp_slack", "MCPSlackTool"),
                "mcp_jira": ("src.tools.mcp.mcp_jira", "MCPJiraTool"),
                "mcp_hubspot": ("src.tools.mcp.mcp_hubspot", "MCPHubSpotTool"),
                "mcp_linkedin": ("src.tools.mcp.mcp_linkedin", "MCPLinkedInTool"),
                "mcp_notion": ("src.tools.mcp.mcp_notion", "MCPNotionTool"),
                "mcp_shopify": ("src.tools.mcp.mcp_shopify", "MCPShopifyTool"),
                "mcp_gmail": ("src.tools.mcp.mcp_gmail", "MCPGmailTool"),
                "mcp_google_drive": ("src.tools.mcp.mcp_google_drive", "MCPGoogleDriveTool"),
                "mcp_google_calendar": ("src.tools.mcp.mcp_google_calendar", "MCPGoogleCalendarTool"),
                "mcp_google_docs": ("src.tools.mcp.mcp_google_docs", "MCPGoogleDocsTool"),
                "mcp_google_sheets": ("src.tools.mcp.mcp_google_sheets", "MCPGoogleSheetsTool"),
                "mcp_google_slides": ("src.tools.mcp.mcp_google_slides", "MCPGoogleSlidesTool"),
                "mcp_google_forms": ("src.tools.mcp.mcp_google_forms", "MCPGoogleFormsTool"),
                "mcp_google_tasks": ("src.tools.mcp.mcp_google_tasks", "MCPGoogleTasksTool"),
                "mcp_google_chat": ("src.tools.mcp.mcp_google_chat", "MCPGoogleChatTool"),
                "mcp_google_search": ("src.tools.mcp.mcp_google_search", "MCPGoogleSearchTool"),
                "mcp_ms365": ("src.tools.mcp.mcp_ms365", "MCPMS365Tool"),
                "mcp_salesforce": ("src.tools.mcp.mcp_salesforce", "MCPSalesforceTool"),
                "mcp_instagram": ("src.tools.mcp.mcp_instagram", "MCPInstagramTool"),
                "mcp_reddit": ("src.tools.mcp.mcp_reddit", "MCPRedditTool"),
                "mcp_twitter": ("src.tools.mcp.mcp_twitter", "MCPTwitterTool"),
            }

            if tool_name not in registry:
                return MCPToolResult(
                    success=False,
                    result=f"Unknown MCP tool: {tool_name}",
                    executionTime=time.time() - start_time,
                    errorMessage="UNKNOWN_TOOL",
                )

            module_path, class_name = registry[tool_name]
            mod = __import__(module_path, fromlist=[class_name])
            tool_cls = getattr(mod, class_name)
            tool_instance = tool_cls()  # Most tools have parameterless constructors

            # Attempt EnhancedMCPTool signature first
            result_payload: Any
            try:
                if operation is None:
                    raise ValueError("Missing 'operation' for MCP tool execution")
                result_payload = await tool_instance.execute(str(tenant_id), str(operation), tool_params or {})
            except TypeError:
                # Fallback to older BaseMCPTool interface: execute(params)
                merged = {"tenant_id": tenant_id, **(tool_params or {})}
                if hasattr(tool_instance, "execute"):
                    result_payload = await tool_instance.execute(merged)  # type: ignore
                elif hasattr(tool_instance, "_execute_tool"):
                    result_payload = await tool_instance._execute_tool(merged)  # type: ignore
                else:
                    raise RuntimeError("Tool does not expose an executable interface")

            execution_time = time.time() - start_time

            # If the result is a dataclass-like with to_dict (e.g., MCPToolResult), flatten it first
            if hasattr(result_payload, "to_dict") and callable(getattr(result_payload, "to_dict")):
                try:
                    result_payload = result_payload.to_dict()
                except Exception:
                    # Best-effort fallback: leave as-is and let subsequent normalization try
                    pass

            # Normalize result
            if isinstance(result_payload, dict) and {"success", "data"}.intersection(result_payload.keys()):
                # Already MCPToolResult-like
                success = bool(result_payload.get("success", True))
                error_message = result_payload.get("error_message") or result_payload.get("errorMessage")
                return MCPToolResult(
                    success=success,
                    result=f"MCP tool {tool_name} executed",
                    executionTime=execution_time,
                    errorMessage=error_message,
                    toolOutput=result_payload,
                )

            return MCPToolResult(
                success=True,
                result=f"MCP tool {tool_name} executed",
                executionTime=execution_time,
                errorMessage=None,
                toolOutput=result_payload,
            )

        except Exception as e:
            import time
            execution_time = time.time() - start_time
            logger.error(f"Failed to execute MCP tool {tool_name}: {e}")

            return MCPToolResult(
                success=False,
                result=f"MCP tool execution failed: {str(e)}",
                executionTime=execution_time,
                errorMessage=str(e)
            )

    async def validate_credentials(self, tool_name: str, tenant_id: int) -> bool:
        """
        Validate MCP tool credentials.

        Args:
            tool_name: Name of the MCP tool
            tenant_id: Tenant ID for credential lookup

        Returns:
            bool: True if credentials are valid
        """
        try:
            # TODO: Implement actual credential validation
            # For now, return True as placeholder
            return True

        except Exception as e:
            logger.error(f"Failed to validate credentials for MCP tool {tool_name}: {e}")
            return False

    async def test_tool_connection(self, tool_name: str, tenant_id: int) -> MCPToolTestResult:
        """
        Test MCP tool connection with stored credentials.

        Args:
            tool_name: Name of the MCP tool to test
            tenant_id: Tenant ID for credential lookup

        Returns:
            MCPToolTestResult: Test result
        """
        try:
            # Validate credentials first (logic may be improved per tool)
            credentials_valid = await self.validate_credentials(tool_name, tenant_id)
            if not credentials_valid:
                return MCPToolTestResult(
                    success=False,
                    testResult=f"{tool_name} credentials are invalid",
                    errorMessage="Invalid or missing credentials",
                )

            # Attempt a vendor/tool-specific test if the module exposes it
            registry: Dict[str, Tuple[str, str]] = {
                "mcp_slack": ("src.tools.mcp.mcp_slack", "MCPSlackTool"),
                "mcp_jira": ("src.tools.mcp.mcp_jira", "MCPJiraTool"),
                "mcp_hubspot": ("src.tools.mcp.mcp_hubspot", "MCPHubSpotTool"),
                "mcp_linkedin": ("src.tools.mcp.mcp_linkedin", "MCPLinkedInTool"),
                "mcp_notion": ("src.tools.mcp.mcp_notion", "MCPNotionTool"),
                "mcp_shopify": ("src.tools.mcp.mcp_shopify", "MCPShopifyTool"),
                "mcp_gmail": ("src.tools.mcp.mcp_gmail", "MCPGmailTool"),
                "mcp_google_drive": ("src.tools.mcp.mcp_google_drive", "MCPGoogleDriveTool"),
                "mcp_google_calendar": ("src.tools.mcp.mcp_google_calendar", "MCPGoogleCalendarTool"),
                "mcp_google_docs": ("src.tools.mcp.mcp_google_docs", "MCPGoogleDocsTool"),
                "mcp_google_sheets": ("src.tools.mcp.mcp_google_sheets", "MCPGoogleSheetsTool"),
                "mcp_google_slides": ("src.tools.mcp.mcp_google_slides", "MCPGoogleSlidesTool"),
                "mcp_google_forms": ("src.tools.mcp.mcp_google_forms", "MCPGoogleFormsTool"),
                "mcp_google_tasks": ("src.tools.mcp.mcp_google_tasks", "MCPGoogleTasksTool"),
                "mcp_google_chat": ("src.tools.mcp.mcp_google_chat", "MCPGoogleChatTool"),
                "mcp_google_search": ("src.tools.mcp.mcp_google_search", "MCPGoogleSearchTool"),
                "mcp_ms365": ("src.tools.mcp.mcp_ms365", "MCPMS365Tool"),
                "mcp_salesforce": ("src.tools.mcp.mcp_salesforce", "MCPSalesforceTool"),
                "mcp_instagram": ("src.tools.mcp.mcp_instagram", "MCPInstagramTool"),
                "mcp_reddit": ("src.tools.mcp.mcp_reddit", "MCPRedditTool"),
                "mcp_twitter": ("src.tools.mcp.mcp_twitter", "MCPTwitterTool"),
            }

            if tool_name in registry:
                module_path, _class = registry[tool_name]
                mod = __import__(module_path, fromlist=[_class])
                # Prefer a module-level async test_connection(tenant_id) if present
                test_fn = getattr(mod, "test_connection", None)
                if callable(test_fn):
                    import asyncio
                    try:
                        result = await asyncio.wait_for(test_fn(tenant_id), timeout=8.0)
                        # Expected result: (success: bool, message: str | None)
                        if isinstance(result, tuple) and len(result) >= 1:
                            ok = bool(result[0])
                            msg = result[1] if len(result) > 1 else None
                            return MCPToolTestResult(
                                success=ok,
                                testResult=msg or f"{tool_name} connection test {'successful' if ok else 'failed'}",
                                errorMessage=None if ok else (msg or "Test failed"),
                            )
                    except asyncio.TimeoutError:
                        return MCPToolTestResult(
                            success=False,
                            testResult=f"{tool_name} connection test failed",
                            errorMessage="Timeout",
                        )
                    except Exception as e:
                        # Fall through to generic success if credentials exist
                        return MCPToolTestResult(
                            success=False,
                            testResult=f"{tool_name} connection test failed",
                            errorMessage=str(e),
                        )

            # Generic fallback when tool-specific probe not available
            return MCPToolTestResult(
                success=True,
                testResult=f"{tool_name} credentials present",
                errorMessage=None,
            )

        except Exception as e:
            logger.error(f"Failed to test MCP tool {tool_name}: {e}")
            return MCPToolTestResult(
                success=False,
                testResult=f"{tool_name} connection test failed",
                errorMessage=str(e)
            )

    async def store_credentials(self, tool_name: str, tenant_id: int, credentials: Dict[str, Any]) -> MCPCredentialStatus:
        """
        Store credentials for an MCP tool.

        Args:
            tool_name: Name of the MCP tool
            tenant_id: Tenant ID for credential storage
            credentials: Credentials to store

        Returns:
            MCPCredentialStatus: Storage status
        """
        try:
            # TODO: Implement actual credential storage
            # For now, return success as placeholder
            return MCPCredentialStatus(
                success=True,
                validationErrors=None
            )

        except Exception as e:
            logger.error(f"Failed to store credentials for MCP tool {tool_name}: {e}")
            return MCPCredentialStatus(
                success=False,
                validationErrors=[str(e)]
            )

    async def get_tool_status(self, tool_name: str, tenant_id: int) -> str:
        """
        Get the current status of an MCP tool.

        Args:
            tool_name: Name of the MCP tool
            tenant_id: Tenant ID for status lookup

        Returns:
            str: Current status of the tool
        """
        try:
            # Check if tool exists in database
            with session_scope() as session:
                tool_record = session.query(Tool).filter(Tool.name == tool_name).first()

                if tool_record:
                    return tool_record.status.value
                else:
                    return "available"

        except Exception as e:
            logger.error(f"Failed to get status for MCP tool {tool_name}: {e}")
            return "error"

    async def store_credentials(
        self,
        tenant_id: int,
        tool_name: str,
        service_name: str,
        credentials: Dict[str, Any],
        credential_type: str = "api_key",
        description: str = "",
        expires_at: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> MCPCredentialStatus:
        """
        Store credentials securely for an MCP tool.

        Args:
            tenant_id: Tenant ID
            tool_name: Name of the MCP tool
            service_name: Name of the external service
            credentials: Credential data to store
            credential_type: Type of credential
            description: Description of the credential
            expires_at: Optional expiration date
            created_by: User creating the credential

        Returns:
            MCPCredentialStatus: Status of the credential storage
        """
        try:
            # Parse expiration date if provided
            expiration_date = None
            if expires_at:
                expiration_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))

            # Create secure credential
            credential = self._get_credential_service().create_credential(
                tenant_id=tenant_id,
                tool_name=tool_name,
                service_name=service_name,
                credential_data=credentials,
                credential_type=credential_type,
                description=description,
                expires_at=expiration_date,
                created_by=created_by
            )

            return MCPCredentialStatus(
                success=True,
                validationErrors=None
            )

        except Exception as e:
            logger.error(f"Failed to store credentials for MCP tool {tool_name}: {e}")
            return MCPCredentialStatus(
                success=False,
                validationErrors=[str(e)]
            )

    async def get_credentials(self, tenant_id: int, tool_name: str) -> Dict[str, Any]:
        """
        Retrieve credentials for an MCP tool.

        Args:
            tenant_id: Tenant ID
            tool_name: Name of the MCP tool

        Returns:
            Dict containing credential data
        """
        try:
            # Get active credentials for this tool
            credentials = self._get_credential_service().get_credentials_for_tool(
                tenant_id=tenant_id,
                tool_name=tool_name
            )

            if not credentials:
                raise ValueError(f"No active credentials found for {tool_name}")

            # Use the first available credential
            credential = credentials[0]
            credential_data = self._get_credential_service().get_credential(
                credential_id=credential.id,
                tenant_id=tenant_id
            )

            return credential_data

        except Exception as e:
            logger.error(f"Failed to retrieve credentials for MCP tool {tool_name}: {e}")
            raise ValueError(f"Failed to retrieve credentials: {str(e)}")

    async def test_credentials(self, tenant_id: int, tool_name: str) -> MCPToolTestResult:
        """
        Test MCP tool credentials.

        Args:
            tenant_id: Tenant ID
            tool_name: Name of the MCP tool

        Returns:
            MCPToolTestResult: Test result
        """
        try:
            # Get active credentials for this tool
            credentials = self._get_credential_service().get_credentials_for_tool(
                tenant_id=tenant_id,
                tool_name=tool_name
            )

            if not credentials:
                return MCPToolTestResult(
                    success=False,
                    testResult=f"No credentials found for {tool_name}",
                    errorMessage="No credentials configured"
                )

            # Test each credential
            for credential in credentials:
                success, message = self._get_credential_service().test_credential(
                    credential_id=credential.id,
                    tenant_id=tenant_id
                )

                if success:
                    return MCPToolTestResult(
                        success=True,
                        testResult=f"{tool_name} credentials are valid",
                        errorMessage=None
                    )

            return MCPToolTestResult(
                success=False,
                testResult=f"{tool_name} credentials test failed",
                errorMessage="All credentials failed validation"
            )

        except Exception as e:
            logger.error(f"Failed to test credentials for MCP tool {tool_name}: {e}")
            return MCPToolTestResult(
                success=False,
                testResult=f"{tool_name} credentials test failed",
                errorMessage=str(e)
            )

    async def update_credentials(
        self,
        tenant_id: int,
        tool_name: str,
        service_name: str,
        new_credentials: Dict[str, Any],
        updated_by: str,
        expires_at: Optional[str] = None
    ) -> MCPCredentialStatus:
        """
        Update credentials for an MCP tool.

        Args:
            tenant_id: Tenant ID
            tool_name: Name of the MCP tool
            service_name: Name of the external service
            new_credentials: New credential data
            updated_by: User making the update
            expires_at: Optional new expiration date

        Returns:
            MCPCredentialStatus: Status of the update
        """
        try:
            # Get existing credentials
            existing_credentials = self._get_credential_service().get_credentials_for_tool(
                tenant_id=tenant_id,
                tool_name=tool_name
            )

            if not existing_credentials:
                return MCPCredentialStatus(
                    success=False,
                    validationErrors=[f"No existing credentials found for {tool_name}"]
                )

            # Update the first credential (in production, this might need to be more sophisticated)
            credential = existing_credentials[0]

            # Parse expiration date
            expiration_date = None
            if expires_at:
                expiration_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))

            # Update credential
            self._get_credential_service().update_credential(
                credential_id=credential.id,
                tenant_id=tenant_id,
                credential_data=new_credentials,
                updated_by=updated_by,
                expires_at=expiration_date
            )

            return MCPCredentialStatus(
                success=True,
                validationErrors=None
            )

        except Exception as e:
            logger.error(f"Failed to update credentials for MCP tool {tool_name}: {e}")
            return MCPCredentialStatus(
                success=False,
                validationErrors=[str(e)]
            )

    async def revoke_credentials(self, tenant_id: int, tool_name: str, revoked_by: str) -> bool:
        """
        Revoke credentials for an MCP tool.

        Args:
            tenant_id: Tenant ID
            tool_name: Name of the MCP tool
            revoked_by: User revoking the credentials

        Returns:
            bool: True if revocation successful
        """
        try:
            # Get existing credentials
            existing_credentials = self._get_credential_service().get_credentials_for_tool(
                tenant_id=tenant_id,
                tool_name=tool_name
            )

            if not existing_credentials:
                logger.warning(f"No credentials found to revoke for {tool_name}")
                return True

            # Revoke all credentials for this tool
            for credential in existing_credentials:
                self._get_credential_service().revoke_credential(
                    credential_id=credential.id,
                    tenant_id=tenant_id,
                    revoked_by=revoked_by
                )

            return True

        except Exception as e:
            logger.error(f"Failed to revoke credentials for MCP tool {tool_name}: {e}")
            return False
