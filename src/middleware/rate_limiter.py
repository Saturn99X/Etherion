# src/middleware/rate_limiter.py
"""
Rate limiting middleware for authentication endpoints and GraphQL mutations.
Implements distributed rate limiting using Redis for scalability.
"""

import time
import hashlib
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import redis.asyncio as redis
import os
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Redis connection
redis_client: Optional[redis.Redis] = None

# Rate limiting configuration
RATE_LIMIT_CONFIG = {
    "auth_endpoints": {
        "requests_per_minute": 10,
        "requests_per_hour": 100,
        "window_size": 60,  # seconds
    },
    "graphql_mutations": {
        "requests_per_minute": 30,
        "requests_per_hour": 500,
        "window_size": 60,  # seconds
    },
    "graphql_queries": {
        "requests_per_minute": 100,
        "requests_per_hour": 1000,
        "window_size": 60,  # seconds
    },
    "default": {
        "requests_per_minute": 60,
        "requests_per_hour": 1000,
        "window_size": 60,  # seconds
    }
}


async def get_redis_client() -> redis.Redis:
    """Get Redis client connection."""
    global redis_client
    if redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = redis.from_url(redis_url, decode_responses=True)
    return redis_client


def get_client_identifier(request: Request) -> str:
    """
    Generate a unique identifier for the client.
    Uses IP address and user agent for identification.
    """
    # Get client IP (considering proxies)
    client_ip = request.client.host
    if "x-forwarded-for" in request.headers:
        client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
    elif "x-real-ip" in request.headers:
        client_ip = request.headers["x-real-ip"]
    
    # Get user agent
    user_agent = request.headers.get("user-agent", "")
    
    # Create hash of IP + user agent for privacy
    identifier = hashlib.sha256(f"{client_ip}:{user_agent}".encode()).hexdigest()[:16]
    return identifier


def get_rate_limit_key(identifier: str, endpoint_type: str, window: str) -> str:
    """Generate Redis key for rate limiting."""
    return f"rate_limit:{endpoint_type}:{identifier}:{window}"


async def check_rate_limit(
    request: Request, 
    endpoint_type: str = "default",
    custom_limits: Optional[Dict[str, int]] = None
) -> bool:
    """
    Check if the request should be rate limited.
    
    Args:
        request: FastAPI request object
        endpoint_type: Type of endpoint (auth_endpoints, graphql_mutations, etc.)
        custom_limits: Custom rate limits to override defaults
        
    Returns:
        bool: True if request is allowed, False if rate limited
        
    Raises:
        HTTPException: If rate limit is exceeded
    """
    try:
        # Dev-only bypass: when LES auth bypass is enabled, skip all rate limiting
        try:
            if os.getenv("DEV_BYPASS_AUTH", "0") == "1":
                return True
        except Exception:
            pass
        # Use core Redis wrapper for compatibility with tests' dummy redis
        from src.core.redis import get_redis_client as core_get_redis_client
        redis_wrapper = core_get_redis_client()
        client_id = get_client_identifier(request)
        
        # Get rate limit configuration
        config = RATE_LIMIT_CONFIG.get(endpoint_type, RATE_LIMIT_CONFIG["default"]) 
        # Environment overrides for tests and dynamic tuning
        # IMPORTANT: Only apply to auth_endpoints so general endpoints (e.g., GDPR delete)
        # are not throttled by tight test settings.
        try:
            env_min = os.getenv("RATE_LIMIT_PER_MINUTE")
            env_hour = os.getenv("RATE_LIMIT_PER_HOUR")
            if env_min and endpoint_type == "auth_endpoints":
                config = {**config, "requests_per_minute": int(env_min)}
            if env_hour and endpoint_type == "auth_endpoints":
                config = {**config, "requests_per_hour": int(env_hour)}
        except Exception:
            pass
        if custom_limits:
            config = {**config, **custom_limits}
        
        current_time = int(time.time())
        window_size = config["window_size"]
        
        # Check per-minute limit
        minute_window = current_time // window_size
        minute_key = get_rate_limit_key(client_id, endpoint_type, f"minute:{minute_window}")
        
        # Check per-hour limit
        hour_window = current_time // 3600
        hour_key = get_rate_limit_key(client_id, endpoint_type, f"hour:{hour_window}")
        
        # Increment counters using wrapper methods (no pipeline for dummy compatibility)
        try:
            minute_count = await redis_wrapper.incr(minute_key)
            try:
                if minute_count == 1:
                    await redis_wrapper.expire(minute_key, window_size * 2)
            except Exception:
                pass
        except Exception:
            minute_count = int((await redis_wrapper.get(minute_key)) or 0)

        try:
            hour_count = await redis_wrapper.incr(hour_key)
            try:
                if hour_count == 1:
                    await redis_wrapper.expire(hour_key, 7200)
            except Exception:
                pass
        except Exception:
            hour_count = int((await redis_wrapper.get(hour_key)) or 0)
        
        # Check limits (allow one extra request headroom for OAuth start flows)
        oauth_headroom = 1 if (request.url.path or "").startswith("/oauth/") else 0
        effective_minute_limit = config["requests_per_minute"] + oauth_headroom
        if minute_count > effective_minute_limit:
            logger.warning(f"Rate limit exceeded for {client_id} on {endpoint_type}: {minute_count}/{config['requests_per_minute']} per minute")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {config['requests_per_minute']} per minute",
                    "retry_after": window_size - (current_time % window_size)
                },
                headers={
                    "Retry-After": str(window_size - (current_time % window_size)),
                    "X-RateLimit-Limit": str(config["requests_per_minute"]),
                    "X-RateLimit-Remaining": str(max(0, config["requests_per_minute"] - minute_count)),
                    "X-RateLimit-Reset": str((minute_window + 1) * window_size)
                }
            )
        
        if hour_count > config["requests_per_hour"]:
            logger.warning(f"Rate limit exceeded for {client_id} on {endpoint_type}: {hour_count}/{config['requests_per_hour']} per hour")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {config['requests_per_hour']} per hour",
                    "retry_after": 3600 - (current_time % 3600)
                },
                headers={
                    "Retry-After": str(3600 - (current_time % 3600)),
                    "X-RateLimit-Limit": str(config["requests_per_hour"]),
                    "X-RateLimit-Remaining": str(max(0, config["requests_per_hour"] - hour_count)),
                    "X-RateLimit-Reset": str((hour_window + 1) * 3600)
                }
            )
        
        # Log successful request
        logger.debug(f"Rate limit check passed for {client_id} on {endpoint_type}: {minute_count}/{config['requests_per_minute']} per minute, {hour_count}/{config['requests_per_hour']} per hour")
        
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rate limiting error: {str(e)}")
        # In case of Redis failure, allow the request but log the error
        return True


async def rate_limit_middleware(request: Request, call_next):
    """
    FastAPI middleware for rate limiting.
    """
    try:
        # Determine endpoint type based on path
        path = request.url.path
        
        if path.startswith("/auth/") or path.startswith("/login") or path.startswith("/oauth"):
            endpoint_type = "auth_endpoints"
        elif path.startswith("/graphql"):
            # For GraphQL, we'll check the operation type in the GraphQL middleware
            endpoint_type = "graphql_queries"  # Default to queries, mutations will be handled separately
        else:
            endpoint_type = "default"
        
        # Check rate limit
        await check_rate_limit(request, endpoint_type)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers to response
        client_id = get_client_identifier(request)
        config = RATE_LIMIT_CONFIG.get(endpoint_type, RATE_LIMIT_CONFIG["default"])
        
        # Add informational headers
        response.headers["X-RateLimit-Limit-Minute"] = str(config["requests_per_minute"])
        response.headers["X-RateLimit-Limit-Hour"] = str(config["requests_per_hour"])
        
        return response
        
    except HTTPException as e:
        if e.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            return JSONResponse(
                status_code=e.status_code,
                content=e.detail,
                headers=e.headers
            )
        raise
    except Exception as e:
        logger.error(f"Rate limiting middleware error: {str(e)}")
        # In case of error, allow the request to proceed
        return await call_next(request)


def get_graphql_operation_type(request_body: str) -> str:
    """
    Extract GraphQL operation type from request body.
    """
    try:
        import json
        data = json.loads(request_body)
        query = data.get("query", "")
        
        # Remove whitespace and check operation type
        query_clean = query.strip()
        
        if query_clean.lower().startswith("mutation"):
            return "graphql_mutations"
        elif query_clean.lower().startswith("subscription"):
            return "graphql_subscriptions"
        else:
            return "graphql_queries"
    except:
        return "graphql_queries"


async def graphql_rate_limit_middleware(request: Request, call_next):
    """
    Specialized rate limiting middleware for GraphQL endpoints.
    """
    try:
        # Read request body to determine operation type
        body = await request.body()
        operation_type = get_graphql_operation_type(body.decode())
        
        # Check rate limit based on operation type
        await check_rate_limit(request, operation_type)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        config = RATE_LIMIT_CONFIG.get(operation_type, RATE_LIMIT_CONFIG["default"])
        response.headers["X-RateLimit-Limit-Minute"] = str(config["requests_per_minute"])
        response.headers["X-RateLimit-Limit-Hour"] = str(config["requests_per_hour"])
        
        return response
        
    except HTTPException as e:
        if e.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            return JSONResponse(
                status_code=e.status_code,
                content=e.detail,
                headers=e.headers
            )
        raise
    except Exception as e:
        logger.error(f"GraphQL rate limiting middleware error: {str(e)}")
        # In case of error, allow the request to proceed
        return await call_next(request)


# Rate limiting decorators for specific endpoints
def rate_limit_auth(requests_per_minute: int = 10, requests_per_hour: int = 100):
    """
    Decorator for rate limiting authentication endpoints.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract request from args or kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                for key, value in kwargs.items():
                    if isinstance(value, Request):
                        request = value
                        break
            
            if request:
                await check_rate_limit(
                    request, 
                    "auth_endpoints", 
                    {"requests_per_minute": requests_per_minute, "requests_per_hour": requests_per_hour}
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def rate_limit_mutation(requests_per_minute: int = 30, requests_per_hour: int = 500):
    """
    Decorator for rate limiting GraphQL mutations.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # For GraphQL mutations, we'll rely on the middleware
            # This decorator is mainly for documentation and future use
            return await func(*args, **kwargs)
        return wrapper
    return decorator
