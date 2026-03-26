# src/utils/tenant_context.py
from contextvars import ContextVar
from typing import Optional

# This ContextVar will hold the tenant_id for the current asynchronous context or thread.
tenant_context: ContextVar[Optional[int]] = ContextVar('tenant_id', default=None)

def get_tenant_context() -> Optional[int]:
    """Retrieves the tenant_id from the current context."""
    return tenant_context.get()

def set_tenant_context(tenant_id: Optional[int]) -> None:
    """Sets the tenant_id for the current context."""
    tenant_context.set(tenant_id)