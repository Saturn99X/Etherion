project_id  = "fabled-decker-476913-v9"
region      = "us-central1"
environment = "prod"

# Disable GSM container creation - secrets already exist
manage_secrets = false

primary_domain = "etherionai.com"
dns_zone_name  = "etherionai-com"

# Service accounts
tenant_service_account_email = "tenant-ops@fabled-decker-476913-v9.iam.gserviceaccount.com"

# Billing/alerts
billing_account_id = "01979A-3429E4-56DDB0"
alert_email        = "alerts@etherionai.com"

# Database settings (align with Phase 2 deployed instance)
database_tier              = "db-custom-2-4096"
database_availability_type = "ZONAL"
deletion_protection        = true

# Optional tenants list (empty for now)
tenant_ids = []

# Redis configuration
redis_memory_size_gb = 1

# Secret environment variables mapped from GSM (required by API)
secret_env_vars = {
  DATABASE_URL        = { name = "etherion-database-url-prod", key = "latest" }
  ASYNC_DATABASE_URL  = { name = "etherion-async-database-url-prod", key = "latest" }
  SECRET_KEY          = { name = "app-secret-key", key = "latest" }
  JWT_SECRET_KEY      = { name = "app-secret-key", key = "latest" }
  ADMIN_INGEST_SECRET = { name = "etherion-admin-ingest-secret", key = "latest" }
  # Required pricing envs consumed at import-time in src/services/pricing/services.py
  BQ_PRICE_SLOT_PER_HOUR = { name = "BQ_PRICE_SLOT_PER_HOUR", key = "latest" }
  # OAuth providers - only Google is configured
  GOOGLE_CLIENT_ID     = { name = "GOOGLE_CLIENT_ID", key = "latest" }
  GOOGLE_CLIENT_SECRET = { name = "GOOGLE_CLIENT_SECRET", key = "latest" }
  OAUTH_STATE_SECRET   = { name = "OAUTH_STATE_SECRET", key = "latest" }
  GITHUB_CLIENT_ID     = { name = "GITHUB_CLIENT_ID", key = "latest" }
  GITHUB_CLIENT_SECRET = { name = "GITHUB_CLIENT_SECRET", key = "latest" }
  # High-privilege DSN for RLS/schema management (db-rls-apply); optional.
  RLS_DATABASE_URL = { name = "etherion-rls-database-url-prod", key = "latest" }
}

# Seed required secret values for bootstrap (replace with real values later)
secret_seed_values = {}

# DB-side RLS provisioner enabled by default
enable_rls              = true
enable_db_rls_job       = true
enable_db_migration_job = true

# Enable services (toggle frontend/monitoring as needed)
enable_api_service       = true
enable_worker_service    = true
enable_frontend_service  = false
enable_monitoring_module = false

# Container image URLs (repository paths only; tags supplied by CI/vars)
api_image_url      = "us-central1-docker.pkg.dev/fabled-decker-476913-v9/cloud-run-source-deploy/langchain-app/etherion-api:12753096bb86f94cc05a5bb797da01cefb474d3c"
worker_image_url   = "us-central1-docker.pkg.dev/fabled-decker-476913-v9/cloud-run-source-deploy/langchain-app/etherion-worker:12753096bb86f94cc05a5bb797da01cefb474d3c"
frontend_image_url = "us-central1-docker.pkg.dev/fabled-decker-476913-v9/cloud-run-source-deploy/langchain-app/etherion-frontend:latest"

# Use app entrypoints and default health path for real images
api_disable_custom_entrypoint    = false
api_health_check_path            = "/health"
worker_disable_custom_entrypoint = false

# Values to seed NEXT_PUBLIC_* GSM secret versions (public IDs)
next_public_google_client_id = "649975678815-7c4jrglusp536q6htuvmkraaa9jeq604.apps.googleusercontent.com"
next_public_github_client_id = "Ov23liGhbtnyBG5RNwW3"