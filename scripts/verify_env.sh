#!/bin/bash
# Verify critical environment variables are set in production
# Usage: ./scripts/verify_env.sh

set -e

echo "=== Environment Variable Verification ==="
echo ""

REQUIRED_VARS=(
  "GOOGLE_CLIENT_ID"
  "GOOGLE_CLIENT_SECRET"
  "GITHUB_CLIENT_ID"
  "GITHUB_CLIENT_SECRET"
  "NEXT_PUBLIC_GOOGLE_CLIENT_ID"
  "NEXT_PUBLIC_GITHUB_CLIENT_ID"
  "NEXT_PUBLIC_AUTH_CALLBACK_URL"
  "NEXT_PUBLIC_GRAPHQL_ENDPOINT"
)

OPTIONAL_VARS=(
  "MICROSOFT_CLIENT_ID"
  "MICROSOFT_CLIENT_SECRET"
  "MICROSOFT_TENANT_ID"
)

missing=()
present=()

echo "Checking required variables..."
for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var}" ]]; then
    missing+=("$var")
    echo "  ✗ $var: NOT SET"
  else
    present+=("$var")
    # Show first 10 chars to verify it's not empty
    value="${!var}"
    preview="${value:0:10}..."
    echo "  ✓ $var: SET ($preview)"
  fi
done

echo ""
echo "Checking optional variables..."
for var in "${OPTIONAL_VARS[@]}"; do
  if [[ -z "${!var}" ]]; then
    echo "  - $var: not set (optional)"
  else
    value="${!var}"
    preview="${value:0:10}..."
    echo "  ✓ $var: SET ($preview)"
  fi
done

echo ""
echo "=== Summary ==="
echo "Required variables: ${#REQUIRED_VARS[@]}"
echo "Present: ${#present[@]}"
echo "Missing: ${#missing[@]}"

if [[ ${#missing[@]} -gt 0 ]]; then
  echo ""
  echo "ERROR: Missing required environment variables:"
  printf '  - %s\n' "${missing[@]}"
  echo ""
  echo "Please configure these variables before deploying."
  exit 1
fi

echo ""
echo "✓ All required environment variables are set!"
exit 0
