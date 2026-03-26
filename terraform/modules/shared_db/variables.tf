# Variables for the shared database module

variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "instance_name" {
  description = "Name of the Cloud SQL instance"
  type        = string
  default     = "etherion-shared-db"
}

variable "region" {
  description = "Google Cloud region"
  type        = string
  default     = "us-central1"
}

variable "tier" {
  description = "Machine type for the Cloud SQL instance"
  type        = string
  default     = "db-f1-micro"  # Small instance for development
}

variable "availability_type" {
  description = "Availability type for the Cloud SQL instance"
  type        = string
  default     = "ZONAL"  # Use REGIONAL for production
}

variable "disk_size" {
  description = "Initial disk size in GB"
  type        = number
  default     = 20
}

variable "disk_autoresize_limit" {
  description = "Maximum disk size for autoresize in GB"
  type        = number
  default     = 100
}

variable "vpc_network" {
  description = "VPC network for private IP"
  type        = string
  default     = "default"
}

variable "deletion_protection" {
  description = "Enable deletion protection"
  type        = bool
  default     = true
}