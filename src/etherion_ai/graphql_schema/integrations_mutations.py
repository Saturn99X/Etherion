# src/etherion_ai/graphql_schema/integrations_mutations.py
import strawberry
import json
from typing import Optional
from sqlmodel import Session
from src.database.models import Tenant
from src.utils.secrets_manager import TenantSecretsManager
from src.etherion_ai.graphql_schema.output_types import IntegrationStatus
from src.etherion_ai.graphql_schema.input_types import IntegrationInput as IntegrationCredentialsInput
from src.database.db import get_session
from src.auth.service import get_current_user
from src.database.models import User


@strawberry.type
class IntegrationsMutations:
    """GraphQL mutations for managing service integrations."""
    
    @strawberry.mutation
    async def save_integration_credentials(
        self,
        credentials_input: IntegrationCredentialsInput,
        current_user: User = strawberry.dependency(get_current_user),
        db_session: Session = strawberry.dependency(get_session)
    ) -> IntegrationStatus:
        """
        Save integration credentials for a service.
        
        Args:
            credentials_input: Input containing service name and credentials
            current_user: Current authenticated user
            db_session: Database session
            
        Returns:
            IntegrationStatus: Status of the integration after saving credentials
        """
        try:
            # Parse credentials JSON
            try:
                credentials_dict = json.loads(credentials_input.credentials)
            except json.JSONDecodeError as e:
                return IntegrationStatus(
                    serviceName=credentials_input.serviceName,
                    status="validation_failed",
                    validationErrors=[f"Invalid JSON in credentials: {str(e)}"]
                )
            
            # Validate credentials based on service type
            validation_errors = await self._validate_credentials(
                credentials_input.serviceName,
                credentials_dict
            )
            
            if validation_errors:
                return IntegrationStatus(
                    serviceName=credentials_input.serviceName,
                    status="validation_failed",
                    validationErrors=validation_errors
                )
            
            # Store credentials in Secret Manager
            secrets_manager = TenantSecretsManager()
            
            # Store each credential separately
            store_results = []
            for key, value in credentials_dict.items():
                success = await secrets_manager.store_secret(
                    tenant_id=str(current_user.tenant_id),
                    service_name=credentials_input.serviceName,
                    key_type=key,
                    value=str(value)
                )
                store_results.append(success)
            
            # Check if all credentials were stored successfully
            if all(store_results):
                return IntegrationStatus(
                    serviceName=credentials_input.serviceName,
                    status="connected",
                    validationErrors=None
                )
            else:
                return IntegrationStatus(
                    serviceName=credentials_input.serviceName,
                    status="validation_failed",
                    validationErrors=["Failed to store credentials in secret manager"]
                )
                
        except Exception as e:
            return IntegrationStatus(
                serviceName=credentials_input.serviceName,
                status="validation_failed",
                validationErrors=[f"Error saving credentials: {str(e)}"]
            )
    
    async def _validate_credentials(self, service_name: str, credentials: dict) -> list:
        """
        Validate credentials for a specific service.
        
        Args:
            service_name: Name of the service
            credentials: Dictionary of credentials
            
        Returns:
            list: List of validation errors (empty if valid)
        """
        validation_errors = []
        
        # Service-specific validation
        if service_name == "resend":
            if "api_key" not in credentials:
                validation_errors.append("Missing required field: api_key")
            elif not isinstance(credentials["api_key"], str) or len(credentials["api_key"]) < 10:
                validation_errors.append("Invalid API key format")
                
        elif service_name == "twitter":
            required_fields = ["api_key", "api_secret", "access_token", "access_token_secret"]
            for field in required_fields:
                if field not in credentials:
                    validation_errors.append(f"Missing required field: {field}")
                    
        elif service_name == "linkedin":
            required_fields = ["client_id", "client_secret", "access_token"]
            for field in required_fields:
                if field not in credentials:
                    validation_errors.append(f"Missing required field: {field}")
                    
        else:
            validation_errors.append(f"Unsupported service: {service_name}")
            
        return validation_errors