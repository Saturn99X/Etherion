# Etherion AI Platform Overview

Welcome to Etherion—a multi-tenant, enterprise-grade platform for running autonomous AI agents at scale. This guide introduces the system architecture, how requests flow through the platform, and the core design principles that make it tick.

## What Is Etherion?

Etherion is a Platform-as-a-Service (PaaS) for AI agents. It lets organizations:

- **Define and deploy custom agents** that orchestrate complex workflows across dozens of data sources (Gmail, Slack, Notion, Shopify, Jira, Salesforce, and more).
- **Execute agent jobs asynchronously**, tracking progress in real time via WebSocket subscriptions.
- **Store and retrieve AI-generated artifacts**—documents, images, transcripts—with full versioning.
- **Manage multi-tenant isolation** so multiple organizations can safely share hardware without seeing each other's data.
- **Control costs** through credit-based billing, rate limiting, and quota enforcement per tenant.

Think of it as Zapier + n8n, but with large language models as first-class orchestrators. Instead of workflows defined by visual rules, agents in Etherion reason through problems, call tools in real time, and adapt as they learn from results.

## Who Uses Etherion?

**Enterprise Teams** building internal tools that need AI reasoning. For example:
- A support team runs an agent to triage customer issues by fetching ticket metadata from Jira, enriching it with Gmail context, and proposing solutions.
- A product team deploys an agent that monitors Slack for feature requests, queries the knowledge base, and generates prioritized backlogs.

**SaaS Companies** embedding AI into their product without building orchestration from scratch. Etherion provides:
- OAuth integrations for 8+ cloud platforms out of the box.
- Tenant isolation via both database row-level security and application-layer enforcement.
- Cost tracking per customer with revenue sharing via Stripe webhooks.

## The Problem Etherion Solves

Building multi-tenant AI orchestration is hard. Teams must solve:

1. **Concurrency & queuing**: How do you run hundreds of agent jobs without blocking the API?
2. **Data isolation**: How do you prevent one tenant's agent from reading another's Slack messages?
3. **Cost attribution**: Which customer's job consumed that $0.50 of GPT-4 tokens?
4. **Webhook handling**: How do you integrate with external services (Stripe, Slack, Jira) reliably?
5. **Real-time feedback**: How do you stream agent progress to a UI via WebSocket without overwhelming the broker?

Etherion answers all of these with a battle-tested architecture (Celery + PostgreSQL + Redis + MinIO) running on bare metal, Kubernetes, or NixOS.

## Core Architecture at a Glance

The platform comprises five core services:

```
┌─────────────────────────────────────────────────────────────┐
│                       GraphQL API                           │
│              (FastAPI + Strawberry)                         │
│  mutations: executeGoal, subscriptions: onJobStatusChange   │
└──────────────┬────────────────────────┬─────────────────────┘
               │                        │
               ▼                        ▼
        ┌──────────────┐      ┌─────────────────┐
        │ Job Broker   │      │  Pub/Sub Event  │
        │  (Celery)    │      │  Bus (Redis)    │
        └──────┬───────┘      └────────┬────────┘
               │                       │
               ▼                       ▼
        ┌──────────────┐      ┌─────────────────┐
        │  Workers     │      │   Client Apps   │
        │ (orchestrate │      │   (Browser UI)  │
        │   goals)     │      │                 │
        └──────┬───────┘      └─────────────────┘
               │
               ▼
        ┌──────────────┐
        │  Data Silo   │
        │  (Gmail,     │
        │   Notion,    │
        │   Slack...)  │
        └──────────────┘
```

1. **GraphQL API** accepts requests and enforces tenant context + authentication.
2. **Job Broker** (Celery) queues work across multiple workers.
3. **Event Bus** (Redis) broadcasts job status changes back to the UI.
4. **Workers** fetch jobs, orchestrate agent reasoning loops, and integrate with external systems.
5. **Data Silos** represent connected services (Gmail, Slack, Notion) where the agent executes tool calls.

## Request Lifecycle Example

When a user runs an agent job:

1. **Client** calls `executeGoal(agentId, input)` via GraphQL.
2. **API** validates auth, assigns the job to the tenant, and enqueues a Celery task.
3. **Worker** picks up the job and enters an agentic loop: "think → act → observe → repeat."
4. **Agent** calls tools (e.g., "fetch Gmail messages") which trigger MCP tool handlers.
5. **MCP Handler** reaches out to the data silo (Gmail API) with tenant-scoped credentials.
6. **Result** flows back through the agent, which decides on the next step.
7. **Progress** is published to Redis, triggering WebSocket messages to the UI.
8. **Job Complete** updates the database and emits a final event.
9. **Artifacts** (transcripts, images) are stored in object storage (MinIO/GCS) for later retrieval.

For a complete walkthrough, see `request-lifecycle.md`.

## Key Design Principles

### Multi-Tenancy First
Every request includes a `tenant_id` that threads through the entire call stack. Databases use RLS; caches are namespaced; credentials are stored in per-tenant secret vaults. There is no "default" tenant—it's always explicit.

### Asynchronous Everything
Jobs are enqueued, not executed inline. Even fast operations go through Celery. This ensures:
- The API remains responsive during heavy computation.
- Long-running agent loops don't block HTTP connections.
- Work can be retried with exponential backoff if workers fail.

### Credential Isolation
OAuth tokens and API keys are stored in per-tenant secret managers. Workers fetch credentials at execution time using the tenant ID. There's no shared secret store.

### Event-Driven Updates
The UI subscribes to a WebSocket that publishes job status changes from Redis. This replaces polling and keeps the UI reactive even with hundreds of concurrent jobs.

### Quota & Rate Limiting
Tenants have per-vendor quotas (e.g., "max 5000 Slack API calls per day"). Incoming webhooks and API requests increment Redis counters. When a quota is exceeded, requests fail with a 429 status and retry-after header.

## What's Inside This Documentation

- **`architecture.md`** — Deep dive into the five core services, their data flow, and deployment topology.
- **`request-lifecycle.md`** — Annotated trace of an agent job from HTTP request to completion, with code snippets from each layer.

Start with `README.md` (this file) to understand the why, then move to `architecture.md` for the how, and finally `request-lifecycle.md` to see it all in action.
