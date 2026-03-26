variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
}

variable "primary_domain" {
  description = "Primary domain name (e.g., etherionai.com)"
  type        = string
}

variable "domains" {
  description = "List of domains for SSL certificate"
  type        = list(string)
}

variable "subdomains" {
  description = "List of subdomains to create"
  type        = list(string)
  default     = []
}

variable "cloud_run_service_name" {
  description = "Name of the Cloud Run service"
  type        = string
}

variable "dns_zone_name" {
  description = "Name of the DNS managed zone"
  type        = string
}
