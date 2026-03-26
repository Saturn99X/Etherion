variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Region/Location for buckets"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment label (dev|staging|prod)"
  type        = string
}

variable "tenant_ids" {
  description = "List of tenant IDs to create buckets for"
  type        = list(string)
}

variable "common_labels" {
  description = "Common labels to apply"
  type        = map(string)
  default     = {}
}

variable "enable_versioning_for_assets" {
  description = "Enable object versioning for assets buckets"
  type        = bool
  default     = true
}

variable "kms_key_name" {
  description = "CMEK key resource name for bucket encryption (optional)"
  type        = string
  default     = null
}
