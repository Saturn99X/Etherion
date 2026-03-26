# The Etherion CLI: Platform Operations Unified

The `etherion` command-line interface is the single entry point for every operational task on the Etherion platform. Instead of reaching for Docker commands, Ansible playbooks, SQL migration tools, and systemd units scattered across your infrastructure, you type one command. It wraps all of that complexity into clear, predictable operations.

Think of it like this: Kubernetes has `kubectl`, Terraform has `terraform`, and Etherion has `etherion`. But unlike those tools, the `etherion` CLI doesn't assume you're running on a specific platform. You can bootstrap locally with Docker, run migrations on a bare-metal PostgreSQL, start workers on native systemd, and later tear it all down with a single command. It adapts to your environment.

## Why This Exists

Before the CLI, operations were fragmented. A new developer would need to know:
- How to start Docker Compose services
- Where database migrations live and how to run them
- How to configure environment variables
- What health checks mean in the logs
- How to diagnose if something broke

The CLI centralizes all of that knowledge. It validates your configuration before starting anything, shows clear error messages when something is missing, and provides a common interface across local development, testing, and production environments.

The design philosophy is simple: **fail fast with a clear message, never with a cryptic traceback at startup**.

## The Nine Commands at a Glance

### `etherion init`

Scaffolds the configuration for a new Etherion deployment. Creates `.env.example`, Alembic migration infrastructure, and either Docker Compose or bare-metal deployment files depending on your mode.

Use this first, always. It's idempotent — running it twice won't overwrite existing configs.

### `etherion bootstrap`

Starts the infrastructure services your application needs: PostgreSQL, Redis, MinIO (object storage), and Vault (optional, for secrets). In Docker mode, it runs `docker-compose up` and polls services until they're healthy. In native mode, it assumes systemd is already managing the services and validates that they're running.

This is what you run after `init` to get a working local environment, or after provisioning a bare-metal server.

### `etherion migrate [revision]`

Runs Alembic database migrations, bringing your PostgreSQL schema from its current state to the target revision (default: `head`, the latest). Validates that `DATABASE_URL` is set and reachable before running migrations. Gives you clear feedback on success or failure with the exact migration command that ran.

### `etherion serve`

Starts the Etherion API server using Uvicorn. Validates all required secrets (`JWT_SECRET_KEY`, `SECRET_KEY`, database and Redis URLs) before binding to the port. Accepts `--host`, `--port`, `--workers`, and `--reload` flags to override `.env` settings, but respects `.env` defaults if not overridden.

In production, this runs under systemd supervision so that if the process crashes, it restarts automatically.

### `etherion worker start`

Starts a Celery worker listening on configured queues (default: `celery,worker-artifacts`). Validates that the message broker (Redis or RabbitMQ) is reachable and that `DATABASE_URL` is set. Accepts `--queues`, `--concurrency`, and `--loglevel` flags to configure parallelism and logging.

Workers pull async jobs from the broker and execute them, with their state persisted in the database.

### `etherion worker beat`

Starts the Celery Beat scheduler, which periodically enqueues recurring tasks (like "check for model updates every hour"). Like `worker start`, it validates the broker connection and database URL. The beat scheduler and workers are separate processes; you typically run one beat per deployment and multiple worker instances for parallelism.

### `etherion status`

Queries the health of every service the platform depends on:
- PostgreSQL version and connectivity
- Redis version and connectivity
- MinIO object storage availability
- API server HTTP health endpoint
- Celery worker heartbeat (queue bindings)
- Vault status (if `SECRETS_BACKEND=vault`)

Runs these checks concurrently and displays results in a table. Each check shows a pass/fail icon and timing. If a required env var is missing, the check shows `?` with a hint about what needs to be set.

### `etherion create-tenant`

Creates a new tenant (isolated customer workspace) and an admin user for that tenant. Takes `--name`, `--email`, `--password`, and optional `--subdomain` flags. Auto-generates a subdomain from the name if omitted. Creates both database records and returns the tenant ID for later reference.

This is typically run once per new customer onboarding, though it can be repeated to create multiple tenants in one deployment.

### `etherion where`

The "where is everything?" command. Shows:
- Files created by Etherion on your filesystem (`.env`, Alembic migrations, configs)
- Running processes (API server, Celery worker, beat scheduler)
- Docker containers and volumes (if Docker is running)
- Connection strings from `.env` (database, Redis, MinIO, Vault)
- How to stop each component

Use this to orient yourself on a new server or to diagnose what's running when something goes wrong. It's a snapshot of the current state without modifying anything.

## Environment Variable Validation

Every command that needs configuration validates it before doing anything. The validation is structured in layers:

1. **File existence**: Does `.env` exist? If not, a clear message tells you how to create it.
2. **Required variables**: For each command, specific env vars are required (see `commands.md`). If any are missing or empty, you get a list of which ones with hints on what they should be.
3. **Connectivity**: Does the database respond? Can Redis be reached? These checks happen as the command runs.

The goal is to fail fast with a named problem ("Missing DATABASE_URL") instead of watching the application start, then crash 30 seconds later with "connection refused" deep in some library's traceback.

## Local Development Workflow

```bash
# First time
etherion init --mode docker
# Edit .env with your local secrets (copy from .env.example if unsure)
etherion bootstrap
# Start the API in foreground (for development)
etherion serve --reload

# In another terminal
etherion worker start
etherion worker beat

# Check everything is healthy
etherion status

# Show what's running
etherion where

# Stop services (Ctrl+C stops serve/worker, then:)
docker compose -f docker-compose.services.yml down
```

## Production Deployment Workflow

On a bare-metal server (or VM) running NixOS with systemd:

```bash
# Provisioned by Ansible (see nix-and-ansible.md)
etherion init --mode nix
# .env is injected by Vault Agent via systemd environment files
# Services are managed by systemd units

# After an app update
etherion migrate
systemctl restart etherion-api
systemctl restart etherion-worker

# Diagnose issues
etherion status
etherion where
```

## Exit Codes and Error Messages

All commands exit with status 0 on success, 1 on validation failure or runtime error. Error messages are written to stderr and are always prefixed with a clear problem statement, never a traceback. For example:

```
✗ Missing required environment variable(s):

  • DATABASE_URL
  • JWT_SECRET_KEY

  Set these in .env (or export them) before retrying.
  See .env.example for reference values.
```

This is not a crash; it's actionable feedback. The developer immediately knows what to do next.

## Next Steps

- Read `commands.md` for the detailed behavior of each command, including all flags and required environment variables.
- Read `dot-env-guards.md` to understand how environment validation works under the hood.
- Read `bare-metal-stack.md` to understand the production infrastructure (NixOS, Ansible, systemd, Vault).
- Read `nix-and-ansible.md` to see how deployments are orchestrated.
