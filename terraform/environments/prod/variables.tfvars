# Multi-tenant production environment configuration
# IMPORTANT: Replace all placeholder values with your actual values!

# Project configuration
project_id    = "etherion-ai-production" # New production project
region        = "us-central1"           # Provided by user
platform_name = "etherion"              # Platform name (can be customized)
environment   = "prod"                  # Valid values: dev, staging, prod

# Domain configuration
primary_domain = "etherionai.com" # Provided by user
dns_zone_name  = "etherionai-com" # Proposed managed zone name

# DNS providers
use_cloud_dns  = false
use_cloudflare = true
# Do NOT set cloudflare_api_token here; supply via environment:
# export TF_VAR_cloudflare_api_token="<token>"
lb_ip = "34.128.148.250" # set to GCLB IPv4 when known

# Multi-tenant configuration
enable_multi_tenant          = true
tenant_ids                   = []                                                           # Add your actual tenant IDs here
tenant_service_account_email = "tenant-ops@etherion-ai-production.iam.gserviceaccount.com" # Proposed SA

# Container images (repository paths only; tags supplied by CI/vars)
api_image_url      = "us-central1-docker.pkg.dev/etherion-ai-production/etherion/api"
worker_image_url   = "us-central1-docker.pkg.dev/etherion-ai-production/etherion/worker"
frontend_image_url = "us-central1-docker.pkg.dev/etherion-ai-production/etherion/frontend"

# Database configuration
database_tier              = "db-custom-2-4096"
database_availability_type = "REGIONAL"
deletion_protection        = true

# Redis configuration
redis_memory_size_gb = 1
redis_version        = "REDIS_7_0"

# BigQuery knowledge base configuration
enable_bigquery_knowledge_base = true

# Storage configuration
enable_tenant_storage = true
bucket_naming_pattern = "tnt-{tenant_id}-{type}"

# Cost tracking configuration
enable_cost_tracking     = true
enable_credit_management = true

# AI assets repository configuration
enable_ai_assets_repository    = true
enable_cross_agent_utilization = true

# Monitoring configuration
enable_monitoring     = true
enable_tenant_metrics = true
enable_cost_alerts    = true

# Security configuration
enable_rls              = true
enable_tenant_isolation = true

# Secrets mapping for services (API reads only what is explicitly listed)
secret_env_vars = {
  # Core application and database secrets
  DATABASE_URL        = { name = "etherion-database-url-prod",       key = "latest" }
  ASYNC_DATABASE_URL  = { name = "etherion-async-database-url-prod", key = "latest" }
  SECRET_KEY          = { name = "app-secret-key",                   key = "latest" }
  JWT_SECRET_KEY      = { name = "app-secret-key",                   key = "latest" }
  ADMIN_INGEST_SECRET = { name = "etherion-admin-ingest-secret",     key = "latest" }

  BQ_PRICE_SLOT_PER_HOUR = { name = "BQ_PRICE_SLOT_PER_HOUR",        key = "latest" }

  # Web search provider
  EXA_API_KEY         = { name = "EXA_API_KEY",                      key = "latest" }
}