from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
import json
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os
from ..db import get_session


class CredentialStatus(str, Enum):
    """Credential status enumeration for lifecycle management."""
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    INVALID = "INVALID"


class SecureCredential(SQLModel, table=True):
    """
    Secure credential storage model with encryption at rest.

    This model stores sensitive credentials for MCP tools and integrations
    with encryption, access controls, and audit logging.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(index=True, description="Tenant that owns this credential")
    user_id: Optional[int] = Field(default=None, index=True, description="User that created this credential")

    # Tool/integration identification
    tool_name: str = Field(index=True, description="Name of the MCP tool or integration")
    service_name: str = Field(index=True, description="Name of the external service")
    environment: str = Field(default="production", index=True, description="Environment (development, staging, production)")

    # Credential metadata
    credential_type: str = Field(description="Type of credential (api_key, oauth_token, etc.)")
    description: str = Field(description="Human-readable description of the credential")
    status: CredentialStatus = Field(default=CredentialStatus.ACTIVE, index=True)

    # Security metadata
    encrypted_data: str = Field(description="Encrypted credential data")
    encryption_key_id: str = Field(description="ID of the encryption key used")
    checksum: str = Field(description="SHA-256 checksum of the encrypted data for integrity")

    # Audit fields
    created_by: Optional[str] = Field(default=None, description="User ID that created the credential")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    last_used_at: Optional[datetime] = Field(default=None, index=True)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(default=None, description="When the credential expires")

    # Access control
    access_count: int = Field(default=0, description="Number of times credential has been accessed")
    last_accessed_by: Optional[str] = Field(default=None, description="Last user to access the credential")

    def update_timestamp(self) -> None:
        """Update the last_updated_at timestamp."""
        self.last_updated_at = datetime.utcnow()

    def record_access(self, user_id: Optional[str] = None) -> None:
        """Record credential access for audit purposes."""
        self.access_count += 1
        self.last_used_at = datetime.utcnow()
        if user_id:
            self.last_accessed_by = user_id

    def is_expired(self) -> bool:
        """Check if credential is expired."""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

    def is_valid(self) -> bool:
        """Check if credential is valid and active."""
        return (
            self.status == CredentialStatus.ACTIVE
            and not self.is_expired()
            and self.encrypted_data is not None
        )

    def get_credential_data(self, decryption_key: str) -> Dict[str, Any]:
        """
        Decrypt and return credential data.

        Args:
            decryption_key: Master key for decryption

        Returns:
            Dict containing the decrypted credential data

        Raises:
            ValueError: If credential is invalid or decryption fails
        """
        if not self.is_valid():
            raise ValueError(f"Credential {self.id} is not valid or active")

        try:
            # Derive encryption key
            key = self._derive_key(decryption_key, self.encryption_key_id)

            # Decrypt data
            fernet = Fernet(key)
            decrypted_data = fernet.decrypt(self.encrypted_data.encode())

            # Parse JSON
            credential_data = json.loads(decrypted_data.decode())

            # Record access
            self.record_access()

            return credential_data

        except Exception as e:
            self.status = CredentialStatus.INVALID
            raise ValueError(f"Failed to decrypt credential: {str(e)}")

    def set_credential_data(self, credential_data: Dict[str, Any], encryption_key: str, created_by: str) -> None:
        """
        Encrypt and store credential data.

        Args:
            credential_data: Plain text credential data
            encryption_key: Master key for encryption
            created_by: User ID creating the credential
        """
        try:
            # Generate unique key ID for this credential
            key_id = base64.b64encode(os.urandom(16)).decode()

            # Derive encryption key
            key = self._derive_key(encryption_key, key_id)

            # Convert to JSON and encrypt
            json_data = json.dumps(credential_data).encode()
            fernet = Fernet(key)
            encrypted_data = fernet.encrypt(json_data).decode()

            # Calculate checksum for integrity
            checksum = self._calculate_checksum(encrypted_data)

            # Store encrypted data
            self.encrypted_data = encrypted_data
            self.encryption_key_id = key_id
            self.checksum = checksum
            self.created_by = created_by
            self.status = CredentialStatus.ACTIVE

        except Exception as e:
            raise ValueError(f"Failed to encrypt credential: {str(e)}")

    def _derive_key(self, master_key: str, key_id: str) -> bytes:
        """Derive encryption key using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=key_id.encode(),
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(master_key.encode()))

    def _calculate_checksum(self, data: str) -> str:
        """Calculate SHA-256 checksum of encrypted data."""
        import hashlib
        return hashlib.sha256(data.encode()).hexdigest()

    def rotate_credential(self, new_credential_data: Dict[str, Any], encryption_key: str, updated_by: str) -> None:
        """
        Rotate credential with new data.

        Args:
            new_credential_data: New credential data
            encryption_key: Master key for encryption
            updated_by: User ID performing the rotation
        """
        # Store old credential data for audit
        old_data = self.get_credential_data(encryption_key)

        # Set new credential data
        self.set_credential_data(new_credential_data, encryption_key, updated_by)

        # Mark as updated
        self.update_timestamp()

    def revoke_credential(self) -> None:
        """Revoke the credential, making it unusable."""
        self.status = CredentialStatus.REVOKED
        self.update_timestamp()

    class Config:
        """Pydantic configuration for ORM compatibility."""
        from_attributes = True
        arbitrary_types_allowed = True

    def __str__(self) -> str:
        return f"SecureCredential(tool='{self.tool_name}', service='{self.service_name}', status='{self.status.value}')"

    def __repr__(self) -> str:
        return f"SecureCredential(id={self.id}, tool='{self.tool_name}', service='{self.service_name}', status='{self.status.value}')"
