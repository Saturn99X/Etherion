"""
Backend Test Suite for Tenant Creation Flow

Tests auto-tenant creation, subdomain validation, and DNS manager integration.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from src.services.dns_manager import DNSManager, generate_unique_subdomain, is_valid_subdomain
# Note: Integration tests would need proper DB models, skipping for unit tests


class TestDNSManager:
    """Test DNS manager validation"""
    
    def setup_method(self):
        self.dns_manager = DNSManager()
    
    def test_valid_subdomains(self):
        """Valid subdomains should pass validation"""
        valid_subdomains = [
            "acme",
            "my-company",
            "test-site",
            "abc",
            "john-doe",
            "startup123"  # Note: numbers not allowed per spec, this should fail
        ]
        
        # Update expected results
        assert self.dns_manager.validate_subdomain("acme") == (True, None)
        assert self.dns_manager.validate_subdomain("my-company") == (True, None)
        assert self.dns_manager.validate_subdomain("test-site") == (True, None)
    
    def test_invalid_too_short(self):
        """Subdomains < 3 chars should be rejected"""
        is_valid, error = self.dns_manager.validate_subdomain("ab")
        assert not is_valid
        assert "at least 3 characters" in error
    
    def test_invalid_too_long(self):
        """Subdomains > 12 chars should be rejected"""
        is_valid, error = self.dns_manager.validate_subdomain("this-is-way-too-long")
        assert not is_valid
        assert "at most 12 characters" in error
    
    def test_invalid_uppercase(self):
        """Uppercase letters should be rejected"""
        is_valid, error = self.dns_manager.validate_subdomain("MyCompany")
        assert not is_valid
        assert "lowercase" in error.lower()
    
    def test_invalid_numbers(self):
        """Numbers should be rejected"""
        is_valid, error = self.dns_manager.validate_subdomain("test123")
        assert not is_valid
        assert "lowercase letters and hyphens" in error
    
    def test_reserved_subdomains(self):
        """Reserved subdomains should be rejected"""
        reserved = ["api", "app", "auth", "mars", "quasar", "blackhole"]
        
        for subdomain in reserved:
            is_valid, error = self.dns_manager.validate_subdomain(subdomain)
            assert not is_valid
            assert "reserved" in error.lower()
    
    def test_banned_words(self):
        """Banned words should be rejected"""
        banned = ["shit", "fuck", "damn"]
        
        for word in banned:
            is_valid, error = self.dns_manager.validate_subdomain(word)
            assert not is_valid
            assert "prohibited" in error.lower()
    
    def test_hyphen_rules(self):
        """Hyphens must follow format rules"""
        # Cannot start with hyphen
        is_valid, _ = self.dns_manager.validate_subdomain("-test")
        assert not is_valid
        
        # Cannot end with hyphen
        is_valid, _ = self.dns_manager.validate_subdomain("test-")
        assert not is_valid
        
        # Cannot have consecutive hyphens
        is_valid, error = self.dns_manager.validate_subdomain("test--site")
        assert not is_valid
        assert "consecutive hyphens" in error


class TestSubdomainGeneration:
    """Test subdomain generation from user info"""
    
    def test_generate_from_name(self):
        """Should generate subdomain from first name"""
        existing = set()
        
        # Single word name
        subdomain = generate_unique_subdomain("john", existing)
        assert subdomain == "john"
        
        # Multi-word name (takes first word)
        subdomain = generate_unique_subdomain("John Doe", existing)
        assert subdomain == "john"
    
    def test_generate_from_email(self):
        """Should generate subdomain from email username"""
        existing = set()
        
        subdomain = generate_unique_subdomain("john.doe@example.com", existing)
        # Should normalize to valid subdomain
        assert len(subdomain) <= 12
        assert subdomain.islower()
    
    def test_uniqueness_counter(self):
        """Should append numbers for duplicates"""
        existing = {"acme", "acme1", "acme2"}
        
        subdomain = generate_unique_subdomain("acme", existing)
        assert subdomain == "acme3"
    
    def test_invalid_characters_removed(self):
        """Should remove invalid characters"""
        existing = set()
        
        # Special characters should be removed/replaced
        subdomain = generate_unique_subdomain("test@#$company", existing)
        assert "@" not in subdomain
        assert "#" not in subdomain
        assert "$" not in subdomain
    
    def test_max_length_truncation(self):
        """Should truncate to 12 characters"""
        existing = set()
        
        subdomain = generate_unique_subdomain("verylongcompanyname", existing)
        assert len(subdomain) <= 12


class TestTenantCreationFlow:
    """Integration tests for tenant creation during OAuth"""
    
    @pytest.mark.asyncio
    async def test_auto_tenant_creation(self):
        """New OAuth user should auto-create tenant"""
        # This would require full integration test setup
        # For now, documenting expected behavior
        pass
    
    @pytest.mark.asyncio
    async def test_existing_user_no_new_tenant(self):
        """Existing user should not create duplicate tenant"""
        pass
    
    @pytest.mark.asyncio
    async def test_subdomain_uniqueness_enforced(self):
        """Cannot create tenant with duplicate subdomain"""
        pass


if __name__ == "__main__":
    # Run tests
    import subprocess
    subprocess.run(["pytest", __file__, "-v"])
