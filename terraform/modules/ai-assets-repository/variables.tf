variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "enable_tenant_buckets" {
  description = "Enable per-tenant AI asset buckets"
  type        = bool
  default     = true
}

variable "tenant_ids" {
  description = "List of tenant IDs for multi-tenant buckets"
  type        = list(string)
  default     = []
}

variable "asset_retention_days" {
  description = "Asset retention period in days"
  type        = number
  default     = 365
}

variable "kms_key_name" {
  description = "KMS key name for encryption"
  type        = string
  default     = null
}

variable "service_account_email" {
  description = "Service account email for asset processing"
  type        = string
}

variable "enable_asset_processing" {
  description = "Enable asset processing functions"
  type        = bool
  default     = true
}

variable "enable_asset_search" {
  description = "Enable asset search functions"
  type        = bool
  default     = true
}

variable "enable_asset_cleanup" {
  description = "Enable asset cleanup functions"
  type        = bool
  default     = true
}

variable "function_source_bucket" {
  description = "GCS bucket for Cloud Function source code"
  type        = string
  default     = ""
}

variable "function_source_object" {
  description = "GCS object for Cloud Function source code"
  type        = string
  default     = ""
}

variable "asset_cleanup_schedule" {
  description = "Schedule for asset cleanup (cron format)"
  type        = string
  default     = "0 2 * * *"  # Daily at 2 AM
}

variable "enable_asset_versioning" {
  description = "Enable asset versioning"
  type        = bool
  default     = true
}

variable "enable_asset_encryption" {
  description = "Enable asset encryption"
  type        = bool
  default     = true
}
