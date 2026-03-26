#!/usr/bin/env bash
# Seed LLM API keys and service credentials from local .env into Vault
set -euo pipefail

source .env

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"

echo "Seeding secrets into Vault..."

# LLM API keys
[ -n "${GEMINI_API_KEY:-}" ] && vault kv put secret/etherion/llm/gemini api_key="$GEMINI_API_KEY"
[ -n "${ANTHROPIC_API_KEY:-}" ] && vault kv put secret/etherion/llm/anthropic api_key="$ANTHROPIC_API_KEY"
[ -n "${OPENROUTER_API_KEY:-}" ] && vault kv put secret/etherion/llm/openrouter api_key="$OPENROUTER_API_KEY"
[ -n "${OPENAI_API_KEY:-}" ] && vault kv put secret/etherion/llm/openai api_key="$OPENAI_API_KEY"

# Database
vault kv put secret/etherion/postgres \
  url="${DATABASE_URL:-}" \
  user="${POSTGRES_USER:-etherion}" \
  password="${POSTGRES_PASSWORD:-etherion}" \
  db="${POSTGRES_DB:-etherion}"

# Redis
vault kv put secret/etherion/redis url="${REDIS_URL:-redis://localhost:6379/0}"

# MinIO
vault kv put secret/etherion/minio \
  endpoint="${MINIO_ENDPOINT:-http://localhost:9000}" \
  access_key="${MINIO_ACCESS_KEY:-minioadmin}" \
  secret_key="${MINIO_SECRET_KEY:-minioadmin}"

# JWT
vault kv put secret/etherion/jwt \
  secret_key="${JWT_SECRET_KEY:-}" \
  algorithm="${JWT_ALGORITHM:-HS256}"

echo "Secrets seeded successfully."
