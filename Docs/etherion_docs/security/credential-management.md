# Credential Management in Etherion

## Overview

Etherion manages credentials for integrations (Shopify, Resend, Twitter, etc.) with encryption at rest and strict access controls. Credentials are never stored in plain text. Instead, each credential is encrypted using a per-credential encryption key derived with PBKDF2, ensuring that even a database breach does not immediately expose secrets.

## The SecureCredential Model

All credentials in Etherion conform to the `SecureCredential` SQLModel. This is the schema:

```python
class SecureCredential(SQLModel, table=True):
    id: Optional[int]                    # Primary key
    tenant_id: int                       # Which tenant owns this
    user_id: Optional[int]               # Which user created it

    # Identification
    tool_name: str                       # e.g., "resend", "shopify"
    service_name: str                    # e.g., "email_service", "ecommerce"
    environment: str                     # "development", "staging", "production"

    # Metadata
    credential_type: str                 # e.g., "api_key", "oauth_token"
    description: str                     # Human-readable label
    status: CredentialStatus             # ACTIVE, EXPIRED, REVOKED, INVALID

    # Security: Encryption
    encrypted_data: str                  # The actual secret (encrypted)
    encryption_key_id: str               # Which key was used
    checksum: str                        # SHA-256 of encrypted_data for integrity

    # Audit
    created_by: Optional[str]            # User ID
    created_at: datetime                 # When it was stored
    last_used_at: Optional[datetime]     # When the app last accessed it
    last_updated_at: datetime            # When metadata changed
    expires_at: Optional[datetime]       # If applicable

    # Access control
    access_count: int                    # How many times accessed
    last_accessed_by: Optional[str]      # Who accessed it last
```

### Why Each Field Matters

- **tenant_id**: Prevents accidental cross-tenant leakage. A query for `tenant_id=A`'s credentials will never return tenant B's credentials.

- **encryption_key_id**: Enables key rotation. When keys are rotated, old credentials can be re-encrypted with new keys. The old key ID is stored so the correct key is used for decryption.

- **checksum**: Ensures the encrypted data was not corrupted or tampered with. If the checksum doesn't match during decryption, the credential is marked INVALID.

- **access_count & last_accessed_by**: Enables detection of suspicious access patterns. If a credential is accessed 100 times in 5 minutes by user X, that's unusual and should be investigated.

- **status**: Allows credentials to be revoked without deleting them. If an API key is compromised, it's marked REVOKED, and all future access attempts fail gracefully.

## Encryption at Rest

### How Encryption Works

When a credential is stored, Etherion:

1. **Generates a per-credential key ID** (random 16 bytes, base64-encoded)
2. **Derives the encryption key** using PBKDF2:
   ```python
   key = PBKDF2HMAC(
       algorithm=SHA256,
       length=32,
       salt=key_id.encode(),
       iterations=100000,
   ).derive(master_key.encode())
   ```
   The master key is provided at runtime (from environment or Vault).

3. **Encrypts the credential** using Fernet (AES-128 in CBC mode with HMAC):
   ```python
   fernet = Fernet(urlsafe_base64_encode(key))
   encrypted_data = fernet.encrypt(json.dumps(credential_dict).encode())
   ```

4. **Stores the encrypted data, key ID, and checksum**:
   ```python
   credential.encrypted_data = encrypted_data        # The secret
   credential.encryption_key_id = key_id             # How to decrypt it
   credential.checksum = sha256(encrypted_data)      # Integrity check
   ```

### Why PBKDF2?

PBKDF2 is slow (100,000 iterations by default). This is intentional. If an attacker obtains the database and the master key, they would need 100,000 hashing operations per credential to decrypt it. This provides a computational barrier.

### Decryption

To retrieve a credential:

```python
credential.get_credential_data(master_key)
```

This method:

1. Derives the key using the stored key_id
2. Verifies the credential is ACTIVE and not expired
3. Decrypts the data
4. Records the access in `last_used_at` and `access_count` (audit trail)
5. Returns the decrypted data (usually a dict with fields like `api_key`, `client_secret`, etc.)

If decryption fails (wrong key, corrupted data), the credential is marked INVALID.

## Vault Backend (Bare-Metal Production)

In production on bare-metal infrastructure, Etherion can use HashiCorp Vault for even stronger credential management.

### Vault Architecture

```
┌─────────────────────┐
│   Etherion App      │
│  (NixOS System)     │
│                     │
│  CredentialManager  │
│  (Vault Client)     │
└──────────┬──────────┘
           │
    AppRole Auth
    (role_id, secret_id)
           │
           ▼
┌─────────────────────┐
│  HashiCorp Vault    │
│  (Bare-metal)       │
│                     │
│  etherion/          │
│  ├─ tenant123/      │
│  │  ├─ resend/      │
│  │  │  └─ api_key   │
│  │  └─ shopify/     │
│  │     └─ token     │
│  └─ tenant456/      │
│     └─ ...          │
└─────────────────────┘
```

### AppRole Authentication

AppRole is Vault's machine-to-machine authentication:

1. **role_id**: Public identifier (like a username)
2. **secret_id**: Private secret (like a password)

Both are required to authenticate. They are provided to the application at deployment time via environment variables:

```bash
VAULT_ROLE_ID=etherion-app
VAULT_SECRET_ID=<32-char-secret>
VAULT_ADDR=https://vault.internal:8200
```

### Path Convention

Vault credentials follow the path convention:

```
etherion/{tenant_id}/{service}/{type}
```

Examples:

- `etherion/tenant123/resend/api_key` → Resend API key for tenant 123
- `etherion/tenant456/shopify/oauth_token` → OAuth token for Shopify integration
- `etherion/tenant456/shopify/webhook_secret` → Webhook signing secret

This convention ensures:
- Multi-tenancy is explicit (a tenant cannot read another tenant's path)
- Service isolation (Resend secrets are separate from Shopify secrets)
- Type clarity (api_key vs. oauth_token)

### Vault ACL Example

Vault policies enforce fine-grained access:

```hcl
path "etherion/*" {
  capabilities = ["create", "read", "update", "delete"]
}

path "etherion/tenant123/*" {
  capabilities = ["read", "list"]
}

# But not:
path "etherion/tenant456/*" {
  capabilities = ["deny"]
}
```

The Etherion app can read any tenant's secrets (it's the system app), but individual services or tenants cannot.

### Audit Trail

Vault logs all access:

```json
{
  "time": "2026-03-26T12:34:56Z",
  "type": "auth",
  "auth": {
    "client_token": "s.xxx",
    "accessor": "xxx",
    "display_name": "AppRole",
    "policies": ["default", "etherion"]
  },
  "request": {
    "operation": "read",
    "path": "etherion/tenant123/resend/api_key",
    "client_ip": "10.0.0.5"
  }
}
```

## Database-Backed Credentials (Development)

During development and testing, Etherion can use database-backed credentials (encrypted in PostgreSQL) instead of Vault. This is simpler but less secure:

- **Trade-off**: Database credentials are encrypted in the database schema, so a database dump is not immediately useful. However, if an attacker compromises the application process, they can access the master encryption key in memory.

- **Use case**: Local development, CI/CD testing, small deployments where Vault is overkill.

The same `SecureCredential` model is used; the difference is where the encrypted data is stored (PostgreSQL vs. Vault).

## When to Use Vault vs. Database

| Scenario | Recommendation | Reason |
|----------|---|----------|
| Local development | Database | Simpler setup; Vault not available locally |
| Staging/QA | Database | Faster iteration; lower sensitivity |
| Production (multi-tenant) | Vault | Stronger audit trail; separated storage |
| Production (single-tenant) | Database | Acceptable if compliance allows; faster |
| High-security tenants | Vault | Regulatory requirement (HIPAA, PCI-DSS) |
| Key rotation needed | Vault | Vault makes rotation easier |

## Credential Lifecycle

### Creating a Credential

```python
# User provides service name and secret
async def store_credential(tenant_id, service_name, api_key):
    credential = SecureCredential(
        tenant_id=tenant_id,
        tool_name="resend",
        service_name=service_name,
        credential_type="api_key",
        description="Resend email service API key",
        environment="production"
    )

    # Encrypt and store
    credential.set_credential_data(
        {"api_key": api_key},
        encryption_key=master_key,
        created_by=user_id
    )

    # Save to database or Vault
    db.add(credential)
    db.commit()

    # Audit log
    await log_data_modification(
        user_id=user_id,
        tenant_id=tenant_id,
        data_type="credential",
        operation="create",
        details={"service": service_name}
    )
```

### Accessing a Credential

```python
# During GraphQL mutation or API call
async def use_credential(tenant_id, service_name):
    credential = db.query(SecureCredential).filter(
        SecureCredential.tenant_id == tenant_id,
        SecureCredential.service_name == service_name,
        SecureCredential.status == CredentialStatus.ACTIVE
    ).first()

    if not credential:
        raise CredentialNotFound()

    # Decrypt
    decrypted = credential.get_credential_data(master_key)
    api_key = decrypted["api_key"]

    # Audit log
    await log_data_access(
        user_id=user_id,
        tenant_id=tenant_id,
        data_type="credential",
        operation="read",
        details={"service": service_name, "access_count": credential.access_count}
    )

    return api_key
```

### Rotating a Credential

```python
async def rotate_credential(tenant_id, service_name, new_api_key):
    credential = db.query(SecureCredential).filter(
        SecureCredential.tenant_id == tenant_id,
        SecureCredential.service_name == service_name
    ).first()

    # Store old credential for recovery if needed
    old_key = credential.encryption_key_id

    # Set new data (generates new key ID)
    credential.rotate_credential(
        {"api_key": new_api_key},
        encryption_key=master_key,
        updated_by=user_id
    )

    db.commit()

    # Audit log
    await log_data_modification(
        user_id=user_id,
        tenant_id=tenant_id,
        data_type="credential",
        operation="rotate",
        details={"service": service_name, "old_key_id": old_key}
    )
```

### Revoking a Credential

```python
async def revoke_credential(tenant_id, service_name, reason="compromised"):
    credential = db.query(SecureCredential).filter(
        SecureCredential.tenant_id == tenant_id,
        SecureCredential.service_name == service_name
    ).first()

    credential.revoke_credential()
    db.commit()

    # Audit log (CRITICAL severity)
    await log_security_violation(
        user_id=user_id,
        tenant_id=tenant_id,
        violation_type="credential_revoked",
        details={"service": service_name, "reason": reason}
    )
```

## Security Implications

1. **Key Compromise**: If the master encryption key is exposed, all credentials can be decrypted. This is why the master key is stored separately (in Vault, environment variables, or a secrets management system) and not in the application code.

2. **Token Hijacking**: Even if a credential is leaked, the audit logs show which user accessed it and when. Anomalies can be detected.

3. **Credential Reuse**: Etherion tracks when each credential was last used. If a credential is never accessed, it's a candidate for removal.

4. **Compliance**: Audit logs of credential access satisfy compliance requirements (SOC 2, HIPAA, PCI-DSS).

## Best Practices

1. **Rotate Regularly**: Change API keys every 90 days
2. **Monitor Access**: Alert on unusual credential access patterns
3. **Limit Scope**: Each integration should have minimal permissions (least privilege)
4. **Use Short-Lived Tokens**: Prefer OAuth tokens over static API keys
5. **Expire Credentials**: Set `expires_at` for time-limited credentials
6. **Secure the Master Key**: Store it in Vault or a hardware security module (HSM)
7. **Audit Everything**: Review credential access logs weekly

## Troubleshooting

**Q: Credential decryption fails with "INVALID"**
- The encryption key was lost or changed
- The database record was corrupted
- Solution: Regenerate the credential

**Q: Why is access_count increasing but I'm not using it?**
- The system may be periodically checking credential validity
- Another user/service has access
- Solution: Review audit logs for that credential

**Q: Can I export all credentials?**
- No. Credentials are encrypted and only decryptable with the master key
- Even database dumps are useless without the key
- This is intentional
