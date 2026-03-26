terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.9"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 4.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# Systematic GSM -> env mapping for all services
locals {
  # Auto map core secrets to env names plus all declared additional_secret_ids
  auto_secret_env_vars = merge(
    {
      DATABASE_URL        = { name = "etherion-database-url-prod", key = "latest" },
      RLS_DATABASE_URL    = { name = "etherion-rls-database-url-prod", key = "latest" },
      ASYNC_DATABASE_URL  = { name = "etherion-async-database-url-prod", key = "latest" },
      SECRET_KEY          = { name = "app-secret-key", key = "latest" },
      JWT_SECRET_KEY      = { name = "app-secret-key", key = "latest" },
      ADMIN_INGEST_SECRET = { name = "etherion-admin-ingest-secret", key = "latest" },
    },
    { for sid in local.additional_secret_ids : sid => { name = sid, key = "latest" } }
  )

  # Allow tfvars overrides to take precedence
  all_secret_env_vars = merge(local.auto_secret_env_vars, var.secret_env_vars)

  # Only expose public NEXT_PUBLIC_* values to the frontend container
  frontend_secret_env_vars = { for k, v in local.all_secret_env_vars : k => v if startswith(k, "NEXT_PUBLIC_") }

  # Required APIs (Vertex AI Search is fully disabled; Discovery Engine not enabled)
  required_apis_list = concat([
    "compute.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudkms.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "bigquerydatatransfer.googleapis.com",
    "billingbudgets.googleapis.com",
    "pubsub.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "documentai.googleapis.com",
    "certificatemanager.googleapis.com",
    "dns.googleapis.com",
    "servicenetworking.googleapis.com",
    "vpcaccess.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudfunctions.googleapis.com",
    "eventarc.googleapis.com",
  ])
}

# Project metadata (project number used for service agents)
data "google_project" "this" {}

data "google_client_openid_userinfo" "me" {}

output "debug_current_identity" {
  value = data.google_client_openid_userinfo.me.email
}

# Tenant Ops service account used by storage/cost modules
resource "google_service_account" "tenant_ops" {
  account_id   = "tenant-ops"
  display_name = "Tenant Ops"
  description  = "Service account for tenant operations"
}

# Enable required APIs for multi-tenant platform
resource "google_project_service" "required_apis" {
  # Manually enabled to bypass 403s
  for_each = toset([])

  service            = each.value
  disable_on_destroy = false
}

# Per-tenant Service Accounts (for BigQuery dataset writes via impersonation)
resource "google_service_account" "tenant_sa" {
  for_each     = toset(var.tenant_ids)
  account_id   = "sa-tenant-${each.value}"
  display_name = "Tenant SA ${each.value}"
  description  = "Per-tenant service account for data plane operations (BQ writes)"
}

# Data ingestion (Cloud Functions + GCS + Pub/Sub)
module "data_ingestion" {
  source = "../../modules/data_ingestion"
  count  = var.enable_data_ingestion ? 1 : 0

  name_prefix   = local.name_prefix
  project_id    = var.project_id
  region        = var.region
  force_destroy = false

  depends_on = [
    google_project_service.required_apis
  ]
}

// Grant CMEK usage to the BigQuery encryption service account (required for dataset/table encryption)
resource "google_kms_crypto_key_iam_member" "bq_encryption_service_cmek" {
  crypto_key_id = module.kms.crypto_key_id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:bq-${data.google_project.this.number}@bigquery-encryption.iam.gserviceaccount.com"

  depends_on = [
    module.kms
  ]
}

# Cloud DNS managed zone for primary domain (Phase 1.3 prerequisite)
module "cloud_dns_zone" {
  count  = var.use_cloud_dns ? 1 : 0
  source = "../../modules/cloud-dns-managed-zone"

  project_id     = var.project_id
  dns_zone_name  = var.dns_zone_name
  primary_domain = var.primary_domain
  depends_on     = [google_project_service.required_apis]
}

# KMS module for tenant encryption keys
module "kms" {
  source = "../../modules/kms"

  project_id      = var.project_id
  location        = var.region
  key_ring_name   = "${local.platform_name}-data"
  crypto_key_name = "bq-cmek"

  depends_on = [
    google_project_service.required_apis
  ]
}

# KMS IAM member grants for tenant SAs (non-authoritative; avoids role binding contention)
resource "google_kms_crypto_key_iam_member" "tenant_sa_kms_member" {
  for_each      = toset(var.tenant_ids)
  crypto_key_id = module.kms.crypto_key_id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:sa-tenant-${each.key}@${var.project_id}.iam.gserviceaccount.com"
}

# Deprecated phase1_lb_compat module removed - using multi_tenant_lb instead

# VPC Network for multi-tenant isolation
module "vpc" {
  source = "../../modules/vpc"

  project_id  = local.project_id
  region      = local.region
  environment = local.environment

  depends_on = [
    google_project_service.required_apis,
    google_kms_crypto_key_iam_member.bq_encryption_service_cmek
  ]
}

# Multi-tenant database with Row-Level Security
module "multi_tenant_db" {
  source = "../../modules/multi-tenant-db"

  project_id = local.project_id
  region     = local.region
  vpc_id     = module.vpc.vpc_id

  # Database configuration
  instance_name       = "etherion-prod-db"
  database_name       = "etherion_prod_db"
  database_user       = "etherion_user"
  tier                = var.database_tier
  availability_type   = var.database_availability_type
  deletion_protection = var.deletion_protection

  # Multi-tenant configuration
  # Disable DB-side RLS setup provisioner during apply (runs from outside VPC)
  enable_rls       = false
  tenant_isolation = var.enable_tenant_isolation

  depends_on = [
    google_project_service.required_apis,
    module.vpc
  ]
}

# Redis for asynchronous task queuing
module "redis" {
  source = "../../modules/redis"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment
  vpc_network = module.vpc.vpc_id

  # Redis configuration for Celery
  memory_size_gb = var.redis_memory_size_gb
  redis_version  = var.redis_version

  # Align with Phase 2 bootstrap to avoid duplicate peering and alerts
  enable_private_services_access = false
  enable_monitoring              = false

  depends_on = [
    google_project_service.required_apis,
    module.vpc
  ]
}

# BigQuery datasets for per-tenant knowledge bases
module "bigquery_knowledge_base" {
  source = "../../modules/bigquery-knowledge-base"

  project_id    = local.project_id
  region        = local.region
  platform_name = local.platform_name
  environment   = local.environment

  # Dataset naming
  platform_dataset_name = local.platform_dataset_name
  tenant_dataset_prefix = local.tenant_dataset_prefix

  # Common labels
  common_labels = local.common_labels

  # Multi-tenant BigQuery configuration
  enable_tenant_datasets = var.enable_bigquery_knowledge_base
  enable_partitioning    = true
  enable_clustering      = true
  tenant_ids             = var.tenant_ids

  # Required: data retention (days)
  retention_days = var.kb_retention_days

  # Grant dataset ownership to API service account
  dataset_owner_email = google_service_account.tenant_ops.email

  # Allow API/worker services to write to tenant datasets (required for ingestion bootstrap)
  api_service_account_email    = var.enable_api_service ? module.api_service[0].service_account_email : ""
  worker_service_account_email = var.enable_worker_service ? module.worker_artifacts_service[0].service_account_email : ""

  # CMEK and staging configuration
  kms_key_name                   = module.kms.crypto_key_id
  create_vector_indexes          = false
  enable_staging_datasets        = var.enable_staging_datasets
  staging_suffix                 = var.staging_suffix
  staging_default_table_ttl_days = var.staging_default_table_ttl_days

  # Tenant SAs and Row Access Policy members
  tenant_service_account_emails = { for k, sa in google_service_account.tenant_sa : k => sa.email }
  tenant_row_access_members     = var.tenant_row_access_members

  depends_on = [google_project_service.required_apis]
}




# Per-tenant GCS buckets for media and assets
module "tenant_storage" {
  source                       = "../../modules/tenant-storage"
  project_id                   = var.project_id
  region                       = var.region
  environment                  = var.environment
  enable_tenant_buckets        = true
  bucket_prefix                = local.tenant_prefix
  tenant_ids                   = var.tenant_ids
  tenant_service_account_email = var.tenant_service_account_email
  # Keep function disabled for now
  enable_signed_url_generator = false
}

# Separate API and Worker Cloud Run services
module "api_service" {
  count  = var.enable_api_service ? 1 : 0
  source = "../../modules/cloud-run-api"

  project_id       = var.project_id
  region           = var.region
  vpc_connector_id = module.vpc.vpc_connector_id

  # Domain wiring for OAuth/MCP callbacks and app defaults
  primary_domain = var.primary_domain
  auth_base_url  = "https://auth.${var.primary_domain}"
  mcp_base_url   = "https://mcp.${var.primary_domain}"

  # API service configuration (no background processing)
  service_name              = local.api_service_name
  image_url                 = var.api_image_url
  service_account_email     = "${var.project_id}-api-service@${var.project_id}.iam.gserviceaccount.com"
  container_port            = 8080
  disable_custom_entrypoint = var.api_disable_custom_entrypoint
  health_check_path         = var.api_health_check_path

  # Quota-safe scaling and resources
  min_instances = 1
  max_instances = 5
  cpu_limit     = "1"
  memory_limit  = "2Gi"

  # Database and Redis connections
  database_connection_name = module.multi_tenant_db.connection_name
  database_user            = module.multi_tenant_db.database_user
  database_password        = module.multi_tenant_db.database_password
  database_name            = module.multi_tenant_db.database_name
  redis_host               = module.redis.redis_host
  redis_port               = module.redis.redis_port
  redis_auth_string        = module.redis.redis_auth_string
  # Use DATABASE_URL/ASYNC_DATABASE_URL from GSM only
  use_secret_database_url = true

  # Multi-tenant configuration
  enable_multi_tenant = true
  enable_rls          = true

  # OAuth callback reachability via Load Balancer
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  # Allow unauthenticated invocations; network access is still constrained by ingress and the HTTPS LB
  enable_public_access       = true
  lb_invoker_service_account = ""

  # Per-service rate limit
  rate_limit_per_minute = var.api_rate_limit_per_minute

  # Environment and secrets
  environment = var.environment
  # Inject only explicitly provided GSM secrets (merged with auto-mapped ones)
  secret_env_vars = local.all_secret_env_vars

  # DISABLE invite enforcement - allow automatic tenant creation
  multi_tenant_enforce_invite = false

  depends_on = [
    module.multi_tenant_db,
    module.redis,
    module.vpc,
    google_secret_manager_secret.database_url,
    google_secret_manager_secret.async_database_url,
    google_secret_manager_secret.admin_ingest_secret,
    google_secret_manager_secret.additional,
    google_secret_manager_secret_version.next_public,
    google_secret_manager_secret_version.app_secret_key_latest,
    time_sleep.wait_for_app_secret_version
  ]
}

module "worker_agents_service" {
  count  = var.enable_worker_service ? 1 : 0
  source = "../../modules/cloud-run-worker"

  project_id         = var.project_id
  region             = var.region
  vpc_connector_id   = module.vpc.vpc_connector_id
  vpc_egress_setting = "ALL_TRAFFIC" # Allow external network access (HuggingFace, etc.)

  # Worker service configuration (Celery background processing)
  service_name              = local.worker_agents_service_name
  service_account_id        = "${var.environment}-worker-agents-svc"
  image_url                 = var.worker_image_url
  disable_custom_entrypoint = var.worker_disable_custom_entrypoint

  # Quota-safe scaling and resources
  # IMPORTANT: min_instances=1 required because Cloud Run can't auto-wake workers on
  # Redis queue messages. At least one worker must always be running to poll for tasks.
  min_instances = 1
  max_instances = 5
  cpu_limit     = "4"
  memory_limit  = "4Gi"

  # Database connection for Cloud SQL unix sockets
  database_connection_name = module.multi_tenant_db.connection_name

  # Environment variables (non-sensitive only)
  environment_variables = {
    GOOGLE_CLOUD_PROJECT  = var.project_id
    ENVIRONMENT           = var.environment
    REDIS_URL             = "rediss://:${module.redis.redis_auth_string}@${module.redis.redis_host}:${module.redis.redis_port}/2?ssl_cert_reqs=none"
    CELERY_BROKER_URL     = "rediss://:${module.redis.redis_auth_string}@${module.redis.redis_host}:${module.redis.redis_port}/0?ssl_cert_reqs=none"
    CELERY_RESULT_BACKEND = "rediss://:${module.redis.redis_auth_string}@${module.redis.redis_host}:${module.redis.redis_port}/1?ssl_cert_reqs=none"
    # Comma-separated allowlist for SA impersonation enforcement in app code
    IMPERSONATION_ALLOWED_SAS = join(",", [for k, sa in google_service_account.tenant_sa : sa.email])
    # Audit logging - must write to /tmp for Cloud Run (read-only root filesystem)
    AUDIT_LOG_FILE     = "/tmp/logs/audit.log"
    CELERY_QUEUE       = "worker-agents"
    CELERY_CONCURRENCY = 8
  }
  # Inject required secrets for worker from GSM (ALL secrets, as requested)
  secret_env_vars = local.all_secret_env_vars

  # Asynchronous processing configuration
  # (removed: enable_celery, worker_count — not supported by module)

  depends_on = [
    module.api_service,
    module.multi_tenant_db,
    module.redis,
    module.vpc,
    google_secret_manager_secret.database_url,
    google_secret_manager_secret.async_database_url,
    google_secret_manager_secret.admin_ingest_secret,
    google_secret_manager_secret.additional,
    google_secret_manager_secret_version.app_secret_key_latest,
    time_sleep.wait_for_app_secret_version
  ]
}

module "worker_artifacts_service" {
  count  = var.enable_worker_service ? 1 : 0
  source = "../../modules/cloud-run-worker"

  project_id         = var.project_id
  region             = var.region
  vpc_connector_id   = module.vpc.vpc_connector_id
  vpc_egress_setting = "ALL_TRAFFIC" # Allow external network access (HuggingFace, etc.)

  # Worker service configuration (Celery background processing)
  service_name              = local.worker_artifacts_service_name
  service_account_id        = "${var.environment}-worker-artifacts-svc"
  image_url                 = var.worker_image_url
  disable_custom_entrypoint = var.worker_disable_custom_entrypoint

  # Quota-safe scaling and resources
  # IMPORTANT: min_instances=1 required because Cloud Run can't auto-wake workers on
  # Redis queue messages. At least one worker must always be running to poll for tasks.
  min_instances = 1
  max_instances = 5
  cpu_limit     = "4"
  memory_limit  = "4Gi"

  # Database connection for Cloud SQL unix sockets
  database_connection_name = module.multi_tenant_db.connection_name

  # Environment variables (non-sensitive only)
  environment_variables = {
    GOOGLE_CLOUD_PROJECT  = var.project_id
    ENVIRONMENT           = var.environment
    REDIS_URL             = "rediss://:${module.redis.redis_auth_string}@${module.redis.redis_host}:${module.redis.redis_port}/2?ssl_cert_reqs=none"
    CELERY_BROKER_URL     = "rediss://:${module.redis.redis_auth_string}@${module.redis.redis_host}:${module.redis.redis_port}/0?ssl_cert_reqs=none"
    CELERY_RESULT_BACKEND = "rediss://:${module.redis.redis_auth_string}@${module.redis.redis_host}:${module.redis.redis_port}/1?ssl_cert_reqs=none"
    # Comma-separated allowlist for SA impersonation enforcement in app code
    IMPERSONATION_ALLOWED_SAS = join(",", [for k, sa in google_service_account.tenant_sa : sa.email])
    # Audit logging - must write to /tmp for Cloud Run (read-only root filesystem)
    AUDIT_LOG_FILE     = "/tmp/logs/audit.log"
    CELERY_QUEUE       = "worker-artifacts,high_priority,low_priority"
    CELERY_CONCURRENCY = 8
  }

  # Inject required secrets for worker from GSM (ALL secrets, as requested)
  secret_env_vars = local.all_secret_env_vars

  depends_on = [
    module.worker_agents_service,
    module.multi_tenant_db,
    module.redis,
    module.vpc,
    google_secret_manager_secret.database_url,
    google_secret_manager_secret.async_database_url,
    google_secret_manager_secret.admin_ingest_secret,
    google_secret_manager_secret.additional,
    google_secret_manager_secret_version.app_secret_key_latest,
    time_sleep.wait_for_app_secret_version
  ]
}

resource "google_project_iam_member" "worker_artifacts_bigquery_admin" {
  count   = var.enable_worker_service ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${module.worker_artifacts_service[0].service_account_email}"
}

resource "google_project_iam_member" "worker_agents_bigquery_admin" {
  count   = var.enable_worker_service ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${module.worker_agents_service[0].service_account_email}"
}

resource "google_project_iam_member" "api_bigquery_admin" {
  count   = var.enable_api_service ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${module.api_service[0].service_account_email}"
}

# Allow worker SA to impersonate tenant SAs (Token Creator)
resource "google_service_account_iam_member" "tenant_sa_token_creator" {
  for_each           = var.enable_worker_service ? toset(var.tenant_ids) : []
  service_account_id = google_service_account.tenant_sa[each.key].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${module.worker_artifacts_service[0].service_account_email}"
}

resource "google_service_account_iam_member" "tenant_sa_token_creator_agents" {
  for_each           = var.enable_worker_service ? toset(var.tenant_ids) : []
  service_account_id = google_service_account.tenant_sa[each.key].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${module.worker_agents_service[0].service_account_email}"
}

# Frontend Cloud Run service (Next.js UI)
module "frontend_service" {
  count  = var.enable_frontend_service ? 1 : 0
  source = "../../modules/cloud-run-frontend"

  project_id = var.project_id
  region     = var.region

  service_name   = local.frontend_service_name
  image_url      = var.frontend_image_url
  environment    = var.environment
  container_port = 3000

  # Runtime env for client to discover API endpoints via window.ENV
  environment_variables = {
    NEXT_PUBLIC_API_URL             = "https://api.${var.primary_domain}"
    NEXT_PUBLIC_GRAPHQL_ENDPOINT    = "https://api.${var.primary_domain}/graphql"
    NEXT_PUBLIC_GRAPHQL_WS_ENDPOINT = ""
    NEXT_PUBLIC_AUTH_CALLBACK_URL   = "https://app.${var.primary_domain}/auth/callback"
    # Streaming (SSE) — FE streams via its own proxy route
    NEXT_PUBLIC_CHAT_SSE_URL = "https://app.${var.primary_domain}/api/stream"
    # Upstream orchestrator SSE endpoint consumed by the proxy route (server-only)
    ORCHESTRATOR_SSE_URL    = "https://api.${var.primary_domain}/api/sse/chat"
    NEXT_PUBLIC_BYPASS_AUTH = "false"
  }
  # Public OAuth IDs pulled from GSM (auto + overrides)
  secret_env_vars = local.frontend_secret_env_vars

  depends_on = [
    google_secret_manager_secret_version.next_public
  ]
}
module "multi_tenant_lb" {
  count  = 1 # ENABLED for production
  source = "../../modules/multi-tenant-lb"

  project_id = local.project_id
  region     = local.region

  # Load balancer configuration
  lb_name        = "etherion-prod"
  primary_domain = var.primary_domain
  dns_zone_name  = var.dns_zone_name # Not used (Cloudflare manages DNS)

  # Core subdomains (api/auth/mcp route to API, app routes to Frontend)
  subdomains = ["api", "auth", "mcp", "app"]

  # Empty tenant_ids - using wildcard certificate instead
  tenant_ids = []

  # Security controls
  kill_switch_enabled = false

  # Backend Cloud Run services
  api_service_name      = var.enable_api_service ? module.api_service[0].service_name : "etherion-api"
  worker_service_name   = var.enable_worker_service ? module.worker_agents_service[0].service_name : "etherion-worker"
  frontend_service_name = var.enable_frontend_service ? module.frontend_service[0].service_name : "etherion-frontend"

  depends_on = [
    module.api_service,
    module.worker_agents_service,
    module.worker_artifacts_service
  ]
}

# Cost tracking infrastructure
module "cost_tracking" {
  source                    = "../../modules/cost-tracking"
  project_id                = var.project_id
  region                    = var.region
  environment               = var.environment
  enable_real_time_tracking = false
  enable_credit_management  = false
  enable_cost_aggregation   = false
  service_account_email     = var.tenant_service_account_email
  depends_on                = [module.multi_tenant_db, google_service_account.tenant_ops]
}

# AI-generated assets repository
module "ai_assets_repository" {
  source                = "../../modules/ai-assets-repository"
  project_id            = var.project_id
  region                = var.region
  environment           = "production"
  enable_tenant_buckets = true
  tenant_ids            = var.tenant_ids
  service_account_email = var.tenant_service_account_email
  # Keep optional functions off for now
  enable_asset_processing = false
  enable_asset_search     = false
  enable_asset_cleanup    = false
  depends_on              = [module.multi_tenant_db, google_service_account.tenant_ops]
}

# Monitoring and observability
module "monitoring" {
  count  = var.enable_monitoring_module ? 1 : 0
  source = "../../modules/monitoring"

  project_id  = var.project_id
  region      = var.region
  environment = "production"

  # Multi-tenant monitoring
  enable_cost_alerts = true

  # Service monitoring
  api_url            = "https://api.${var.primary_domain}"
  worker_url         = "https://worker.${var.primary_domain}"
  logging_dataset_id = module.bigquery_knowledge_base.platform_dataset_id

  # Notification channels
  notification_channels = [module.billing_guardrails.notification_channel_id]

  # Alerting thresholds
  too_many_requests_per_minute_threshold = var.too_many_requests_per_minute_threshold
  error_rate_threshold                   = var.error_rate_threshold
  response_time_threshold                = var.response_time_threshold
  cost_threshold_usd                     = var.cost_threshold_usd
  credit_low_threshold                   = var.credit_low_threshold
  alert_auto_close_duration              = var.alert_auto_close_duration

  depends_on = [
    module.bigquery_knowledge_base
  ]
}

# Cloud Run Job to apply/update DB RLS from inside the VPC (manual/CI trigger)
module "db_rls_job" {
  count  = var.enable_db_rls_job ? 1 : 0
  source = "../../modules/cloud-run-job"

  project_id = var.project_id
  region     = var.region
  job_name   = "db-rls-apply"

  # Use Postgres image to get psql client. Connect via Cloud SQL unix socket.
  image_url = "postgres:17"
  command   = ["bash", "-lc"]
  args = [
    "set -euo pipefail; echo \"$RLS_SQL_B64\" | base64 -d > /tmp/rls.sql && SANITIZED_URL=$(echo \"$DATABASE_URL\" | sed 's/^postgresql[^:]*:/postgresql:/') && psql -v ON_ERROR_STOP=1 \"$SANITIZED_URL\" -f /tmp/rls.sql"
  ]

  # Environment variables
  env_vars = {}

  # RLS SQL provided via Secret Manager (base64-encoded); create secret container only in secrets.tf
  secret_env_vars = merge(
    {
      RLS_SQL_B64 = {
        name = "RLS_SQL_B64"
        key  = "latest"
      }
    },
    {
      # Prefer a dedicated high-privilege DSN for RLS if provided (RLS_DATABASE_URL),
      # otherwise fall back to the standard application DATABASE_URL.
      DATABASE_URL = lookup(local.all_secret_env_vars, "RLS_DATABASE_URL", local.all_secret_env_vars["DATABASE_URL"])
    }
  )

  service_account_email = var.enable_worker_service ? module.worker_agents_service[0].service_account_email : var.tenant_service_account_email
  cloud_sql_connection  = module.multi_tenant_db.connection_name
  vpc_connector_id      = module.vpc.vpc_connector_id
}

# Cloud Run Job to run Alembic migrations (CI/CD trigger)
module "db_migration_job" {
  count  = var.enable_db_migration_job ? 1 : 0
  source = "../../modules/cloud-run-job"

  project_id = var.project_id
  region     = var.region
  job_name   = "db-migrate"

  # Reuse the API image, it has alembic + code
  image_url   = var.api_image_url
  command     = ["alembic", "upgrade", "head"]
  working_dir = "/app"

  # Connect to Cloud SQL via VPC (Private IP)
  vpc_connector_id      = module.vpc.vpc_connector_id
  cloud_sql_connection  = module.multi_tenant_db.connection_name
  service_account_email = var.enable_worker_service ? module.worker_agents_service[0].service_account_email : var.tenant_service_account_email

  # Secrets
  # CRITICAL: We need BOTH database URLs for migrations:
  # - ETHERION_DATABASE_URL (etherion user): To disable RLS on alembic_version (only owner can ALTER TABLE)
  # - DATABASE_URL (postgres user via RLS_DATABASE_URL): For running the actual migrations
  secret_env_vars = {
    # Primary migration connection (postgres user for high-privilege operations)
    "DATABASE_URL" = lookup(local.all_secret_env_vars, "RLS_DATABASE_URL", local.all_secret_env_vars["DATABASE_URL"])
    # Table owner connection (etherion user) - needed to disable RLS on alembic_version
    # because only the table owner can ALTER TABLE to change RLS settings
    "ETHERION_DATABASE_URL" = local.all_secret_env_vars["DATABASE_URL"]
  }

  depends_on = [
    module.multi_tenant_db,
    module.vpc
  ]
}

# Billing guardrails: dataset + budget + pubsub + email channel
module "billing_guardrails" {
  source = "../../modules/billing-guardrails"

  project_id         = var.project_id
  billing_account_id = var.billing_account_id
  alert_email        = var.alert_email

  # Budget monthly threshold default aligns w/ cost_threshold_usd
  budget_amount_monthly_usd = var.cost_threshold_usd

  # Cloud Armor not used in multi_tenant_lb - Cloudflare handles security
  security_policy_id = var.enable_security_policy ? google_compute_security_policy.platform_security_policy[0].id : ""

  # Spend-guard deployment (optional; deploys only if image URL is provided)
  spend_guard_image_url = var.spend_guard_image_url
  threshold_usd         = var.spend_guard_threshold_usd
  lookback_hours        = var.spend_guard_lookback_hours
  schedule_cron         = var.spend_guard_schedule_cron
  schedule_time_zone    = var.spend_guard_schedule_time_zone

  # Temporarily skip budget creation until billing IAM is granted
  enable_budget = false

  depends_on = [google_project_service.required_apis]
}
