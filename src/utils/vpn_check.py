import os
from typing import Tuple
import httpx


class VPNCheckResult:
    def __init__(self, is_risky: bool, reason: str = "", raw: dict | None = None):
        self.is_risky = is_risky
        self.reason = reason
        self.raw = raw or {}


async def is_vpn_or_proxy(ip: str) -> VPNCheckResult:
    """Check if an IP is likely VPN/Proxy/Hosting using pluggable providers.
    Providers (selected by VPN_CHECK_PROVIDER env):
      - ipinfo: requires IPINFO_TOKEN; flags privacy.vpn/proxy/hosting or ASN type 'hosting'
      - ipdata: requires IPDATA_KEY; flags threat.is_proxy/is_tor or ASN type 'hosting'
    If provider or token missing, returns not risky.
    """
    ip = (ip or "").strip()
    if not ip or ip.lower() == "unknown":
        return VPNCheckResult(False, "no_ip")

    provider = (os.getenv("VPN_CHECK_PROVIDER") or "").lower().strip()

    try:
        if provider == "ipinfo":
            token = os.getenv("IPINFO_TOKEN")
            if not token:
                return VPNCheckResult(False, "ipinfo_token_missing")
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"https://ipinfo.io/{ip}/privacy?token={token}")
                if r.status_code == 200:
                    data = r.json()
                    if data.get("vpn") or data.get("proxy") or data.get("hosting"):
                        return VPNCheckResult(True, "ipinfo_privacy_flag", data)
                # Fallback to ASN type
                r2 = await client.get(f"https://ipinfo.io/{ip}/json?token={token}")
                if r2.status_code == 200:
                    d2 = r2.json()
                    org = d2.get("org", "")
                    # Heuristic: major cloud ASN keywords
                    if any(k in (org or "").lower() for k in ["amazon", "aws", "google", "gcp", "microsoft", "azure", "digitalocean", "ovh", "hetzner", "linode", "vultr"]):
                        return VPNCheckResult(True, "asn_hosting_heuristic", d2)
            return VPNCheckResult(False, "ipinfo_clean")

        if provider == "ipdata":
            key = os.getenv("IPDATA_KEY")
            if not key:
                return VPNCheckResult(False, "ipdata_key_missing")
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"https://api.ipdata.co/{ip}?api-key={key}")
                if r.status_code == 200:
                    d = r.json()
                    threat = d.get("threat") or {}
                    if threat.get("is_proxy") or threat.get("is_tor") or threat.get("is_datacenter"):
                        return VPNCheckResult(True, "ipdata_threat_flag", d)
                    asn_name = ((d.get("asn") or {}).get("name") or "").lower()
                    if any(k in asn_name for k in ["amazon", "google", "microsoft", "azure", "digitalocean", "ovh", "hetzner", "linode", "vultr"]):
                        return VPNCheckResult(True, "ipdata_asn_hosting", d)
            return VPNCheckResult(False, "ipdata_clean")

        # Unknown provider or not configured
        return VPNCheckResult(False, "provider_not_configured")
    except Exception as e:
        # Fail open (do not block) on provider errors
        return VPNCheckResult(False, f"provider_error:{e}")
