variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
}

variable "force_destroy" {
  description = "Force destroy the ingestion bucket (for testing)"
  type        = bool
  default     = false
}
