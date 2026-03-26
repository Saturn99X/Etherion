# Setup Guide

This guide covers local development setup and production deployment for Etherion.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | 3.13+ recommended |
| Docker + Compose | 24+ | For Docker mode |
| Go | 1.22+ | Only if building TUI from source |

---

## 1. Install the CLI

```bash
pip install etherion etherion-tui
```

---

## 2. Scaffold Configuration

```bash
mkdir my-etherion && cd my-etherion
etherion init
```

This writes `.env` and `docker-compose.yml` into the current directory.
Open `.env` and fill in at minimum:

```env
# Required
JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
SECRET_KEY=<another long random string>
POSTGRES_PASSWORD=<choose a password>

# At least one LLM provider
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...

# Auth (Login OAuth — register your own apps)
GOOGLE_CLIENT_ID=       # console.cloud.google.com/auth/clients
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=       # github.com/settings/applications/new
GITHUB_CLIENT_SECRET=
```

See `.env.example` for the full reference including all silo OAuth providers.

---

## 3. Boot Infrastructure

```bash
etherion bootstrap --mode docker
```

This starts:
- **PostgreSQL 16 + pgvector** on port 5432
- **Redis 7** on port 6379
- **MinIO** on port 9000 (console: 9001)

Verify everything is healthy:

```bash
etherion status
```

---

## 4. Run Migrations

```bash
etherion migrate
```

Applies all Alembic migrations and sets up Row-Level Security policies.

---

## 5. Create First Tenant

```bash
etherion tenant create \
  --email admin@example.com \
  --password 'YourPassword123!' \
  --subdomain mycompany
```

---

## 6. Start Services

```bash
# API server (port 8080)
etherion serve

# Celery worker (separate terminal)
etherion worker start

# Open the Terminal UI
etherion-tui
```

API playground: `http://localhost:8080/graphql`
MinIO console: `http://localhost:9001` (user: `etherion`, pass: from `.env`)

---

## OAuth Integrations (Silo OAuth)

For the AI agents to read your third-party data, each operator registers their own OAuth app.
The TUI → **OAuth** tab has step-by-step instructions for every provider. Summary:

| Provider | Register at | Env vars |
|----------|-------------|---------|
| Google | `console.cloud.google.com/auth/clients` | `OAUTH_GOOGLE_CLIENT_ID` + `SECRET` |
| Slack | `api.slack.com/apps` | `SLACK_USER_OAUTH_CLIENT_ID` + `SECRET` |
| Microsoft 365 | `entra.microsoft.com` → App registrations | `MICROSOFT_OAUTH_CLIENT_ID` + `SECRET` |
| Shopify | `partners.shopify.com` or store admin | `SHOPIFY_OAUTH_CLIENT_ID` + `SECRET` |
| Jira | API token: `id.atlassian.com/manage-profile/security/api-tokens` | entered in TUI |
| Notion | Integration: `notion.so/profile/integrations` | entered in TUI |
| HubSpot | Private App: HubSpot → Settings → Private Apps | entered in TUI |
| GitHub | PAT: github.com → Settings → Developer settings | entered in TUI |
| Linear | API Key: `linear.app/settings/account/security` | entered in TUI |

Set the redirect URI for browser-based providers to:
`{YOUR_AUTH_BASE_URL}/oauth/silo/{provider}/callback`

---

## Running Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests (requires running services)
pytest tests/integration/ -v

# With coverage
pytest tests/unit/ --cov=src --cov-report=html
```

---

## Production Deployment

### Docker Compose (single server)

```bash
# On your server
git clone https://github.com/Saturn99X/Etherion.git
cd Etherion
cp .env.example .env
# Fill in .env — set ENVIRONMENT=production and real secrets

etherion bootstrap --mode docker
etherion migrate
etherion serve --host 0.0.0.0
```

Put a reverse proxy (nginx / Caddy) in front for TLS.

### NixOS / Bare Metal (declarative)

The `nix` mode provisions the full stack declaratively:

```bash
etherion bootstrap --mode nix
```

This applies NixOS modules via Ansible for:
- `systemd` services (API, worker, frontend)
- MinIO with persistent volumes
- Vault with AppRole auth
- PostgreSQL with pgvector extension
- Redis

Full NixOS configuration is in `infra/`.

---

## Environment Variables Reference

See [`.env.example`](.env.example) for the complete annotated reference.

Key sections:
- **Core** — `ENVIRONMENT`, `PRIMARY_DOMAIN`, `AUTH_BASE_URL`
- **Database** — `DATABASE_URL`, `POSTGRES_*`
- **Security** — `JWT_SECRET_KEY`, `SECRET_KEY`
- **LLM providers** — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.
- **Login OAuth** — for signing in to Etherion (Google, GitHub, Microsoft)
- **Silo OAuth** — for AI agent data access (all 9 providers)
- **Storage** — `STORAGE_BACKEND`, `MINIO_*`
- **Vault** — `VAULT_ADDR`, `VAULT_TOKEN`

---

## Troubleshooting

**`etherion status` shows Postgres unreachable**
→ Run `etherion bootstrap --mode docker` first, or check `docker ps`.

**`alembic upgrade head` fails with permission error**
→ Ensure `DATABASE_URL` in `.env` uses a superuser or a user with `CREATE` privileges.

**MinIO upload errors**
→ Check `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` match what's in `.env`.

**OAuth redirect mismatch**
→ Ensure the redirect URI you registered with the provider exactly matches
  `{AUTH_BASE_URL}/oauth/silo/{provider}/callback`.

**TUI can't connect**
→ Make sure `etherion serve` is running and `ETHERION_API_URL` in the TUI config points to it.

---

## Getting Help

- Email: [architect@etherionai.com](mailto:architect@etherionai.com)
- Open a GitHub issue with the `question` label
- Read `Z/tech.md` for architecture context before asking
