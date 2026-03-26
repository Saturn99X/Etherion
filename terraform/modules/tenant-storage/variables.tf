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
  description = "Enable per-tenant GCS buckets"
  type        = bool
  default     = true
}

variable "tenant_ids" {
  description = "List of tenant IDs for multi-tenant buckets"
  type        = list(string)
  default     = []
}

variable "bucket_naming_pattern" {
  description = "Pattern for tenant bucket naming"
  type        = string
  default     = "tnt-{tenant_id}-{type}"
}

variable "bucket_prefix" {
  description = "Prefix for tenant bucket names"
  type        = string
  default     = "tnt"
}

variable "media_retention_days" {
  description = "Media retention period in days"
  type        = number
  default     = 365
}

variable "assets_retention_days" {
  description = "Assets retention period in days"
  type        = number
  default     = 1095  # 3 years
}

variable "webhook_retention_days" {
  description = "Webhook retention period in days"
  type        = number
  default     = 7
}

variable "kms_key_name" {
  description = "KMS key name for encryption"
  type        = string
  default     = null
}

variable "tenant_service_account_email" {
  description = "Service account email for tenant access"
  type        = string
}

variable "enable_signed_url_generator" {
  description = "Enable Cloud Function for signed URL generation"
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
