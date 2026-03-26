# Etherion Commands Deep Dive

Each command is explained below: what it does, what environment variables it needs, what happens when they're missing, and real code examples from the implementation.

## `etherion init [--mode {docker,ansible,nix,all}] [--target {path}]`

**Purpose**: Scaffold a new Etherion deployment by creating configuration files in the target directory.

**Default mode**: `all` (copies Docker, Ansible, and NixOS configs). Useful for projects that might deploy anywhere.

**What it creates**:
- `.env.example` — Reference template with all required variables and sane defaults
- `alembic.ini` — Database migration configuration (only created if not present, never overwritten)
- `alembic/env.py` and `alembic/versions/` — Migration infrastructure
- `docker-compose.services.yml` — Service definitions for PostgreSQL, Redis, MinIO (if mode includes `docker`)
- `ansible/` directory — Deployment playbooks and roles (if mode includes `ansible`)
- `nix/` directory — NixOS module definitions (if mode includes `nix`)

**Examples**:

```bash
# Local development (Docker)
etherion init --mode docker --target .

# Bare-metal deployment (NixOS + Ansible)
etherion init --mode nix --target ./infra

# All-in-one (supports all deployment methods)
etherion init
```

**If `.env` already exists**: The command does not overwrite it. It prints a message and moves on, so running `init` twice is safe.

**Exit on error**: If the target directory cannot be created or files cannot be written, you get a clear error with the specific file path that failed.

---

## `etherion bootstrap [--mode {docker,native}]`

**Purpose**: Start infrastructure services (PostgreSQL, Redis, MinIO, Vault) that the application depends on.

**Default mode**: `docker` (starts services via Docker Compose).

**What it does**:

In **docker mode**:
1. Checks for `docker-compose.services.yml` (created by `etherion init`)
2. Runs `docker compose up -d` to start services in the background
3. Falls back to legacy `docker-compose` if modern `docker compose` is not available
4. Polls each service (PostgreSQL, Redis, MinIO) until it responds to health checks
5. Times out after 90 seconds if any service doesn't become healthy
6. Prints `✓ All services healthy` on success

In **native mode**:
- Assumes PostgreSQL, Redis, and MinIO are already managed by systemd on this machine
- Performs the same health checks but does not start any containers
- Useful after a bare-metal deployment where services are provisioned by Ansible/systemd

**Example**:

```bash
# Start Docker services locally
etherion bootstrap --mode docker

# Validate that native systemd services are running
etherion bootstrap --mode native
```

**Environment variables** (optional in docker mode, consulted if present):
- `DATABASE_URL` — PostgreSQL connection string (default: `postgresql://etherion:etherion@localhost:5432/etherion`)
- `REDIS_URL` or `ETHERION_REDIS_URL` — Redis URL (default: `redis://localhost:6379/0`)
- `MINIO_ENDPOINT` — MinIO HTTP endpoint (default: `http://localhost:9000`)

**If `.env` is missing**: Prints a warning and uses default service credentials. This is intentional for first-time setup.

**If a service times out**: Exits with status 1 and lists which services failed to become healthy. Example:

```
Timed out waiting for: PostgreSQL, Redis
```

---

## `etherion migrate [revision]`

**Purpose**: Run Alembic database migrations to bring the PostgreSQL schema in sync with the application code.

**Arguments**:
- `revision` (default: `head`) — Alembic revision target. Can be a specific revision hash, `head` (latest), or `+1` (one forward).

**Required environment variables**:
- `DATABASE_URL` — PostgreSQL connection string (e.g., `postgresql+psycopg2://user:pass@localhost:5432/etherion`)

**What happens**:

1. Validates that `.env` exists and `DATABASE_URL` is set
2. Logs the truncated database URL (first 40 chars) for visibility
3. Constructs and runs: `python -m alembic upgrade <revision>`
4. Streams alembic's output to stdout so you see what's happening
5. Exits with the same status code as alembic

**Examples**:

```bash
# Migrate to the latest version
etherion migrate

# Migrate to a specific revision
etherion migrate 2c1a2b3d4e5f

# Migrate forward one step
etherion migrate +1
```

**If `DATABASE_URL` is missing**:

```
✗ Missing required environment variable(s):

  • DATABASE_URL

  Set these in .env (or export them) before retrying.
  See .env.example for reference values.
```

**If the database is unreachable**: Alembic will fail with a connection error, and the command exits with status 1. The alembic error message tells you what went wrong (e.g., "connection refused" if the database is down).

---

## `etherion serve [--host {host}] [--port {port}] [--workers {n}] [--reload]`

**Purpose**: Start the Etherion GraphQL API server using Uvicorn.

**Flags**:
- `--host` — Override `API_HOST` from `.env` (default: `0.0.0.0`, listen on all interfaces)
- `--port` — Override `API_PORT` from `.env` (default: `8080`)
- `--workers` — Number of worker processes (default: `1`, useful for production)
- `--reload` — Auto-reload on code changes (development only; forces workers=1)

**Required environment variables**:
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` (or `ETHERION_REDIS_URL`) — Redis URL for caching and task queue
- `JWT_SECRET_KEY` — Secret for signing JWT tokens (minimum 32 random bytes, base64-encoded)
- `SECRET_KEY` — Flask/session secret (used by some middleware)

**What happens**:

1. Validates `.env` exists and all four required vars are non-empty
2. Loads `.env` into the environment (via `python-dotenv`)
3. Resolves host and port from flags or `.env`
4. Prints: `Starting API on {host}:{port}`
5. Runs: `uvicorn src.etherion_ai.app:app --host {host} --port {port} ...`

**Examples**:

```bash
# Start with defaults from .env
etherion serve

# Start on a different port
etherion serve --port 3000

# Production mode with 4 worker processes
etherion serve --workers 4

# Development mode with auto-reload
etherion serve --reload

# Start on specific host and port
etherion serve --host 127.0.0.1 --port 8080
```

**If required vars are missing**:

```
✗ Missing required environment variable(s):

  • JWT_SECRET_KEY
  • SECRET_KEY

  Set these in .env (or export them) before retrying.
  See .env.example for reference values.
```

**If the database is unreachable**: The API starts but immediately fails when it tries to query the database. Uvicorn keeps running and retries, so the error appears in the logs, not on startup.

---

## `etherion worker start [--queues {queue1,queue2}] [--concurrency {n}] [--loglevel {level}]`

**Purpose**: Start a Celery worker that pulls async jobs from the message broker and executes them.

**Flags**:
- `--queues` (default: `celery,worker-artifacts`) — Comma-separated queue names to listen on
- `--concurrency` (default: `4`) — Number of concurrent task executions (threads in this case)
- `--loglevel` (default: `info`) — One of `debug`, `info`, `warning`, `error`, `critical`

**Required environment variables**:
- `CELERY_BROKER_URL` (or `REDIS_URL` / `ETHERION_REDIS_URL`) — Message broker connection (typically Redis)
- `DATABASE_URL` — PostgreSQL connection string (tasks may write to the database)

**What happens**:

1. Validates `.env` exists and both required vars are non-empty
2. Loads `.env` into the environment
3. Prints: `Starting Celery worker (queues={queues})`
4. Runs: `python -m celery -A src.core.celery.celery_app worker --pool=threads --concurrency=... --loglevel=...`
5. The worker loops forever, polling the broker for tasks

**Examples**:

```bash
# Start with defaults
etherion worker start

# Listen on custom queues
etherion worker start --queues priority-tasks,batch-jobs

# More concurrent tasks (threads)
etherion worker start --concurrency 8

# Debug logging
etherion worker start --loglevel debug

# Combined
etherion worker start --queues gpu-jobs --concurrency 2 --loglevel info
```

**If `DATABASE_URL` or broker URL is missing**:

```
✗ Missing required environment variable(s):

  • CELERY_BROKER_URL
  • DATABASE_URL

  Set these in .env (or export them) before retrying.
  See .env.example for reference values.
```

**If the broker is unreachable**: Celery logs a warning and retries. It does not exit immediately, so you may not notice for a few seconds. Check logs for `[WARNING]` messages from `celery.connection`.

---

## `etherion worker beat [--loglevel {level}]`

**Purpose**: Start the Celery Beat scheduler, which periodically enqueues recurring tasks (cron-like jobs).

**Flags**:
- `--loglevel` (default: `info`) — One of `debug`, `info`, `warning`, `error`, `critical`

**Required environment variables**:
- `CELERY_BROKER_URL` (or `REDIS_URL`) — Message broker connection
- `DATABASE_URL` — PostgreSQL connection string

**What happens**:

1. Validates `.env` and required vars (same as `worker start`)
2. Prints: `Starting Celery beat scheduler`
3. Runs: `python -m celery -A src.core.celery.celery_app beat --loglevel=...`
4. Reads scheduled tasks from the database and enqueues them at the right times

**Examples**:

```bash
# Start beat scheduler
etherion worker beat

# Debug mode
etherion worker beat --loglevel debug
```

**Important**: Only run one beat scheduler per Celery cluster. If you start two, they'll both enqueue tasks at the same time, causing duplicates. For redundancy (beat failover), use Redis-based locking or Celery's HA beat features (outside the scope of this CLI).

---

## `etherion status`

**Purpose**: Health-check all services without modifying anything. Useful for diagnostics and monitoring.

**Flags**: None.

**What it checks** (in parallel):
- PostgreSQL: Queries `SELECT version()`, returns version string
- Redis: Calls `PING`, returns Redis version
- MinIO: Hits `/minio/health/live` HTTP endpoint
- API: Hits `/health` HTTP endpoint, returns HTTP status code
- Worker: Counts Celery queue bindings (presence of workers)
- Vault: Queries `/v1/sys/health` (only if `SECRETS_BACKEND=vault`)

**Output**: A table with columns `Service`, `Status`, `Detail`. Status is `✓` (green) for healthy, `?` (yellow) for missing required env var, or `✗` (red) for error.

**Example output**:

```
Etherion Platform Status

 Service        Status  Detail
─────────────────────────────────────────────────────────
 PostgreSQL     ✓       PostgreSQL 14.7 on x86_64-pc... (45ms)
 Redis          ✓       Redis 7.0.0 (12ms)
 MinIO          ✓       http://localhost:9000 (8ms)
 API            ✓       HTTP 200 at http://localhost:8080 (23ms)
 Worker         ✓       2 queue binding(s) (5ms)
 Vault          ?       VAULT_ADDR not set
```

**If a service is down**:

```
 PostgreSQL     ✗       connection refused
```

**Environment variables**:
- Optional: `DATABASE_URL`, `REDIS_URL`, `MINIO_ENDPOINT`, `API_HOST`, `API_PORT`, `VAULT_ADDR`
- Missing vars are shown as `?` with a hint; they do not cause the command to fail

**If `.env` is missing**: Prints a warning and uses environment variables only (or defaults). The command still runs.

---

## `etherion create-tenant --name {name} --email {email} --password {password} [--subdomain {subdomain}]`

**Purpose**: Create a new tenant (isolated customer workspace) and an admin user in one transaction.

**Flags**:
- `--name` (required) — Tenant display name (e.g., "Acme Corp")
- `--email` (required) — Admin user email address
- `--password` (required) — Admin user password (plain text; hashed before storage)
- `--subdomain` (optional) — Tenant subdomain (e.g., "acme"). Auto-derived from name if omitted.

**Required environment variables**:
- `DATABASE_URL` — PostgreSQL connection string

**What happens**:

1. Validates `.env` and `DATABASE_URL`
2. Auto-derives subdomain from name if not provided (converts to lowercase, replaces non-alphanumeric with hyphens)
3. Generates a unique `tenant_id` (format: `t_{12-char-hex}`)
4. Hashes password using PBKDF2-SHA256 (200,000 iterations)
5. Inserts `Tenant` and `User` records into the database in a single transaction
6. Prints the generated `tenant_id` and admin email on success
7. Rolls back on any error (database constraint violation, missing table, etc.)

**Examples**:

```bash
# Create with explicit subdomain
etherion create-tenant \
  --name "Acme Corporation" \
  --email admin@acme.com \
  --password "SecurePassword123!" \
  --subdomain acme

# Auto-derive subdomain from name
etherion create-tenant \
  --name "Acme Corporation" \
  --email admin@acme.com \
  --password "SecurePassword123!"
# subdomain becomes "acme-corporation"
```

**Output on success**:

```
Creating tenant Acme Corporation (subdomain=acme)…
✓ Tenant created: t_a1b2c3d4e5f6g7h8
✓ Admin user:    admin@acme.com
```

**If `DATABASE_URL` is missing**:

```
✗ Missing required environment variable(s):

  • DATABASE_URL
```

**If subdomain is already taken** (or other database error):

```
Error: (psycopg2.IntegrityError) duplicate key value violates unique constraint "uq_tenant_subdomain"
```

The transaction rolls back, so neither the tenant nor user is created. The process exits with status 1.

---

## `etherion where`

**Purpose**: Show all files, processes, containers, and connections on this machine. A diagnostic snapshot without modifying anything.

**Flags**: None.

**What it displays** (5 sections):

1. **Files & Directories**: `.env`, `.env.example`, `alembic.ini`, migration files, TUI config, etc.
2. **Running Processes**: API server (uvicorn), Celery worker, Celery beat, with PIDs
3. **Docker Containers**: List of running/stopped containers and their port mappings
4. **Configuration Summary**: Connection strings from `.env` (database URL, Redis, MinIO endpoint, API host:port, active LLM backend, secrets backend, etc.)
5. **How to Stop / Clean Up**: Commands to kill processes, tear down Docker services, or delete configs

**Example output**:

```
Files & Directories

 Item                    Path                                          Note
─────────────────────────────────────────────────────────────────────────────
 ✓ Project .env          /home/user/etherion/.env                     Main configuration
 ✓ .env.example          /home/user/etherion/.env.example             Reference template
 ✓ docker-compose file   /home/user/etherion/docker-compose...        Service definitions
 ✓ Alembic config        /home/user/etherion/alembic.ini              Database migrations
 ✓ Alembic migrations    /home/user/etherion/alembic/versions         Migration history
 — TUI config            ~/.config/etherion/tui.json                  Not yet created


Running Processes

 Process                 PID(s)      How to stop
─────────────────────────────────────────────────────────────────────────────
 ✓ API server            12345       kill 12345
 ✓ Celery worker         12346       kill 12346
 — Celery beat           not running


Docker Containers

 Name                    Status              Ports
─────────────────────────────────────────────────────────────────────────────
 etherion-postgres       Up 2 hours          5432:5432
 etherion-redis          Up 2 hours          6379:6379
 etherion-minio          Up 2 hours          9000:9000

Docker volumes (data lives here): etherion-postgres-data, etherion-redis-data


Configuration Summary

 Key                     Value                                       Note
─────────────────────────────────────────────────────────────────────────────
 DATABASE_URL            postgresql+psycopg2://user:***@loc...       PostgreSQL
 REDIS_URL               redis://localhost:6379/0                    Redis
 MINIO_ENDPOINT          http://localhost:9000                       MinIO
 API_HOST:PORT           0.0.0.0:8080                                Etherion API
 LLM_PROVIDER            anthropic                                   Active LLM backend
 SECRETS_BACKEND         vault                                       Secrets storage
 KB_VECTOR_BACKEND       pgvector                                    Knowledge-base backend


How to Stop / Clean Up

 Action                  Command
─────────────────────────────────────────────────────────────────────────────
 Stop API server         kill $(pgrep -f 'uvicorn|etherion serve')
 Stop Celery worker      kill $(pgrep -f 'celery worker')
 Stop Docker services    docker compose -f docker-compose.services.yml down
 Remove Docker data      docker compose -f docker-compose.services.yml down -v  ← destroys DB!
 Delete TUI config       rm ~/.config/etherion/tui.json
```

**Environment variables**: None required; the command reads `.env` if present but doesn't fail if missing.

**Platform differences**: On Windows, the command uses `tasklist` instead of `ps aux` to find processes and shows Windows-specific paths for the TUI config.

---

## Exit Codes Summary

All commands follow this pattern:
- **0**: Success (command completed as intended)
- **1**: Validation failure (missing required env var, file not found, etc.) or runtime error (database unreachable, Docker daemon not running, etc.)

Validation failures always print a clear error message before exiting. Runtime errors may print a traceback (from the underlying library) after a clear initial message.
