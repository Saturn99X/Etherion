#!/usr/bin/env bash
# Seed Google Secret Manager from log.txt exports, aligning with Terraform secret IDs.
# Usage: seed_gsm_from_log.sh -p <PROJECT_ID> [-f <log_file>] [--dry-run]
# Notes:
# - Does NOT print secret values.
# - Creates secret containers if missing, then adds a new version for each.
# - Maps special keys to canonical secret IDs used in Terraform.
# - Skips overriding app-secret-key; Terraform seeds a random version. Change only if you know what you're doing.

set -euo pipefail

PROJECT=""
LOG_FILE="log.txt"
DRY_RUN=0

usage() {
  cat <<EOF
Seed Google Secret Manager from an exports file.

Required:
  -p PROJECT_ID          GCP project ID
Optional:
  -f FILE                Input file (default: log.txt) containing lines like: export KEY=VALUE
  --dry-run              Show what would be created without mutating GSM

Examples:
  $0 -p etherion-474013
  $0 -p etherion-474013 -f logs/export.env --dry-run
EOF
}

# Parse args
while (( "$#" )); do
  case "$1" in
    -p)
      PROJECT="${2:-}"; shift 2;;
    -f)
      LOG_FILE="${2:-}"; shift 2;;
    --dry-run)
      DRY_RUN=1; shift;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown argument: $1" >&2; usage; exit 1;;
  esac
done

if [[ -z "${PROJECT}" ]]; then
  echo "ERROR: -p PROJECT_ID is required" >&2
  usage
  exit 1
fi

if [[ ! -f "${LOG_FILE}" ]]; then
  echo "ERROR: File not found: ${LOG_FILE}" >&2
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud CLI not found in PATH" >&2
  exit 1
fi

# Read KEY=VALUE from lines 'export KEY=VALUE' into an associative array preserving last occurrence
declare -A env_kv
while IFS= read -r line; do
  [[ "$line" =~ ^export[[:space:]]+ ]] || continue
  line="${line#export }"
  key="${line%%=*}"
  val="${line#*=}"
  # Trim trailing CR if any (Windows endings)
  val="${val%$'\r'}"
  env_kv["$key"]="$val"
done < "${LOG_FILE}"

# Helper to insert a mapping if the source KEY exists
add_map() {
  local src_key="$1"; shift
  local dest_id="$1"; shift
  local value="${env_kv[${src_key}]:-}"
  if [[ -n "${value}" ]]; then
    secrets_to_seed["${dest_id}"]="${value}"
  fi
}

# Aggregate secrets to seed
declare -A secrets_to_seed

# Core DB and admin
add_map "DATABASE_URL" "etherion-database-url-prod"
add_map "ASYNC_DATABASE_URL" "etherion-async-database-url-prod"
add_map "ETHERION_ADMIN_INGEST_SECRET" "etherion-admin-ingest-secret"

# Session/state + vendors
add_map "OAUTH_STATE_SECRET" "OAUTH_STATE_SECRET"
add_map "EXA_API_KEY" "EXA_API_KEY"

# Stripe
add_map "STRIPE_SECRET_KEY" "STRIPE_SECRET_KEY"
add_map "STRIPE_WEBHOOK_SECRET" "STRIPE_WEBHOOK_SECRET"
add_map "PRICE_ID_STARTER" "PRICE_ID_STARTER"

# Pricing & vector-store costs used by services
for k in \
  PRICE_PER_1K_INPUT_TOKENS PRICE_PER_1K_OUTPUT_TOKENS PRICE_PER_API_CALL \
  PRICE_PER_MB_INBOUND PRICE_PER_MB_OUTBOUND PRICE_PER_MS_COMPUTE \
  PRICING_CURRENCY VS_INDEX_FREE_GIB VS_INDEX_PRICE_PER_GIB_MONTH \
  VS_PRICE_ADVANCED_ADDON_PER_1K_Q VS_PRICE_ENTERPRISE_PER_1K_Q VS_PRICE_STANDARD_PER_1K_Q \
  BQ_PRICE_SLOT_PER_HOUR \
; do
  if [[ -n "${env_kv[$k]:-}" ]]; then
    secrets_to_seed["$k"]="${env_kv[$k]}"
  fi
done

# OAuth providers (both canonical Terraform IDs and legacy oauth-* IDs)
# Google
add_map "OAUTH_GOOGLE_CLIENT_ID" "oauth-google-client-id"
add_map "OAUTH_GOOGLE_CLIENT_ID" "GOOGLE_CLIENT_ID"
add_map "OAUTH_GOOGLE_CLIENT_SECRET" "oauth-google-client-secret"
add_map "OAUTH_GOOGLE_CLIENT_SECRET" "GOOGLE_CLIENT_SECRET"
# GitHub
add_map "OAUTH_GITHUB_CLIENT_ID" "oauth-github-client-id"
add_map "OAUTH_GITHUB_CLIENT_ID" "GITHUB_CLIENT_ID"
add_map "OAUTH_GITHUB_CLIENT_SECRET" "oauth-github-client-secret"
add_map "OAUTH_GITHUB_CLIENT_SECRET" "GITHUB_CLIENT_SECRET"
# Microsoft
add_map "OAUTH_MS_CLIENT_ID" "oauth-ms-client-id"
add_map "OAUTH_MS_CLIENT_ID" "MICROSOFT_CLIENT_ID"
add_map "OAUTH_MS_CLIENT_SECRET" "oauth-ms-client-secret"
add_map "OAUTH_MS_CLIENT_SECRET" "MICROSOFT_CLIENT_SECRET"
add_map "MS365_TENANT_ID" "ms365-tenant-id"
add_map "MS365_TENANT_ID" "MICROSOFT_TENANT_ID"

# Slack
for k in SLACK_BOT_TOKEN SLACK_SIGNING_SECRET SLACK_USER_OAUTH_CLIENT_ID SLACK_USER_OAUTH_CLIENT_SECRET; do
  if [[ -n "${env_kv[$k]:-}" ]]; then
    secrets_to_seed["$k"]="${env_kv[$k]}"
  fi
done

# CRM/Integrations (HubSpot, Jira, Notion, Shopify)
for k in \
  HUBSPOT_OAUTH_CLIENT_ID HUBSPOT_OAUTH_CLIENT_SECRET \
  JIRA_API_TOKEN JIRA_CLOUD_ID JIRA_DOMAIN JIRA_EMAIL JIRA_WEBHOOK_SECRET \
  NOTION_OAUTH_CLIENT_ID NOTION_OAUTH_CLIENT_SECRET NOTION_WEBHOOK_SECRET \
  SHOPIFY_OAUTH_CLIENT_ID SHOPIFY_OAUTH_CLIENT_SECRET SHOPIFY_WEBHOOK_SHARED_SECRET \
; do
  if [[ -n "${env_kv[$k]:-}" ]]; then
    secrets_to_seed["$k"]="${env_kv[$k]}"
  fi
done

# Explicitly avoid overriding app-secret-key unless explicitly desired
if [[ -n "${env_kv[APP_SECRET_KEY]:-}" ]]; then
  echo "NOTE: APP_SECRET_KEY present but will NOT override 'app-secret-key' by default." >&2
fi
if [[ -n "${env_kv[SECRET_KEY]:-}" || -n "${env_kv[JWT_SECRET_KEY]:-}" ]]; then
  echo "NOTE: SECRET_KEY/JWT_SECRET_KEY present; both map to 'app-secret-key' via Terraform. Not overriding." >&2
fi

# Ensure/create and add versions
created=0
versions_added=0
failed=0
processed=0

ensure_secret() {
  local id="$1"
  if ! gcloud secrets describe "$id" --project="$PROJECT" >/dev/null 2>&1; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "DRY-RUN: would create secret $id"
    else
      gcloud secrets create "$id" --project="$PROJECT" --replication-policy="automatic" >/dev/null
      echo "Created secret: $id"
      ((created++)) || true
    fi
  fi
}

add_version() {
  local id="$1"; local value="$2"
  # Decode shell-escaped sequences (e.g., `\?`, `\(`, `\)`), preserving raw bytes otherwise.
  # printf '%b' interprets common backslash escapes but does not append a newline.
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: would add version for $id"
  else
    if printf '%b' "$value" | gcloud secrets versions add "$id" --project="$PROJECT" --data-file=- >/dev/null; then
      ((versions_added++)) || true
      echo "Added version: $id"
    else
      ((failed++)) || true
      echo "FAILED to add version: $id" >&2
    fi
  fi
}

for id in "${!secrets_to_seed[@]}"; do
  value="${secrets_to_seed[$id]}"
  ((processed++)) || true
  ensure_secret "$id"
  add_version "$id" "$value"
done

echo "Done. project=${PROJECT} processed=${processed} created=${created} versions_added=${versions_added} failed=${failed}"
