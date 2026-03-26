# Variables for Redis Memorystore Terraform Module

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = can(regex("^(dev|staging|prod)$", var.environment))
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "region" {
  description = "GCP region for Redis instance"
  type        = string
  default     = "us-central1"
}

variable "vpc_network" {
  description = "VPC network for Redis instance"
  type        = string
}

# Redis Configuration
variable "redis_tier" {
  description = "Redis tier (BASIC or STANDARD_HA)"
  type        = string
  default     = "STANDARD_HA"
  validation {
    condition     = can(regex("^(BASIC|STANDARD_HA)$", var.redis_tier))
    error_message = "Redis tier must be BASIC or STANDARD_HA."
  }
}

variable "memory_size_gb" {
  description = "Redis memory size in GB"
  type        = number
  default     = 1
  validation {
    condition     = var.memory_size_gb >= 1 && var.memory_size_gb <= 300
    error_message = "Memory size must be between 1 and 300 GB."
  }
}

variable "redis_version" {
  description = "Redis version"
  type        = string
  default     = "REDIS_6_X"
}

variable "auth_enabled" {
  description = "Enable Redis AUTH"
  type        = bool
  default     = true
}

variable "transit_encryption_mode" {
  description = "Transit encryption mode (SERVER_AUTHENTICATION, DISABLED)"
  type        = string
  default     = "SERVER_AUTHENTICATION"
  validation {
    condition     = can(regex("^(SERVER_AUTHENTICATION|DISABLED)$", var.transit_encryption_mode))
    error_message = "Transit encryption mode must be SERVER_AUTHENTICATION or DISABLED."
  }
}

variable "persistence_enabled" {
  description = "Enable Redis persistence"
  type        = bool
  default     = true
}

# Cache instance configuration
variable "enable_cache_instance" {
  description = "Create additional Redis instance for caching"
  type        = bool
  default     = false
}

variable "cache_memory_size_gb" {
  description = "Cache Redis instance memory size in GB"
  type        = number
  default     = 2
}

# Network configuration
variable "enable_private_services_access" {
  description = "Enable private services access for Redis"
  type        = bool
  default     = true
}

# Optional legacy Redis VM (disabled by default)
variable "enable_redis_stack_vm" {
  description = "Create a legacy Redis Stack VM for debugging/transition"
  type        = bool
  default     = false
}

variable "create_firewall_rules" {
  description = "Create firewall rules for Redis access"
  type        = bool
  default     = true
}

variable "redis_source_ranges" {
  description = "Source IP ranges allowed to access Redis"
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

# Monitoring configuration
variable "enable_monitoring" {
  description = "Enable Redis monitoring alerts"
  type        = bool
  default     = true
}

variable "notification_channels" {
  description = "Notification channels for Redis alerts"
  type        = list(string)
  default     = []
}

variable "max_connections_threshold" {
  description = "Maximum connections threshold for alerting"
  type        = number
  default     = 1000
}

# Access control
variable "redis_access_members" {
  description = "List of members to grant Redis access"
  type        = list(string)
  default     = []
}

# Labels and tagging
variable "common_labels" {
  description = "Common labels to apply to all resources"
  type        = map(string)
  default = {
    project     = "etherion-ai"
    managed-by  = "terraform"
  }
}
