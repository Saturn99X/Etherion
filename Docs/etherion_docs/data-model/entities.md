# Etherion Entities: A Deep Dive

This document walks through every major entity in Etherion, explaining what it represents, its key fields, and the reasoning behind the design. Think of this as reading the mind of the architect.

## Tenant

**What it represents**: An isolated workspace. In a SaaS context, this is typically a company or organization. Etherion is a multi-tenant platform, so each Tenant is completely separate.

**Key fields**:

- `id` — Primary key (PostgreSQL serial)
- `tenant_id` — A 13-character URL-safe unique identifier (not a serial). Used in URLs and APIs because it's shorter and more memorable than an integer
- `subdomain` — Unique DNS subdomain (e.g., "acme-corp.etherion.dev"). Used for vanity URLs and tenant routing
- `name` — Display name (e.g., "Acme Corp")
- `admin_email` — Contact email for tenant administrators
- `default_retention_policy_days` — How long data persists before archival (default 365 days)
- `is_active` — Whether the tenant is operational
- `created_at` — Timestamp of creation

**Why these fields exist**:

The dual-ID pattern (`id` and `tenant_id`) is intentional. The integer `id` is for internal database relationships and RLS policies (it's fast and compact). The string `tenant_id` is for external APIs and URLs (it's opaque and doesn't leak internal database structure). The `subdomain` enables domain-based tenant routing — if you visit `acme-corp.etherion.dev`, the app knows it's for that tenant.

The `default_retention_policy_days` sets a baseline for data expiration. Files, messages, and execution traces all respect this, ensuring compliance with data residency requirements.

## User

**What it represents**: A human who belongs to exactly one Tenant. This is not a global user — it's a tenant-scoped user.

**Key fields**:

- `id` — Primary key
- `user_id` — A unique identifier (OAuth subject, email, or system-generated)
- `email` — Email address for authentication and contact
- `name` — Display name
- `profile_picture_url` — Avatar from OAuth provider
- `provider` — OAuth provider name (e.g., "google", "apple")
- `tenant_id` — Foreign key to Tenant (the constraint that makes this user scoped to one tenant)
- `is_admin` — Whether user has admin privileges within the tenant
- `is_active` — Whether account is active
- `last_login` — Last successful authentication timestamp
- `password_hash` — For non-OAuth users (optional)
- `created_at`, `updated_at` — Audit timestamps

**Why these fields exist**:

The `provider` field tracks the OAuth provider. This matters because a user might authenticate via Google on a desktop but Apple on mobile — same user, potentially different identifiers. The `profile_picture_url` is cached from the OAuth response to avoid repeated remote calls.

The `is_admin` flag enables role-based access control within a tenant. Not all users can invite others or modify settings.

The `tenant_id` foreign key is **critical**: it ensures that a user belongs to exactly one tenant. No user can span multiple tenants; you must create separate User records in each tenant if needed.

## Project

**What it represents**: A logical grouping for conversations and knowledge base files. Think of it as a "workspace" or "case" within a Tenant.

**Key fields**:

- `id` — Primary key
- `name` — Project name (e.g., "Q2 Sales Analysis")
- `description` — Markdown-friendly project summary
- `tenant_id` — Foreign key to Tenant
- `user_id` — Foreign key to User (who created/owns it)
- `created_at` — Timestamp

**Why these fields exist**:

Projects enable hierarchical organization. A tenant with 50 conversations might organize them as:
- Project A: "Customer Support"
- Project B: "Data Analysis"
- Project C: "Marketing Drafts"

The `user_id` indicates the project owner, but the project is visible to all users in the tenant (RLS policies can enforce view/edit permissions if needed). The `description` is free-form text to document the project's purpose.

## Conversation

**What it represents**: A single chat session. Each Conversation is a container for Messages (turns in the chat). When a user starts a new chat, a new Conversation is created.

**Key fields**:

- `id` — Primary key
- `title` — User-provided or auto-generated conversation title (e.g., "Help with Python debugging")
- `project_id` — Foreign key to Project (which project this conversation belongs to)
- `tenant_id` — Foreign key to Tenant (redundant with Project's tenant, but present for query efficiency)
- `created_at` — Timestamp

**Why these fields exist**:

The `title` helps users quickly find conversations in their history. The dual foreign keys (`project_id` and `tenant_id`) is a denormalization for performance. Queries like "get all conversations in tenant X" don't need to join through Project; they can filter by `tenant_id` directly.

Note: The design separates Conversation (stateless container) from Thread (streaming-friendly, long-running). Conversation is simpler and older; Thread is newer and supports streaming agents and tool invocations.

## Message

**What it represents**: A single turn in a Conversation. A message has a role (user, assistant, system) and content.

**Key fields**:

- `id` — Primary key
- `role` — Either "user", "assistant", or "system"
- `content` — The message text
- `conversation_id` — Foreign key to Conversation
- `tenant_id` — Foreign key to Tenant (for RLS filtering)
- `created_at` — Timestamp

**Why these fields exist**:

The `role` field enables the UI to render messages differently (user messages on the right, assistant on the left). The separation of roles also helps when logging and auditing.

The `tenant_id` is present for RLS enforcement. Combined with Conversation's ownership chain, it ensures no cross-tenant message leaks.

## Thread & ThreadMessage

**What it represents**: A modern alternative to Conversation for long-running, streaming interactions. Thread supports branching (via `parent_id` and `branch_id`) and is more aligned with agent-based interactions.

**ThreadMessage key fields**:

- `message_id` — Unique identifier (not an integer, to support distributed systems)
- `thread_id` — Foreign key to Thread
- `role` — "user", "assistant", "system", or "tool"
- `content` — Message text
- `parent_id` — For threading: which message this is a reply to
- `branch_id` — For branching: alternative conversation branches
- `metadata_json` — JSON storage for extra fields (LLM model, temperature, etc.)
- `created_at` — Timestamp

**Why this design**:

Threads support exploration of alternative generation paths. A user might say "Actually, try a different approach" which creates a new branch without losing the previous conversation. The `parent_id` and `branch_id` fields enable this tree structure.

The `metadata_json` field is a common pattern in Etherion: use JSON strings for semi-structured data that doesn't warrant a full table.

## MessageArtifact

**What it represents**: Attachments to messages (images, files, code blocks, etc.).

**Key fields**:

- `message_id` — Foreign key to Message
- `kind` — Type: "image", "file", "code", "link", etc.
- `payload_ref` — Storage reference (e.g., S3 URI, MinIO path)
- `created_at` — Timestamp

**Why this design**:

Messages often include rich media. Rather than storing binary data in the message content, artifacts are stored separately and referenced. The `payload_ref` is a URI, not raw data, so the database doesn't bloat.

## ToolInvocation

**What it represents**: A record of when an agent called an external tool (API, database query, web search, etc.).

**Key fields**:

- `invocation_id` — Unique identifier for this invocation
- `thread_id` — Which thread this tool was invoked in
- `message_id` — Which message triggered the invocation (optional)
- `tool` — Name of the tool (e.g., "web_search", "postgres_query")
- `params_json` — The input parameters as JSON
- `status` — "PENDING", "RUNNING", "COMPLETED", "FAILED", or "TIMEOUT"
- `result_json` — The output as JSON (if completed)
- `cost` — Cost in USD (for billing)
- `timings` — Performance metrics as JSON
- `created_at` — Timestamp

**Why this design**:

Tool invocations are the audit trail. Every time an agent runs `web_search("climate change")`, this record shows what happened. The `status` field enables polling. The `cost` field feeds into billing. The `timings` help debug performance.

## Job

**What it represents**: An async execution of a goal or task. Jobs are queued, executed asynchronously (possibly on worker machines), and then completed or failed.

**Key fields**:

- `id` — Primary key
- `job_id` — A 16-character URL-safe identifier (e.g., "job_aBcDeFgHiJkLmNo")
- `tenant_id` — Foreign key to Tenant
- `user_id` — Foreign key to User (who initiated the job)
- `status` — One of: QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED, PENDING_APPROVAL
- `job_type` — String describing what the job does (e.g., "execute_goal", "generate_report")
- `input_data` — JSON string of input parameters
- `output_data` — JSON string of results (if completed)
- `error_message` — If FAILED, the error text
- `thread_id` — Optional: which thread this job is running in (for streaming)
- `created_at` — When the job was queued
- `started_at` — When execution began
- `completed_at` — When execution finished
- `expires_at` — Global timeout for the job
- `trace_data_uri` — Storage location of execution logs

**Why this design**:

Jobs decouple user-facing requests from backend work. A user might submit a 5-minute report generation task and check back later. The `status` enum enables the UI to show progress. The `job_id` is URL-safe so it can be included in notifications and links without escaping.

The `input_data` and `output_data` are stored as JSON strings rather than separate tables. This keeps the schema simple and allows flexible payloads.

The `thread_id` enables integration with streaming: a job can stream updates to a Thread as it progresses.

## ExecutionCost

**What it represents**: A billing record for the API calls made during a Job's execution. When an agent calls Claude or GPT-4, a cost is incurred. This entity records it.

**Key fields**:

- `job_id` — Which job this cost is associated with
- `tenant_id` — Which tenant is being charged
- `step_name` — Which step in the job (e.g., "Specialist: drafting_agent")
- `model_used` — Which LLM (e.g., "gpt-4", "claude-3-opus")
- `input_tokens` — Prompt tokens
- `output_tokens` — Completion tokens
- `step_cost` — Cost in USD (calculated from token counts and model pricing)
- `timestamp` — When this cost was incurred

**Why this design**:

Etherion charges customers based on API usage. This table is the source of truth for billing. By storing `input_tokens` and `output_tokens` separately, the system can recalculate costs if pricing changes (e.g., a new model becomes cheaper).

## CustomAgentDefinition

**What it represents**: A user-defined AI agent. A tenant can create custom agents with specific system prompts, allowed tools, and model preferences.

**Key fields**:

- `custom_agent_id` — URL-safe unique identifier (e.g., "ca_aBcDeFgHiJkLmNo")
- `tenant_id` — Foreign key to Tenant
- `name` — Display name (e.g., "Research Assistant")
- `description` — What this agent does
- `system_prompt` — The LLM system prompt defining behavior
- `tool_names` — JSON list of allowed tool names (e.g., ["web_search", "database_query"])
- `model_name` — Which LLM to use (e.g., "gemini-2.5-flash")
- `max_iterations` — How many reasoning loops before stopping (default 10)
- `timeout_seconds` — Execution timeout (default 300 seconds)
- `temperature` — LLM creativity setting (0.1 to 2.0)
- `is_active` — Whether the agent can be used
- `is_system_agent` — Whether it's platform-provided or user-defined
- `is_deleted` — Soft-delete flag
- `version` — Semantic version (e.g., "1.0.0")
- `is_latest_version` — Whether this is the most recent version
- `execution_count` — Total number of times this agent has run
- `last_executed_at` — When it last ran
- `custom_metadata` — JSON for additional configuration

**Why this design**:

Agents are the computational units in Etherion. By allowing users to define their own, the platform becomes extensible. The `tool_names` list restricts which APIs the agent can call (a security boundary). The version fields enable tracking agent evolution over time.

The `is_system_agent` flag distinguishes between built-in agents (immutable) and user-created ones (mutable).

## AgentTeam

**What it represents**: A collection of CustomAgentDefinitions that work together, plus a set of pre-approved tools they can use.

**Key fields**:

- `agent_team_id` — URL-safe unique identifier (e.g., "at_aBcDeFgHiJkLmNo")
- `tenant_id` — Foreign key to Tenant
- `name` — Team name (e.g., "Research Team")
- `description` — What the team does
- `custom_agent_ids` — JSON list of CustomAgentDefinition IDs in the team
- `pre_approved_tool_names` — JSON list of tool names the team can use
- `is_active` — Whether the team can be executed
- `version` — Semantic version
- `is_latest_version` — Whether this is the most recent version
- `max_concurrent_executions` — How many team executions can run at once (default 5)
- `default_timeout_seconds` — Team execution timeout (default 1800 seconds)
- `execution_count` — Total executions
- `last_executed_at` — Last execution timestamp

**Why this design**:

Teams enable orchestration. Instead of invoking agents individually, you can invoke a team. Internally, the team might delegate to different agents depending on the task. The `pre_approved_tool_names` list acts as a team-level permission grant, simplifying security policies.

## ProjectKBFile

**What it represents**: A document in a Project's Knowledge Base. Users can upload PDFs, docs, or text files to give agents additional context.

**Key fields**:

- `file_name` — Original filename
- `file_uri` — Storage reference (e.g., MinIO path)
- `file_size` — Size in bytes
- `mime_type` — Content type (e.g., "application/pdf")
- `status` — "processing", "available", or "failed" (reflects indexing state)
- `error_message` — If processing failed, why
- `retention_policy_days` — How long to keep this file (inherits from tenant default)
- `archive_after` — Calculated timestamp of when to archive
- `project_id` — Foreign key to Project
- `tenant_id` — Foreign key to Tenant
- `created_at` — Timestamp

**Why this design**:

The `status` field reflects asynchronous processing. When a file is uploaded, it's queued for indexing. The `status` transitions from "processing" to "available" or "failed". This allows the UI to show progress and prevents queries against incomplete indices.

The `retention_policy_days` and `archive_after` fields enable GDPR compliance — files are automatically deleted or archived after a retention period.

## UserObservation

**What it represents**: Behavioral data learned about a user over time. This entity stores patterns like preferred tone, technical level, learning style, and what approaches have worked or failed.

**Key fields**:

Communication preferences:
- `preferred_tone` — "formal", "casual", "technical", "friendly"
- `response_length_preference` — "concise", "detailed", "comprehensive"
- `technical_level` — "beginner", "intermediate", "expert"

Behavioral patterns:
- `patience_level` — "high", "medium", "low"
- `risk_tolerance` — "conservative", "balanced", "aggressive"
- `decision_making_style` — "analytical", "intuitive", "collaborative"

Success patterns:
- `successful_tools` — JSON list of tools that have worked well
- `successful_approaches` — JSON list of effective strategies
- `failed_approaches` — JSON list of what to avoid
- `learning_style` — "visual", "hands-on", "theoretical"

Metadata:
- `observation_count` — How many times the user has been observed
- `confidence_score` — 0.0 to 1.0, confidence in these observations
- `last_observation_at` — When observations were last updated

**Why this design**:

Observations enable personalization. Over time, as a user interacts with agents, the system learns how they prefer to work. Agents can adapt their responses using this data. The `confidence_score` prevents acting on weak signals from few observations.

The JSON fields (stored as strings) are semi-structured because new observation types might be discovered without schema changes.

## ExecutionTraceStep

**What it represents**: A single step in an agent's reasoning chain. When an agent thinks through a problem, each reasoning step is recorded here.

**Key fields**:

- `invocation_id` — Which tool invocation this step is part of
- `step_index` — Sequence number (step 1, 2, 3, etc.)
- `step_type` — Type of step (e.g., "think", "call_tool", "receive_result")
- `content` — The step's content (reasoning, tool input, tool output)
- `timestamp` — When the step occurred

**Why this design**:

Trace steps provide observability. They help debug agent behavior and show users what the agent was thinking. The `step_index` enables reconstruction of the reasoning chain in order.

---

## Key Patterns

1. **Every entity has `tenant_id`** — This is non-negotiable for RLS enforcement
2. **Foreign keys for ownership chains** — Project → Tenant, Conversation → Project → Tenant, etc.
3. **URL-safe IDs for external use** — `job_id`, `custom_agent_id`, `agent_team_id` are for APIs and URLs
4. **JSON for semi-structured data** — `input_data`, `tool_names`, `metadata_json` avoid unnecessary tables
5. **Soft deletes with `is_deleted` flag** — Preserve audit trails by marking deleted rather than removing
6. **Version fields for evolution** — Track changes to agents and teams over time
7. **Timestamps everywhere** — `created_at`, `updated_at`, `last_activity_at` for auditing

These patterns make the schema predictable and secure. When you add a new entity, follow them.
