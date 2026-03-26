# Computed values for the multi-tenant production environment

locals {
  # Platform configuration
  platform_name = var.platform_name
  environment   = var.environment
  project_id    = var.project_id
  region        = var.region

  # Computed naming patterns
  name_prefix   = "${local.platform_name}-${local.environment}"
  tenant_prefix = "tnt"

  # Domain configuration
  primary_domain = var.primary_domain
  dns_zone_name  = var.dns_zone_name

  # Multi-tenant configuration
  tenant_subdomain_pattern = "{tenant_id}.${local.primary_domain}"

  # Database configuration
  database_name = "${local.name_prefix}-db"
  database_user = "${local.platform_name}_user"

  # Redis configuration
  redis_name = "${local.name_prefix}-redis"

  # BigQuery configuration
  platform_dataset_name = "${local.platform_name}_${local.environment}_kb"
  # Must match application dataset convention: tnt_{tenant_id}
  tenant_dataset_prefix = "tnt_{tenant_id}"

  # Vertex AI Search configuration
  search_engine_name = "${local.platform_name}-${local.environment}-search"
  datastore_name     = "${local.platform_name}-${local.environment}-datastore"

  # Storage configuration
  storage_bucket_prefix = "${local.tenant_prefix}-{tenant_id}"

  # Cloud Run configuration
  api_service_name      = "${local.platform_name}-api"
  worker_service_name   = "${local.platform_name}-worker"
  worker_agents_service_name    = "${local.platform_name}-worker-agents"
  worker_artifacts_service_name = "${local.platform_name}-worker-artifacts"
  frontend_service_name = "${local.platform_name}-frontend"

  # Load balancer configuration
  lb_name = "${local.platform_name}-lb"

  # Monitoring configuration
  monitoring_dashboard_name = "${local.platform_name} Platform Dashboard"

  # Cost tracking configuration
  cost_tracking_dataset = "${local.platform_name}_cost_tracking"

  # AI assets configuration
  ai_assets_bucket = "${local.platform_name}-ai-assets"

  # Service account configuration
  service_account_prefix = "${local.platform_name}-service"

  # Labels for all resources
  common_labels = {
    environment = local.environment
    platform    = local.platform_name
    project     = local.project_id
    managed_by  = "terraform"
  }

  # Tenant-specific labels
  tenant_labels = {
    for tenant_id in var.tenant_ids : tenant_id => merge(local.common_labels, {
      tenant_id = tenant_id
    })
  }
}
