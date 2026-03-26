# src/utils/network_security.py
import re
import socket
import ssl
import ipaddress
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
import os
import json
import time
from dataclasses import dataclass, field
from enum import Enum


class SecurityZone(Enum):
    """Network security zones."""
    INTERNAL = "internal"
    EXTERNAL = "external"
    RESTRICTED = "restricted"
    PUBLIC = "public"


class NetworkPolicyAction(Enum):
    """Network policy actions."""
    ALLOW = "allow"
    DENY = "deny"
    LOG = "log"


@dataclass
class NetworkEndpoint:
    """Represents a network endpoint."""
    host: str
    port: int
    protocol: str = "https"
    zone: SecurityZone = SecurityZone.EXTERNAL
    trusted: bool = False


@dataclass
class NetworkPolicy:
    """Represents a network security policy."""
    name: str
    source_zone: SecurityZone
    destination_zone: SecurityZone
    action: NetworkPolicyAction
    allowed_domains: List[str] = field(default_factory=list)
    allowed_ips: List[str] = field(default_factory=list)
    allowed_ports: List[int] = field(default_factory=list)
    description: str = ""


@dataclass
class EndpointValidationResult:
    """Result of endpoint validation."""
    valid: bool
    reason: str = ""
    endpoint: Optional[NetworkEndpoint] = None
    policy_matched: Optional[NetworkPolicy] = None


class NetworkSecurityManager:
    """Manages network security policies and endpoint validation."""
    
    def __init__(self):
        self.policies: List[NetworkPolicy] = []
        self.trusted_domains: Set[str] = set()
        self.blocked_domains: Set[str] = set()
        self.allowed_ip_ranges: List[ipaddress.IPv4Network] = []
        self.blocked_ip_ranges: List[ipaddress.IPv4Network] = []
        self._load_default_policies()
        self._load_configuration()
    
    def _load_default_policies(self):
        """Load default network security policies."""
        # Default policy: Allow internal to internal
        internal_policy = NetworkPolicy(
            name="internal_to_internal",
            source_zone=SecurityZone.INTERNAL,
            destination_zone=SecurityZone.INTERNAL,
            action=NetworkPolicyAction.ALLOW,
            description="Allow internal zone communications"
        )
        self.policies.append(internal_policy)
        
        # Default policy: Restrict internal to external
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
            description="Allow external API calls with domain restrictions"
        )
        self.policies.append(external_policy)
        
        # Default policy: Deny internal to restricted
        restricted_policy = NetworkPolicy(
            name="internal_to_restricted",
            source_zone=SecurityZone.INTERNAL,
            destination_zone=SecurityZone.RESTRICTED,
            action=NetworkPolicyAction.DENY,
            description="Deny access to restricted zones"
        )
        self.policies.append(restricted_policy)
    
    def _load_configuration(self):
        """Load network security configuration from environment."""
        # Load trusted domains
        trusted_domains_str = os.getenv('NETWORK_TRUSTED_DOMAINS', '')
        if trusted_domains_str:
            self.trusted_domains.update(trusted_domains_str.split(','))
        
        # Load blocked domains
        blocked_domains_str = os.getenv('NETWORK_BLOCKED_DOMAINS', '')
        if blocked_domains_str:
            self.blocked_domains.update(blocked_domains_str.split(','))
        
        # Load allowed IP ranges
        allowed_ips_str = os.getenv('NETWORK_ALLOWED_IPS', '')
        if allowed_ips_str:
            for ip_range in allowed_ips_str.split(','):
                try:
                    self.allowed_ip_ranges.append(ipaddress.IPv4Network(ip_range.strip()))
                except ValueError:
                    pass  # Ignore invalid IP ranges
        
        # Load blocked IP ranges
        blocked_ips_str = os.getenv('NETWORK_BLOCKED_IPS', '')
        if blocked_ips_str:
            for ip_range in blocked_ips_str.split(','):
                try:
                    self.blocked_ip_ranges.append(ipaddress.IPv4Network(ip_range.strip()))
                except ValueError:
                    pass  # Ignore invalid IP ranges
    
    def add_policy(self, policy: NetworkPolicy):
        """Add a network policy."""
        self.policies.append(policy)
    
    def remove_policy(self, policy_name: str) -> bool:
        """Remove a network policy by name."""
        for i, policy in enumerate(self.policies):
            if policy.name == policy_name:
                del self.policies[i]
                return True
        return False
    
    def validate_endpoint(self, url: str, source_zone: SecurityZone = SecurityZone.INTERNAL) -> EndpointValidationResult:
        """
        Validate a network endpoint against security policies.
        
        Args:
            url: The URL to validate
            source_zone: The source security zone
            
        Returns:
            EndpointValidationResult with validation result
        """
        try:
            # Parse the URL
            parsed_url = urlparse(url)
            host = parsed_url.hostname
            port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
            protocol = parsed_url.scheme
            
            if not host:
                return EndpointValidationResult(
                    valid=False,
                    reason="Invalid URL: missing hostname"
                )
            
            # Create endpoint object
            endpoint = NetworkEndpoint(
                host=host,
                port=port,
                protocol=protocol,
                zone=self._determine_zone(host)
            )
            
            # Check if domain is explicitly blocked
            if host in self.blocked_domains or any(host.endswith(domain) for domain in self.blocked_domains):
                return EndpointValidationResult(
                    valid=False,
                    reason=f"Domain {host} is explicitly blocked",
                    endpoint=endpoint
                )
            
            # Check IP address if it's an IP
            try:
                ip_addr = ipaddress.ip_address(host)
                # Check if IP is in blocked ranges
                for blocked_range in self.blocked_ip_ranges:
                    if ip_addr in blocked_range:
                        return EndpointValidationResult(
                            valid=False,
                            reason=f"IP {host} is in blocked range {blocked_range}",
                            endpoint=endpoint
                        )
                # Check if IP is in allowed ranges (if any are configured)
                if self.allowed_ip_ranges:
                    allowed = False
                    for allowed_range in self.allowed_ip_ranges:
                        if ip_addr in allowed_range:
                            allowed = True
                            break
                    if not allowed:
                        return EndpointValidationResult(
                            valid=False,
                            reason=f"IP {host} is not in allowed ranges",
                            endpoint=endpoint
                        )
            except ValueError:
                # Not an IP address, check domain restrictions
                pass
            
            # Check against policies
            for policy in self.policies:
                if (policy.source_zone == source_zone and 
                    policy.destination_zone == endpoint.zone):
                    
                    # Check if explicitly allowed
                    if policy.action == NetworkPolicyAction.ALLOW:
                        # Check domain allowlist
                        if policy.allowed_domains:
                            if not any(host.endswith(domain) or host == domain for domain in policy.allowed_domains):
                                continue  # Check next policy
                        
                        # Check port allowlist
                        if policy.allowed_ports and port not in policy.allowed_ports:
                            continue  # Check next policy
                        
                        # Policy matches and allows this endpoint
                        return EndpointValidationResult(
                            valid=True,
                            reason="Endpoint allowed by policy",
                            endpoint=endpoint,
                            policy_matched=policy
                        )
                    elif policy.action == NetworkPolicyAction.DENY:
                        # Policy explicitly denies this endpoint
                        return EndpointValidationResult(
                            valid=False,
                            reason=f"Endpoint denied by policy: {policy.name}",
                            endpoint=endpoint,
                            policy_matched=policy
                        )
            
            # Default deny if no policy matches
            return EndpointValidationResult(
                valid=False,
                reason="No matching policy found for endpoint",
                endpoint=endpoint
            )
            
        except Exception as e:
            return EndpointValidationResult(
                valid=False,
                reason=f"Error validating endpoint: {str(e)}"
            )
    
    def _determine_zone(self, host: str) -> SecurityZone:
        """Determine the security zone for a host."""
        # Check if it's an internal domain
        internal_domains = os.getenv('NETWORK_INTERNAL_DOMAINS', 'localhost,127.0.0.1').split(',')
        if any(host.endswith(domain) or host == domain for domain in internal_domains):
            return SecurityZone.INTERNAL
        
        # Check if it's in trusted domains
        if host in self.trusted_domains or any(host.endswith(domain) for domain in self.trusted_domains):
            return SecurityZone.EXTERNAL
        
        # Check if it's an IP address in internal range
        try:
            ip_addr = ipaddress.ip_address(host)
            # Private IP ranges
            private_ranges = [
                ipaddress.IPv4Network('10.0.0.0/8'),
                ipaddress.IPv4Network('172.16.0.0/12'),
                ipaddress.IPv4Network('192.168.0.0/16'),
                ipaddress.IPv4Network('127.0.0.0/8')
            ]
            if any(ip_addr in private_range for private_range in private_ranges):
                return SecurityZone.INTERNAL
        except ValueError:
            pass  # Not an IP address
        
        # Default to external
        return SecurityZone.EXTERNAL
    
    def is_trusted_domain(self, domain: str) -> bool:
        """Check if a domain is trusted."""
        return (domain in self.trusted_domains or 
                any(domain.endswith(trusted_domain) for trusted_domain in self.trusted_domains))
    
    def add_trusted_domain(self, domain: str):
        """Add a trusted domain."""
        self.trusted_domains.add(domain)
    
    def remove_trusted_domain(self, domain: str) -> bool:
        """Remove a trusted domain."""
        if domain in self.trusted_domains:
            self.trusted_domains.remove(domain)
            return True
        return False
    
    def get_policies(self) -> List[NetworkPolicy]:
        """Get all network policies."""
        return self.policies.copy()


class CertificateValidator:
    """Validates SSL/TLS certificates for HTTPS endpoints."""
    
    def __init__(self):
        self.trusted_ca_bundle = os.getenv('TRUSTED_CA_BUNDLE', None)
        self.custom_ca_cert = os.getenv('CUSTOM_CA_CERT', None)
    
    def validate_certificate(self, host: str, port: int = 443) -> Tuple[bool, str]:
        """
        Validate SSL/TLS certificate for a host.
        
        Args:
            host: The hostname to validate
            port: The port to connect to (default: 443)
            
        Returns:
            Tuple of (valid, reason)
        """
        try:
            # Create SSL context
            context = ssl.create_default_context()
            
            # If custom CA cert is provided, load it
            if self.custom_ca_cert and os.path.exists(self.custom_ca_cert):
                context.load_verify_locations(self.custom_ca_cert)
            elif self.trusted_ca_bundle and os.path.exists(self.trusted_ca_bundle):
                context.load_verify_locations(self.trusted_ca_bundle)
            
            # Connect and validate certificate
            with socket.create_connection((host, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    
                    # Check certificate validity
                    not_after = cert.get('notAfter')
                    if not_after:
                        import datetime
                        expiry_date = datetime.datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                        if expiry_date < datetime.datetime.utcnow():
                            return False, f"Certificate expired on {not_after}"
                    
                    # Check certificate matches hostname
                    ssl.match_hostname(cert, host)
                    
                    return True, "Certificate is valid"
                    
        except ssl.CertificateError as e:
            return False, f"Certificate validation failed: {str(e)}"
        except ssl.SSLError as e:
            return False, f"SSL error: {str(e)}"
        except socket.timeout:
            return False, "Connection timeout during certificate validation"
        except Exception as e:
            return False, f"Error validating certificate: {str(e)}"


class EgressFilter:
    """Filters outbound network traffic based on security policies."""
    
    def __init__(self, network_security_manager: NetworkSecurityManager):
        self.network_security_manager = network_security_manager
        self.certificate_validator = CertificateValidator()
        self.flow_logs: List[Dict] = []
        self.max_flow_logs = int(os.getenv('MAX_FLOW_LOGS', '1000'))
    
    def filter_egress(self, url: str, source_zone: SecurityZone = SecurityZone.INTERNAL) -> Tuple[bool, str]:
        """
        Filter egress traffic for a URL.
        
        Args:
            url: The URL to filter
            source_zone: The source security zone
            
        Returns:
            Tuple of (allowed, reason)
        """
        start_time = time.time()
        
        # Validate endpoint
        validation_result = self.network_security_manager.validate_endpoint(url, source_zone)
        
        # Log the flow
        flow_log = {
            'timestamp': time.time(),
            'url': url,
            'source_zone': source_zone.value,
            'allowed': validation_result.valid,
            'reason': validation_result.reason,
            'validation_time_ms': (time.time() - start_time) * 1000
        }
        
        # Add to flow logs
        self.flow_logs.append(flow_log)
        if len(self.flow_logs) > self.max_flow_logs:
            self.flow_logs = self.flow_logs[-self.max_flow_logs:]
        
        if not validation_result.valid:
            return False, validation_result.reason
        
        # Validate certificate for HTTPS endpoints
        if validation_result.endpoint and validation_result.endpoint.protocol == 'https':
            cert_valid, cert_reason = self.certificate_validator.validate_certificate(
                validation_result.endpoint.host, 
                validation_result.endpoint.port
            )
            
            # Add certificate validation to flow log
            flow_log['certificate_valid'] = cert_valid
            flow_log['certificate_reason'] = cert_reason
            
            if not cert_valid:
                return False, f"Certificate validation failed: {cert_reason}"
        
        return True, "Egress traffic allowed"
    
    def get_flow_logs(self, limit: int = 100) -> List[Dict]:
        """Get recent flow logs."""
        return self.flow_logs[-limit:] if self.flow_logs else []


# Global instances
network_security_manager = NetworkSecurityManager()
egress_filter = EgressFilter(network_security_manager)
certificate_validator = CertificateValidator()


def validate_api_endpoint(url: str, source_zone: SecurityZone = SecurityZone.INTERNAL) -> Tuple[bool, str]:
    """
    Validate an API endpoint against network security policies.
    
    Args:
        url: The API endpoint URL to validate
        source_zone: The source security zone
        
    Returns:
        Tuple of (valid, reason)
    """
    return egress_filter.filter_egress(url, source_zone)


def add_trusted_domain(domain: str):
    """Add a trusted domain to the network security manager."""
    network_security_manager.add_trusted_domain(domain)


def remove_trusted_domain(domain: str) -> bool:
    """Remove a trusted domain from the network security manager."""
    return network_security_manager.remove_trusted_domain(domain)


def get_network_policies() -> List[NetworkPolicy]:
    """Get all network policies."""
    return network_security_manager.get_policies()