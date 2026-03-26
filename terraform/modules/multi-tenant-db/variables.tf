variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
}

variable "vpc_id" {
  description = "VPC network ID"
  type        = string
}

variable "instance_name" {
  description = "Cloud SQL instance name"
  type        = string
}

variable "database_name" {
  description = "Primary database name"
  type        = string
}

variable "database_user" {
  description = "Primary database user"
  type        = string
}

variable "tier" {
  description = "Cloud SQL instance tier"
  type        = string
  default     = "db-n1-standard-2"
}

variable "availability_type" {
  description = "Database availability type"
  type        = string
  default     = "REGIONAL"
}

variable "deletion_protection" {
  description = "Enable deletion protection"
  type        = bool
  default     = true
}

variable "enable_rls" {
  description = "Enable Row-Level Security"
  type        = bool
  default     = true
}

variable "tenant_isolation" {
  description = "Enable tenant isolation"
  type        = bool
  default     = true
}

variable "password_rotation_id" {
  description = "Arbitrary string to force DB password rotation when changed"
  type        = string
  default     = ""
}
