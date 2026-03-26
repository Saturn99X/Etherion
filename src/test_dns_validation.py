"""
Test script for subdomain validation.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from services.dns_manager import DNSManager, is_valid_subdomain

def test_subdomains():
    manager = DNSManager()
    
    test_cases = [
        # Valid subdomains
        ("acme", True),
        ("my-company", True),
        ("abc", True),
        ("test-site", True),
        
        # Invalid: too short
        ("ab", False),
        
        # Invalid: too long
        ("this-is-way-too-long", False),
        
        # Invalid: reserved
        ("api", False),
        ("mars", False),
        ("quasar", False),
        
        # Invalid: banned words
        ("shit", False),
        ("fuck", False),
        ("nigger", False),
        
        # Invalid: contains numbers
        ("test123", False),
        
        # Invalid: uppercase
        ("MyCompany", False),
        
        # Invalid: special chars
        ("my_company", False),
        ("my.company", False),
        
        # Invalid: starts with hyphen
        ("-test", False),
        
        # Invalid: ends with hyphen
        ("test-", False),
        
        # Invalid: consecutive hyphens
        ("test--site", False),
    ]
    
    print("Testing subdomain validation:")
    print("=" * 60)
    
    for subdomain, expected in test_cases:
        is_valid, error = manager.validate_subdomain(subdomain)
        status = "✓" if is_valid == expected else "✗"
        
        if is_valid != expected:
            print(f"{status} {subdomain:20} Expected: {expected}, Got: {is_valid}")
            if error:
                print(f"   Error: {error}")
        else:
            print(f"{status} {subdomain:20} -> {'Valid' if is_valid else error}")
    
    print("=" * 60)
    print("Validation tests complete!")

if __name__ == "__main__":
    test_subdomains()
