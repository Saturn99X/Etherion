"""
Integration tests for the secrets manager with Google Secret Manager.

These tests verify that the secrets manager correctly integrates with
Google Secret Manager and handles different environments properly.
"""

import pytest
import os
import asyncio
from unittest.mock import patch, MagicMock
from src.utils.secrets_manager import TenantSecretsManager
from src.config import Environment, EnvironmentConfig


class TestSecretsManagerIntegration:
    """Test the integration between secrets manager and Google Secret Manager."""
    
    @pytest.fixture
    def mock_gsm_client(self):
        """Mock Google Secret Manager client."""
        with patch('google.cloud.secretmanager.SecretManagerServiceClient') as mock_client:
            # Mock the client instance
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            
            # Mock successful secret access
            mock_response = MagicMock()
            mock_response.payload.data = b"test-secret-value"
            mock_instance.access_secret_version.return_value = mock_response
            
            # Mock successful secret creation
            mock_create_response = MagicMock()
            mock_create_response.name = "projects/test-project/secrets/test-secret/versions/1"
            mock_instance.create_secret.return_value = mock_create_response
            
            # Mock successful secret version addition
            mock_version_response = MagicMock()
            mock_version_response.name = "projects/test-project/secrets/test-secret/versions/1"
            mock_instance.add_secret_version.return_value = mock_version_response
            
            yield mock_instance
    
    @pytest.fixture
    def secrets_manager(self, mock_gsm_client):
        """Create a secrets manager instance with mocked GSM client."""
        with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test-project', 'ENVIRONMENT': 'test'}):
            return TenantSecretsManager()
    
    @pytest.mark.asyncio
    async def test_retrieve_secret_from_gsm_success(self, secrets_manager, mock_gsm_client):
        """Test successful secret retrieval from Google Secret Manager."""
        with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test-project'}):
            secret_value = await secrets_manager._retrieve_secret_from_storage(
                "test-secret", "tenant-1", "openai", "api_key"
            )
            
            assert secret_value == "test-secret-value"
            mock_gsm_client.access_secret_version.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retrieve_secret_from_gsm_not_found(self, secrets_manager, mock_gsm_client):
        """Test secret retrieval when secret doesn't exist."""
        # Mock secret not found exception
        from google.api_core import exceptions as gcp_exceptions
        mock_gsm_client.access_secret_version.side_effect = gcp_exceptions.NotFound("Secret not found")
        
        secret_value = await secrets_manager._retrieve_secret_from_storage(
            "non-existent-secret", "tenant-1", "openai", "api_key"
        )
        
        assert secret_value is None
    
    @pytest.mark.asyncio
    async def test_store_secret_in_gsm_success(self, secrets_manager, mock_gsm_client):
        """Test successful secret storage in Google Secret Manager."""
        success = await secrets_manager.store_secret(
            "tenant-1", "openai", "api_key", "new-secret-value"
        )
        
        assert success is True
        mock_gsm_client.add_secret_version.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_store_secret_in_gsm_failure(self, secrets_manager, mock_gsm_client):
        """Test secret storage failure."""
        # Mock storage failure
        mock_gsm_client.add_secret_version.side_effect = Exception("Storage failed")
        
        success = await secrets_manager.store_secret(
            "tenant-1", "openai", "api_key", "new-secret-value"
        )
        
        assert success is False
    
    @pytest.mark.asyncio
    async def test_get_secret_with_caching(self, secrets_manager, mock_gsm_client):
        """Test that secrets are cached after retrieval."""
        # First call should hit GSM
        secret1 = await secrets_manager.get_secret("tenant-1", "openai", "api_key")
        assert secret1 == "test-secret-value"
        assert mock_gsm_client.access_secret_version.call_count == 1
        
        # Second call should hit cache
        secret2 = await secrets_manager.get_secret("tenant-1", "openai", "api_key")
        assert secret2 == "test-secret-value"
        assert mock_gsm_client.access_secret_version.call_count == 1  # No additional calls
    
    @pytest.mark.asyncio
    async def test_singleflight_prevents_duplicate_requests(self, secrets_manager, mock_gsm_client):
        """Test that singleflight prevents duplicate concurrent requests."""
        # Mock slow GSM response
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(0.1)
            mock_response = MagicMock()
            mock_response.payload.data = b"slow-secret-value"
            return mock_response
        
        mock_gsm_client.access_secret_version.side_effect = slow_response
        
        # Start multiple concurrent requests
        tasks = []
        for i in range(3):
            task = asyncio.create_task(
                secrets_manager.get_secret("tenant-1", "openai", "api_key")
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks)
        
        # All results should be the same
        assert all(result == "slow-secret-value" for result in results)
        
        # GSM should only be called once due to singleflight
        assert mock_gsm_client.access_secret_version.call_count == 1
    
    def test_environment_configuration_integration(self):
        """Test that secrets manager uses environment configuration correctly."""
        with patch.dict(os.environ, {'ENVIRONMENT': 'dev'}):
            manager = TenantSecretsManager()
            
            # Check that dev environment settings are applied
            assert manager.config.environment.value == 'dev'
            assert manager._cache_ttl == 60  # Dev has shorter TTL
            assert manager._redis_enabled is False  # Dev has Redis disabled
    
    def test_production_environment_configuration(self):
        """Test that production environment uses appropriate settings."""
        with patch.dict(os.environ, {'ENVIRONMENT': 'prod'}):
            manager = TenantSecretsManager()
            
            # Check that prod environment settings are applied
            assert manager.config.environment.value == 'prod'
            assert manager._cache_ttl == 600  # Prod has longer TTL
            assert manager._redis_enabled is True  # Prod has Redis enabled
    
    @pytest.mark.asyncio
    async def test_secret_naming_convention(self, secrets_manager, mock_gsm_client):
        """Test that secrets follow the correct naming convention."""
        await secrets_manager.get_secret("tenant-123", "resend", "api_key")
        
        # Verify the correct secret name was used
        call_args = mock_gsm_client.access_secret_version.call_args
        secret_name = call_args[1]['request']['name']
        expected_name = "projects/test-project/secrets/tenant-123--resend--api_key/versions/latest"
        assert secret_name == expected_name
    
    @pytest.mark.asyncio
    async def test_error_handling_and_logging(self, secrets_manager, mock_gsm_client):
        """Test that errors are properly handled and logged."""
        # Mock an error
        mock_gsm_client.access_secret_version.side_effect = Exception("GSM Error")
        
        # This should not raise an exception
        secret_value = await secrets_manager.get_secret("tenant-1", "openai", "api_key")
        
        assert secret_value is None
    
    @pytest.mark.asyncio
    async def test_cache_statistics(self, secrets_manager, mock_gsm_client):
        """Test that cache statistics are properly tracked."""
        # Get a secret (cache miss)
        await secrets_manager.get_secret("tenant-1", "openai", "api_key")
        
        # Get the same secret again (cache hit)
        await secrets_manager.get_secret("tenant-1", "openai", "api_key")
        
        stats = secrets_manager.get_cache_statistics()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['total_accesses'] == 2
        assert stats['hit_ratio'] == 0.5
    
    @pytest.mark.asyncio
    async def test_cleanup_on_shutdown(self, secrets_manager, mock_gsm_client):
        """Test that resources are properly cleaned up on shutdown."""
        # Get a secret to populate cache
        await secrets_manager.get_secret("tenant-1", "openai", "api_key")
        
        # Verify cache has entries
        stats_before = secrets_manager.get_cache_statistics()
        assert stats_before['current_cache_size'] > 0
        
        # Shutdown
        await secrets_manager.shutdown()
        
        # Verify cache is cleared
        stats_after = secrets_manager.get_cache_statistics()
        assert stats_after['current_cache_size'] == 0


class TestEnvironmentConfiguration:
    """Test environment configuration integration."""
    
    def test_development_environment_config(self):
        """Test development environment configuration."""
        with patch.dict(os.environ, {'ENVIRONMENT': 'dev'}):
            config = EnvironmentConfig()
            
            assert config.environment == Environment.DEVELOPMENT
            assert config.get('debug') is True
            assert config.get('redis_enabled') is False
            assert config.get('cache_ttl') == 60
            assert config.get('rate_limit_per_minute') == 1000
    
    def test_production_environment_config(self):
        """Test production environment configuration."""
        with patch.dict(os.environ, {'ENVIRONMENT': 'prod'}):
            config = EnvironmentConfig()
            
            assert config.environment == Environment.PRODUCTION
            assert config.get('debug') is False
            assert config.get('redis_enabled') is True
            assert config.get('cache_ttl') == 600
            assert config.get('rate_limit_per_minute') == 60
    
    def test_environment_variable_overrides(self):
        """Test that environment variables can override configuration."""
        with patch.dict(os.environ, {
            'ENVIRONMENT': 'prod',
            'REDIS_ENABLED': 'false',
            'CACHE_TTL': '120'
        }):
            config = EnvironmentConfig()
            
            # Environment variables should override defaults
            assert config.get('redis_enabled') is False
            assert config.get('cache_ttl') == 120
    
    def test_secret_name_generation(self):
        """Test that secret names are generated correctly for different environments."""
        with patch.dict(os.environ, {'ENVIRONMENT': 'dev'}):
            config = EnvironmentConfig()
            
            assert config.get_secret_name('database_url') == 'etherion-database-url-dev'
            assert config.get_secret_name('secret_key') == 'etherion-secret-key-dev'
            assert config.get_secret_name('jwt_secret') == 'etherion-jwt-secret-dev'
        
        with patch.dict(os.environ, {'ENVIRONMENT': 'prod'}):
            config = EnvironmentConfig()
            
            assert config.get_secret_name('database_url') == 'etherion-database-url-prod'
            assert config.get_secret_name('secret_key') == 'etherion-secret-key-prod'
            assert config.get_secret_name('jwt_secret') == 'etherion-jwt-secret-prod'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
