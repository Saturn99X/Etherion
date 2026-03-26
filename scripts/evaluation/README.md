# Etherion Evaluation Harness (Scripts)

This folder contains a **script-per-step** evaluation harness for an end-to-end platform test:

1. Create a new tenant (via GraphQL `passwordSignup`).
2. Ensure the tenant Knowledge Base (BigQuery dataset + tables) exists.
3. Ingest `entropy.pdf` directly into the tenant KB (no OAuth / no connectors) and run semantic search.
   - Additionally: backfill per-object embeddings and run object-KB vector search.
   - Optionally: fetch+ingest an object result via the object-KB admin endpoint.
4. Ask IO to create a 3-specialist physics teaching team and inspect its chosen tools.
5. Ask the team orchestrator 7 questions (increasing difficulty), **sequentially**, waiting for each job to complete before sending the next.

The scripts are **async**, persist all raw artifacts to disk (`state.json`, trace `.jsonl` files), and are designed so another agent can:
- run them in order,
- fix blocking bugs,
- and write conclusions + evaluation reports.

## Files

- `eval_lib.py`
  - Shared helpers: GraphQL HTTP calls, admin ingestion call, WebSocket trace subscription writer, state read/write, helpers for unique emails/subdomains.

- `eval_1_create_tenant.py`
  - Calls `passwordSignup` and writes `scripts/evaluation/state.json`.

- `eval_2_ensure_kb.py`
  - Calls `/webhook/admin/ingest-bytes` with a small text payload to force KB bootstrap.
  - Then verifies dataset/tables via BigQuery API (if creds available).

- `eval_3_ingest_entropy_pdf.py`
  - Reads local `/home/saturnx/langchain-app/entropy.pdf`.
  - Uploads it via `/webhook/admin/ingest-bytes` using `base64_content`.
  - Runs semantic search via `BQVectorSearchService` and LIKE search via `KBQueryService`.
  - Backfills embeddings into `tnt_{tenant}.media_object_embeddings` for the ingested object `gcs_uri`, runs `BQMediaObjectSearchService.search`, and optionally calls `/webhook/admin/object-kb/fetch-ingest`.

- `eval_4_create_physics_team.py`
  - Calls `createAgentTeam(team_input: AgentTeamInput!)` with a spec requesting exactly 3 specialists.
  - Saves `team_id`, `customAgentIDs`, and `preApprovedToolNames` into `state.json`.

- `eval_5_run_questions.py`
  - Executes 7 `executeGoal` jobs against the created team.
  - Subscribes to `subscribeToExecutionTrace(job_id)` via WebSocket.
  - Writes each job’s full trace stream to JSONL under `scripts/evaluation/out/physics_team_questions/`.
  - Fetches `getArchivedTraceSummary(job_id)` after completion.

## Output artifacts

- `scripts/evaluation/state.json`
  - Shared state file produced/updated by each script.
  - Stores: auth token, tenant_id (decoded from JWT payload), team_id, KB verification results, ingestion results, and question-run metadata.

- `scripts/evaluation/out/physics_team_questions/*.jsonl`
  - Raw execution trace events, one JSON object per line.
  - This is the authoritative artifact for tool-use + delegation analysis.

## Run order

Run scripts **in this exact order**:

1. `python scripts/evaluation/eval_1_create_tenant.py`
2. `python scripts/evaluation/eval_2_ensure_kb.py`
3. `python scripts/evaluation/eval_3_ingest_entropy_pdf.py`
4. `python scripts/evaluation/eval_4_create_physics_team.py`
5. `python scripts/evaluation/eval_5_run_questions.py`

### Robustness Features (2025-12-25 Update)

All scripts now include:
- **Automatic retry logic** for transient failures (Celery/Redis connection issues)
- **Fallback KB creation** if admin ingest fails (eval_2)
- **Graceful error handling** - scripts continue and log errors instead of crashing
- **Detailed progress logging** for debugging
- **Error context** with helpful troubleshooting tips

## Run everything in the existing venv (required)

These scripts require third-party Python packages (notably `httpx` for HTTP GraphQL calls and `websockets` for the GraphQL WS trace subscriber). Run the evaluation using the repo’s existing virtual environment at `./venv`.

### Activate the venv

From the repo root:

```bash
source venv/bin/activate
```

### Install dependencies into the venv

For a full end-to-end run (all 5 steps):

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install websockets
```

Alternatively, without activating the venv you can run everything explicitly via venv paths:

```bash
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install websockets

./venv/bin/python scripts/evaluation/eval_1_create_tenant.py
./venv/bin/python scripts/evaluation/eval_2_ensure_kb.py
./venv/bin/python scripts/evaluation/eval_3_ingest_entropy_pdf.py
./venv/bin/python scripts/evaluation/eval_4_create_physics_team.py
./venv/bin/python scripts/evaluation/eval_5_run_questions.py
```

## Environment variables

### Endpoints

- `ETHERION_GRAPHQL_HTTP`
  - Default: `https://api.etherionai.com/graphql`

- `ETHERION_GRAPHQL_WS`
  - Default: `wss://api.etherionai.com/graphql`

- `ETHERION_ADMIN_INGEST_URL`
  - Default: `https://api.etherionai.com/webhook/admin/ingest-bytes`

- `ETHERION_ADMIN_OBJECT_FETCH_INGEST_URL`
  - Default: `https://api.etherionai.com/webhook/admin/object-kb/fetch-ingest`

- `ETHERION_ADMIN_INGEST_SECRET`
  - Default: `test-secret-123`
  - The API currently accepts this value explicitly for E2E testing.

### Knowledge base mode

- `KB_OBJECT_TABLES_ENABLED`
  - When true, the backend `unified_research_tool` may return `object_results` from the per-object object-KB.

- `KB_DIRECT_GCS_FETCH_ENABLED`
  - When true, the backend enables direct `gs://...` fetch + ingest bridging (tenant-validated + size-capped).

### State + output paths

- `ETHERION_EVAL_STATE`
  - Default: `/home/saturnx/langchain-app/scripts/evaluation/state.json`

- `ETHERION_EVAL_OUT_DIR`
  - Default: `/home/saturnx/langchain-app/scripts/evaluation/out`

### Tenant creation

- `ETHERION_EVAL_EMAIL` / `ETHERION_EVAL_PASSWORD` / `ETHERION_EVAL_SUBDOMAIN` / `ETHERION_EVAL_NAME`
  - Optional overrides for `passwordSignup`.

- `ETHERION_INVITE_TOKEN`
  - Optional; only needed if `MULTI_TENANT_ENFORCE_INVITE=true` in the target environment.

### PDF path

- `ETHERION_EVAL_PDF`
  - Default: `/home/saturnx/langchain-app/entropy.pdf`

### BigQuery verification prerequisites

Scripts 2 and 3 perform **BigQuery API** verification and/or semantic search using:
- `google-cloud-bigquery`
- ADC/service account credentials
- `GOOGLE_CLOUD_PROJECT`

If BigQuery credentials are not available, the scripts will still record the ingestion call results, but KB verification/semantic search may error and will be captured in `state.json`.

## Tenant continuity / same tenant across the evaluation

- The harness is designed so **all scripts operate on the same tenant**.
- `eval_1_create_tenant.py` produces `state.json` containing:
  - `access_token`
  - decoded JWT payload `tenant_id`
- Scripts 2–5 read `tenant_id` and `access_token` from `state.json`.

## Size limits (entropy.pdf)

The admin ingestion endpoint enforces a hard limit:
- **10MB max** (`413` if exceeded)

`entropy.pdf` in this repo is ~1.4MB, so it should ingest without hitting the API size limit. If you use a different `entropy.pdf` (~2.8MB), it is still safely below 10MB.

## Operational note: log-based evaluation

These scripts intentionally save **raw trace** events to disk. The evaluation agent should:

- correlate each `job_id` to Cloud Run logs (`etherion-api` and `etherion-worker`) around the timestamps in the trace JSONL
- verify:
  - whether `DUAL_SEARCH` occurred
  - whether web search happened (and which errors occurred, if any)
  - tool invocation events
  - whether KB/vector search is used again opportunistically

---

## Troubleshooting

### Common Issues

#### Celery/Redis Connection Errors
**Symptom**: `Retry limit exceeded while trying to reconnect to the Celery redis result store backend`

**Solution**: The scripts now automatically retry (3 attempts with 10s delay). If all retries fail:
1. Check if Redis is running: `redis-cli ping`
2. Check Celery worker status
3. Verify `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` env vars
4. The eval_2 script will fall back to direct BigQuery KB creation if admin ingest fails

#### Dataset Not Found
**Symptom**: `404 GET .../datasets/tnt_XXX: Not found`

**Solution**: 
- Ensure `GOOGLE_CLOUD_PROJECT` is set correctly
- Run `gcloud auth application-default login` for credentials
- The eval_2 script now automatically creates the dataset if admin ingest fails

#### Authentication Errors
**Symptom**: `credentials` or `authentication` errors

**Solution**:
```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=etherion-ai-production
```

#### Connection Timeouts
**Symptom**: `httpx.TimeoutException` or `httpx.ConnectError`

**Solution**: Scripts now retry automatically. If persistent:
- Check network connectivity
- Verify API endpoints are accessible
- Increase timeout via environment variables

### Reset and Re-run

If you need to reset and re-run:
- delete `scripts/evaluation/state.json`
- delete `scripts/evaluation/out/`

and rerun from step 1.
