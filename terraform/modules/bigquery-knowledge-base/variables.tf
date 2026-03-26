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

variable "platform_dataset_name" {
  description = "Name of the platform dataset"
  type        = string
}

variable "tenant_dataset_prefix" {
  description = "Prefix for tenant dataset names"
  type        = string
}

variable "common_labels" {
  description = "Common labels for all resources"
  type        = map(string)
  default     = {}
}

variable "enable_tenant_datasets" {
  description = "Enable per-tenant BigQuery datasets"
  type        = bool
  default     = true
}

variable "enable_partitioning" {
  description = "Enable table partitioning for cost optimization"
  type        = bool
  default     = true
}

variable "enable_clustering" {
  description = "Enable table clustering for performance"
  type        = bool
  default     = true
}

variable "tenant_ids" {
  description = "List of tenant IDs for multi-tenant datasets"
  type        = list(string)
  default     = []
}

variable "retention_days" {
  description = "Data retention period in days"
  type        = number
}

variable "dataset_owner_email" {
  description = "Principal email to grant OWNER on tenant datasets (e.g., API service account)"
  type        = string
}

variable "api_service_account_email" {
  description = "Optional Cloud Run API service account email to grant roles/bigquery.dataEditor on tenant datasets"
  type        = string
  default     = ""
}

variable "worker_service_account_email" {
  description = "Optional Cloud Run Worker service account email to grant roles/bigquery.dataEditor on tenant datasets"
  type        = string
  default     = ""
}

# Controls optional bootstrap of BigQuery VECTOR INDEX creation for documents tables
variable "create_vector_indexes" {
  description = "If true, bootstrap vector indexes for documents tables"
  type        = bool
  default     = true
}

# CMEK and staging dataset controls
variable "kms_key_name" {
  description = "KMS key resource ID for default encryption of datasets and tables"
  type        = string
  default     = ""
}

variable "enable_staging_datasets" {
  description = "If true, create per-tenant staging datasets for connector landings"
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

# Row Access Policy membership mapping (tenant_id -> list of IAM members)
variable "tenant_row_access_members" {
  description = "Map of tenant_id to list of IAM members granted access to rows for that tenant in shared analytics"
  type        = map(list(string))
  default     = {}
}

# Per-tenant service account emails for dataset writer ACLs
variable "tenant_service_account_emails" {
  description = "Map of tenant_id to service account email (sa-tenant-<id>@project.iam.gserviceaccount.com) to grant WRITER on datasets"
  type        = map(string)
  default     = {}
}
