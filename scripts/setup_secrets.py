#!/usr/bin/env python3
"""
Script to set up secrets in Google Secret Manager for the Etherion AI application.

This script helps users create and populate the necessary secrets in Google Secret Manager
for both development and production environments.

Usage:
    python scripts/setup_secrets.py --environment dev --project-id your-project-id
    python scripts/setup_secrets.py --environment prod --project-id your-project-id
"""

import argparse
import os
import sys
import secrets
import string
from typing import Dict, List, Optional
from google.cloud import secretmanager
from google.api_core import exceptions as gcp_exceptions


def generate_secure_password(length: int = 32) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_jwt_secret(length: int = 64) -> str:
    """Generate a secure JWT secret."""
    return secrets.token_urlsafe(length)


def create_secret_if_not_exists(client: secretmanager.SecretManagerServiceClient, 
                               project_id: str, secret_id: str) -> bool:
    """Create a secret if it doesn't already exist."""
    try:
        parent = f"projects/{project_id}"
        secret = {
            "replication": {
                "automatic": {}
            }
        }
        
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": secret,
            }
        )
        print(f"✅ Created secret: {secret_id}")
        return True
        
    except gcp_exceptions.AlreadyExists:
        print(f"ℹ️  Secret already exists: {secret_id}")
        return True
    except Exception as e:
        print(f"❌ Error creating secret {secret_id}: {e}")
        return False


def add_secret_version(client: secretmanager.SecretManagerServiceClient,
                      project_id: str, secret_id: str, secret_data: str) -> bool:
    """Add a new version to an existing secret."""
    try:
        parent = f"projects/{project_id}/secrets/{secret_id}"
        
        response = client.add_secret_version(
            request={
                "parent": parent,
                "payload": {"data": secret_data.encode("UTF-8")}
            }
        )
        
        print(f"✅ Added version to secret: {secret_id} (version: {response.name.split('/')[-1]})")
        return True
        
    except Exception as e:
        print(f"❌ Error adding version to secret {secret_id}: {e}")
        return False


def setup_environment_secrets(project_id: str, environment: str, 
                            custom_values: Optional[Dict[str, str]] = None) -> bool:
    """Set up all secrets for a specific environment."""
    print(f"🔧 Setting up secrets for {environment} environment in project {project_id}")
    
    # Initialize the Secret Manager client
    try:
        client = secretmanager.SecretManagerServiceClient()
    except Exception as e:
        print(f"❌ Error initializing Secret Manager client: {e}")
        return False
    
    # Define secrets for this environment
    secrets_config = {
        f"etherion-database-url-{environment}": {
            "description": f"Database URL for {environment} environment",
            "generate": False,  # Will be set manually or from custom values
            "default": f"postgresql://etherion_user_{environment}:password@localhost:5432/etherion_{environment}"
        },
        f"etherion-secret-key-{environment}": {
            "description": f"Application secret key for {environment} environment",
            "generate": True,
            "generator": lambda: generate_secure_password(32)
        },
        f"etherion-jwt-secret-{environment}": {
            "description": f"JWT signing secret for {environment} environment",
            "generate": True,
            "generator": lambda: generate_jwt_secret(64)
        }
    }
    
    # Add tenant-specific secrets
    tenant_secrets = [
        f"tenant-1--openai--api_key",
        f"tenant-1--resend--api_key",
        f"tenant-1--sendgrid--api_key",
        f"tenant-1--slack--bot_token",
        f"tenant-1--twitter--bearer_token",
        f"tenant-1--shopify--access_token"
    ]
    
    for tenant_secret in tenant_secrets:
        secrets_config[tenant_secret] = {
            "description": f"Tenant-specific secret: {tenant_secret}",
            "generate": False,  # Will be set manually
            "default": f"your-{tenant_secret.replace('--', '-').replace('_', '-')}-here"
        }
    
    success_count = 0
    total_count = len(secrets_config)
    
    # Create secrets and add versions
    for secret_id, config in secrets_config.items():
        print(f"\n📝 Processing secret: {secret_id}")
        
        # Create the secret if it doesn't exist
        if not create_secret_if_not_exists(client, project_id, secret_id):
            continue
        
        # Determine the secret value
        if custom_values and secret_id in custom_values:
            secret_value = custom_values[secret_id]
            print(f"   Using custom value for {secret_id}")
        elif config["generate"]:
            secret_value = config["generator"]()
            print(f"   Generated secure value for {secret_id}")
        else:
            secret_value = config["default"]
            print(f"   Using default value for {secret_id} (please update manually)")
        
        # Add the secret version
        if add_secret_version(client, project_id, secret_id, secret_value):
            success_count += 1
    
    print(f"\n📊 Summary: {success_count}/{total_count} secrets processed successfully")
    
    if success_count == total_count:
        print("🎉 All secrets set up successfully!")
        return True
    else:
        print("⚠️  Some secrets failed to be set up. Please check the errors above.")
        return False


def main():
    parser = argparse.ArgumentParser(description="Set up secrets in Google Secret Manager")
    parser.add_argument("--environment", required=True, choices=["dev", "prod"],
                       help="Environment to set up secrets for")
    parser.add_argument("--project-id", required=True,
                       help="Google Cloud project ID")
    parser.add_argument("--custom-values", type=str,
                       help="JSON string with custom secret values")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without making changes")
    
    args = parser.parse_args()
    
    # Validate project ID
    if not args.project_id or args.project_id.startswith("your-"):
        print("❌ Please provide a valid Google Cloud project ID")
        sys.exit(1)
    
    # Parse custom values if provided
    custom_values = None
    if args.custom_values:
        try:
            import json
            custom_values = json.loads(args.custom_values)
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing custom values JSON: {e}")
            sys.exit(1)
    
    if args.dry_run:
        print("🔍 Dry run mode - no changes will be made")
        print(f"Would set up secrets for {args.environment} environment in project {args.project_id}")
        return
    
    # Set up the secrets
    success = setup_environment_secrets(args.project_id, args.environment, custom_values)
    
    if success:
        print("\n✅ Secret setup completed successfully!")
        print("\n📋 Next steps:")
        print("1. Update your terraform variables.tfvars file with the correct project ID")
        print("2. Update any tenant-specific secrets with actual API keys")
        print("3. Run terraform plan and apply to deploy your infrastructure")
    else:
        print("\n❌ Secret setup failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
