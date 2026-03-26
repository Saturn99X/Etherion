# BigQuery OAuth Connectors — Execution Log (2025-11-12)

# Documentation References

- **BigQuery Integration Connectors**
  - https://cloud.google.com/integration-connectors/docs/connectors/bigquery/configure

- **BigQuery Data Integration / ELT**
  - https://cloud.google.com/use-cases/data-integration
  - https://cloud.google.com/bigquery/docs/load-transform-export-intro

- **Looker Studio Community Connector (BigQuery)**
  - https://developers.google.com/looker-studio/connector/connect-to-bigquery

- **SAP CDP ↔ BigQuery Integration**
  - https://help.sap.com/docs/customer-data-platform/integration-guide/google-cloud-bigquery

- **BigQuery Row-Level Security (RLS)**
  - https://cloud.google.com/bigquery/docs/managing-row-level-security

- **BigQuery IAM and Access Control**
  - https://cloud.google.com/bigquery/docs/control-access-to-resources-iam

- **BigQuery CMEK (Customer-Managed Encryption Keys)**
  - https://cloud.google.com/bigquery/docs/customer-managed-encryption

- **BigQuery Dataset/Table TTL**
  - Default table expiration on datasets: https://cloud.google.com/bigquery/docs/managing-datasets#default-table-expiration
  - Table expiration overview: https://cloud.google.com/bigquery/docs/managing-tables#table-expiration

- **Cloud Armor**
  - Security policy overview: https://cloud.google.com/armor/docs/security-policy-overview
  - Rules language: https://cloud.google.com/armor/docs/rules-language

- **Service Account Impersonation (Worker → Tenant SA)**
  - https://cloud.google.com/iam/docs/impersonating-service-accounts
  - Token Creator role: https://cloud.google.com/iam/docs/understanding-roles#service-accounts-roles

- **Terraform Registry (Google provider)**
  - BigQuery dataset: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_dataset
  - BigQuery dataset access: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_dataset_access
  - BigQuery dataset IAM: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_dataset_iam
  - BigQuery table IAM: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_table_iam
  - BigQuery row access policy: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_row_access_policy
  - BigQuery job (for DDL if needed): https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigquery_job

## Orders at Start (User Requirements)
- **Maximal implementation, not minimal**
- **Provider focus now: Google Drive** (others later: HubSpot, Jira, Slack)
- **Strict tenant isolation in BigQuery**
  - Per-tenant datasets: `tnt_{tenant}` and `tnt_{tenant}_staging`
  - **RLS for shared analytics** table/view
- **Security hardening**
  - **CMEK** on both staging and prod datasets
  - **Staging TTL** (30–90 days)
  - **Per-tenant SA impersonation** by worker, allowlist targets
  - **Cloud Armor** allowlist + quotas for `/oauth/silo/*`
- **Pipeline components**
  - OAuth via `SiloOAuthService` (tokens in GSM)
  - Connector registry (DB model + REST endpoints)
  - Ingestion worker (Cloud Run) landing data into `tnt_{tenant}_staging.*`
  - Dataform transformations to normalized `tnt_{tenant}.docs`/`assets`
- **Read GCP docs** and align implementation

## Plan We Adopted
- **Terraform: BigQuery module**
  - Add CMEK (KMS key) support
  - Add per-tenant staging datasets with default table TTL
  - Add shared analytics view and RLS
  - Dataset IAM for per-tenant writers (connector SAs)
  - Outputs for staging datasets
- **Terraform: Prod environment wiring**
  - Enable `cloudkms` API; instantiate KMS module; grant BigQuery service agent on key
  - Create per-tenant SAs; allow worker SA to impersonate
  - Pass CMEK/staging/SA maps/RLS into BigQuery module
  - Add Cloud Armor rule for `/oauth/silo/*` (rate limit)
- **Backend**
  - Connector registry endpoints + models
  - OAuth `/oauth/silo/*` endpoints; `SiloOAuthService` storing tokens in GSM
  - Cloud Armor allowlist/rate-limiting for those endpoints
- **Worker (Google Drive first)**
  - Cloud Run service that accepts `tenant_id`, impersonates `sa-tenant-{id}`
  - Pulls data from Google Drive, lands into staging dataset
- **Dataform**
  - Transform staging → normalized per-tenant datasets; produce shared analytics view
- **Testing/QA**
  - Terraform validate/plan; integration tests for RLS + impersonation

## What I Implemented (This Session)
- **BigQuery module: `terraform/modules/bigquery-knowledge-base/`**
  - `variables.tf`
    - Added: `kms_key_name`, `enable_staging_datasets`, `staging_suffix`, `staging_default_table_ttl_days`
    - Added: `tenant_row_access_members` (RLS grantees), `tenant_service_account_emails` (SA writers)
  - `main.tf`
    - Platform dataset `platform_kb` now supports **CMEK** via `default_encryption_configuration`
    - Tenant datasets `tnt_{tenant}` support **CMEK**
    - Created per-tenant **staging datasets** `tnt_{tenant}_staging` with **TTL** and **CMEK**
    - Added **dataset IAM**:
      - `google_bigquery_dataset_iam_member.tenant_dataset_writer`
      - `google_bigquery_dataset_iam_member.tenant_staging_writer`
    - Added shared analytics **view** `analytics_documents_shared` over `platform_kb.documents`
    - Added **RLS policies** per tenant via `null_resource.rls_policy_tenant` executing `bq` DDL
  - `outputs.tf`
    - Added `tenant_staging_datasets` mapping
- **Prod environment variables: `terraform/environments/prod/variables.tf`**
  - Added staging controls (enable, suffix, TTL days)
  - Added `tenant_row_access_members`
  - Added `oauth_silo_rate_limit_per_minute` (already present now)
- **Cloud Armor rule**
  - Authored the correct top-level rule for `/oauth/silo/*` (rate-limit throttle). Note: edit placement pending due to tool ban; see “Open Items”.
- **Docs search**
  - Queried references for BigQuery integration connectors, ELT in BigQuery, Looker Studio BigQuery connector, SAP BigQuery integration
  - Terraform registry fetch for row access policy had transient network error; used known DDL approach via `bq query` instead

## Files Changed
- `terraform/modules/bigquery-knowledge-base/variables.tf`
- `terraform/modules/bigquery-knowledge-base/main.tf`
- `terraform/modules/bigquery-knowledge-base/outputs.tf`
- `terraform/environments/prod/variables.tf`

## Open Items / Why Some Edits Not Applied
- **`terraform/environments/prod/security.tf`**
  - The `/oauth/silo/*` rule was mistakenly nested under `adaptive_protection_config`. Patch attempts overlapped and triggered a tool lock on the file.
  - Action: Move the OAuth throttle to a top-level `rule {}` block (see TODO file for exact snippet).
- **`terraform/environments/prod/main.tf`**
  - Need to wire KMS module, grant BigQuery service agent on key, create per-tenant SAs, allow worker SA to impersonate, and pass new module variables. Attempts overlapped and the tool locked edits.
  - Action: Apply the minimal snippets manually or via one-shot safe command.

## Known Assumptions and Risks
- **RLS via `null_resource` + `bq`**: Works but depends on `bq` CLI availability where Terraform runs. Consider moving to Cloud Run Job or explicit `google_bigquery_row_access_policy` resource when available/stable.
- **KMS permissions**: Ensure BigQuery service agent has `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the CMEK.
- **Dataset IAM scope**: Writer roles granted at dataset level as requested; refine if stricter table-level needed.
- **Cloud Armor rule order**: Priority must be correct (e.g., after Stripe 300, before general API throttle) and not nested.

## Next Steps
See companion TODO: `Logs/Project/todo-connector-bq-oauth-2025-11-12.md`.
