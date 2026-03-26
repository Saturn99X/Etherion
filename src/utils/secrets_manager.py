# src/utils/secrets_manager.py
import asyncio
import threading
import time
import os
import json
import sys
from typing import Dict, Optional, Any, List, Set
from dataclasses import dataclass, field
from collections import OrderedDict
import redis
from .secure_string import SecureString
from .logging_utils import get_logger, SecurityEvent, performance_monitor
from .metrics_collector import metrics_collector, record_credential_access, record_cache_operation, record_error
from ..config import get_config
from ..security import enforce_tenant_isolation, validate_tenant_access, log_credential_access
from src.security.credential_manager import CredentialManager


@dataclass
class SecretCacheEntry:
    """Represents a cached secret with expiration time and metadata."""
    value: SecureString
    expires_at: float
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    version: int = 1


@dataclass
class CacheStatistics:
    """Tracks cache performance statistics."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    errors: int = 0
    total_accesses: int = 0
    avg_access_time: float = 0.0


@dataclass
class SingleflightEntry:
    """Represents a singleflight request in progress."""
    future: asyncio.Future
    waiters: Set[asyncio.Future] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)


class SingleflightManager:
    """
    Manages singleflight requests to prevent duplicate concurrent requests for the same resource.
    
    This ensures that if multiple requests come in for the same secret simultaneously,
    only one actual request is made to Google Secret Manager, and all others wait for that result.
    """
    
    def __init__(self, cleanup_interval: int = 300, max_request_age: int = 600, enable_cleanup: bool = True):
        self._active_requests: Dict[str, SingleflightEntry] = {}
        self._lock = asyncio.Lock()
        self._cleanup_interval = cleanup_interval  # Default 5 minutes, can be overridden for testing
        self._max_request_age = max_request_age  # Default 10 minutes, can be overridden for testing
        self._cleanup_task = None
        self._cleanup_started = False
        self._enable_cleanup = enable_cleanup
    
    def _start_cleanup_task(self):
        """Start the cleanup task for expired singleflight entries."""
        if not self._cleanup_started and self._enable_cleanup:
            try:
                if self._cleanup_task is None or self._cleanup_task.done():
                    self._cleanup_task = asyncio.create_task(self._cleanup_expired_requests())
                    self._cleanup_started = True
            except RuntimeError:
                # No event loop running, will start later
                pass
    
    async def _cleanup_expired_requests(self):
        """Clean up expired singleflight requests."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                current_time = time.time()
                
                async with self._lock:
                    expired_keys = []
                    for key, entry in self._active_requests.items():
                        if current_time - entry.created_at > self._max_request_age:
                            expired_keys.append(key)
                    
                    for key in expired_keys:
                        entry = self._active_requests.pop(key, None)
                        if entry and not entry.future.done():
                            entry.future.cancel()
                            # Cancel all waiters
                            for waiter in entry.waiters:
                                if not waiter.done():
                                    waiter.cancel()
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but continue cleanup
                print(f"Error in singleflight cleanup: {e}")
    
    async def get_or_create(self, key: str, coro_func, *args, **kwargs):
        """
        Get or create a singleflight request for the given key.
        
        Args:
            key: Unique identifier for the request
            coro_func: Coroutine function to execute
            *args: Arguments for the coroutine function
            **kwargs: Keyword arguments for the coroutine function
            
        Returns:
            The result of the coroutine function
        """
        # First, check if there's an active request
        async with self._lock:
            if key in self._active_requests:
                entry = self._active_requests[key]
                # Wait for the existing request (even if done, we'll get the cached result)
                try:
                    result = await entry.future
                    return result
                except Exception as e:
                    # Clean up failed request
                    self._active_requests.pop(key, None)
                    raise
        
        # Create a new request
        async with self._lock:
            # Double-check that no one else created a request while we were waiting
            if key in self._active_requests:
                entry = self._active_requests[key]
                # Wait for the existing request
                try:
                    result = await entry.future
                    return result
                except Exception as e:
                    # Clean up failed request
                    self._active_requests.pop(key, None)
                    raise
            
            # Create new request
            future = asyncio.create_task(coro_func(*args, **kwargs))
            entry = SingleflightEntry(future=future)
            self._active_requests[key] = entry
        
        # Wait for the result
        try:
            result = await future
            return result
        except Exception as e:
            # Clean up failed request
            async with self._lock:
                self._active_requests.pop(key, None)
            raise
    
    def get_active_count(self) -> int:
        """Get the number of active singleflight requests."""
        return len(self._active_requests)
    
    def get_active_keys(self) -> List[str]:
        """Get the list of active singleflight request keys."""
        return list(self._active_requests.keys())
    
    async def shutdown(self):
        """Shutdown the singleflight manager and cancel all active requests."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        async with self._lock:
            for entry in self._active_requests.values():
                if not entry.future.done():
                    entry.future.cancel()
                for waiter in entry.waiters:
                    if not waiter.done():
                        waiter.cancel()
            self._active_requests.clear()


class TenantSecretsManager:
    """
    Manages tenant-specific secrets with advanced caching, concurrency control, and distributed caching.
    
    Secret naming convention: [tenant_id]--[service_name]--[key_type]
    Example: tenant123--resend--api_key
    """
    
    def __init__(self):
        # Initialize logger
        self.logger = get_logger("secrets_manager")
        
        # Get environment configuration
        self.config = get_config()
        
        # Cache configuration
        self._cache: OrderedDict[str, SecretCacheEntry] = OrderedDict()
        self._cache_ttl = self.config.get('cache_ttl', 300)  # Use environment-specific TTL
        self._max_cache_size = int(os.getenv('SECRET_CACHE_MAX_SIZE', '1000'))
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._lock_timeout = float(os.getenv('SECRET_CACHE_LOCK_TIMEOUT', '5.0'))
        
        # Cache statistics
        self._stats = CacheStatistics()
        self._stats_lock = threading.Lock()
        
        # Singleflight manager for preventing duplicate concurrent requests
        self._singleflight = SingleflightManager()
        self._credential_manager = CredentialManager()
        
        # Redis configuration for distributed caching
        is_test_env = bool(os.getenv("PYTEST_CURRENT_TEST")) or ("pytest" in sys.modules)
        self._redis_client = None
        redis_config = self.config.get_redis_config()
        self._redis_enabled = bool(redis_config.get('enabled', False)) and not is_test_env
        self._redis_host = redis_config.get('host', 'localhost')
        self._redis_port = redis_config.get('port', 6379)
        self._redis_db = redis_config.get('db', 0)
        self._redis_password = redis_config.get('password')
        self._redis_ssl = redis_config.get('ssl', False)
        self._redis_ttl = int(os.getenv('REDIS_SECRET_TTL', '3600'))  # 1 hour default
        
        # Log initialization
        self.logger.info("Initializing TenantSecretsManager", 
                        redis_enabled=self._redis_enabled,
                        redis_ssl=self._redis_ssl,
                        cache_ttl=self._cache_ttl,
                        max_cache_size=self._max_cache_size)
        
        # Initialize Redis client if enabled
        if self._redis_enabled:
            self._init_redis_client()
        
        # Cache cleanup timer
        self._cleanup_timer = None
        self._start_cleanup_timer()
    
    def _init_redis_client(self) -> None:
        """Initialize Redis client for distributed caching."""
        try:
            import ssl
            ssl_kwargs = {}
            if self._redis_ssl:
                ssl_kwargs = {
                    "ssl": True,
                    "ssl_cert_reqs": ssl.CERT_NONE
                }

            self._redis_client = redis.Redis(
                host=self._redis_host,
                port=self._redis_port,
                db=self._redis_db,
                password=self._redis_password,
                decode_responses=False,
                socket_connect_timeout=30,  # Increased for production
                socket_timeout=30,  # Increased for production
                retry_on_timeout=True,
                health_check_interval=30,
                max_connections=20,  # Connection pool size
                socket_keepalive=True,
                socket_keepalive_options={},
                **ssl_kwargs
            )
            # Test connection
            self._redis_client.ping()
            self.logger.info("Redis client initialized successfully")
        except Exception as e:
            self.logger.error("Failed to initialize Redis client", error=str(e))
            self._redis_client = None
    
    def _start_cleanup_timer(self) -> None:
        """Start a background timer for cache cleanup."""
        def cleanup_expired_entries():
            try:
                self._cleanup_expired_cache_entries()
            except Exception as e:
                self.logger.error(f"Error in cache cleanup: {e}")
            finally:
                # Schedule next cleanup only if not shutting down
                if not getattr(self, '_shutdown', False):
                    self._cleanup_timer = threading.Timer(60.0, cleanup_expired_entries)  # Every minute
                    self._cleanup_timer.daemon = True
                    self._cleanup_timer.start()
        
        self._cleanup_timer = threading.Timer(60.0, cleanup_expired_entries)
        self._cleanup_timer.daemon = True
        self._cleanup_timer.start()
    
    def shutdown(self) -> None:
        """Shutdown the secrets manager and cleanup resources."""
        self._shutdown = True
        if self._cleanup_timer:
            self._cleanup_timer.cancel()
            self._cleanup_timer = None
        
        # Close Redis client if exists
        if hasattr(self, '_redis_client') and self._redis_client:
            try:
                self._redis_client.close()
            except Exception as e:
                self.logger.error(f"Error closing Redis client: {e}")
            finally:
                self._redis_client = None
    
    def _cleanup_expired_cache_entries(self) -> None:
        """Remove expired entries from the cache."""
        current_time = time.time()
        expired_keys = []
        
        with self._lock:
            for key, entry in self._cache.items():
                if current_time > entry.expires_at:
                    expired_keys.append(key)
            
            for key in expired_keys:
                entry = self._cache.pop(key)
                entry.value.clear()
                with self._stats_lock:
                    self._stats.evictions += 1
                
                # Log eviction
                self.logger.info("Cache entry evicted due to expiration", key=key)
    
    def _is_cache_valid(self, cache_entry: SecretCacheEntry) -> bool:
        """Check if a cache entry is still valid."""
        return time.time() < cache_entry.expires_at
    
    def _update_cache_stats(self, hit: bool = True, access_time: float = 0.0) -> None:
        """Update cache statistics."""
        with self._stats_lock:
            self._stats.total_accesses += 1
            if hit:
                self._stats.hits += 1
            else:
                self._stats.misses += 1
            
            # Update average access time
            if access_time > 0:
                total_time = self._stats.avg_access_time * (self._stats.total_accesses - 1) + access_time
                self._stats.avg_access_time = total_time / self._stats.total_accesses
    
    @performance_monitor("get_cached_secret")
    def _get_cached_secret(self, key: str) -> Optional[str]:
        """Retrieve a secret from cache if it exists and is valid."""
        start_time = time.time()
        correlation_id = self.logger._generate_correlation_id()
        
        # Try to acquire lock with timeout
        if not self._lock.acquire(timeout=self._lock_timeout):
            with self._stats_lock:
                self._stats.errors += 1
            self.logger.warning("Failed to acquire cache lock within timeout", 
                              key=key, timeout=self._lock_timeout)
            record_error("secrets_manager", "lock_timeout", key=key)
            raise TimeoutError("Failed to acquire cache lock within timeout")
        
        try:
            # Log audit event for credential access
            self.logger.log_audit_event(
                SecurityEvent.CREDENTIAL_ACCESS,
                "INFO",
                {"operation": "cache_get", "key": key},
                correlation_id=correlation_id
            )
            
            # Check local cache first
            if key in self._cache:
                cache_entry = self._cache.pop(key)  # Remove to update LRU order
                if self._is_cache_valid(cache_entry):
                    # Update access metadata
                    cache_entry.last_accessed = time.time()
                    cache_entry.access_count += 1
                    
                    # Move to end of OrderedDict to mark as recently used
                    self._cache[key] = cache_entry
                    
                    # Update stats
                    access_time = time.time() - start_time
                    self._update_cache_stats(hit=True, access_time=access_time)
                    record_cache_operation("get", True, access_time * 1000)
                    
                    self.logger.debug("Secret retrieved from local cache", 
                                    key=key, 
                                    access_count=cache_entry.access_count,
                                    expires_in=cache_entry.expires_at - time.time())
                    
                    return cache_entry.value.get_value()
                else:
                    # Remove expired entry and clear its memory
                    cache_entry.value.clear()
                    with self._stats_lock:
                        self._stats.evictions += 1
                    self.logger.info("Expired cache entry removed", key=key)
            
            # Check Redis cache if enabled
            if self._redis_enabled and self._redis_client:
                try:
                    redis_key = f"secret:{key}"
                    cached_data = self._redis_client.get(redis_key)
                    if cached_data:
                        data = json.loads(cached_data.decode('utf-8'))
                        secure_value = SecureString(data['value'])
                        expires_at = data['expires_at']
                        
                        if time.time() < expires_at:
                            # Cache in local memory as well
                            cache_entry = SecretCacheEntry(
                                value=secure_value,
                                expires_at=expires_at,
                                last_accessed=time.time(),
                                access_count=1,
                                version=data.get('version', 1)
                            )
                            self._set_cache_entry(key, cache_entry)
                            
                            # Update stats
                            access_time = time.time() - start_time
                            self._update_cache_stats(hit=True, access_time=access_time)
                            record_cache_operation("get_redis", True, access_time * 1000)
                            
                            self.logger.debug("Secret retrieved from Redis cache", 
                                            key=key, 
                                            version=data.get('version', 1))
                            
                            return secure_value.get_value()
                        else:
                            # Expired in Redis, clean it up
                            self._redis_client.delete(redis_key)
                except Exception as e:
                    self.logger.warning("Failed to retrieve from Redis cache", 
                                      key=key, error=str(e))
                    record_error("secrets_manager", "redis_get_failure", key=key)
            
            # Update stats for miss
            access_time = time.time() - start_time
            self._update_cache_stats(hit=False, access_time=access_time)
            record_cache_operation("get", False, access_time * 1000)
            
            self.logger.debug("Secret not found in cache", key=key)
            return None
        finally:
            # Ensure the lock is always released even if we returned early
            try:
                self._lock.release()
            except Exception:
                pass

    @performance_monitor("delete_secret")
    async def delete_secret(self, tenant_id: str, service_name: str, key_type: str) -> bool:
        """
        Delete a tenant-specific secret from storage and clear caches.

        Args:
            tenant_id: Tenant identifier
            service_name: Service name
            key_type: Secret key type (e.g., 'credentials', 'api_key')

        Returns:
            True on best-effort deletion, False otherwise
        """
        secret_key = f"{tenant_id}--{service_name}--{key_type}"
        try:
            # Clear local cache if present
            try:
                if self._lock.acquire(timeout=self._lock_timeout):
                    try:
                        if secret_key in self._cache:
                            entry = self._cache.pop(secret_key)
                            try:
                                entry.value.clear()
                            except Exception:
                                pass
                    finally:
                        self._lock.release()
            except Exception:
                pass

            # Invalidate distributed cache
            try:
                self._invalidate_redis_cache(secret_key)
            except Exception:
                pass

            # Revoke from underlying storage
            try:
                self._credential_manager.revoke_secret(tenant_id, service_name, key_type)
            except Exception:
                # Best-effort; if storage revoke fails, caches are still cleared
                pass

            return True
        except Exception:
            return False
    
    @performance_monitor("set_cache_entry")
    def _set_cache_entry(self, key: str, entry: SecretCacheEntry) -> None:
        """Set a cache entry with LRU eviction if needed."""
        # Remove existing entry if present
        if key in self._cache:
            old_entry = self._cache.pop(key)
            old_entry.value.clear()
        
        # Check if we need to evict entries
        eviction_count = 0
        while len(self._cache) >= self._max_cache_size and self._cache:
            # Remove least recently used entry (first item in OrderedDict)
            oldest_key, oldest_entry = self._cache.popitem(last=False)
            oldest_entry.value.clear()
            with self._stats_lock:
                self._stats.evictions += 1
            eviction_count += 1
            
            self.logger.debug("LRU cache entry evicted", key=oldest_key)
        
        if eviction_count > 0:
            self.logger.info("LRU eviction completed", 
                           evicted_count=eviction_count, 
                           remaining_cache_size=len(self._cache))
        
        # Add new entry
        self._cache[key] = entry
        
        # Update Redis cache if enabled
        if self._redis_enabled and self._redis_client:
            try:
                redis_key = f"secret:{key}"
                data = {
                    'value': entry.value.get_value(),
                    'expires_at': entry.expires_at,
                    'version': entry.version
                }
                self._redis_client.setex(
                    redis_key,
                    self._redis_ttl,
                    json.dumps(data)
                )
                self.logger.debug("Secret stored in Redis cache", key=key)
            except Exception as e:
                self.logger.warning("Failed to update Redis cache", 
                                  key=key, error=str(e))
                record_error("secrets_manager", "redis_set_failure", key=key)
    
    @performance_monitor("set_cached_secret")
    def _set_cached_secret(self, key: str, value: str, version: int = 1) -> None:
        """Store a secret in cache with expiration."""
        correlation_id = self.logger._generate_correlation_id()
        
        # Log audit event for credential storage
        self.logger.log_audit_event(
            SecurityEvent.CREDENTIAL_ACCESS,
            "INFO",
            {"operation": "cache_set", "key": key},
            correlation_id=correlation_id
        )
        
        # Try to acquire lock with timeout
        if not self._lock.acquire(timeout=self._lock_timeout):
            with self._stats_lock:
                self._stats.errors += 1
            self.logger.warning("Failed to acquire cache lock within timeout for set operation", 
                              key=key, timeout=self._lock_timeout)
            record_error("secrets_manager", "lock_timeout_set", key=key)
            raise TimeoutError("Failed to acquire cache lock within timeout")
        
        try:
            # Clear existing entry if present
            if key in self._cache:
                old_entry = self._cache[key]
                old_entry.value.clear()
                self.logger.debug("Existing cache entry cleared", key=key)
            
            expires_at = time.time() + self._cache_ttl
            secure_value = SecureString(value)
            cache_entry = SecretCacheEntry(
                value=secure_value,
                expires_at=expires_at,
                last_accessed=time.time(),
                access_count=0,
                version=version
            )
            
            self._set_cache_entry(key, cache_entry)
            record_credential_access("local_cache", True)
            self.logger.info("Secret stored in cache", key=key, version=version)
        finally:
            self._lock.release()
    
    @performance_monitor("clear_cache")
    def _clear_cache(self) -> None:
        """Clear all cached secrets and wipe their memory."""
        # Try to acquire lock with timeout
        if not self._lock.acquire(timeout=self._lock_timeout):
            with self._stats_lock:
                self._stats.errors += 1
            self.logger.warning("Failed to acquire cache lock within timeout for clear operation")
            record_error("secrets_manager", "lock_timeout_clear")
            raise TimeoutError("Failed to acquire cache lock within timeout")
        
        try:
            cache_size = len(self._cache)
            for cache_entry in self._cache.values():
                cache_entry.value.clear()
            self._cache.clear()
            
            self.logger.info("Local cache cleared", entries_cleared=cache_size)
            
            # Clear Redis cache if enabled
            if self._redis_enabled and self._redis_client:
                try:
                    # This is a simplified approach - in production you might want to be more selective
                    keys = self._redis_client.keys("secret:*")
                    if keys:
                        deleted_count = self._redis_client.delete(*keys)
                        self.logger.info("Redis cache cleared", keys_deleted=deleted_count)
                except Exception as e:
                    self.logger.warning("Failed to clear Redis cache", error=str(e))
                    record_error("secrets_manager", "redis_clear_failure")
        finally:
            self._lock.release()
    
    def _invalidate_redis_cache(self, key: str) -> None:
        """Invalidate a specific entry in Redis cache."""
        if self._redis_enabled and self._redis_client:
            try:
                redis_key = f"secret:{key}"
                result = self._redis_client.delete(redis_key)
                if result > 0:
                    self.logger.debug("Redis cache entry invalidated", key=key)
            except Exception as e:
                self.logger.warning("Failed to invalidate Redis cache entry", 
                                  key=key, error=str(e))
                record_error("secrets_manager", "redis_invalidate_failure", key=key)
    
    @performance_monitor("get_secret")
    async def get_secret(self, tenant_id: str, service_name: str, key_type: str) -> Optional[str]:
        """
        Retrieve a tenant-specific secret.
        
        Args:
            tenant_id: The tenant identifier
            service_name: The service name (e.g., 'resend', 'twitter')
            key_type: The type of key (e.g., 'api_key', 'access_token')
            
        Returns:
            The secret value or None if not found
        """
        # Start cleanup task if not already started
        self._singleflight._start_cleanup_task()
        
        start_time = time.time()
        # Create the secret key using the naming convention
        secret_key = f"{tenant_id}--{service_name}--{key_type}"
        
        # Enforce tenant isolation before accessing the secret
        if not enforce_tenant_isolation(tenant_id, "secret", secret_key, "read"):
            self.logger.warning("Tenant isolation violation prevented secret access",
                              tenant_id=tenant_id,
                              secret_key=secret_key)
            return None
        
        self.logger.info("Retrieving secret", 
                        tenant_id=tenant_id, 
                        service_name=service_name, 
                        key_type=key_type)
        
        # Check cache first
        try:
            cached_value = self._get_cached_secret(secret_key)
            if cached_value:
                duration = time.time() - start_time
                record_credential_access(f"{service_name}_{key_type}", True)
                self.logger.info("Secret retrieved from cache", 
                               tenant_id=tenant_id, 
                               service_name=service_name, 
                               key_type=key_type,
                               duration_ms=duration*1000)
                # Attempt JSON decode for credential-like keys
                return self._maybe_decode_secret(key_type, cached_value)
        except TimeoutError:
            self.logger.warning("Cache lock timeout when retrieving secret", 
                              secret_key=secret_key)
        
        # Use singleflight to prevent duplicate concurrent requests for the same secret
        try:
            secret_value = await self._singleflight.get_or_create(
                secret_key,
                self._retrieve_secret_from_storage,
                secret_key,
                tenant_id,
                service_name,
                key_type
            )
            
            if secret_value:
                # Cache the retrieved secret
                try:
                    self._set_cached_secret(secret_key, secret_value)
                except TimeoutError:
                    self.logger.warning("Cache lock timeout when storing secret", 
                                      secret_key=secret_key)
                
                duration = time.time() - start_time
                record_credential_access(f"{service_name}_{key_type}", True)
                
                # Log credential access to audit logger
                log_credential_access(
                    component="secrets_manager",
                    credential_type=f"{service_name}_{key_type}",
                    tenant_id=tenant_id,
                    success=True,
                    details={"duration_ms": duration*1000}
                )
                
                self.logger.info("Secret retrieved from storage", 
                               tenant_id=tenant_id, 
                               service_name=service_name, 
                               key_type=key_type,
                               duration_ms=duration*1000)
                # Attempt JSON decode for credential-like keys
                return self._maybe_decode_secret(key_type, secret_value)
            else:
                duration = time.time() - start_time
                record_credential_access(f"{service_name}_{key_type}", False)
                
                # Log failed credential access to audit logger
                log_credential_access(
                    component="secrets_manager",
                    credential_type=f"{service_name}_{key_type}",
                    tenant_id=tenant_id,
                    success=False,
                    details={"duration_ms": duration*1000, "reason": "not_found"}
                )
                
                self.logger.info("Secret not found in storage", 
                               tenant_id=tenant_id, 
                               service_name=service_name, 
                               key_type=key_type,
                               duration_ms=duration*1000)
        except Exception as e:
            with self._stats_lock:
                self._stats.errors += 1
            self.logger.error("Error retrieving secret", 
                            secret_key=secret_key, 
                            error=str(e))
            record_error("secrets_manager", "get_secret_failure", secret_key=secret_key)
            return None
        
        return None
    
    def _should_json_decode(self, key_type: str, value: str) -> bool:
        """Determine if a secret should be JSON-decoded.
        Decodes common credential key types or when the payload looks like JSON.
        """
        try:
            if not isinstance(value, str):
                return False
            key_type = (key_type or "").lower()
            if key_type in {
                "oauth_credentials",
                "credentials",
                "oauth_client",
                "user_token_credentials",
                "webhook_secret",
            }:
                return True
            v = value.lstrip()
            return (v.startswith("{") and v.endswith("}")) or (v.startswith("[") and v.endswith("]"))
        except Exception:
            return False

    def _maybe_decode_secret(self, key_type: str, value: Any) -> Any:
        """Return JSON-decoded value when appropriate; otherwise return as-is."""
        try:
            if not isinstance(value, str):
                return value
            if not self._should_json_decode(key_type, value):
                return value
            return json.loads(value)
        except Exception:
            return value
    
    async def _retrieve_secret_from_storage(self, secret_key: str, tenant_id: str, service_name: str, key_type: str) -> Optional[str]:
        """
        Retrieve a secret from storage (Google Secret Manager or simulation).
        This method is called by singleflight to ensure only one request per secret.
        
        Args:
            secret_key: The secret key
            tenant_id: The tenant identifier
            service_name: The service name
            key_type: The type of key
            
        Returns:
            The secret value or None if not found
        """
        try:
            # Retrieve secret from Google Secret Manager
            secret_value = self._credential_manager.get_secret(tenant_id, service_name, key_type)
            
            self.logger.info("Secret retrieved from storage via singleflight", 
                           secret_key=secret_key,
                           tenant_id=tenant_id,
                           service_name=service_name,
                           key_type=key_type,
                           found=secret_value is not None)
            
            return secret_value
            
        except Exception as e:
            self.logger.error("Error in singleflight secret retrieval", 
                            secret_key=secret_key, 
                            error=str(e))
            raise
    
    @performance_monitor("store_secret")
    async def store_secret(self, tenant_id: str, service_name: str, key_type: str, value: str) -> bool:
        """
        Store a tenant-specific secret.
        
        Args:
            tenant_id: The tenant identifier
            service_name: The service name (e.g., 'resend', 'twitter')
            key_type: The type of key (e.g., 'api_key', 'access_token')
            value: The secret value to store
            
        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()
        # Create the secret key using the naming convention
        secret_key = f"{tenant_id}--{service_name}--{key_type}"
        
        # Enforce tenant isolation before storing the secret
        if not enforce_tenant_isolation(tenant_id, "secret", secret_key, "write"):
            self.logger.warning("Tenant isolation violation prevented secret storage",
                              tenant_id=tenant_id,
                              secret_key=secret_key)
            return False
        
        self.logger.info("Storing secret", 
                        tenant_id=tenant_id, 
                        service_name=service_name, 
                        key_type=key_type)
        
        try:
            # Store secret in Google Secret Manager
            self._credential_manager.store_secret(tenant_id, service_name, key_type, value)
            
            # Assume success if no exception was raised
            success = True
            
            if success:
                # Update cache
                try:
                    self._set_cached_secret(secret_key, value)
                    # Invalidate Redis cache to ensure consistency
                    self._invalidate_redis_cache(secret_key)
                except TimeoutError:
                    self.logger.warning("Cache lock timeout when storing secret", 
                                      secret_key=secret_key)
                
                duration = time.time() - start_time
                record_credential_access(f"{service_name}_{key_type}", True)
                self.logger.info("Secret stored successfully", 
                               tenant_id=tenant_id, 
                               service_name=service_name, 
                               key_type=key_type,
                               duration_ms=duration*1000)
                return True
            else:
                duration = time.time() - start_time
                record_credential_access(f"{service_name}_{key_type}", False)
                self.logger.warning("Failed to store secret", 
                                  tenant_id=tenant_id, 
                                  service_name=service_name, 
                                  key_type=key_type,
                                  duration_ms=duration*1000)
                return False
        except Exception as e:
            with self._stats_lock:
                self._stats.errors += 1
            self.logger.error("Error storing secret", 
                            secret_key=secret_key, 
                            error=str(e))
            record_error("secrets_manager", "store_secret_failure", secret_key=secret_key)
            return False
    
    @performance_monitor("set_secret")
    async def set_secret(
        self,
        tenant_id: str,
        service_name: str,
        key_type: str,
        secret_value: Optional[Any] = None,
        value: Optional[Any] = None,
    ) -> bool:
        """
        Convenience wrapper to store a secret, accepting either raw strings or dicts.

        Accepts either `secret_value` or `value` (for compatibility with existing code).
        Dicts/lists will be JSON-serialized. Strings are stored as-is.
        """
        payload = secret_value if secret_value is not None else value
        if payload is None:
            self.logger.warning("set_secret called without a value", service_name=service_name, key_type=key_type)
            return False

        try:
            if isinstance(payload, (dict, list)):
                serialized = json.dumps(payload, separators=(",", ":"))
            else:
                serialized = str(payload)
        except Exception as e:
            self.logger.error("Failed to serialize secret payload", error=str(e))
            return False

        return await self.store_secret(tenant_id, service_name, key_type, serialized)
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        with self._stats_lock:
            stats = {
                'hits': self._stats.hits,
                'misses': self._stats.misses,
                'evictions': self._stats.evictions,
                'errors': self._stats.errors,
                'total_accesses': self._stats.total_accesses,
                'hit_ratio': self._stats.hits / max(self._stats.total_accesses, 1),
                'avg_access_time': self._stats.avg_access_time,
                'current_cache_size': len(self._cache),
                'max_cache_size': self._max_cache_size,
                'redis_enabled': self._redis_enabled
            }
            self.logger.debug("Cache statistics retrieved", **stats)
            return stats
    
    def get_cache_contents(self) -> List[Dict[str, Any]]:
        """Get information about cached entries (without exposing actual secrets)."""
        with self._lock:
            entries = []
            current_time = time.time()
            for key, entry in self._cache.items():
                entries.append({
                    'key': key,
                    'expires_in': max(0, entry.expires_at - current_time),
                    'last_accessed': entry.last_accessed,
                    'access_count': entry.access_count,
                    'version': entry.version
                })
            self.logger.debug("Cache contents retrieved", entry_count=len(entries))
            return entries
    
    def clear_statistics(self) -> None:
        """Reset cache statistics."""
        with self._stats_lock:
            self._stats.hits = 0
            self._stats.misses = 0
            self._stats.evictions = 0
            self._stats.errors = 0
            self._stats.total_accesses = 0
            self._stats.avg_access_time = 0.0
        self.logger.info("Cache statistics cleared")
    
    
    def get_singleflight_stats(self) -> Dict[str, Any]:
        """Get statistics about singleflight requests."""
        return {
            "active_requests": self._singleflight.get_active_count(),
            "active_keys": self._singleflight.get_active_keys()
        }
    
    async def shutdown(self):
        """Shutdown the secrets manager and clean up resources."""
        try:
            # Cancel cleanup timer
            if self._cleanup_timer:
                self._cleanup_timer.cancel()
            
            # Shutdown singleflight manager
            await self._singleflight.shutdown()
            
            # Clear cache
            self._clear_cache()
            
            self.logger.info("TenantSecretsManager shutdown completed")
        except Exception as e:
            self.logger.error("Error during shutdown", error=str(e))
    
    def __del__(self):
        """Destructor to ensure all cached secrets are cleared."""
        try:
            # Cancel cleanup timer
            if self._cleanup_timer:
                self._cleanup_timer.cancel()
            
            self._clear_cache()
            self.logger.info("TenantSecretsManager destroyed")
        except Exception as e:
            self.logger.error("Error during destruction", error=str(e))
            # Ignore any errors during destruction
            pass
