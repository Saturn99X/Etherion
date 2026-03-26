# Etherion Security Architecture

## Overview

Etherion implements a multi-layered defense strategy that protects tenant data through a combination of authentication, authorization, encryption, audit logging, and network controls. This document explains the security posture of the platform at a conceptual level. Each layer is independent but works together to create a comprehensive security model.

## Defense in Depth

Etherion uses the principle of defense in depth: even if one security layer is bypassed, others remain intact. The platform implements security controls at three levels:

1. **Boundary Layer**: Network security, rate limiting, CSRF protection
2. **Access Layer**: Authentication, authorization, encryption
3. **Data Layer**: Audit logging, credential management, tenant isolation

### The Trust Boundary

A trust boundary is where data moves between trusted and untrusted zones. In Etherion:

- **Untrusted**: The public internet (browsers, third-party APIs)
- **Semi-trusted**: API clients with valid authentication credentials
- **Trusted**: Internal services running on the bare-metal infrastructure (Matchbox-booted NixOS systems managed by Ansible)

All data crossing these boundaries is validated, encrypted, and logged.

## Layers of Protection

### Layer 1: Network Security

At the network level, Etherion enforces:

- **Egress Filtering**: Outbound connections from the application are restricted to a whitelist of trusted domains. When the application needs to call an external API (e.g., Resend for email, Shopify for e-commerce), the request is validated against network policies before it leaves the server.

- **IP Allowlisting**: Tenants can optionally configure IP ranges from which their users may connect. This prevents token hijacking from unexpected geographic locations or networks.

- **VPN Detection**: The system can check whether a request originates from a VPN, proxy, or hosting provider using third-party intelligence (ipinfo or ipdata). High-risk access is logged but not blocked by default; instead, additional verification may be required.

- **Certificate Validation**: HTTPS endpoints are validated for certificate authenticity and expiry before any connection is made.

**Why this matters**: A compromised internal process should not be able to exfiltrate data by making unexpected network calls. By restricting egress, we prevent lateral movement and data theft through the API surface.

### Layer 2: Authentication & Authorization

All API requests must be authenticated. Etherion uses JWT tokens issued during login or OAuth flows:

- **JWT Tokens**: Bearer tokens signed with a secret key. The token contains the user ID and tenant ID, preventing a user from one tenant from accessing another tenant's data.

- **Session Management**: The token includes a session ID (SHA256 hash of the token itself), which is used for audit correlation and CSRF validation.

- **Authorization Checks**: Before any operation, the system verifies that the requesting user is a member of the target tenant and has the appropriate role (currently USER or ADMIN).

**Why this matters**: Authentication proves who you are; authorization proves you should have access to this specific resource. Together, they form the access control foundation.

### Layer 3: Data at Rest - Encryption

Sensitive data (API keys, OAuth tokens, credentials) is encrypted before storage:

- **SecureCredential Model**: Each credential is stored with PBKDF2-derived encryption keys. The encrypted data is stored in the database with metadata about when it was created, last used, and its status (active, expired, revoked).

- **Vault Integration** (Bare-metal production): For highly sensitive credentials, Etherion can use HashiCorp Vault with AppRole authentication. Credentials are stored at paths like `etherion/{tenant_id}/{service}/{type}`, and access is logged.

- **Database-backed Credentials** (Development/testing): During development, credentials are encrypted in the PostgreSQL database itself using Fernet symmetric encryption.

- **Access Recording**: Every time a credential is decrypted, the access is logged with the user ID, timestamp, and reason. This allows detection of unusual access patterns.

**Why this matters**: Even if the database is breached, encrypted credentials are useless without the encryption key (which is managed separately).

### Layer 4: Data in Motion - CSRF & Security Headers

All state-changing operations (POST, PUT, PATCH, DELETE) are protected:

- **CSRF Tokens**: The double-submit cookie pattern is used. A CSRF token tied to the session is required in the `X-CSRF-Token` header for non-GraphQL REST endpoints. GraphQL mutations require an `Authorization` header (preventing same-site CSRF).

- **Security Headers**: Responses include:
  - `Content-Security-Policy`: Prevents inline script execution
  - `Strict-Transport-Security`: Forces HTTPS
  - `X-Frame-Options`: Prevents clickjacking
  - `X-Content-Type-Options`: Prevents MIME type sniffing

**Why this matters**: CSRF exploits browser behavior where cookies are sent automatically. By requiring an additional token or header that JavaScript cannot read from other domains, we prevent the attack.

### Layer 5: Rate Limiting

Each endpoint has per-tenant and per-IP rate limits:

- **Per-IP Limits**: 100 requests/minute, 1000 requests/hour (general); auth endpoints have stricter limits
- **Per-Tenant Limits**: Applied to GraphQL queries to prevent resource exhaustion
- **Logging**: Rate limit violations are logged with severity MEDIUM

**Why this matters**: Rate limiting prevents brute force attacks (credential guessing, SQL injection scanning) and DoS attacks.

### Layer 6: Input Validation & Sanitization

All user input is validated and sanitized:

- **Pattern Matching**: Inputs are checked against whitelists of allowed characters
- **SQL Injection Detection**: Patterns like `SELECT...FROM`, `UNION`, and stacked queries are detected and logged as security violations
- **XSS Prevention**: HTML is escaped; dangerous patterns like `<script>`, `javascript:`, and event handlers are rejected
- **File Upload Validation**: Filenames are sanitized; only whitelisted extensions are allowed
- **Length Limits**: JSON payloads have a 1MB limit; individual strings have 10KB limits

**Why this matters**: Input validation is the first line of defense against injection attacks. Sanitization ensures that even if malicious input gets through, it cannot be executed.

### Layer 7: Audit Logging

Every security-relevant event is logged:

- **What is logged**:
  - Authentication attempts (success and failure)
  - Authorization failures (user tried to access resource they don't own)
  - Data access and modification (queries, mutations)
  - API key access and rotation
  - Rate limit violations
  - Security violations (detected SQL injection, XSS, etc.)
  - Tool invocations and their parameters

- **Log Structure**: Each audit log entry is a JSON object containing:
  ```json
  {
    "event_id": "unique_hash",
    "timestamp": "2026-03-26T12:34:56Z",
    "event_type": "authentication_success",
    "severity": "low",
    "user_id": "user123",
    "tenant_id": "tenant456",
    "session_id": "abc123...",
    "ip_address": "192.0.2.1",
    "user_agent": "Mozilla/5.0...",
    "endpoint": "/graphql",
    "method": "POST",
    "details": { /* event-specific data */ },
    "success": true
  }
  ```

- **Retention**: Logs are kept for 90 days by default (configurable via `AUDIT_LOG_RETENTION_DAYS`)

- **Real-time Monitoring**: Logs are also published to Redis channels for real-time monitoring dashboards

**Why this matters**: Audit logs are the evidence trail. If a security incident occurs, logs show exactly what happened, who did it, when, and from where. This enables forensic investigation and compliance reporting.

### Layer 8: Tenant Isolation

All operations respect tenant boundaries:

- **Request Context**: Each request carries a `tenant_id` in the JWT token
- **Database Scoping**: Queries are automatically scoped to the tenant's data
- **Audit Logging**: Every access includes the tenant ID, preventing one tenant from seeing another's logs
- **Credential Namespacing**: Credentials are stored with the tenant ID in the key (e.g., `tenant123--resend--api_key`)

**Why this matters**: In a multi-tenant system, the biggest risk is data leakage between tenants. Tenant isolation is a mandatory control that must be present at every layer.

## Threat Model

Etherion protects against these threat vectors:

| Threat | Control | Layer |
|--------|---------|-------|
| Compromised credentials | Rate limiting, account lockout | Boundary |
| Token hijacking | VPN detection, IP allowlisting, HTTPS enforcement | Network/Motion |
| Session fixation | CSRF tokens, session IDs | Boundary |
| SQL injection | Input validation, parameterized queries | Data |
| XSS in UI | Content-Security-Policy, HTML escaping | Motion |
| Unauthorized data access | JWT validation, role-based authorization | Access |
| Lateral movement between tenants | Tenant isolation, scoped queries | Data |
| Credential exposure | Encryption at rest, PBKDF2 derivation | Data |
| Brute force attacks | Rate limiting, account lockout | Boundary |
| Insider threats | Audit logging, access records | Data |
| API abuse | Rate limiting, CSRF protection | Boundary |

## Security Configuration

Security features are configured via environment variables:

```bash
# Audit logging
AUDIT_LOG_DIR=/tmp/etherion/audit          # Where logs are written
AUDIT_LOG_RETENTION_DAYS=90                # How long to keep logs
AUDIT_LOG_MAX_FILE_SIZE=100MB              # Log file rotation size

# Rate limiting
RATELIMIT_ENABLED=true
RATELIMIT_REQUESTS_PER_MINUTE=100
RATELIMIT_REQUESTS_PER_HOUR=1000

# VPN detection
VPN_CHECK_PROVIDER=ipinfo                  # ipinfo or ipdata
IPINFO_TOKEN=<token>
IPDATA_KEY=<key>

# Network security
NETWORK_TRUSTED_DOMAINS=api.shopify.com,resend.com
NETWORK_BLOCKED_DOMAINS=
NETWORK_ALLOWED_IPS=
NETWORK_BLOCKED_IPS=10.0.0.0/8

# CSRF protection
CSRF_PROTECTION_ENABLED=true
CSRF_HEADER_NAME=X-CSRF-Token

# Security headers
SECURITY_HEADERS_ENABLED=true
```

## Best Practices for Operators

1. **Regularly Review Audit Logs**: Check for unusual patterns (multiple failed auth attempts, access from unexpected IPs)
2. **Rotate Secrets**: Change encryption keys and Vault AppRole credentials regularly
3. **Monitor Network Policies**: Ensure egress filters are still appropriate as integrations change
4. **Test Incident Response**: Simulate a breach and practice your response plan
5. **Keep Systems Updated**: Apply patches to NixOS systems managed by Ansible quickly
6. **Enable VPN Detection**: If your tenants use primarily fixed office networks, enable VPN detection to catch unusual access
7. **Set Appropriate Rate Limits**: Balance security (tight limits) with usability (loose limits)

## Further Reading

- [Credential Management](credential-management.md) — How secrets are stored and managed
- [Audit Logging](audit-logging.md) — Understanding audit logs and forensics
- [Rate Limiting & CSRF](rate-limiting-and-csrf.md) — Boundary protection mechanisms
- [Network Security](network-security.md) — Egress filtering and VPN detection
