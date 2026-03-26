variable "project_id" {
  description = "Google Cloud Project ID"
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

variable "dns_zone_name" {
  description = "Name of the DNS managed zone"
  type        = string
}

variable "api_service_name" {
  description = "API Cloud Run service name"
  type        = string
}

variable "worker_service_name" {
  description = "Worker Cloud Run service name"
  type        = string
}

variable "enable_tenant_subdomains" {
  description = "Enable tenant subdomain support"
  type        = bool
  default     = true
}

variable "subdomain_pattern" {
  description = "Pattern for tenant subdomains"
  type        = string
  default     = "{tenant_id}.etherionai.com"
}

variable "subdomains" {
  description = "List of subdomains to create"
  type        = list(string)
  default     = ["app", "auth", "mcp"]
}

variable "tenant_ids" {
  description = "List of tenant IDs for subdomain creation"
  type        = list(string)
  default     = []
}

variable "enable_ssl_redirect" {
  description = "Enable HTTP to HTTPS redirect"
  type        = bool
  default     = true
}

variable "enable_cdn" {
  description = "Enable CDN for static content"
  type        = bool
  default     = true
}

variable "enable_security_policy" {
  description = "Enable security policy for DDoS protection"
  type        = bool
  default     = true
}

variable "kill_switch_enabled" {
  description = "Enable global kill-switch (deny-all) Cloud Armor rule"
  type        = bool
  default     = false
}

variable "rate_limit_requests_per_minute" {
  description = "Rate limit for requests per minute"
  type        = number
  default     = 100
}

variable "rate_limit_requests_per_hour" {
  description = "Rate limit for requests per hour"
  type        = number
  default     = 1000
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "lb_name" {
  description = "Load balancer name"
  type        = string
}

variable "frontend_service_name" {
  description = "Frontend Cloud Run service name"
  type        = string
}
