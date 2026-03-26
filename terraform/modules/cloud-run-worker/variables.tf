# Variables for Cloud Run Worker module

variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
}

variable "service_account_id" {
  description = "Service account account_id to create for this worker (must be globally unique within the project)"
  type        = string
  default     = ""
}

variable "image_url" {
  description = "Container image URL"
  type        = string
}

variable "database_connection_name" {
  description = "Cloud SQL connection name (PROJECT:REGION:INSTANCE)"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "environment_variables" {
  description = "Plain environment variables to inject"
  type        = map(string)
  default     = {}
}

variable "secret_env_vars" {
  description = "Secret environment variables from Secret Manager"
  type = map(object({
    name = string  # Secret name
    key  = string  # Version (e.g., 'latest')
  }))
  default = {}
}

variable "min_instances" {
  description = "Minimum instances"
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Maximum instances"
  type        = number
  default     = 50
}

variable "cpu_limit" {
  description = "CPU limit"
  type        = string
  default     = "2"
}

variable "memory_limit" {
  description = "Memory limit"
  type        = string
  default     = "4Gi"
}

# Allow disabling custom command/args when deploying placeholder images
variable "disable_custom_entrypoint" {
  description = "If true, omit custom command/args and use container default entrypoint"
  type        = bool
  default     = false
}

variable "cpu_request" {
  description = "CPU request"
  type        = string
  default     = "1"
}

variable "memory_request" {
  description = "Memory request"
  type        = string
  default     = "2Gi"
}

variable "execution_environment" {
  description = "Cloud Run execution environment"
  type        = string
  default     = "EXECUTION_ENVIRONMENT_GEN2"
}

variable "request_timeout" {
  description = "Request timeout in seconds"
  type        = number
  default     = 900
}

variable "template_annotations" {
  description = "Annotations on template"
  type        = map(string)
  default     = {}
}

variable "service_annotations" {
  description = "Annotations on service"
  type        = map(string)
  default     = {}
}

variable "common_labels" {
  description = "Common labels"
  type        = map(string)
  default     = {}
}

variable "invoker_members" {
  description = "IAM members for run.invoker"
  type        = list(string)
  default     = []
}

variable "vpc_connector_id" {
  description = "Existing VPC connector ID for private egress"
  type        = string
  default     = ""
}

# Optional: create a VPC connector within the module (off by default)
variable "create_vpc_connector" {
  description = "Create a VPC Access connector in this module"
  type        = bool
  default     = false
}

variable "vpc_network" {
  description = "VPC network self link or name (required if create_vpc_connector = true)"
  type        = string
  default     = ""
}

variable "connector_ip_cidr_range" {
  description = "IP CIDR range for the VPC connector (required if create_vpc_connector = true)"
  type        = string
  default     = ""
}

variable "connector_min_throughput" {
  description = "Connector min throughput"
  type        = number
  default     = 200
}

variable "connector_max_throughput" {
  description = "Connector max throughput"
  type        = number
  default     = 300
}

variable "connector_subnet_name" {
  description = "Existing subnet name for the VPC connector (required if create_vpc_connector = true)"
  type        = string
  default     = ""
}

variable "vpc_egress_setting" {
  description = "VPC egress setting"
  type        = string
  default     = "PRIVATE_RANGES_ONLY"
}

# Monitoring
variable "enable_monitoring" {
  description = "Enable monitoring alerts"
  type        = bool
  default     = true
}

variable "notification_channels" {
  description = "Notification channels for alerts"
  type        = list(string)
  default     = []
}

variable "cpu_alert_threshold" {
  description = "CPU usage alert threshold"
  type        = number
  default     = 0.8
}

variable "memory_alert_threshold" {
  description = "Memory usage alert threshold"
  type        = number
  default     = 0.8
}
