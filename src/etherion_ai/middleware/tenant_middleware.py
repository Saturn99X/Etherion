from fastapi import Request
from src.auth.jwt import decode_access_token
from src.services.dns_manager import extract_subdomain_from_request, RESERVED_SUBDOMAINS
from src.database.models import Tenant
from sqlmodel import select


async def tenant_middleware(request: Request, call_next):
    """
    Resolve tenant from JWT token or Host subdomain.
    
    Sets request.state.tenant_id and request.state.subdomain for downstream use.
    
    Resolution priority:
    1. JWT token (for authenticated requests)
    2. Host subdomain (for unauthenticated requests to tenant subdomains)
    
    Reserved subdomains (api, app, auth, etc.) are not treated as tenants.
    """
    tenant_id = None
    subdomain = None
    
    # Try JWT first (authenticated requests)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        try:
            token_data = decode_access_token(token)
            tenant_id = token_data.tenant_id
        except Exception:
            pass
    
    # Extract subdomain from Host header
    subdomain = extract_subdomain_from_request(request)
    
    # If subdomain is not reserved and we don't have tenant_id from JWT, look it up
    if subdomain and subdomain not in RESERVED_SUBDOMAINS and not tenant_id:
        # Get database session from request state (set by graphql_context_middleware)
        auth_ctx = getattr(request.state, "auth_context", None)
        if auth_ctx:
            db_session = auth_ctx.get("db_session")
            if db_session:
                try:
                    tenant = db_session.exec(
                        select(Tenant).where(Tenant.subdomain == subdomain)
                    ).first()
                    if tenant:
                        tenant_id = tenant.id
                except Exception:
                    # If lookup fails, don't block request
                    pass
    
    # Set resolved values on request state
    if subdomain and subdomain not in RESERVED_SUBDOMAINS:
        request.state.subdomain = subdomain
    request.state.tenant_id = tenant_id
    
    response = await call_next(request)
    return response
