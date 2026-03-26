import logging
import os
import secrets
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import json
from contextlib import contextmanager

from ..database.db import get_session, session_scope
from ..database.models.secure_credential import SecureCredential, CredentialStatus
from ..auth.service import get_current_user
from ..core.security.audit_logger import log_security_event, SecurityEventType

logger = logging.getLogger(__name__)


class SecureCredentialService:
    """
    Secure credential management service with encryption, audit logging, and access controls.

    This service provides a high-level interface for managing sensitive credentials
    for MCP tools and integrations with proper encryption, access controls, and audit trails.
    """

    def __init__(self):
        self.master_key = self._get_or_create_master_key()
        self.key_rotation_days = int(os.getenv('CREDENTIAL_KEY_ROTATION_DAYS', '90'))

    def _get_or_create_master_key(self) -> str:
        """Get or create the master encryption key."""
        # In production, require GSM/env-provided key; do not generate at runtime
        master_key = os.getenv('MASTER_ENCRYPTION_KEY')
        if master_key:
            return master_key

        allow_dev = os.getenv('ALLOW_DEV_GENERATED_MASTER_KEY', 'false').lower() == 'true'
        environment = os.getenv('APP_ENV', 'development').lower()
        if environment != 'production' and allow_dev:
            # Generate only in explicitly-allowed dev mode
            generated = base64.urlsafe_b64encode(os.urandom(32)).decode()
            logger.warning("Generated dev master key. Set MASTER_ENCRYPTION_KEY for production!")
            return generated

        raise RuntimeError("MASTER_ENCRYPTION_KEY is required in this environment.")

    def _validate_credential_data(self, credential_data: Dict[str, Any], tool_name: str) -> None:
        """Validate credential data for a specific tool."""
        # Define validation rules for each tool
        validation_rules = {
            'mcp_slack': {
                'required_fields': ['bot_token'],
                'optional_fields': ['app_token', 'verification_token']
            },
            'mcp_email': {
                'required_fields': ['api_key'],
                'optional_fields': ['domain', 'from_email']
            },
            'mcp_jira': {
                'required_fields': ['email', 'api_token'],
                'optional_fields': ['site_url']
            },
            'mcp_hubspot': {
                'required_fields': ['api_key'],
                'optional_fields': ['portal_id']
            },
            'mcp_linkedin': {
                'required_fields': ['access_token'],
                'optional_fields': ['refresh_token', 'expires_at']
            },
            'mcp_notion': {
                'required_fields': ['token'],
                'optional_fields': ['workspace_id']
            },
            'mcp_resend': {
                'required_fields': ['api_key'],
                'optional_fields': ['domain_id']
            },
            'mcp_shopify': {
                'required_fields': ['access_token', 'shop_domain'],
                'optional_fields': ['api_version', 'webhook_secret']
            },
            'mcp_twitter': {
                'required_fields': ['api_key', 'api_secret', 'access_token', 'access_token_secret'],
                'optional_fields': ['bearer_token']
            },
            'mcp_redfin': {
                'required_fields': ['api_key'],
                'optional_fields': ['base_url']
            },
            'mcp_zillow': {
                'required_fields': ['api_key'],
                'optional_fields': ['base_url']
            }
        }

        if tool_name not in validation_rules:
            raise ValueError(f"Unknown tool: {tool_name}")

        rules = validation_rules[tool_name]

        # Check required fields
        for field in rules['required_fields']:
            if field not in credential_data or not credential_data[field]:
                raise ValueError(f"Missing required field: {field}")

        # Validate field formats
        for field, value in credential_data.items():
            if isinstance(value, str):
                # Basic validation - check for obviously invalid values
                if len(value.strip()) < 4:
                    raise ValueError(f"Field {field} appears to be too short")
                if value.strip() == 'your_key_here' or value.strip() == 'api_key_here':
                    raise ValueError(f"Field {field} contains placeholder value")

    def create_credential(
        self,
        tenant_id: int,
        tool_name: str,
        service_name: str,
        credential_data: Dict[str, Any],
        credential_type: str = "api_key",
        description: str = "",
        expires_at: Optional[datetime] = None,
        created_by: Optional[str] = None,
        environment: str = "production"
    ) -> SecureCredential:
        """
        Create a new secure credential.

        Args:
            tenant_id: Tenant ID that owns the credential
            tool_name: Name of the MCP tool
            service_name: Name of the external service
            credential_data: Plain text credential data
            credential_type: Type of credential (api_key, oauth_token, etc.)
            description: Human-readable description
            expires_at: Optional expiration date
            created_by: User ID creating the credential
            environment: Environment (development, staging, production)

        Returns:
            SecureCredential: Created credential object
        """
        # Validate credential data
        self._validate_credential_data(credential_data, tool_name)

        try:
            with session_scope() as session:
                # Check for existing credential
                existing = session.query(SecureCredential).filter(
                    SecureCredential.tenant_id == tenant_id,
                    SecureCredential.tool_name == tool_name,
                    SecureCredential.service_name == service_name,
                    SecureCredential.environment == environment,
                    SecureCredential.status == CredentialStatus.ACTIVE
                ).first()

                if existing:
                    raise ValueError(f"Active credential already exists for {tool_name} in {environment}")

                # Create new credential
                credential = SecureCredential(
                    tenant_id=tenant_id,
                    tool_name=tool_name,
                    service_name=service_name,
                    credential_type=credential_type,
                    description=description,
                    environment=environment,
                    expires_at=expires_at,
                    created_by=created_by
                )

                # Encrypt and store credential data
                credential.set_credential_data(credential_data, self.master_key, created_by or "system")

                session.add(credential)
                session.commit()
                session.refresh(credential)

                # Log security event
                log_security_event(
                    event_type=SecurityEventType.CREDENTIAL_CREATED,
                    user_id=created_by,
                    tenant_id=tenant_id,
                    resource_type="credential",
                    resource_id=str(credential.id),
                    details={
                        "tool_name": tool_name,
                        "service_name": service_name,
                        "credential_type": credential_type
                    }
                )

                logger.info(f"Created secure credential for {tool_name} in tenant {tenant_id}")
                return credential

        except Exception as e:
            logger.error(f"Failed to create credential for {tool_name}: {e}")
            raise

    def get_credential(
        self,
        credential_id: int,
        tenant_id: int,
        accessed_by: Optional[str] = None,
        validate_status: bool = True
    ) -> Dict[str, Any]:
        """
        Retrieve and decrypt a credential.

        Args:
            credential_id: ID of the credential
            tenant_id: Tenant ID for access control
            accessed_by: User accessing the credential
            validate_status: Whether to validate credential status

        Returns:
            Dict containing decrypted credential data
        """
        try:
            with session_scope() as session:
                credential = session.query(SecureCredential).filter(
                    SecureCredential.id == credential_id,
                    SecureCredential.tenant_id == tenant_id
                ).first()

                if not credential:
                    raise ValueError(f"Credential {credential_id} not found")

                if validate_status and not credential.is_valid():
                    raise ValueError(f"Credential {credential_id} is not valid")

                # Decrypt and return data
                credential_data = credential.get_credential_data(self.master_key)

                # Record access
                credential.record_access(accessed_by)
                session.commit()

                # Log access
                log_security_event(
                    event_type=SecurityEventType.CREDENTIAL_ACCESSED,
                    user_id=accessed_by,
                    tenant_id=tenant_id,
                    resource_type="credential",
                    resource_id=str(credential_id),
                    details={"tool_name": credential.tool_name}
                )

                return credential_data

        except Exception as e:
            logger.error(f"Failed to retrieve credential {credential_id}: {e}")
            raise

    def get_credentials_for_tool(
        self,
        tenant_id: int,
        tool_name: str,
        environment: str = "production"
    ) -> List[SecureCredential]:
        """Get all credentials for a specific tool."""
        try:
            with session_scope() as session:
                credentials = session.query(SecureCredential).filter(
                    SecureCredential.tenant_id == tenant_id,
                    SecureCredential.tool_name == tool_name,
                    SecureCredential.environment == environment,
                    SecureCredential.status == CredentialStatus.ACTIVE
                ).all()

                return credentials

        except Exception as e:
            logger.error(f"Failed to get credentials for {tool_name}: {e}")
            return []

    def update_credential(
        self,
        credential_id: int,
        tenant_id: int,
        credential_data: Dict[str, Any],
        updated_by: str,
        expires_at: Optional[datetime] = None
    ) -> SecureCredential:
        """
        Update a credential with new data.

        Args:
            credential_id: ID of the credential to update
            tenant_id: Tenant ID for access control
            credential_data: New credential data
            updated_by: User making the update
            expires_at: New expiration date

        Returns:
            Updated credential object
        """
        try:
            with session_scope() as session:
                credential = session.query(SecureCredential).filter(
                    SecureCredential.id == credential_id,
                    SecureCredential.tenant_id == tenant_id
                ).first()

                if not credential:
                    raise ValueError(f"Credential {credential_id} not found")

                if credential.status != CredentialStatus.ACTIVE:
                    raise ValueError(f"Cannot update credential with status {credential.status.value}")

                # Validate new credential data
                self._validate_credential_data(credential_data, credential.tool_name)

                # Update credential data
                credential.rotate_credential(credential_data, self.master_key, updated_by)

                if expires_at:
                    credential.expires_at = expires_at

                credential.update_timestamp()
                session.commit()
                session.refresh(credential)

                # Log update
                log_security_event(
                    event_type=SecurityEventType.CREDENTIAL_UPDATED,
                    user_id=updated_by,
                    tenant_id=tenant_id,
                    resource_type="credential",
                    resource_id=str(credential_id),
                    details={"tool_name": credential.tool_name}
                )

                logger.info(f"Updated credential {credential_id} for {credential.tool_name}")
                return credential

        except Exception as e:
            logger.error(f"Failed to update credential {credential_id}: {e}")
            raise

    def revoke_credential(self, credential_id: int, tenant_id: int, revoked_by: str) -> bool:
        """
        Revoke a credential.

        Args:
            credential_id: ID of the credential to revoke
            tenant_id: Tenant ID for access control
            revoked_by: User revoking the credential

        Returns:
            True if revocation successful
        """
        try:
            with session_scope() as session:
                credential = session.query(SecureCredential).filter(
                    SecureCredential.id == credential_id,
                    SecureCredential.tenant_id == tenant_id
                ).first()

                if not credential:
                    raise ValueError(f"Credential {credential_id} not found")

                credential.revoke_credential()
                session.commit()

                # Log revocation
                log_security_event(
                    event_type=SecurityEventType.CREDENTIAL_REVOKED,
                    user_id=revoked_by,
                    tenant_id=tenant_id,
                    resource_type="credential",
                    resource_id=str(credential_id),
                    details={"tool_name": credential.tool_name}
                )

                logger.info(f"Revoked credential {credential_id} for {credential.tool_name}")
                return True

        except Exception as e:
            logger.error(f"Failed to revoke credential {credential_id}: {e}")
            return False

    def test_credential(self, credential_id: int, tenant_id: int) -> Tuple[bool, str]:
        """
        Test a credential by attempting to decrypt it.

        Args:
            credential_id: ID of the credential to test
            tenant_id: Tenant ID for access control

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Try to decrypt the credential
            credential_data = self.get_credential(credential_id, tenant_id)

            # Basic validation - check if we got valid data
            if not credential_data or not isinstance(credential_data, dict):
                return False, "Invalid credential data structure"

            return True, "Credential is valid and accessible"

        except Exception as e:
            return False, f"Credential test failed: {str(e)}"

    def rotate_master_key(self, new_master_key: str) -> int:
        """
        Rotate the master encryption key for all credentials.

        Args:
            new_master_key: New master key

        Returns:
            Number of credentials rotated
        """
        try:
            rotated_count = 0

            with session_scope() as session:
                # Get all active credentials
                credentials = session.query(SecureCredential).filter(
                    SecureCredential.status == CredentialStatus.ACTIVE
                ).all()

                for credential in credentials:
                    try:
                        # Decrypt with old key
                        old_data = credential.get_credential_data(self.master_key)

                        # Generate new key ID
                        new_key_id = base64.b64encode(os.urandom(16)).decode()

                        # Derive new encryption key
                        new_key = self._derive_key(new_master_key, new_key_id)

                        # Encrypt with new key
                        json_data = json.dumps(old_data).encode()
                        fernet = Fernet(new_key)
                        encrypted_data = fernet.encrypt(json_data).decode()

                        # Update credential
                        credential.encrypted_data = encrypted_data
                        credential.encryption_key_id = new_key_id
                        credential.update_timestamp()

                        rotated_count += 1

                    except Exception as e:
                        logger.error(f"Failed to rotate credential {credential.id}: {e}")
                        continue

                session.commit()

            logger.info(f"Rotated master key for {rotated_count} credentials")
            return rotated_count

        except Exception as e:
            logger.error(f"Failed to rotate master key: {e}")
            raise

    def _derive_key(self, master_key: str, key_id: str) -> bytes:
        """Derive encryption key using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=key_id.encode(),
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(master_key.encode()))

    def cleanup_expired_credentials(self) -> int:
        """Clean up expired credentials."""
        try:
            cleaned_count = 0

            with session_scope() as session:
                expired_credentials = session.query(SecureCredential).filter(
                    SecureCredential.expires_at < datetime.utcnow(),
                    SecureCredential.status == CredentialStatus.ACTIVE
                ).all()

                for credential in expired_credentials:
                    credential.status = CredentialStatus.EXPIRED
                    cleaned_count += 1

                session.commit()

            logger.info(f"Cleaned up {cleaned_count} expired credentials")
            return cleaned_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired credentials: {e}")
            return 0

    def get_credential_audit_log(self, credential_id: int, tenant_id: int) -> List[Dict[str, Any]]:
        """Get audit log for a credential."""
        # This would typically integrate with an audit logging system
        # For now, return basic information
        return []
