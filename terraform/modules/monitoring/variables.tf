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

variable "logging_dataset_id" {
  description = "BigQuery dataset ID for logging"
  type        = string
}

variable "api_url" {
  description = "API service URL for uptime checks"
  type        = string
}

variable "worker_url" {
  description = "Worker service URL for uptime checks"
  type        = string
}

variable "notification_channels" {
  description = "List of notification channel IDs for alerts"
  type        = list(string)
  default     = []
}

variable "enable_uptime_checks" {
  description = "Enable uptime checks"
  type        = bool
  default     = true
}

variable "enable_cost_alerts" {
  description = "Enable cost-related alerts"
  type        = bool
  default     = true
}

variable "enable_security_alerts" {
  description = "Enable security-related alerts"
  type        = bool
  default     = true
}

variable "error_rate_threshold" {
  description = "Error rate threshold for alerts"
  type        = number
  default     = 0.05  # 5%
}

variable "response_time_threshold" {
  description = "Response time threshold for alerts (seconds)"
  type        = number
  default     = 5.0
}

variable "cost_threshold_usd" {
  description = "Cost threshold for alerts (USD)"
  type        = number
  default     = 100.0
}

variable "credit_low_threshold" {
  description = "Low credit threshold for alerts"
  type        = number
  default     = 10.0
}

variable "alert_auto_close_duration" {
  description = "Auto-close duration for alerts (seconds)"
  type        = string
  default     = "1800s"  # 30 minutes
}

variable "too_many_requests_per_minute_threshold" {
  description = "Threshold for 429 Too Many Requests per minute across services"
  type        = number
  default     = 1000
}

# Additional monitoring controls
variable "logs_retention_days" {
  description = "Retention period for the default logging bucket (days)"
  type        = number
  default     = 60
}

variable "enable_service_load_alerts" {
  description = "Enable request rate and concurrency alerts as proxies for CPU/memory saturation"
  type        = bool
  default     = true
}

variable "high_request_rate_per_second_threshold" {
  description = "Threshold for high request rate (requests per second across services)"
  type        = number
  default     = 200
}

variable "high_concurrency_threshold" {
  description = "Threshold for high concurrent requests across services"
  type        = number
  default     = 1000
}

variable "enable_latency_dashboard_tiles" {
  description = "Include latency percentile tiles (p50/p95/p99) in the dashboard"
  type        = bool
  default     = true
}
