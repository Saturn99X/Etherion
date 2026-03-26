"""
Environment configuration management for Etherion AI.

This module handles environment-specific configurations and provides
a centralized way to manage different deployment environments.
"""

import os
from typing import Dict, Any, Optional
from enum import Enum


class Environment(Enum):
    """Supported deployment environments."""
    DEVELOPMENT = "dev"
    STAGING = "staging"
    PRODUCTION = "prod"
    TESTING = "test"


class EnvironmentConfig:
    """Configuration manager for different environments."""
    
    def __init__(self, environment: Optional[Environment] = None):
        """
        Initialize environment configuration.
        
        Args:
            environment: The environment to configure. If None, will be detected from ENV variable.
        """
        self.environment = environment or self._detect_environment()
        self.config = self._load_config()
    
    def _detect_environment(self) -> Environment:
        """Detect the current environment from environment variables."""
        env_str = os.getenv('ENVIRONMENT', 'prod').lower()
        # Map common aliases to canonical enum values
        alias_map = {
            'development': 'dev',
            'dev': 'dev',
            'staging': 'staging',
            'stage': 'staging',
            'production': 'prod',
            'prod': 'prod',
            'testing': 'test',
            'test': 'test',
        }
        canonical = alias_map.get(env_str, env_str)
        try:
            return Environment(canonical)
        except ValueError:
            print(f"Warning: Unknown environment '{env_str}', defaulting to development")
            return Environment.DEVELOPMENT
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration for the current environment."""
        base_config = {
            'environment': self.environment.value,
            'debug': self.environment == Environment.DEVELOPMENT,
            'log_level': 'DEBUG' if self.environment == Environment.DEVELOPMENT else 'INFO',
            # Knowledge base and web search backend defaults (Phase 13)
            'kb_backend': 'bq',   # options: 'bq' (authoritative), 'vertex' (legacy gated)
            'use_exa': True,      # controls web search provider usage
            'kb_object_tables_enabled': False,
            'kb_direct_gcs_fetch_enabled': False,
        }
        
        # Environment-specific configurations
        env_configs = {
            Environment.DEVELOPMENT: {
                'database_url_secret': 'etherion-database-url-dev',
                'secret_key_secret': 'etherion-secret-key-dev',
                'jwt_secret': 'etherion-jwt-secret-dev',
                'redis_enabled': False,  # Disable Redis in dev for simplicity
                'cache_ttl': 60,  # Shorter cache TTL for development
                'rate_limit_per_minute': 1000,  # Higher limits for development
                'rate_limit_per_hour': 10000,
                'enable_metrics': False,
                'enable_audit_logging': True,
            },
            Environment.STAGING: {
                'database_url_secret': 'etherion-database-url-staging',
                'secret_key_secret': 'etherion-secret-key-staging',
                'jwt_secret': 'etherion-jwt-secret-staging',
                'redis_enabled': True,
                'cache_ttl': 300,  # 5 minutes
                'rate_limit_per_minute': 120,
                'rate_limit_per_hour': 1000,
                'enable_metrics': True,
                'enable_audit_logging': True,
            },
            Environment.PRODUCTION: {
                'database_url_secret': 'etherion-database-url-prod',
                'secret_key_secret': 'etherion-secret-key-prod',
                'jwt_secret': 'etherion-jwt-secret-prod',
                'redis_enabled': True,
                'cache_ttl': 600,  # 10 minutes
                'rate_limit_per_minute': 120,
                'rate_limit_per_hour': 500,
                'enable_metrics': True,
                'enable_audit_logging': True,
                'kb_object_tables_enabled': True,
                'kb_direct_gcs_fetch_enabled': True,
            },
            Environment.TESTING: {
                'database_url_secret': 'etherion-database-url-test',
                'secret_key_secret': 'etherion-secret-key-test',
                'jwt_secret': 'etherion-jwt-secret-test',
                'redis_enabled': False,
                'cache_ttl': 30,  # Very short for testing
                'rate_limit_per_minute': 10000,  # No limits for testing
                'rate_limit_per_hour': 100000,
                'enable_metrics': False,
                'enable_audit_logging': False,
            }
        }
        
        # Merge base config with environment-specific config
        config = {**base_config, **env_configs.get(self.environment, {})}
        
        # Override with environment variables if present
        config = self._apply_env_overrides(config)
        
        return config
    
    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to the configuration."""
        overrides = {
            'debug': os.getenv('DEBUG'),
            'log_level': os.getenv('LOG_LEVEL'),
            'cache_ttl': os.getenv('SECRET_CACHE_TTL'),
            'rate_limit_per_minute': os.getenv('RATE_LIMIT_PER_MINUTE'),
            'rate_limit_per_hour': os.getenv('RATE_LIMIT_PER_HOUR'),
            'enable_metrics': os.getenv('ENABLE_METRICS'),
            'enable_audit_logging': os.getenv('ENABLE_AUDIT_LOGGING'),
            # New flags
            'kb_backend': os.getenv('KB_BACKEND', 'bq'),
            'use_exa': os.getenv('USE_EXA', 'true'),
            'kb_object_tables_enabled': os.getenv('KB_OBJECT_TABLES_ENABLED'),
            'kb_direct_gcs_fetch_enabled': os.getenv('KB_DIRECT_GCS_FETCH_ENABLED'),
        }

        for key, value in overrides.items():
            if value is not None:
                # Convert string values to appropriate types
                if key in ['debug', 'redis_enabled', 'enable_metrics', 'enable_audit_logging', 'use_exa', 'kb_object_tables_enabled', 'kb_direct_gcs_fetch_enabled']:
                    config[key] = value.lower() in ('true', '1', 'yes', 'on')
                elif key in ['cache_ttl', 'rate_limit_per_minute', 'rate_limit_per_hour']:
                    try:
                        config[key] = int(value)
                    except ValueError:
                        pass  # Keep original value if conversion fails
                else:
                    # passthrough string values like kb_backend
                    config[key] = value

        return config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.config.get(key, default)
    def get_secret_name(self, secret_type: str) -> str:
        """Get the secret name for a specific type in the current environment."""
        secret_mapping = {
            'database_url': 'database_url_secret',
            'secret_key': 'secret_key_secret',
            'jwt_secret': 'jwt_secret',
        }
        
        config_key = secret_mapping.get(secret_type)
        if not config_key:
            raise ValueError(f"Unknown secret type: {secret_type}")
        
        return self.get(config_key)
    
    def is_production(self) -> bool:
        """Check if the current environment is production."""
        return self.environment == Environment.PRODUCTION
    
    def is_development(self) -> bool:
        """Check if the current environment is development."""
        return self.environment == Environment.DEVELOPMENT
    
    def is_testing(self) -> bool:
        """Check if the current environment is testing."""
        return self.environment == Environment.TESTING
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration for the current environment."""
        return {
            'url_secret_name': self.get_secret_name('database_url'),
            'pool_size': 5 if self.is_production() else 2,
            'max_overflow': 10 if self.is_production() else 5,
            'pool_timeout': 30,
            'pool_recycle': 3600,
        }
    
    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration for the current environment."""
        if not self.get('redis_enabled', False):
            return {'enabled': False}
        
        redis_url = os.getenv('REDIS_URL')
        if redis_url:
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            return {
                'enabled': True,
                'host': parsed.hostname,
                'port': parsed.port or 6379,
                'db': int(parsed.path.lstrip('/')) if parsed.path and parsed.path != '/' else 0,
                'password': parsed.password,
                'ssl': parsed.scheme == 'rediss',
                'decode_responses': True,
            }

        return {
            'enabled': True,
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', '6379')),
            'db': int(os.getenv('REDIS_DB', '0')),
            'password': os.getenv('REDIS_PASSWORD'),
            'ssl': self.is_production(),
            'decode_responses': True,
        }
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration for the current environment."""
        return {
            'rate_limit_per_minute': self.get('rate_limit_per_minute', 60),
            'rate_limit_per_hour': self.get('rate_limit_per_hour', 500),
            'enable_audit_logging': self.get('enable_audit_logging', True),
            'jwt_secret_name': self.get_secret_name('jwt_secret'),
            'secret_key_name': self.get_secret_name('secret_key'),
        }
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """Get monitoring configuration for the current environment."""
        return {
            'enable_metrics': self.get('enable_metrics', False),
            'metrics_port': int(os.getenv('METRICS_PORT', '9090')),
            'health_check_path': '/healthz',
            'readiness_check_path': '/ready',
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the configuration to a dictionary."""
        return self.config.copy()


# Global configuration instance
config = EnvironmentConfig()


def get_config() -> EnvironmentConfig:
    """Get the global configuration instance."""
    return config


def get_secret_name(secret_type: str) -> str:
    """Get the secret name for a specific type in the current environment."""
    return config.get_secret_name(secret_type)


def is_production() -> bool:
    """Check if the current environment is production."""
    return config.is_production()


def is_development() -> bool:
    """Check if the current environment is development."""
    return config.is_development()


def is_testing() -> bool:
    """Check if the current environment is testing."""
    return config.is_testing()
