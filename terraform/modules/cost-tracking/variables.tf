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

variable "enable_real_time_tracking" {
  description = "Enable real-time cost tracking"
  type        = bool
  default     = true
}

variable "enable_credit_management" {
  description = "Enable credit management system"
  type        = bool
  default     = true
}

variable "enable_cost_aggregation" {
  description = "Enable cost aggregation jobs"
  type        = bool
  default     = true
}

variable "service_account_email" {
  description = "Service account email for cost tracking functions"
  type        = string
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

variable "cost_aggregation_schedule" {
  description = "Schedule for cost aggregation (cron format)"
  type        = string
  default     = "0 */6 * * *"  # Every 6 hours
}

variable "credit_balance_schedule" {
  description = "Schedule for credit balance updates (cron format)"
  type        = string
  default     = "0 */1 * * *"  # Every hour
}

variable "enable_cost_alerts" {
  description = "Enable cost alert notifications"
  type        = bool
  default     = true
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
