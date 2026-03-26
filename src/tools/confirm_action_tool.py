# src/tools/confirm_action_tool.py
from typing import Any, Dict, Literal, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from .mcp.base_mcp_tool import EnhancedMCPTool, MCPToolResult, AuthType
from src.utils.input_sanitization import InputSanitizer


class ConfirmActionInput(BaseModel):
    action_description: str = Field(
        ...,
        description="Description of the action to confirm",
    )
    action_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the underlying action to be confirmed",
    )
    urgency_level: Literal["low", "medium", "high"] = Field(
        "medium",
        description="Urgency level for prioritization and UX treatment",
    )


class ConfirmActionTool(EnhancedMCPTool):
    def __init__(self):
        super().__init__(
            name="confirm_action",
            description="Present an action to the user for confirmation before execution",
            auth_type=AuthType.CUSTOM,
        )

    def list_operations(self, max_ops: int = 50):
        return ["confirm_action"]

    def _get_operation_schema(self, operation: str):
        if (operation or "").lower() != "confirm_action":
            return None
        return {
            "action_description": {"type": str, "required": True},
            "action_parameters": {"type": dict, "required": False},
            "urgency_level": {"type": str, "required": False},
        }

    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> MCPToolResult:
        if (operation or "").lower() != "confirm_action":
            return MCPToolResult(success=False, error_message=f"Unsupported operation: {operation}")

        """
        Present an action to the user for confirmation.
        
        Args:
            params: Dictionary containing action parameters
                - action_description (str): Description of the action to confirm
                - action_parameters (dict): Parameters for the action
                - urgency_level (str, optional): Urgency level ("low", "medium", "high")
                
        Returns:
            MCPToolResult: Result indicating user confirmation decision
        """
        try:
            # Validate and sanitize required parameters
            if 'action_description' not in params or not params['action_description']:
                return MCPToolResult(
                    success=False,
                    error_message="Missing required field: action_description",
                    error_code="MISSING_FIELD"
                )
            
            # Sanitize input parameters
            action_description = InputSanitizer.sanitize_string(
                str(params['action_description']), 
                max_length=1000
            )
            
            action_parameters = params.get('action_parameters', {})
            if isinstance(action_parameters, dict):
                # Sanitize action parameters
                sanitized_params = {}
                for key, value in action_parameters.items():
                    if isinstance(value, str):
                        sanitized_params[key] = InputSanitizer.sanitize_string(
                            value, 
                            max_length=500
                        )
                    else:
                        sanitized_params[key] = value
                action_parameters = sanitized_params
            
            urgency_level = params.get('urgency_level', 'medium')
            if urgency_level not in ['low', 'medium', 'high']:
                urgency_level = 'medium'
            
            user_id = params.get('user_id', 'unknown')
            
            # Log the confirmation request
            self.logger.info(
                f"Confirmation requested for tenant {tenant_id}, user {user_id}: {action_description}"
            )
            
            # In a real implementation, this would interface with the frontend
            # to display a confirmation dialog to the user
            # For now, we'll simulate user confirmation
            
            # Simulate user confirmation (in a real app, this would wait for actual user input)
            user_confirmed = self._simulate_user_confirmation(
                action_description, 
                action_parameters, 
                urgency_level
            )
            
            # Log the confirmation result
            self.logger.info(
                f"Confirmation result for tenant {tenant_id}, user {user_id}: {user_confirmed}"
            )
            
            if user_confirmed:
                return MCPToolResult(
                    success=True,
                    data={
                        "confirmed": True,
                        "action_description": action_description,
                        "action_parameters": action_parameters,
                        "urgency_level": urgency_level,
                        "confirmation_timestamp": self._get_timestamp(),
                        "tenant_id": tenant_id,
                        "user_id": user_id
                    }
                )
            else:
                return MCPToolResult(
                    success=True,
                    data={
                        "confirmed": False,
                        "action_description": action_description,
                        "action_parameters": action_parameters,
                        "urgency_level": urgency_level,
                        "confirmation_timestamp": self._get_timestamp(),
                        "tenant_id": tenant_id,
                        "user_id": user_id
                    }
                )
                
        except Exception as e:
            return MCPToolResult(
                success=False,
                error_message=f"Error during action confirmation: {str(e)}",
                error_code="CONFIRMATION_ERROR"
            )
    
    def _simulate_user_confirmation(self, action_description: str, 
                                    action_parameters: Dict[str, Any], 
                                    urgency_level: str) -> bool:
        """
        Simulate user confirmation for an action.
        
        In a real implementation, this would:
        1. Send a message to the frontend via WebSocket or other mechanism
        2. Display a confirmation dialog to the user
        3. Wait for user response
        4. Return the user's decision
        
        Args:
            action_description: Description of the action
            action_parameters: Parameters for the action
            urgency_level: Urgency level of the action
            
        Returns:
            bool: True if user confirmed, False otherwise
        """
        # For simulation purposes, we'll log the action and return True
        print(f"[ACTION CONFIRMATION] {urgency_level.upper()} urgency action:")
        print(f"  Description: {action_description}")
        print(f"  Parameters: {action_parameters}")
        print("  Simulating user confirmation: APPROVED")
        
        # In a real implementation, this would actually wait for user input
        # For now, we'll simulate approval for high/medium urgency and rejection for low urgency
        if urgency_level == "low":
            return False
        return True
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def get_schema_hints(self, max_ops: int = 15) -> Dict[str, Any]:
        try:
            schema = ConfirmActionInput.model_json_schema()
        except Exception:
            schema = ConfirmActionInput.schema()
        return {"input_schema": schema}