# src/etherion_ai/graphql_schema/integrations_types.py
import strawberry
from typing import Optional, List


@strawberry.type
class IntegrationStatus:
    """
    Represents the status of a service integration.
    
    Example:
    {
      "serviceName": "resend",
      "configurationStatus": "configured",
      "validationErrors": []
    }
    """
    service_name: str = strawberry.field(
        description="The name of the service (e.g., 'resend', 'twitter', 'linkedin')"
    )
    
    configuration_status: str = strawberry.field(
        description="The configuration status ('not_configured', 'configured', 'validation_failed')"
    )
    
    validation_errors: Optional[List[str]] = strawberry.field(
        default=None,
        description="List of validation errors if configuration failed"
    )


@strawberry.input
class IntegrationCredentialsInput:
    """
    Input for storing integration credentials.
    
    Example:
    {
      "serviceName": "resend",
      "credentials": {
        "api_key": "re_123456789"
      }
    }
    """
    service_name: str = strawberry.field(
        description="The name of the service (e.g., 'resend', 'twitter', 'linkedin')"
    )
    
    credentials: str = strawberry.field(
        description="JSON string containing the credentials for the service"
    )