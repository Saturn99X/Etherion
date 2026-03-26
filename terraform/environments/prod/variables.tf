# Variables for the multi-tenant production environment

variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "google_credentials_json" {
  description = "Google service account credentials JSON used by Terraform providers (optional; if empty, ADC is used)"
  type        = string
  default     = ""
}

# Spend-guard configuration
variable "spend_guard_image_url" {
  description = "Container image URL for the spend-guard Cloud Run service (leave empty to disable)"
  type        = string
  default     = ""
}

variable "spend_guard_threshold_usd" {
  description = "Spend threshold in USD for the last lookback window to trigger the kill-switch"
  type        = number
  default     = 100.0
}

variable "spend_guard_lookback_hours" {
  description = "Lookback window in hours for the spend computation"
  type        = number
  default     = 24
}

variable "spend_guard_schedule_cron" {
  description = "Cloud Scheduler cron for spend checks"
  type        = string
  default     = "*/15 * * * *"
}

variable "spend_guard_schedule_time_zone" {
  description = "Time zone for the spend-guard scheduler"
  type        = string
  default     = "UTC"
}

variable "region" {
  description = "Google Cloud region"
  type        = string
  default     = "us-central1"
}

variable "platform_name" {
  description = "Name of the platform"
  type        = string
  default     = "etherion"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "primary_domain" {
  description = "Primary domain name (e.g., etherionai.com)"
  type        = string
}

variable "dns_zone_name" {
  description = "Name of the DNS managed zone"
  type        = string
}

# Multi-tenant configuration
variable "enable_multi_tenant" {
  description = "Enable multi-tenant architecture"
  type        = bool
  default     = true
}

variable "tenant_subdomain_pattern" {
  description = "Pattern for tenant subdomains (e.g., {tenant_id}.etherionai.com)"
  type        = string
  default     = "{tenant_id}.etherionai.com"
}

variable "tenant_ids" {
  description = "List of tenant IDs for multi-tenant resources"
  type        = list(string)
  default     = []
}

variable "tenant_service_account_email" {
  description = "Service account email for tenant operations"
  type        = string
}

# Container images
variable "api_image_url" {
  description = "API service container image URL"
  type        = string
}

variable "worker_image_url" {
  description = "Worker service container image URL"
  type        = string
}

variable "frontend_image_url" {
  description = "Frontend service container image URL"
  type        = string
}

# Connector worker image (for GCP connectors ingestion)
variable "connector_worker_image_url" {
  description = "Connector worker Cloud Run image URL"
  type        = string
  default     = ""
}

# Database configuration
variable "database_tier" {
  description = "Cloud SQL instance tier"
  type        = string
  default     = "db-n1-standard-2"
}

variable "database_availability_type" {
  description = "Database availability type"
  type        = string
  default     = "REGIONAL"
}

# Redis configuration
variable "redis_memory_size_gb" {
  description = "Redis memory size in GB"
  type        = number
  default     = 1
}

variable "redis_version" {
  description = "Redis version"
  type        = string
  default     = "REDIS_7_0"
}

# BigQuery configuration
variable "enable_bigquery_knowledge_base" {
  description = "Enable BigQuery knowledge base"
  type        = bool
  default     = true
}

variable "kb_retention_days" {
  description = "Default data retention period (days) for BigQuery knowledge base datasets/tables"
  type        = number
  default     = 3650
}

# RLS grantees per tenant for shared analytics table/view
variable "tenant_row_access_members" {
  description = "Map of tenant_id to list of IAM members allowed to see that tenant's rows"
  type        = map(list(string))
  default     = {}
}

# Staging dataset controls for connectors
variable "enable_staging_datasets" {
  description = "Create per-tenant staging datasets for connector landings"
  type        = bool
  default     = true
}

variable "staging_suffix" {
  description = "Suffix appended to tenant dataset id for staging datasets"
  type        = string
  default     = "_staging"
}

variable "staging_default_table_ttl_days" {
  description = "Default TTL (days) for tables in staging datasets"
  type        = number
  default     = 60
}



# Storage configuration
variable "enable_tenant_storage" {
  description = "Enable per-tenant storage buckets"
  type        = bool
  default     = true
}

variable "bucket_naming_pattern" {
  description = "Pattern for tenant bucket naming"
  type        = string
  default     = "tnt-{tenant_id}-{type}"
}

# Cost tracking configuration
variable "enable_cost_tracking" {
  description = "Enable real-time cost tracking"
  type        = bool
  default     = true
}

variable "enable_credit_management" {
  description = "Enable credit balance management"
  type        = bool
  default     = true
}

# AI assets repository configuration
variable "enable_ai_assets_repository" {
  description = "Enable AI-generated assets repository"
  type        = bool
  default     = true
}

variable "enable_cross_agent_utilization" {
  description = "Enable cross-agent asset utilization"
  type        = bool
  default     = true
}

# Monitoring configuration
variable "enable_monitoring" {
  description = "Enable comprehensive monitoring"
  type        = bool
  default     = true
}

variable "enable_tenant_metrics" {
  description = "Enable per-tenant metrics"
  type        = bool
  default     = true
}

variable "enable_cost_alerts" {
  description = "Enable cost tracking alerts"
  type        = bool
  default     = true
}

# Security configuration
variable "enable_rls" {
  description = "Enable Row-Level Security"
  type        = bool
  default     = true
}

variable "enable_tenant_isolation" {
  description = "Enable tenant isolation"
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Enable deletion protection for critical resources"
  type        = bool
  default     = true
}

# API per-IP rate limit (requests per minute)
variable "api_rate_limit_per_minute" {
  description = "Per-IP rate limit for API service"
  type        = number
  default     = 120
}

# Monitoring thresholds and alerting
variable "too_many_requests_per_minute_threshold" {
  description = "Threshold for 429 Too Many Requests per minute across services"
  type        = number
  default     = 96
}

variable "error_rate_threshold" {
  description = "Error rate threshold for alerts"
  type        = number
  default     = 0.02
}

variable "response_time_threshold" {
  description = "Response time threshold for alerts (seconds)"
  type        = number
  default     = 3.0
}

variable "cost_threshold_usd" {
  description = "Cost threshold for alerts (USD)"
  type        = number
  default     = 100.0
}

variable "credit_low_threshold" {
  description = "Low credit threshold for alerts"
  type        = number
  default     = 25.0
}

# Billing guardrails configuration
variable "billing_account_id" {
  description = "Cloud Billing account ID (e.g., 011C30-3586D7-9E3979)"
  type        = string
}

variable "alert_email" {
  description = "Email address to receive alert notifications"
  type        = string
}

variable "kill_switch_enabled" {
  description = "Enable global kill-switch (deny-all) at the load balancer via Cloud Armor"
  type        = bool
  default     = false
}

variable "alert_auto_close_duration" {
  description = "Auto-close duration for alerts (duration string e.g. 1800s)"
  type        = string
  default     = "1800s"
}

# Secret environment variables mapping used by services
variable "secret_env_vars" {
  description = "Map of secret environment variables to inject into services"
  type = map(object({
    name = string # Secret name in Secret Manager
    key  = string # Version (e.g., 'latest')
  }))
  default = {}
}

variable "manage_secrets" {
  description = "If true, create GSM secret containers; if false, reference pre-existing GSM secrets only"
  type        = bool
  default     = false
}

# Optional: seed Secret Manager versions from Terraform Cloud workspace variables
# Keys must be secret_ids that exist in GSM (e.g., "app-secret-key", "OAUTH_STATE_SECRET").
# Values are the secret payloads. This map is marked sensitive.
variable "secret_seed_values" {
  description = "Seed values for GSM secrets, keyed by secret_id"
  type        = map(string)
  default     = {}
  sensitive   = true
}

# Gate the DB RLS Cloud Run job until RLS SQL is provided
variable "enable_db_rls_job" {
  description = "Enable the db-rls-apply Cloud Run job"
  type        = bool
  default     = false
}

variable "enable_db_migration_job" {
  description = "Enable the db-migrate Cloud Run job"
  type        = bool
  default     = false
}

# Public OAuth Client IDs exposed to the frontend (safe to expose)
variable "next_public_google_client_id" {
  description = "Google OAuth Client ID for frontend auth URL"
  type        = string
  default     = ""
}

variable "next_public_github_client_id" {
  description = "GitHub OAuth Client ID for frontend auth URL"
  type        = string
  default     = ""
}

variable "next_public_microsoft_client_id" {
  description = "Microsoft OAuth Client ID for frontend auth URL"
  type        = string
  default     = ""
}

variable "next_public_microsoft_tenant_id" {
  description = "Microsoft tenant ID (or 'common')"
  type        = string
  default     = "common"
}

# DNS gating and Cloudflare integration
variable "use_cloud_dns" {
  description = "Use Google Cloud DNS managed zone/records (set false when using Cloudflare)"
  type        = bool
  default     = false
}

variable "use_cloudflare" {
  description = "Manage DNS records in Cloudflare for primary domain"
  type        = bool
  default     = false
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with DNS:Edit on the target zone"
  type        = string
  default     = ""
  sensitive   = true
}

variable "lb_ip" {
  description = "Global load balancer IPv4 address for apex A record when using Cloudflare"
  type        = string
  default     = ""
}

variable "certificate_dns_authorizations" {
  description = "List of Certificate Manager DNS authorization TXT records to publish in Cloudflare"
  type = list(object({
    name    = string
    content = string
  }))
  default = []
}

# Wave 1 — Cloud Armor / Edge Security
variable "adaptive_protection_enabled" {
  description = "Enable Cloud Armor Adaptive Protection (Layer 7 DDoS)"
  type        = bool
  default     = true
}

variable "enforce_cloudflare_only" {
  description = "If true, deny all non-Cloudflare source IPs at Cloud Armor"
  type        = bool
  default     = false
}

variable "cloudflare_ip_ranges" {
  description = "Cloudflare egress IP prefixes to allow at the edge when enforce_cloudflare_only is set"
  type        = list(string)
  default     = []
}

variable "stripe_webhook_rate_limit_per_minute" {
  description = "Per-IP rate limit for Stripe webhook endpoint (requests per minute)"
  type        = number
  default     = 10
}

variable "oauth_silo_rate_limit_per_minute" {
  description = "Per-IP rate limit for /oauth/silo/* endpoints (requests per minute)"
  type        = number
  default     = 30
}

# Feature gates
variable "enable_security_policy" {
  description = "Enable Cloud Armor security policy creation"
  type        = bool
  default     = false
}

variable "enable_data_ingestion" {
  description = "Enable data ingestion Cloud Functions module"
  type        = bool
  default     = false
}

variable "enable_api_service" {
  description = "Enable Cloud Run API service"
  type        = bool
  default     = false
}

variable "enable_worker_service" {
  description = "Enable Cloud Run Worker service"
  type        = bool
  default     = false
}

variable "enable_frontend_service" {
  description = "Enable Cloud Run Frontend service"
  type        = bool
  default     = false
}

variable "enable_monitoring_module" {
  description = "Enable monitoring module"
  type        = bool
  default     = false
}

# Cloud Run entrypoint/health overrides (useful for placeholder images)
variable "api_disable_custom_entrypoint" {
  description = "Disable custom command/args for API Cloud Run"
  type        = bool
  default     = false
}

variable "api_health_check_path" {
  description = "API health check path for probes"
  type        = string
  default     = "/health"
}

variable "worker_disable_custom_entrypoint" {
  description = "Disable custom command/args for Worker Cloud Run"
  type        = bool
  default     = false
}

variable "audit_logs_dataset_id" {
  description = "BigQuery dataset ID for centralized security/audit logs"
  type        = string
  default     = "audit_logs"
}

variable "audit_logs_default_table_ttl_days" {
  description = "Default table TTL for audit logs dataset (days)"
  type        = number
  default     = 90
}
