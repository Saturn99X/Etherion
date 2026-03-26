variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "billing_account_id" {
  description = "Cloud Billing account ID (e.g., 011C30-3586D7-9E3979)"
  type        = string
}

variable "alert_email" {
  description = "Email address to receive alerts"
  type        = string
}

variable "billing_export_dataset_id" {
  description = "BigQuery dataset ID to store Cloud Billing export"
  type        = string
  default     = "billing_export"
}

variable "billing_export_location" {
  description = "Location for the billing export dataset"
  type        = string
  default     = "US"
}

variable "budget_amount_monthly_usd" {
  description = "Monthly budget amount in USD (used for notifications)"
  type        = number
  default     = 100.0
}

variable "enable_budget" {
  description = "Whether to create the Billing Budget resource"
  type        = bool
  default     = true
}

variable "pubsub_topic_name" {
  description = "Pub/Sub topic name for budget notifications"
  type        = string
  default     = "billing-budgets"
}

# Optional: automatic spend guard (last-24h) Cloud Run service
variable "security_policy_id" {
  description = "Cloud Armor security policy ID to control kill-switch rule"
  type        = string
  default     = ""
}

variable "spend_guard_image_url" {
  description = "Container image URL for spend-guard Cloud Run service (leave empty to skip deployment)"
  type        = string
  default     = ""
}

variable "threshold_usd" {
  description = "Spend threshold for the last LOOKBACK_HOURS to trigger kill-switch"
  type        = number
  default     = 100
}

variable "lookback_hours" {
  description = "Hours to look back when computing recent spend"
  type        = number
  default     = 24
}

variable "schedule_cron" {
  description = "Cloud Scheduler cron expression for spend checks"
  type        = string
  default     = "*/15 * * * *"
}

variable "schedule_time_zone" {
  description = "Time zone for the Cloud Scheduler job"
  type        = string
  default     = "UTC"
}

variable "kill_switch_rule_priority" {
  description = "Priority of the kill-switch rule inside the Cloud Armor policy"
  type        = number
  default     = 10
}
