import os
import hashlib
from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Best-effort client IP extraction supporting proxies.
    Order: X-Forwarded-For (first), X-Real-IP, fallback to request.client.host.
    """
    try:
        if not request:
            return "unknown"
        headers = request.headers or {}
        xff = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        xri = headers.get("x-real-ip") or headers.get("X-Real-IP")
        if xri:
            return xri.strip()
        return request.client.host if request.client else "unknown"
    except Exception:
        return "unknown"


def hash_ip(ip: str) -> str:
    """Return a salted SHA-256 hash of the IP to avoid storing raw IPs.
    Uses IP_HASH_SALT env var; falls back to SECRET_KEY; else static dev salt.
    """
    ip = (ip or "").strip()
    salt = os.getenv("IP_HASH_SALT") or os.getenv("SECRET_KEY") or "etherion-dev-salt"
    h = hashlib.sha256()
    h.update((ip + "|" + salt).encode("utf-8"))
    return h.hexdigest()
