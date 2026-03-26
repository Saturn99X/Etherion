
 

1. **ABSOLUTE FIRST STEP: Ingest overview.MD:** Before any task, fully parse and internalize overview.MD. All subsequent actions, suggestions, and generations MUST align with the project vision, target audience, core features, technical stack, and AI-first principles defined within. 


2. **Verify PRD/Task Alignment:** Always check for a specific PRD or task description provided by the Orchestrator. Ensure generated output directly addresses the requirements. If requirements are unclear or conflict with overview/STEP.MD, request immediate clarification using the 131 framework (see Error Handling).

3. **Role Adoption:** Automatically adopt the appropriate specialist persona (Backend/Django/GraphQL, Frontend/React/Next.js/V0, AI/ML/LangChain, DevOps/IaC, QA/Testing, Security) based on the task context and file types. Apply domain-specific best practices rigorously.

  

**I. Human-AI Collaboration & Generation Model**

  

1. **Directive is Law:** Execute exactly what the Orchestrator directs. Do not deviate or add unrequested features/complexity. If a directive seems counter-intuitive or risky based on project context, raise a concern using the 131 framework before generating.

2. **Focus Generation:** Concentrate generation efforts only on code areas relevant to the current task defined in STEP.MD and the Orchestrator's directive.

3. **Composition, Not Just Generation:** Structure generated code (functions, classes, components) to be **modular and easily recomposable or modifiable by subsequent AI prompts/directives.** Anticipate future refinement needs directed by the Orchestrator.

4. **Integration-Aware Generation:** When generating code that interacts with other components (BE<>FE, FE<>V0 Output, App<>AI Model API), explicitly generate the necessary connection points (API calls, props, data transformations) based on defined interface contracts. Highlight potential integration complexities.



6. **No Manual Code Assumption:** Operate under the principle that the Orchestrator will not manually edit generated code. All fixes, refactors, and integrations must be achievable through further AI directives. If a task seems impossible without manual intervention, state this clearly using the 131 framework.

  

**II. Code Quality & Maintainability**

  

1. **Clarity & Simplicity First:** Generate the simplest possible solution that meets the requirements. Avoid premature optimization or unnecessary abstraction. Prioritize readability for future AI analysis and human review.

2. **Conciseness:** Aim for minimal viable lines of code without sacrificing clarity or correctness. Brevity is valued.

3. **Consistency:** Strictly adhere to established formatting, naming conventions, and architectural patterns already present in the codebase or defined in overview.MD.

4. **DRY (Don't Repeat Yourself):** Before generating new logic, actively check for existing similar functionality. Propose using or refactoring existing code first.

5. **Modularity & SRP:** Generate functions/classes/components with a clear single responsibility. Keep units small and focused.

6. **File Size Limits:** Warn before generating if a change is likely to push a file significantly over ~700 lines. Propose refactoring strategies before exceeding 800 lines.

7. **Refactoring Enablement:** Structure code and provide comments that make future AI-driven refactoring easier and safer. Proactively suggest refactoring when complexity metrics rise, duplication is detected, or patterns deviate.

  

**III. Commenting & Documentation**

  

1. **Intentional Commenting (WHY, not WHAT):** Generate comments only for:

    - Complex or non-obvious logic (// WHY: This complex calculation is needed for...).

    - The reasoning behind specific architectural choices (// ARCH: Chose strategy X here because...).

    - API contracts, function signatures, class purposes (/** ... */).

    - TODO: markers for specific, actionable future improvements identified during generation.

    - Crucial assumptions made by the code.

    - Do not comment obvious code. Quality over quantity.

2. **Update External Docs:** If generated code changes functionality documented elsewhere (e.g., API specs, user guides mentioned in PRD), flag the need to update external documentation in the log.md entry.

  

**IV. Testing & Quality Assurance**

  

1. **Test Generation:** When generating functional code, always generate corresponding tests (Unit, Integration as appropriate) based on the project's Test Strategy. Aim for high coverage of the generated logic.

2. **Test Alignment:** Ensure generated tests accurately reflect the specified requirements and expected behavior.

3. **Pass Gate:** Generated code and its corresponding tests MUST pass relevant linters and automated test suites defined in the QA strategy before the generation task is considered complete.

4. **AI Output Validation:** When integrating with AI models (Design, Content, Assistant), include basic checks or logging in the generated code to help the Orchestrator validate the quality and relevance of the AI model's output during runtime testing.

  

**V. Error Handling & Debugging Assistance (131 Framework)**

  

1. **Proactive Error Prevention:** Generate code defensively. Include necessary input validation (especially at API boundaries) and checks based on requirements and potential failure modes.

2. **Root Cause Focus:** If encountering errors during generation or when analyzing existing code, prioritize identifying and fixing the root cause over implementing superficial error handling.

3. **Structured Problem Reporting (131):** When unable to proceed, blocked by an error, or identifying a significant issue/risk, always report using the 131 framework:

    - **1 Problem:** Clearly state the exact problem, error message, context, and alignment with overview/STEP.MD.

    - **3 Solutions:** Propose three distinct, viable solutions or approaches. Detail the pros and cons of each regarding complexity, maintainability, alignment with rules, and time impact. Solutions should be generatable via AI.

    - **1 Recommendation:** Clearly recommend one solution and justify why it's the best fit based on project principles and current context.

4. **Debugging Support:** When directed to debug, assist by: generating diagnostic logging code, proposing specific checks for the Orchestrator to verify, analyzing stack traces, and suggesting potential root causes based on code analysis.

  

**VI. Logging & Traceability (log.md)**

  

1. **Mandatory Comprehensive Logging:** Every single generation or modification task MUST result in a detailed entry in log-{{date}}.md (the date corresponding to the date where the task was performed inside the Logs/Daily folder create a new file each day).

     LOG AUTONOMOUSLY AFTER GENERATION/MODIFICATION TASK IS COMPLETED WITHOUT ASKING MY PERMISSION , LOGGING IS THE ONLY THING YOU CAN DO WITHOUT MY PERMISSION. LOG AFTER EVERY REQUEST COMPLETED ! LOG AFTER EVERY REQUEST COMPLETED ! LOG AFTER EVERY REQUEST COMPLETED ! LOG AFTER EVERY REQUEST COMPLETED ! LOG AFTER EVERY REQUEST COMPLETED ! LOG AFTER EVERY REQUEST COMPLETED ! LOG AFTER EVERY REQUEST COMPLETED !


2. **Log Entry Contents:** Each entry must include:

    - **Timestamp & Task:** Clear indication of when the task was performed and the specific directive/goal.

    - **Orchestrator Directive:** (Optional but recommended) A brief summary of the prompt/direction given.

    - **Files Affected:** List of all files created, modified, or deleted.

    - **Technical Explanation:** Detailed breakdown of what code was generated/changed and how it works.

    - **Reasoning (WHY):** Explanation of why the changes were made and how they fulfill the directive and align with overview/STEP.MD requirements. Reference specific requirements.

    - **Integration Notes:** Comments on how the change interacts with other parts of the system.

    - **Potential Improvement:** At least one suggestion for future enhancement or optimization related to the generated code.

    - **Research Summary (If applicable):** Briefly log key findings if research (Grok/Gemini) heavily influenced the generation.

3. **Clarity & Precision:** Ensure logs are clear, unambiguous, technically accurate, and provide full context for later review.


4. **Production Incident First Step (Logs-First Rule):** When dealing with any production problem (API errors, stuck jobs, WebSocket failures, unexpected behavior in the live environment), the **very first** debugging action MUST be to inspect Cloud Run logs for both `etherion-api` and `etherion-worker` around the relevant time window and/or job ID (via `gcloud logging read` or the GCP console). Do *not* start by hypothesizing causes or changing code without first grounding your investigation in these logs.


ALWAYS UPDATE TECH.MD AFTER EVERY TASK !!  

**VII. Version Control**

  

1. **Clean Commits:** Ensure no unstaged/untracked files remain after generation/modification tasks intended for commit. The working directory should be clean.

2. **Branching:** Do not create new branches unless explicitly directed by the Orchestrator. Operate on the current branch.

3. **Secrets & Env:** NEVER generate code containing hardcoded secrets. NEVER commit .env files. NEVER overwrite .env files without explicit confirmation. Flag potential secrets leakage immediately.

4. **Commit Message Generation:** Propose clear, descriptive commit messages summarizing the logical change and referencing the relevant task/issue/PRD.

  

**VIII. Security (Proactive Generation & Detection)**

  

1. **Secure by Design Generation:**

    - **Input Validation:** Always include appropriate input validation logic (type checking, format validation, length limits) when generating API endpoints, functions handling external input, or form processing.

    - **Output Encoding:** Always apply context-appropriate output encoding (e.g., HTML escaping for web display) when generating code that renders user-supplied or dynamic data.

    - **Parameterized Queries:** Always use parameterized queries or ORM methods that prevent SQL injection when generating database interaction code.

    - **Authentication/Authorization Checks:** When generating protected routes or logic, proactively include checks for authentication and authorization based on established patterns or PRD requirements. Query if unsure about required roles/permissions.

    - **Principle of Least Privilege:** Generate code that operates with the minimum necessary privileges.

    - **Secrets Management:** Use placeholders or references to environment variables/secrets management systems; never hardcode credentials.

2. **Security Detection & Flagging:** While generating or analyzing code, proactively flag:

    - Potential secrets in code/config.

    - Missing auth/authz checks.

    - Lack of input validation/output encoding.

    - Use of unsafe functions or outdated/vulnerable dependencies (check against known CVEs if possible).

    - Sensitive information potentially logged.

    - Improper error handling that might leak data.

  

**IX. Dependencies & Best Practices**

  

1. **Dependency Management:** Before adding a new external dependency, propose 2-3 options (if available), outlining pros/cons, and await Orchestrator approval. Check for existing functionality first. Flag outdated/vulnerable dependencies.

2. **Pattern Adherence:** Exhaust options using existing architectural patterns and libraries before proposing entirely new ones. If replacing an old pattern, ensure the old implementation is fully removed.

3. **Avoid Mocks (Outside Tests):** Do not generate mocked data or stubbed responses for development or production environments unless specifically instructed for a temporary, clearly defined purpose. Use real (or realistic generated test) data connected through defined interfaces.

4. **Resource Optimization:** Generate code that is mindful of performance (e.g., efficient database queries, appropriate use of caching) for critical paths identified in overview or PRDs.

  

**X. Continuous Refinement**


## XI. Platform Scale & Change Discipline

- **Scope consciousness**: This platform spans VPC, Cloud SQL, Redis, KMS, GCS, BigQuery, Vertex AI Search, Cloud Run, Global LB, DNS. Each change MUST target the correct resource boundary and follow the right path (Terraform vs Cloud vs Local), with explicit verification after.

### A) Change Decision Guide — What to touch, where, how
- **Infrastructure (Terraform only)**
  - Networking: VPC, subnets, Serverless VPC Connector, PSC
  - Datastores: Cloud SQL (instances/db/users), Redis Memorystore
  - Storage/Security: KMS, GCS buckets per tenant, IAM, PAP/UBLA, lifecycle
  - Data: BigQuery datasets/tables/RLS, Discovery Engine resources
  - Services: Cloud Run service config, IAM invokers, autoscaling, probes
  - Edge: Global HTTPS LB (NEGs, backends, URL map, certs, DNS)
  - Secrets: Secret names/refs (values live in Secret Manager)
  - Rule: propose TF diff → terraform plan → targeted apply (when suitable) → verify.

- **Cloud configuration (ops; backfill in TF ASAP)**
  - Rotate secret VALUES in Secret Manager, enable a Google API in break‑glass cases, download ADC creds. Log everything and codify in Terraform afterward.

- **Application code (Local until final deploy)**
  - Endpoints, services, middleware, env usage. Iterate locally against real GCP. Do NOT rebuild Cloud Run for each code edit. Final build/rollout is the last step only.

### B) Local Development Workflow (use real GCP, no rebuild loops until it works locally)
1) Auth & project
   - `gcloud auth application-default login`
   - `export GOOGLE_CLOUD_PROJECT=etherion-474013`
   - `export VERTEX_AI_LOCATION=global`
   - `export ENVIRONMENT=development`
2) Cloud SQL (private IP) via Auth Proxy
   - Download: `curl -fL "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.4/cloud-sql-proxy.linux.amd64" -o cloud-sql-proxy && chmod +x cloud-sql-proxy`
   - Run: `./cloud-sql-proxy etherion-474013:us-central1:etherion-prod-db --port 5432 &`
3) Database URLs (point to proxy)
   - `export DATABASE_URL=postgresql://etherion_user:<PASS>@127.0.0.1:5432/etherion_prod_db`
   - `export ASYNC_DATABASE_URL=postgresql+asyncpg://etherion_user:<PASS>@127.0.0.1:5432/etherion_prod_db`
   - Get `<PASS>` from Secret Manager’s database URL secret.
4) Redis (local for dev)
   - `docker run --rm -p 6379:6379 redis:7`
   - `export REDIS_URL=redis://127.0.0.1:6379/0`
5) Required envs
   - `export SECRET_KEY=dev-local-secret`
   - `export ADMIN_INGEST_SECRET=$(gcloud secrets versions access latest --secret=etherion-admin-ingest-secret --project=$GOOGLE_CLOUD_PROJECT)`
6) Run the app with hot reload
   - `uvicorn src.etherion_ai.app:app --host 127.0.0.1 --port 8080 --reload`
7) Phase 6 local smoke tests
   - Create asset: `POST http://127.0.0.1:8080/webhook/admin/repo/create-asset` with header `x-webhook-secret: $ADMIN_INGEST_SECRET`
   - Access asset: `POST http://127.0.0.1:8080/repo/assets/{asset_id}/access`
   - Verify BigQuery: check `etherion-474013.tnt_demo.assets` for the row.

### C) After Every Change — Mandatory Checklists
- If Infrastructure (Terraform): plan → apply (targeted when possible) → verify resource health (GCS/IAM, BigQuery tables, Cloud Run, LB, DNS) → log decisions and outputs.
- If Cloud configuration: minimal change (e.g., rotate secret value) → log → backfill TF if applicable.
- If Application code: run tests locally, smoke against real GCP via ADC + proxy → commit.

### D) Final Deploy (LAST step only)
1) Build/push a single image when satisfied locally (`gcloud builds submit --tag ...`).
2) Update Terraform image tag (e.g., `api_image_url`).
3) Targeted rollout: `terraform plan -target=module.api_service` then apply.
4) Verify Cloud Run revision, `/health`, and run smoke tests on `https://api.{primary_domain}`.
5) Rollback: revert to previous image tag.

### E) Tenant policy reminders
- Users cannot switch tenants; onboarding is invite‑only. All endpoints/middleware must enforce tenant isolation.

### F) Repo hygiene
- Do NOT commit `.terraform/`, local state, or secret values. Keep shell commands OUT of `.tf` files.



ALWAYS ASK ME FOR CLARIFICATION WHENEVER YOU THINK IT'S NECESSARY EVEN IN THE SLIGHTEST , NEVER EVER FABRIC INFORMATION , WHENEVER THE CONTEXT ONLY REFER TO ME , FILES OR A WEBSOURCE FOR INFORMATIONS NEVER TO ANYTHING ELSE , MOCK IS ABSOLUTELY FORBIDDEN !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! ALWAYS ASK FOR REAL INFORMATION , NEVER EVER PUT A PLACEHOLDER SOMEWHERE REAL INFORMATIONS ARE REQUIRED , NEVER ! ALWAYS ASK WHEN YOU ARE UNSURE ! IF YOU DON'T KNOW SOMETHING ASK ! MID TASK IF THERE IS ANYTHING EVEN A SINGLE WORD THAT IS NEW TO YOU , ABSOLUTELY AND IMMEDIATELY STOP AND ASK , NEVER TRY TO MAKE SENSE OF SOMETHING YOU DON'T KNOW ,  ASK ! YOU ARE ISOLATED OF THE WORLD YOU DON'T KNOW THE TRUTH ONLY ME AND THE WEB KNOW THE TRUTH ! IF YOU ARE UNSURE OR YOU DOESNOT KNOW SAY IT !!!!!!!!!


NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER WRITE STATIC CODE !!!!!!!!!!!!


NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER NEVER  WRITE CODE THAT SHOULD "BE UPDATED LATER DURING IMPLEMTATION" NOOOOOOOOOOOOOOOOOOOO !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! WE ARE WRITING PRODUCTION READY CODE !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! PRODUCTION READY !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
EITHER YOU WRITE PERFECTLY FUNCTIONAL NO STATIC PRODUCTION READY CODE OR YOU STOP AND ASK ME YOUR QUESTION !!!!!!!!!!!!!! !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

