<p align="center">
  <img src="./logo.png" alt="Etherion" width="180"/>
</p>

<h1 align="center">Etherion</h1>
<p align="center"><strong>The self-hosted agentic platform. You own it entirely.</strong></p>

<p align="center">
  <a href="https://pypi.org/project/etherion/"><img src="https://img.shields.io/pypi/v/etherion?color=blue&label=etherion" alt="PyPI etherion"/></a>
  <a href="https://pypi.org/project/etherion-tui/"><img src="https://img.shields.io/pypi/v/etherion-tui?color=blue&label=etherion-tui" alt="PyPI etherion-tui"/></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue"/>
  <img src="https://img.shields.io/badge/license-MIT-green"/>
  <img src="https://img.shields.io/badge/release-v0.1.0--alpha-orange"/>
</p>

---

Etherion is an **autonomous, goal-oriented AI platform** you deploy on your own hardware. Give it a business objective — it decomposes, executes, and synthesises the result using a team of AI specialists. No task breakdowns. No SaaS lock-in. No data leaving your infrastructure.

```
User: "Analyse my top 50 customers for churn risk and draft personalised emails"

Platform: → Decomposes goal → Selects specialists → Executes in parallel
          → Reads your CRM (Jira / HubSpot / Shopify) → Writes emails
          → Delivers results. Done.
```

---

## Install

```bash
pip install etherion etherion-tui
```

## Quick Start

```bash
# 1. Scaffold config
etherion init

# 2. Edit .env (API keys, database password, etc.)

# 3. Boot infrastructure  (Postgres + Redis + MinIO via Docker Compose)
etherion bootstrap --mode docker

# 4. Run migrations
etherion migrate

# 5. Create first tenant
etherion tenant create --email you@example.com --password yourpass

# 6. Start API
etherion serve

# 7. Open the terminal UI
etherion-tui
```

That's it. Visit `http://localhost:8080/graphql` for the API playground.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Terminal UI (etherion-tui)  ·  Frontend (Next.js / LobeChat)   │
└────────────────────────┬─────────────────────────────────────────┘
                         │ GraphQL + REST + WebSocket
┌────────────────────────▼─────────────────────────────────────────┐
│                    FastAPI  ·  Strawberry GraphQL                 │
│            JWT auth  ·  CSRF  ·  Rate limiting  ·  RLS           │
└──┬──────────┬──────────┬──────────┬──────────────────────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
PostgreSQL  Redis     MinIO       Vault
+ pgvector  Pub/Sub   Objects     Secrets
  RLS       Celery    Artifacts
```

Every tenant is fully isolated at the **database layer** via Row-Level Security — not just application logic. A bug in application code cannot cause cross-tenant data leaks.

---

## What Makes It Different

### Goal-Oriented Execution
The Orchestrator agent receives a goal, builds a checklist, picks specialists, and executes — no manual task decomposition required.

### Natural Language Agent Creation
```
"Create an agent that watches my Shopify store for abandoned carts
 and sends personalised recovery emails with a 10% discount code."
```
The platform designs the architecture, connects your tools, wires the knowledge base, and deploys it.

### Knowledge Base Without Hallucinations
Every query forces a live web search alongside retrieval. The platform never answers from stale embeddings alone.

### Full Operator Control
- Run on bare metal, VMs, or Docker
- All data stays on your infrastructure
- Secrets injected into RAM via Vault — never written to disk
- OAuth apps registered by YOU, not by us

---

## Features

| Area | Details |
|------|---------|
| **Orchestration** | Checklist-based 2N+1 loop, parallel specialist dispatch, full audit trail |
| **Knowledge base** | pgvector semantic search, per-tenant RLS, multimodal (PDF, images, text) |
| **OAuth integrations** | GitHub, Google, Slack, Microsoft 365, Notion, Jira, HubSpot, Linear, Shopify |
| **Object storage** | MinIO — per-tenant buckets, presigned URLs, artifact management |
| **Secrets** | HashiCorp Vault — secrets injected at runtime, never persisted in env |
| **TUI** | Bubble Tea — onboarding wizard, OAuth manager, live job monitor, tenant switcher |
| **CLI** | `etherion init / bootstrap / migrate / serve / tenant / status` |
| **API** | FastAPI + GraphQL subscriptions, REST, WebSocket, multipart upload |
| **Auth** | JWT, multi-provider OAuth login, invite-only onboarding, per-tenant RLS |
| **Real-time** | Redis Pub/Sub → GraphQL subscriptions → live execution traces in UI |

---

## CLI Reference

```
etherion init          Scaffold .env and docker-compose in current directory
etherion bootstrap     Start infrastructure (--mode docker | nix)
etherion migrate       Run Alembic database migrations
etherion serve         Start the API server
etherion worker        Start Celery worker  (start | beat)
etherion tenant        Manage tenants and users
etherion status        Health-check: Postgres, Redis, MinIO, API, Worker
etherion where         Print config and binary paths
```

---

## Deployment Modes

| Mode | Command | When to use |
|------|---------|-------------|
| **Docker** | `--mode docker` | First install, dev, single server |
| **Nix** | `--mode nix` | Bare-metal, fully declarative, reproducible prod |

For production, the Nix mode provisions the full stack declaratively:
`NixOS → Matchbox → Ansible → systemd + MinIO + Vault`.

---

## Documentation

- [`SETUP.md`](SETUP.md) — Local and production setup guide
- [`Z/agents.md`](Z/agents.md) — Agent-first contribution workflow (read before contributing)
- [`Z/tech.md`](Z/tech.md) — Complete technical architecture
- [`Docs/etherion_docs/`](Docs/etherion_docs/guide.md) — Full platform documentation (12 sections)

---

## Contributing

Etherion uses an **agent-first contribution model**. Before writing a single line, your AI agent must read:

1. `Z/tech.md` — full architecture
2. `Z/agents.md` — contribution workflow and standards

Every PR must include a contribution log (`Logs/Daily/<your-email>`) and a `Z/tech.md` update.
See [`Z/agents.md`](Z/agents.md) for the full workflow.

---

## License

[MIT](LICENSE)

---

## Contact

- **Email** — [architect@etherionai.com](mailto:architect@etherionai.com)
- **X / Twitter** — [@Jonathan_Nde](https://www.x.com/Jonathan_Nde)
- **LinkedIn** — [jonathan-nde](https://www.linkedin.com/in/jonathan-nde-3a5782324/)
