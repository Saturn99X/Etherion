# src/etherion_ai/middleware/graphql_logger.py
"""
GraphQL operation logging middleware.
"""

import logging
from typing import Any, Dict, Optional
from strawberry.types import Info as GraphQLResolveInfo

from src.etherion_ai.utils.logging_utils import log_info

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GraphQLOperationLogger:
    """
    Logger for GraphQL operations.
    """
    
    @staticmethod
    async def log_operation(
        info: GraphQLResolveInfo,
        operation_name: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log GraphQL operation information.
        
        Args:
            info: GraphQL resolve information
            operation_name: Name of the GraphQL operation
            variables: GraphQL variables
        """
        try:
            # Get request ID from request state if available
            request_id = getattr(info.context, "request_id", "unknown")
            
            # Extract query from document
            query = info.context.body if hasattr(info.context, "body") else str(info.field_nodes)
            
            # Log the operation using the available log_info function
            log_info(
                "GraphQL operation executed",
                request_id=request_id,
                operation_name=operation_name,
                query=query[:100],  # Truncate query for logging
                variables_count=len(variables) if variables else 0
            )
        except Exception as e:
            logger.error(f"Error logging GraphQL operation: {str(e)}")