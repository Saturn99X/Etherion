#!/usr/bin/env bash
set -euo pipefail

root_dir="$(dirname "$0")/.."
cd "$root_dir"

append_section() {
  local file="$1"
  shift
  local content="$*"
  if grep -q "^## Deploy & Validate" "$file"; then
    echo "[SKIP] $file already has Deploy & Validate"
  else
    printf "\n%s\n" "$content" >> "$file"
    echo "[APPENDED] $file"
  fi
}

# Common snippets
read -r -d '' COMMON_SMOKE <<'EOF'
## Deploy & Validate (Real Cloud, 100% green)

1. Prereqs
   - gcloud: `gcloud auth login && gcloud auth application-default login`
   - Env: `export GOOGLE_CLOUD_PROJECT=<id> REGION=<region>`
   - Terraform installed

2. Init + Plan (safe)
   - `terraform -chdir=terraform/environments/prod init`
   - `terraform -chdir=terraform/environments/prod plan`

3. Secrets & runtime config
   - Provide `JWT_SECRET_KEY`, `SECRET_KEY`, vendor keys (e.g., `EXA_API_KEY`).
   - Review limits: `Z/Rate-Limits-and-Thresholds.md`.

4. Smoke checks
   - API health: `GET /health` → `{ "status": "OK" }`
   - Rate-limit headers on `/`
   - Cloud Monitoring: dashboard + alert policies (error, latency, 429, cost, credits)

5. Functional validation
   - E2E (assets/KB/web grounding/headers):
     `pytest -q tests/e2e/test_ev_flows.py::test_drive_cf_bq_vertex_preview_download_and_rate_limit -s`
EOF

# Pillar 00 – Cross Cutting
read -r -d '' AUDIT_APPENDIX <<'EOF'
## Audit Appendix

- Desired Features
  - Security-by-default: tenant isolation, CSRF, security headers, layered rate limits (`src/etherion_ai/middleware/*`, `src/middleware/*`, `src/etherion_ai/app.py`).
  - Observability: error reporting + monitoring; dashboards/policies in `terraform/modules/monitoring/`.
  - Grounded intelligence: KB + mandatory web search (`src/tools/unified_research_tool.py`); Vertex as vector cache (`src/tools/vertex_ai_search.py`).
  - Cost transparency: per-operation metering and credits with alerts (`terraform/modules/cost-tracking/`).
  - No public media: private GCS with signed URLs or inline previews (`src/services/content_repository_service.py`).
- Code References
  - See the pillar's “Codebase Mapping” above.
  - Core paths: `src/etherion_ai/`, `src/middleware/`, `src/tools/`, `src/services/`, `src/database/models/`, `src/utils/`, `src/config/`.
  - Terraform modules under `terraform/modules/` for API, workers, VPC, Redis, monitoring, BigQuery KB, Vertex, storage.
- Rate Limits & Thresholds
  - Consolidated guidance: `Z/Rate-Limits-and-Thresholds.md`.
EOF

# Build final block to append (Audit Appendix + common deploy/validate)
APPEND_BLOCK="$AUDIT_APPENDIX

$COMMON_SMOKE"

# Append to all pillar docs idempotently
for f in Z/Pillars/pillar-*.md; do
  if grep -q "^## Audit Appendix" "$f"; then
    echo "[SKIP] $f already has Audit Appendix"
  else
    printf "\n%s\n" "$APPEND_BLOCK" >> "$f"
    echo "[APPENDED] $f"
  fi
done
