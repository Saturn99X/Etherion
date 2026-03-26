# Network Security in Etherion

## Overview

Network security in Etherion is about controlling what the application can access and who can access the application. The system enforces outbound access policies (egress filtering), detects risky access patterns (VPN detection), and validates SSL certificates. This document focuses on network_security.py and vpn_check.py, which implement these controls.

## Security Zones and Policies

Etherion segments the network into security zones and defines policies governing traffic between them:

```
┌─────────────────────────────────────────────────┐
│                   EXTERNAL                      │
│  (Untrusted Internet)                           │
│  ├─ api.shopify.com                             │
│  ├─ resend.com                                  │
│  ├─ twitter.com                                 │
│  └─ evil-attacker.com                           │
└──────────────────┬──────────────────────────────┘
                   │
          Network Security Policy
          (Validate against whitelist)
                   │
                   ▼
┌──────────────────────────────────────┐
│         INTERNAL                     │
│  (NixOS servers running Etherion)    │
│  ├─ localhost:8000                   │
│  ├─ postgres:5432                    │
│  ├─ redis:6379                       │
│  └─ vault:8200                       │
└──────────────────────────────────────┘
```

### Zone Types

```python
class SecurityZone(Enum):
    INTERNAL = "internal"        # Private infrastructure
    EXTERNAL = "external"        # Trusted external services
    RESTRICTED = "restricted"    # Blocked/hostile
    PUBLIC = "public"            # Unauthenticated internet
```

### Policy Actions

```python
class NetworkPolicyAction(Enum):
    ALLOW = "allow"
    DENY = "deny"
    LOG = "log"
```

## Default Policies

When the NetworkSecurityManager initializes, it loads default policies:

```python
# Policy 1: Internal to Internal (always allowed)
internal_policy = NetworkPolicy(
    name="internal_to_internal",
    source_zone=SecurityZone.INTERNAL,
    destination_zone=SecurityZone.INTERNAL,
    action=NetworkPolicyAction.ALLOW,
    description="Internal services can talk to each other"
)

# Policy 2: Internal to External (whitelist-based)
external_policy = NetworkPolicy(
    name="internal_to_external",
    source_zone=SecurityZone.INTERNAL,
    destination_zone=SecurityZone.EXTERNAL,
    action=NetworkPolicyAction.ALLOW,
    allowed_domains=[
        "api.shopify.com",
        "resend.com",
        "googleapis.com",
        "storage.googleapis.com"
    ],
    allowed_ports=[443, 80],
    description="Only call whitelisted APIs on standard ports"
)

# Policy 3: Internal to Restricted (always blocked)
restricted_policy = NetworkPolicy(
    name="internal_to_restricted",
    source_zone=SecurityZone.INTERNAL,
    destination_zone=SecurityZone.RESTRICTED,
    action=NetworkPolicyAction.DENY,
    description="Restricted zones are never accessible"
)
```

## Egress Filtering

Egress filtering controls what the application can access. When Etherion needs to call an external API, the request is validated:

```python
# Usage
allowed, reason = validate_api_endpoint("https://api.shopify.com/v1/products")
if not allowed:
    raise NetworkSecurityException(reason)

# Validation flow
def validate_endpoint(url, source_zone=SecurityZone.INTERNAL):
    # 1. Parse URL
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)

    # 2. Create endpoint object
    endpoint = NetworkEndpoint(host=host, port=port, protocol=parsed.scheme)

    # 3. Check if explicitly blocked
    if host in blocked_domains:
        return EndpointValidationResult(
            valid=False,
            reason=f"Domain {host} is explicitly blocked"
        )

    # 4. Check IP address (if host is an IP)
    try:
        ip = ipaddress.ip_address(host)
        # Check if in blocked ranges
        for blocked_range in blocked_ip_ranges:
            if ip in blocked_range:
                return EndpointValidationResult(valid=False, reason="IP in blocked range")
        # Check if in allowed ranges (if any configured)
        if allowed_ip_ranges and ip not in any(allowed_ranges):
            return EndpointValidationResult(valid=False, reason="IP not in allowed ranges")
    except ValueError:
        pass  # Not an IP, proceed to domain checks

    # 5. Check against policies
    for policy in policies:
        if policy.source_zone == source_zone and policy.destination_zone == endpoint.zone:
            if policy.action == NetworkPolicyAction.ALLOW:
                # Check domain allowlist
                if policy.allowed_domains and host not in policy.allowed_domains:
                    continue
                # Check port allowlist
                if policy.allowed_ports and port not in policy.allowed_ports:
                    continue
                return EndpointValidationResult(valid=True, policy=policy)
            elif policy.action == NetworkPolicyAction.DENY:
                return EndpointValidationResult(valid=False, reason="Denied by policy")

    # Default: deny if no policy matches
    return EndpointValidationResult(valid=False, reason="No matching policy")
```

### Real-World Example

**Scenario**: Etherion tries to call the Shopify API during order sync.

```python
url = "https://api.shopify.com/v1/orders"

# Validation
result = network_security_manager.validate_endpoint(url)

# Check: api.shopify.com in whitelist? YES
# Check: port 443 in allowed ports? YES
# Decision: ALLOWED

# Real request
response = httpx.get(url, headers={"X-Shopify-Access-Token": token})
```

**Scenario**: Malicious code tries to exfiltrate data to attacker.com.

```python
url = "https://attacker.com/exfil?data=secrets"

# Validation
result = network_security_manager.validate_endpoint(url)

# Check: attacker.com in whitelist? NO
# Check: matches any trusted domain? NO
# Decision: DENIED

# Exception raised
raise NetworkSecurityException("Domain attacker.com not in whitelist")
# No data is exfiltrated
```

## Certificate Validation

For HTTPS endpoints, SSL/TLS certificates are validated:

```python
class CertificateValidator:
    def validate_certificate(self, host: str, port: int = 443):
        """
        Validate SSL/TLS certificate for a host.

        Returns:
            (valid, reason) tuple
        """
        try:
            # Create SSL context with default CA certificates
            context = ssl.create_default_context()

            # If custom CA cert is provided, load it
            if custom_ca_cert and os.path.exists(custom_ca_cert):
                context.load_verify_locations(custom_ca_cert)

            # Connect and validate
            with socket.create_connection((host, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()

                    # Check expiry
                    not_after = cert.get('notAfter')
                    if not_after:
                        expiry_date = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                        if expiry_date < datetime.utcnow():
                            return False, f"Certificate expired on {not_after}"

                    # Check hostname matches
                    ssl.match_hostname(cert, host)

                    return True, "Certificate valid"

        except ssl.CertificateError as e:
            return False, f"Certificate validation failed: {e}"
        except Exception as e:
            return False, f"Error: {e}"
```

Certificate validation prevents man-in-the-middle (MITM) attacks:

1. **Hostname Verification**: The certificate must be issued for the domain you're connecting to (not for another domain)
2. **Chain Verification**: The certificate must be signed by a trusted CA
3. **Expiry Check**: The certificate must not be expired
4. **Revocation Check** (optional): The certificate must not be revoked

If any check fails, the connection is rejected.

## VPN Detection

VPN and proxy usage can be risky in production because:

1. **Anonymity**: An attacker using a VPN is hard to track
2. **Location spoofing**: An attacker in Russia can appear to be in US
3. **Account takeover**: If a legitimate user's account is accessed from a VPN, it might indicate compromised credentials

Etherion can detect VPN/proxy usage using third-party intelligence:

```python
async def is_vpn_or_proxy(ip: str) -> VPNCheckResult:
    """
    Check if an IP is likely VPN/Proxy/Hosting.

    Args:
        ip: IPv4 address to check

    Returns:
        VPNCheckResult with is_risky flag and reason
    """
    provider = os.getenv("VPN_CHECK_PROVIDER")  # "ipinfo" or "ipdata"

    if provider == "ipinfo":
        # ipinfo.io API
        r = await httpx.get(
            f"https://ipinfo.io/{ip}/privacy?token={IPINFO_TOKEN}"
        )
        data = r.json()

        # Check privacy flags
        if data.get("vpn") or data.get("proxy") or data.get("hosting"):
            return VPNCheckResult(True, "privacy_flag_detected", data)

        # Check ASN (cloud provider heuristic)
        org = data.get("org", "")
        if any(k in org.lower() for k in ["aws", "google", "microsoft", "azure"]):
            return VPNCheckResult(True, "cloud_provider_detected", data)

    elif provider == "ipdata":
        # ipdata.co API
        r = await httpx.get(
            f"https://api.ipdata.co/{ip}?api-key={IPDATA_KEY}"
        )
        data = r.json()

        # Check threat flags
        threat = data.get("threat", {})
        if threat.get("is_proxy") or threat.get("is_tor"):
            return VPNCheckResult(True, "threat_flag_detected", data)

        # Check ASN
        asn_name = (data.get("asn", {}).get("name") or "").lower()
        if any(k in asn_name for k in ["aws", "google", "microsoft"]):
            return VPNCheckResult(True, "cloud_asn_detected", data)

    return VPNCheckResult(False, "clean", data)
```

### Using VPN Detection

In your middleware or resolver:

```python
async def graphql_resolver(context, args):
    ip_address = context.request.client.host
    user_id = context.user_id

    # Check if IP is risky
    vpn_result = await is_vpn_or_proxy(ip_address)

    if vpn_result.is_risky:
        # Option 1: Block and log
        await log_security_violation(
            user_id=user_id,
            ip_address=ip_address,
            violation_type="vpn_access_attempt",
            details=vpn_result.raw
        )
        raise PermissionError("Access from VPN not allowed")

        # Option 2: Require additional verification
        # require_email_confirmation()

        # Option 3: Log and allow (informational)
        # await log_security_event("vpn_access", ...)

    # Proceed normally
    return await execute_query(...)
```

### Cost and Limitations

**Cost**:
- ipinfo: $0.001-0.01 per request (bulk pricing available)
- ipdata: $0.001-0.01 per request (bulk pricing available)
- DIY: Maintain your own IP database (expensive and outdated)

**Limitations**:
- Providers may have 1-2 second latency (network round trip)
- Detection is heuristic (not 100% accurate)
- Residential proxies may not be detected
- Legitimate cloud providers (AWS, Google) are often flagged as risky

**Recommendation**: Use VPN detection for informational logging, not hard blocks. If a tenant requires VPN blocking, add it to their security settings and respect their choice.

## Flow Logging and Egress Monitoring

All egress connections are logged:

```python
class EgressFilter:
    def filter_egress(self, url: str) -> Tuple[bool, str]:
        """Filter and log outbound connections."""
        start_time = time.time()

        # Validate endpoint
        result = self.network_security_manager.validate_endpoint(url)

        # Create flow log
        flow_log = {
            'timestamp': time.time(),
            'url': url,
            'allowed': result.valid,
            'reason': result.reason,
            'validation_time_ms': (time.time() - start_time) * 1000
        }

        # If HTTPS, validate certificate
        if result.endpoint and result.endpoint.protocol == 'https':
            cert_valid, cert_reason = self.certificate_validator.validate_certificate(
                result.endpoint.host,
                result.endpoint.port
            )
            flow_log['certificate_valid'] = cert_valid
            flow_log['certificate_reason'] = cert_reason

            if not cert_valid:
                return False, f"Certificate validation failed: {cert_reason}"

        # Log flow
        self.flow_logs.append(flow_log)

        return result.valid, result.reason

    def get_flow_logs(self, limit=100):
        """Get recent flow logs for auditing."""
        return self.flow_logs[-limit:]
```

Flow logs enable:
1. **Forensic Investigation**: What did the app try to access during the breach?
2. **Compliance**: Demonstrate that outbound access was controlled
3. **Anomaly Detection**: Alert if the app suddenly tries to access new domains

## Configuration

Network security is configured via environment variables:

```bash
# Trusted domains that Etherion can access
NETWORK_TRUSTED_DOMAINS=api.shopify.com,resend.com,googleapis.com

# Domains that are always blocked
NETWORK_BLOCKED_DOMAINS=

# IP ranges that are allowed (CIDR notation)
NETWORK_ALLOWED_IPS=

# IP ranges that are blocked
NETWORK_BLOCKED_IPS=10.0.0.0/8,172.16.0.0/12

# Internal domains (used to determine security zone)
NETWORK_INTERNAL_DOMAINS=localhost,127.0.0.1,internal.etherion.local

# VPN detection
VPN_CHECK_PROVIDER=ipinfo
IPINFO_TOKEN=<token>
IPDATA_KEY=<key>

# SSL/TLS certificate validation
TRUSTED_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
CUSTOM_CA_CERT=/path/to/custom-ca.pem
```

## Bare-Metal Deployment Considerations

In a bare-metal deployment (Matchbox→NixOS→Ansible→Systemd), network security benefits from:

1. **No VPC/VPN Overhead**: Direct connectivity between services on the same VLAN
2. **Easier Egress Filtering**: Firewall rules are simpler with fewer zones
3. **Better Performance**: No cloud API round trips for network validation

### Bare-Metal Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Data Center Network                       │
│  ┌────────────────┐      ┌────────────────┐                │
│  │  NixOS Server  │      │  NixOS Server  │                │
│  │  (Etherion)    │      │  (Vault)       │                │
│  └────────────────┘      └────────────────┘                │
│  ┌────────────────┐      ┌────────────────┐                │
│  │  NixOS Server  │      │  NixOS Server  │                │
│  │  (PostgreSQL)  │      │  (Redis)       │                │
│  └────────────────┘      └────────────────┘                │
└────────────┬───────────────────────┬──────────────────────┘
             │ Internal firewall     │
             │ (VLAN isolation)      │
             │                       │
┌────────────▼───────────────────────▼──────────────────────┐
│             External Firewall / Load Balancer            │
│  - Whitelist external IPs/ports                           │
│  - Rate limit at edge                                     │
│  - SSL/TLS termination                                    │
└────────────┬────────────────────────────────────────────┘
             │
             ▼ Internet
```

### Egress Policy for Bare-Metal

```bash
# In firewall rules or iptables
# Internal server (10.0.0.5) can only reach whitelisted external IPs

# Allow: api.shopify.com (resolve DNS once, add IPs)
iptables -A OUTPUT -o eth0 -d 23.45.67.89 -p tcp --dport 443 -j ACCEPT

# Allow: resend.com
iptables -A OUTPUT -o eth0 -d 34.56.78.90 -p tcp --dport 443 -j ACCEPT

# Block all other external traffic
iptables -A OUTPUT -o eth0 -j DROP

# Allow internal traffic (VLAN)
iptables -A OUTPUT -o eth1 -j ACCEPT
```

This ensures that even if Etherion is compromised, it cannot make unexpected outbound connections.

## Best Practices

1. **Whitelist First**: Start with a whitelist of known-good destinations, not a blacklist
2. **Regular Audits**: Review egress filter logs monthly to catch new unauthorized access patterns
3. **Certificate Pinning**: For critical integrations, pin the SSL certificate instead of relying on CAs
4. **DNS Validation**: Verify that DNS resolves to expected IPs before connecting
5. **Timeout Protection**: Set connection timeouts (10 seconds) to prevent hung connections from exhausting resources
6. **Error Handling**: When egress is blocked, log and alert, don't silently fail
7. **VPN Detection Context**: Don't use VPN detection as the sole basis for blocking; consider the context (time, user behavior, etc.)
8. **Bare-Metal Hardening**: Use multiple layers (network policy, host firewall, application policy) for defense in depth
