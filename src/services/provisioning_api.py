import asyncpg
import os
import logging
import asyncio
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.database.models import Tenant
from src.database.db import get_session
from src.auth.service import create_user
from src.utils.tenant_context import set_tenant_session
from src.auth.models import UserAuth

logger = logging.getLogger(__name__)


async def create_tenant_database_role(tenant_id: int) -> Dict[str, Any]:
    """
    Create a limited-privilege PostgreSQL role for tenant isolation.
    
    Args:
        tenant_id: The tenant ID to create a role for
        
    Returns:
        Dict with role creation results
        
    Raises:
        ValueError: If DB_SUPERUSER_URI is not configured
        Exception: If role creation fails
    """
    superuser_uri = os.getenv("DB_SUPERUSER_URI")
    if not superuser_uri:
        raise ValueError("DB_SUPERUSER_URI environment variable must be set for tenant provisioning")
    
    role_name = f"tenant_{tenant_id}"
    
    try:
        conn = await asyncpg.connect(superuser_uri)
        try:
            # Start a transaction for atomic role creation
            await conn.execute("BEGIN;")
            
            # Check if role already exists
            role_exists = await conn.fetchval(
                "SELECT 1 FROM pg_roles WHERE rolname = $1", role_name
            )
            
            if role_exists:
                logger.warning(f"Role {role_name} already exists, skipping creation")
                await conn.execute("COMMIT;")
                return {"success": True, "role_name": role_name, "action": "skipped"}
            
            # Create the tenant-specific role with limited privileges
            await conn.execute(f"CREATE ROLE {role_name} NOLOGIN;")
            logger.info(f"Created role {role_name}")
            
            # Grant basic schema usage
            await conn.execute(f"GRANT USAGE ON SCHEMA public TO {role_name};")
            
            # Grant permissions on all existing tables (will be restricted by RLS policies)
            await conn.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role_name};")
            
            # Grant permissions on future tables
            await conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role_name};")
            
            # Grant usage on sequences for auto-incrementing IDs
            await conn.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role_name};")
            await conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role_name};")
            
            # Grant execute permissions on functions (for stored procedures if any)
            await conn.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {role_name};")
            await conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO {role_name};")
            
            # Commit the role creation
            await conn.execute("COMMIT;")
            logger.info(f"Successfully created and configured role {role_name}")
            
            return {
                "success": True,
                "role_name": role_name,
                "action": "created",
                "permissions": [
                    "USAGE on public schema",
                    "SELECT, INSERT, UPDATE, DELETE on all tables",
                    "USAGE, SELECT on all sequences",
                    "EXECUTE on all functions"
                ]
            }
            
        except Exception as e:
            # Rollback on error
            await conn.execute("ROLLBACK;")
            logger.error(f"Failed to create role {role_name}: {e}")
            raise e
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"Database connection failed for role creation: {e}")
        raise


async def drop_tenant_database_role(tenant_id: int) -> Dict[str, Any]:
    """
    Drop a tenant's PostgreSQL role.
    
    Args:
        tenant_id: The tenant ID whose role should be dropped
        
    Returns:
        Dict with role deletion results
        
    Raises:
        ValueError: If DB_SUPERUSER_URI is not configured
        Exception: If role deletion fails
    """
    superuser_uri = os.getenv("DB_SUPERUSER_URI")
    if not superuser_uri:
        raise ValueError("DB_SUPERUSER_URI environment variable must be set for tenant provisioning")
    
    role_name = f"tenant_{tenant_id}"
    
    try:
        conn = await asyncpg.connect(superuser_uri)
        try:
            # Check if role exists
            role_exists = await conn.fetchval(
                "SELECT 1 FROM pg_roles WHERE rolname = $1", role_name
            )
            
            if not role_exists:
                logger.warning(f"Role {role_name} does not exist, skipping deletion")
                return {"success": True, "role_name": role_name, "action": "skipped"}
            
            # Drop the role (CASCADE to handle any dependencies)
            await conn.execute(f"DROP ROLE IF EXISTS {role_name} CASCADE;")
            logger.info(f"Successfully dropped role {role_name}")
            
            return {
                "success": True,
                "role_name": role_name,
                "action": "dropped"
            }
            
        except Exception as e:
            logger.error(f"Failed to drop role {role_name}: {e}")
            raise e
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"Database connection failed for role deletion: {e}")
        raise


async def create_tenant(subdomain: str, admin_email: str, session: AsyncSession) -> Tenant:
    """
    Create a new tenant with limited-privilege PostgreSQL role.
    
    Args:
        subdomain: Unique subdomain for the tenant
        admin_email: Admin email for the tenant
        session: Database session
        
    Returns:
        Tenant: The created tenant
    """
    # Generate unique tenant_id
    tenant = Tenant(
        tenant_id=Tenant.generate_unique_id(),
        subdomain=subdomain,
        name=subdomain.capitalize() + " Tenant",
        admin_email=admin_email
    )
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    # Create limited-privilege role for tenant isolation
    await create_tenant_database_role(tenant.id)

    return tenant

async def provision_tenant(subdomain: str, admin_email: str, tenant_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Provision a new tenant including admin user creation and database role setup.
    
    Args:
        subdomain: Unique subdomain for the tenant
        admin_email: Admin email for the tenant
        tenant_name: Optional display name for the tenant
        
    Returns:
        Dict with provisioning results
        
    Raises:
        Exception: If provisioning fails at any step
    """
    try:
        # Use unscoped session for tenant creation
        async with get_session(None) as session:
            # Check if subdomain already exists
            existing_tenant = await session.exec(
                select(Tenant).where(Tenant.subdomain == subdomain)
            )
            if existing_tenant.first():
                raise ValueError(f"Tenant with subdomain '{subdomain}' already exists")
            
            # Create tenant record
            tenant = await create_tenant(subdomain, admin_email, session)
            
            # Create admin user
            user_auth = UserAuth(
                user_id="admin_" + tenant.tenant_id, 
                email=admin_email, 
                name="Admin", 
                provider="system"
            )
            user = await create_user(session, user_auth, tenant.id)
            
            logger.info(f"Successfully provisioned tenant {tenant.tenant_id} with subdomain {subdomain}")
            
            return {
                "success": True,
                "tenant_id": tenant.tenant_id,
                "tenant_name": tenant.name,
                "subdomain": tenant.subdomain,
                "admin_user_id": user.user_id,
                "admin_email": admin_email,
                "created_at": tenant.created_at.isoformat()
            }
            
    except Exception as e:
        logger.error(f"Failed to provision tenant with subdomain {subdomain}: {e}")
        raise


async def deprovision_tenant(tenant_id: str) -> Dict[str, Any]:
    """
    Deprovision a tenant by removing database role and marking tenant as inactive.
    
    Args:
        tenant_id: The tenant ID to deprovision
        
    Returns:
        Dict with deprovisioning results
        
    Raises:
        Exception: If deprovisioning fails
    """
    try:
        # Use unscoped session for tenant lookup
        async with get_session(None) as session:
            # Find the tenant
            tenant = await session.exec(
                select(Tenant).where(Tenant.tenant_id == tenant_id)
            )
            tenant = tenant.first()
            
            if not tenant:
                raise ValueError(f"Tenant with ID {tenant_id} not found")
            
            # Drop the database role
            role_result = await drop_tenant_database_role(tenant.id)
            
            # Mark tenant as inactive (soft delete)
            tenant.is_active = False
            await session.commit()
            
            logger.info(f"Successfully deprovisioned tenant {tenant_id}")
            
            return {
                "success": True,
                "tenant_id": tenant_id,
                "subdomain": tenant.subdomain,
                "role_cleanup": role_result,
                "deprovisioned_at": tenant.last_updated_at.isoformat()
            }
            
    except Exception as e:
        logger.error(f"Failed to deprovision tenant {tenant_id}: {e}")
        raise


async def get_tenant_info(tenant_id: str) -> Dict[str, Any]:
    """
    Get information about a tenant including role status.
    
    Args:
        tenant_id: The tenant ID to get info for
        
    Returns:
        Dict with tenant information
        
    Raises:
        Exception: If tenant lookup fails
    """
    try:
        async with get_session(None) as session:
            # Find the tenant
            tenant = await session.exec(
                select(Tenant).where(Tenant.tenant_id == tenant_id)
            )
            tenant = tenant.first()
            
            if not tenant:
                raise ValueError(f"Tenant with ID {tenant_id} not found")
            
            # Check if database role exists
            role_name = f"tenant_{tenant.id}"
    superuser_uri = os.getenv("DB_SUPERUSER_URI")
            role_exists = False
            
            if superuser_uri:
                try:
                    conn = await asyncpg.connect(superuser_uri)
                    try:
                        role_exists = await conn.fetchval(
                            "SELECT 1 FROM pg_roles WHERE rolname = $1", role_name
                        ) is not None
                    finally:
                        await conn.close()
                except Exception as e:
                    logger.warning(f"Could not check role status: {e}")
            
            return {
                "success": True,
                "tenant_id": tenant.tenant_id,
                "tenant_name": tenant.name,
                "subdomain": tenant.subdomain,
                "admin_email": tenant.admin_email,
                "credit_balance": tenant.credit_balance,
                "is_active": tenant.is_active,
                "created_at": tenant.created_at.isoformat(),
                "database_role": {
                    "name": role_name,
                    "exists": role_exists
                }
            }
            
    except Exception as e:
        logger.error(f"Failed to get tenant info for {tenant_id}: {e}")
        raise


async def create_tenant_subdomain(tenant_id: int, subdomain: str, primary_domain: str) -> Dict[str, Any]:
    """
    Create DNS record for tenant subdomain.
    
    Args:
        tenant_id: The tenant ID
        subdomain: The subdomain to create (e.g., "tenant1")
        primary_domain: The primary domain (e.g., "etherionai.com")
        
    Returns:
        Dict with subdomain creation results
    """
    from google.cloud import dns
    try:
        # Initialize DNS client
        dns_client = dns.Client()
        
        # Get the managed zone
        zone_name = os.getenv("DNS_ZONE_NAME", "etherionai-zone")
        zone = dns_client.zone(zone_name)

        # Determine target: prefer hostname (CNAME), fallback to IP (A record)
        lb_hostname = os.getenv("LOAD_BALANCER_HOSTNAME")  # e.g., ghs.googlehosted.com or lb.example.com
        lb_ip = os.getenv("LOAD_BALANCER_IP")
        if not lb_hostname and not lb_ip:
            raise ValueError("Either LOAD_BALANCER_HOSTNAME or LOAD_BALANCER_IP must be set")

        fqdn = f"{subdomain}.{primary_domain}."
        ttl = 300
        if lb_hostname:
            record_set = zone.resource_record_set(
                fqdn,
                "CNAME",
                ttl,
                [lb_hostname if lb_hostname.endswith(".") else f"{lb_hostname}."]
            )
            record_type = "CNAME"
            record_target = lb_hostname
        else:
            record_set = zone.resource_record_set(
                fqdn,
                "A",
                ttl,
                [lb_ip]
            )
            record_type = "A"
            record_target = lb_ip
        
        # Add the record to the zone
        changes = zone.changes()
        changes.add_record_set(record_set)
        changes.create()
        
        logger.info(f"Created DNS record {record_type} {fqdn} -> {record_target}")
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "subdomain": subdomain,
            "full_domain": f"{subdomain}.{primary_domain}",
            "record_type": record_type,
            "target": record_target
        }
        
    except Exception as e:
        logger.error(f"Failed to create subdomain for tenant {tenant_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "tenant_id": tenant_id,
            "subdomain": subdomain
        }


async def create_tenant_ssl_certificate(tenant_id: int, subdomain: str, primary_domain: str) -> Dict[str, Any]:
    """
    Create SSL certificate for tenant subdomain using Certificate Manager.
    
    Args:
        tenant_id: The tenant ID
        subdomain: The subdomain
        primary_domain: The primary domain
        
    Returns:
        Dict with certificate creation results
    """
    from google.cloud import certificatemanager
    try:
        # Initialize Certificate Manager client
        cert_client = certificatemanager.CertificateManagerClient()
        
        # Project and location
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        
        # Certificate name
        cert_name = f"tenant-{tenant_id}-cert"
        full_domain = f"{subdomain}.{primary_domain}"
        
        # Create managed certificate
        certificate = certificatemanager.Certificate(
            name=cert_name,
            managed=certificatemanager.Certificate.ManagedCertificate(
                domains=[full_domain]
            )
        )
        
        # Create the certificate
        parent = f"projects/{project_id}/locations/{location}"
        operation = cert_client.create_certificate(
            parent=parent,
            certificate_id=cert_name,
            certificate=certificate
        )
        
        # Wait for the operation to complete
        result = operation.result(timeout=300)  # 5 minutes timeout
        
        logger.info(f"Created SSL certificate for {full_domain}")
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "certificate_name": cert_name,
            "domain": full_domain,
            "certificate_id": result.name
        }
        
    except Exception as e:
        logger.error(f"Failed to create SSL certificate for tenant {tenant_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "tenant_id": tenant_id,
            "subdomain": subdomain
        }


async def provision_tenant_infrastructure(tenant_id: int, subdomain: str, primary_domain: str, cloud_run_service: str) -> Dict[str, Any]:
    """
    Complete tenant infrastructure provisioning including DNS, SSL, and load balancer.
    
    Args:
        tenant_id: The tenant ID
        subdomain: The subdomain to create
        primary_domain: The primary domain
        cloud_run_service: The Cloud Run service name
        
    Returns:
        Dict with complete provisioning results
    """
    results = {
        "tenant_id": tenant_id,
        "subdomain": subdomain,
        "primary_domain": primary_domain,
        "success": True,
        "steps": {}
    }
    
    try:
        # Step 1: Create DNS record
        dns_result = await create_tenant_subdomain(tenant_id, subdomain, primary_domain)
        results["steps"]["dns"] = dns_result
        if not dns_result["success"]:
            results["success"] = False
            return results
        
        # Step 2: Create SSL certificate
        cert_result = await create_tenant_ssl_certificate(tenant_id, subdomain, primary_domain)
        results["steps"]["ssl_certificate"] = cert_result
        if not cert_result["success"]:
            results["success"] = False
            return results
        
        # Step 3: Create database role
        db_result = await create_tenant_database_role(tenant_id)
        results["steps"]["database_role"] = db_result
        if not db_result["success"]:
            results["success"] = False
            return results
        
        logger.info(f"Successfully provisioned infrastructure for tenant {tenant_id}")
        return results
        
    except Exception as e:
        logger.error(f"Failed to provision infrastructure for tenant {tenant_id}: {e}")
        results["success"] = False
        results["error"] = str(e)
        return results
