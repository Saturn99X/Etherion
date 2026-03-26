variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "dns_zone_name" {
  description = "Name of the Cloud DNS managed zone to create"
  type        = string
}

variable "primary_domain" {
  description = "Primary domain (e.g., example.com)"
  type        = string
}

variable "description" {
  description = "Description for the managed zone"
  type        = string
  default     = "Managed by Terraform"
}
