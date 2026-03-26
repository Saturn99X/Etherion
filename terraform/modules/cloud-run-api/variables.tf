variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
}

# Discovery Engine location (typically "global") used by clients
variable "vertex_ai_location" {
  description = "Vertex AI/Discovery Engine location for clients (e.g., global)"
  type        = string
  default     = "global"
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
}

variable "image_url" {
  description = "Container image URL"
  type        = string
}

variable "vpc_connector_id" {
  description = "VPC Access Connector ID"
  type        = string
}

variable "database_connection_name" {
  description = "Cloud SQL connection name"
  type        = string
}

variable "database_user" {
  description = "Database user name"
  type        = string
}

variable "database_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "database_name" {
  description = "Database name"
  type        = string
}

variable "use_secret_database_url" {
  description = "If true, do not set inline DATABASE_URL/ASYNC_DATABASE_URL envs; expect them via secret_env_vars"
  type        = bool
  default     = false
}

variable "redis_host" {
  description = "Redis host address"
  type        = string
}

variable "redis_port" {
  description = "Redis port"
  type        = number
}

variable "redis_auth_string" {
  description = "Redis AUTH string (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "service_account_email" {
  description = "Service account email"
  type        = string
}

variable "enable_multi_tenant" {
  description = "Enable multi-tenant architecture"
  type        = bool
  default     = true
}

variable "enable_rls" {
  description = "Enable Row-Level Security"
  type        = bool
  default     = true
}

variable "enable_cost_tracking" {
  description = "Enable cost tracking"
  type        = bool
  default     = true
}

variable "enable_ai_assets" {
  description = "Enable AI assets repository"
  type        = bool
  default     = true
}

variable "multi_tenant_enforce_invite" {
  description = "Require invite token for new user onboarding when multi-tenant is enabled"
  type        = bool
  default     = false
}

variable "enable_public_access" {
  description = "Enable public access to API"
  type        = bool
  default     = false
}

variable "enable_authenticated_invoker" {
  description = "Grant allAuthenticatedUsers the run.invoker role (not recommended for production)"
  type        = bool
  default     = false
}

variable "lb_invoker_service_account" {
  description = "Service account used by the HTTP(S) load balancer serverless NEG to invoke this Cloud Run service"
  type        = string
  default     = ""
}

variable "ingress" {
  description = "Ingress mode for Cloud Run service: INGRESS_TRAFFIC_ALL | INGRESS_TRAFFIC_INTERNAL_ONLY | INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  type        = string
  default     = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
}

variable "secret_env_vars" {
  description = "Secret environment variables"
  type        = map(object({
    name = string
    key  = string
  }))
  default = {}
}

variable "cpu_limit" {
  description = "CPU limit for containers"
  type        = string
  default     = "2"
}

variable "memory_limit" {
  description = "Memory limit for containers"
  type        = string
  default     = "4Gi"
}

variable "min_instances" {
  description = "Minimum number of instances"
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Maximum number of instances"
  type        = number
  default     = 100
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "container_port" {
  description = "Container port"
  type        = number
  default     = 8000
}
 
variable "rate_limit_per_minute" {
  description = "Per-IP rate limit (requests per minute) enforced by the API middleware"
  type        = number
  default     = 120
}

variable "rollout_token" {
  description = "Token to force new Cloud Run revision on config changes (e.g., DB password rotation)"
  type        = string
  default     = ""
}

# Domain and base URLs for OAuth/MCP callbacks
variable "primary_domain" {
  description = "Primary domain (e.g., etherionai.com)"
  type        = string
  default     = ""
}

variable "mcp_base_url" {
  description = "Base URL for MCP endpoints (e.g., https://mcp.example.com)"
  type        = string
  default     = ""
}

variable "auth_base_url" {
  description = "Base URL for auth portals/callbacks (e.g., https://auth.example.com)"
  type        = string
  default     = ""
}

# Allow disabling custom command/args when deploying placeholder images
variable "disable_custom_entrypoint" {
  description = "If true, omit custom command/args and use container default entrypoint"
  type        = bool
  default     = false
}

# Health check path (for placeholder container use "/")
variable "health_check_path" {
  description = "HTTP path used for startup and liveness probes"
  type        = string
  default     = "/health"
}
