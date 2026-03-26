# BigQuery OAuth Connectors — Remaining Work (2025-11-12)

## Critical Terraform (Prod)
- [x] Cloud Armor: Move `/oauth/silo/*` throttle to top-level rule in `terraform/environments/prod/security.tf` (priority 350; between Stripe 300 and General API 400). [Done 2025-11-09; see `terraform/environments/prod/security.tf` and `variables.tf` (`oauth_silo_rate_limit_per_minute`); HCL nesting fix applied.]
- [ ] KMS: In `terraform/environments/prod/main.tf`
  - [ ] Add `cloudkms.googleapis.com` to `locals.required_apis_list`.
  - [ ] Add `data "google_project" "this" {}`.
  - [ ] Instantiate `module "kms"` (key ring `${local.platform_name}-data`, key `bq-cmek`).
  - [ ] Grant BigQuery service agent `roles/cloudkms.cryptoKeyEncrypterDecrypter` on key.
  - [ ] Create per-tenant SAs `sa-tenant-{id}`.
  - [ ] Grant worker SA `roles/iam.serviceAccountTokenCreator` on those SAs.
  - [ ] Pass to `module "bigquery_knowledge_base"`:
    - [ ] `kms_key_name = module.kms.crypto_key_id`
    - [ ] `enable_staging_datasets`, `staging_suffix`, `staging_default_table_ttl_days`
    - [ ] `tenant_service_account_emails = { for k, sa in google_service_account.tenant_sa : k => sa.email }`
    - [ ] `tenant_row_access_members = var.tenant_row_access_members`
- [ ] Run `terraform validate` and fix any provider/schema mismatches.

## Backend (API + Auth)
- [ ] Connector registry (models + REST endpoints) to track provider, tenant, scopes, status.
- [x] OAuth endpoints `/oauth/silo/*` (init/callback/revoke) using `SiloOAuthService` with GSM storage. [Implemented: `src/services/silo_oauth_service.py`; routes in `src/etherion_ai/app.py` (start/callback added 2025-11-04, revoke 2025-11-06).]
- [x] Cloud Armor allowlist/rate limits should match LB routing to these endpoints. [Throttling configured in `security.tf`; Cloudflare allowlist present per security hardening entries.]

## Worker (Cloud Run) — Google Drive Phase 1
- [ ] Worker impersonates `sa-tenant-{id}` (enforced allowlist) based on scheduler param `tenant_id`.
- [ ] Pull metadata/content via Drive API and land into `tnt_{tenant}_staging.*`.
- [ ] Use CMEK-enabled BQ client and respect staging TTL.
- [ ] Emit metrics and audit logs per tenant.

## Dataform
- [ ] Transform `tnt_{tenant}_staging` → `tnt_{tenant}` normalized tables (docs/assets), preserve lineage.
- [ ] Build/refresh the shared analytics view if needed.

## Security Hardening
- [ ] Ensure BigQuery service agent has CMEK use permission.
- [ ] Confirm dataset ACLs restrict cross-tenant access; validate writer bindings for tenant SAs only.
- [ ] Add worker env `IMPERSONATION_ALLOWED_SAS` (comma-separated allowlisted SAs) and enforce in app code.

## QA & Validation
- [ ] Apply to a test project/tenant and validate:
  - [ ] Tenant SA can write only to its datasets (tenant + staging).
  - [ ] RLS: shared analytics view shows rows only for grantee members.
  - [ ] Cloud Armor rule throttles `/oauth/silo/*` as configured.
  - [ ] CMEK in effect for datasets and tables.
  - [ ] Staging TTL is honored.
- [ ] Add integration tests for impersonation + RLS.

## Notes
- RLS implemented using `null_resource` + `bq query` DDL; consider migrating to `google_bigquery_row_access_policy` when stable.
- Ensure CI/CD runner has `bq` CLI or run the DDL through a Cloud Run Job.
