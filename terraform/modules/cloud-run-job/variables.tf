# Variables for generic Cloud Run Job module

variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
}

variable "job_name" {
  description = "Cloud Run Job name"
  type        = string
}

variable "image_url" {
  description = "Container image URL for the job"
  type        = string
}

variable "command" {
  description = "Container entrypoint command"
  type        = list(string)
  default     = []
}

variable "args" {
  description = "Container args"
  type        = list(string)
  default     = []
}

variable "env_vars" {
  description = "Plain environment variables to inject"
  type        = map(string)
  default     = {}
}

variable "secret_env_vars" {
  description = "Secret environment variables from Secret Manager"
  type = map(object({
    name = string # Secret name in Secret Manager
    key  = string # Version (e.g., 'latest')
  }))
  default = {}
}

variable "service_account_email" {
  description = "Service account email used to run the job"
  type        = string
}

variable "vpc_connector_id" {
  description = "Existing VPC Access connector ID for private egress"
  type        = string
  default     = ""
}

variable "cloud_sql_connection" {
  description = "Cloud SQL connection name (PROJECT:REGION:INSTANCE) to mount /cloudsql for unix sockets"
  type        = string
  default     = ""
}

variable "template_annotations" {
  description = "Annotations on the job template"
  type        = map(string)
  default     = {}
}

variable "labels" {
  description = "Labels for the job"
  type        = map(string)
  default     = {}
}

variable "working_dir" {
  description = "Working directory for the container"
  type        = string
  default     = ""
}
