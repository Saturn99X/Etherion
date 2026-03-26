#!/usr/bin/env bash
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"

echo "=== Vault Init & Setup ==="

# Initialize Vault
echo "Initializing Vault..."
vault operator init \
  -key-shares=5 \
  -key-threshold=3 \
  -format=json > /root/vault-keys.json
chmod 600 /root/vault-keys.json

echo "Vault initialized. Keys saved to /root/vault-keys.json"
echo "WARNING: Secure these keys immediately!"

# Unseal (use first 3 keys)
echo "Unsealing Vault..."
for i in 0 1 2; do
  KEY=$(jq -r ".unseal_keys_b64[$i]" /root/vault-keys.json)
  vault operator unseal "$KEY"
done

# Login with root token
ROOT_TOKEN=$(jq -r '.root_token' /root/vault-keys.json)
vault login "$ROOT_TOKEN"

# Enable KV v2
vault secrets enable -version=2 secret

# Write policies
vault policy write etherion-app vault/policies/etherion-app.hcl
vault policy write etherion-admin vault/policies/etherion-admin.hcl

# Enable AppRole
vault auth enable approle

# Create etherion-app role
vault write auth/approle/role/etherion-app \
  token_policies="etherion-app" \
  token_ttl=1h \
  token_max_ttl=4h \
  secret_id_ttl=0

# Get role credentials
ROLE_ID=$(vault read -field=role_id auth/approle/role/etherion-app/role-id)
SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/etherion-app/secret-id)

echo "=== AppRole Credentials ==="
echo "VAULT_ROLE_ID=$ROLE_ID"
echo "VAULT_SECRET_ID=$SECRET_ID"
echo "Add these to /etc/etherion/.env"
