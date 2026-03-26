variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
}

variable "platform_name" {
  description = "Name of the platform"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "search_engine_name" {
  description = "Name of the search engine"
  type        = string
}

variable "collection_id" {
  description = "Discovery Engine collection ID (usually default_collection)"
  type        = string
  default     = "default_collection"
}

variable "datastore_name" {
  description = "Name of the datastore"
  type        = string
}

variable "industry_vertical" {
  description = "Industry vertical for engine/datastores (e.g., GENERIC)"
  type        = string
  default     = "GENERIC"
}

variable "solution_type" {
  description = "Solution type for the engine (e.g., SOLUTION_TYPE_SEARCH)"
  type        = string
  default     = "SOLUTION_TYPE_SEARCH"
}

variable "search_tier" {
  description = "Search tier for the engine (SEARCH_TIER_STANDARD or SEARCH_TIER_ENTERPRISE)"
  type        = string
  default     = "SEARCH_TIER_STANDARD"
}

variable "tenant_id" {
  description = "Tenant ID for filtering"
  type        = string
  default     = ""
}

variable "common_labels" {
  description = "Common labels for all resources"
  type        = map(string)
  default     = {}
}

variable "enable_tenant_datastores" {
  description = "Enable per-tenant Vertex AI Search datastores"
  type        = bool
  default     = true
}

variable "vector_cache_size" {
  description = "Vector cache size as percentage of original data"
  type        = string
  default     = "20_percent"
}

variable "tenant_ids" {
  description = "List of tenant IDs for multi-tenant datastores"
  type        = list(string)
  default     = []
}

variable "tenant_datastore_prefix" {
  description = "Prefix for tenant datastore IDs (must align with application code)"
  type        = string
  default     = "tenant-kb"
}

variable "enable_bigquery_connection" {
  description = "Enable BigQuery connection for vector updates"
  type        = bool
  default     = true
}

variable "quota_requests_per_minute" {
  description = "Quota limit for requests per minute"
  type        = number
  default     = 100
}

variable "quota_requests_per_day" {
  description = "Quota limit for requests per day"
  type        = number
  default     = 10000
}

variable "rate_limit_requests_per_minute" {
  description = "Rate limit for requests per minute"
  type        = number
  default     = 100
}

variable "enable_google_search_grounding" {
  description = "Enable Google Search grounding"
  type        = bool
  default     = true
}
