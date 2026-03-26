#!/usr/bin/env bash
# Run the full GCP → bare-metal migration test gauntlet.
# Usage: bash scripts/run_migration_tests.sh [pytest options]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export KB_VECTOR_BACKEND=pgvector
export STORAGE_BACKEND=local
export SECRETS_BACKEND=local
export USE_LOCAL_SECRETS=true
export DISABLE_GCP_LOGGING=1
export GOOGLE_CLOUD_PROJECT=test-project
export E2E_DB_RESET=0

# Ensure no real BigQuery/GCS/Vault calls happen in unit tests
# (backends are mocked; these vars just prevent init errors)
export BIGQUERY_LOCATION=us-central1
export GCS_LOCATION=us-central1

TESTS=(
    "tests/unit/test_kb_backend_abstraction.py"
    "tests/unit/test_storage_backend_abstraction.py"
    "tests/unit/test_migrated_services_tier2.py"
    "tests/unit/test_migrated_tools_bare_metal.py"
    "tests/unit/test_vault_credential_backend.py"
    "tests/integration/test_bare_metal_migration_integration.py"
)

echo "============================================="
echo " Etherion GCP→Bare-Metal Migration Gauntlet "
echo "============================================="
echo ""

python -m pytest \
    "${TESTS[@]}" \
    -v \
    --tb=short \
    --no-header \
    -x \
    "$@"

echo ""
echo "============================================="
echo " All migration tests passed! ✓"
echo "============================================="
