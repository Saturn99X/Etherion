# Outputs for Redis Memorystore Terraform Module

output "redis_host" {
  description = "Redis instance host IP address"
  value       = google_redis_instance.celery_broker.host
}

output "redis_port" {
  description = "Redis instance port"
  value       = google_redis_instance.celery_broker.port
}

output "redis_connection_string" {
  description = "Redis connection string for Celery broker"
  value       = "redis://${google_redis_instance.celery_broker.host}:${google_redis_instance.celery_broker.port}/0"
  sensitive   = false
}

output "redis_auth_string" {
  description = "Redis AUTH string (if auth is enabled)"
  value       = google_redis_instance.celery_broker.auth_string
  sensitive   = true
}

output "redis_instance_id" {
  description = "Redis instance ID"
  value       = google_redis_instance.celery_broker.id
}

output "redis_instance_name" {
  description = "Redis instance name"
  value       = google_redis_instance.celery_broker.name
}

output "redis_region" {
  description = "Redis instance region"
  value       = google_redis_instance.celery_broker.region
}

output "redis_tier" {
  description = "Redis instance tier"
  value       = google_redis_instance.celery_broker.tier
}

output "redis_memory_size_gb" {
  description = "Redis instance memory size in GB"
  value       = google_redis_instance.celery_broker.memory_size_gb
}

output "redis_current_location_id" {
  description = "Redis instance current location ID"
  value       = google_redis_instance.celery_broker.current_location_id
}

output "redis_persistence_iam_identity" {
  description = "Redis persistence IAM identity"
  value       = google_redis_instance.celery_broker.persistence_iam_identity
}

# Cache instance outputs (if enabled)
output "cache_host" {
  description = "Cache Redis instance host IP address"
  value       = var.enable_cache_instance ? google_redis_instance.cache[0].host : null
}

output "cache_port" {
  description = "Cache Redis instance port"
  value       = var.enable_cache_instance ? google_redis_instance.cache[0].port : null
}

output "cache_connection_string" {
  description = "Cache Redis connection string"
  value       = var.enable_cache_instance ? "redis://${google_redis_instance.cache[0].host}:${google_redis_instance.cache[0].port}/0" : null
  sensitive   = false
}

output "cache_auth_string" {
  description = "Cache Redis AUTH string (if auth is enabled)"
  value       = var.enable_cache_instance ? google_redis_instance.cache[0].auth_string : null
  sensitive   = true
}

# Network outputs
output "private_ip_address" {
  description = "Private IP address reserved for Redis"
  value       = var.enable_private_services_access ? google_compute_global_address.redis_private_ip[0].address : null
}

output "private_ip_prefix_length" {
  description = "Private IP prefix length"
  value       = var.enable_private_services_access ? google_compute_global_address.redis_private_ip[0].prefix_length : null
}

# Monitoring outputs
output "monitoring_alert_policy_ids" {
  description = "IDs of created monitoring alert policies"
  value = {
    memory_usage     = var.enable_monitoring ? google_monitoring_alert_policy.redis_memory_usage[0].id : null
    connection_count = var.enable_monitoring ? google_monitoring_alert_policy.redis_connection_count[0].id : null
  }
}

# Firewall outputs
output "firewall_rule_name" {
  description = "Name of the created firewall rule for Redis access"
  value       = var.create_firewall_rules ? google_compute_firewall.redis_access[0].name : null
}

# Environment variables for application deployment
output "environment_variables" {
  description = "Environment variables for application containers"
  value = {
    CELERY_BROKER_URL    = "redis://${google_redis_instance.celery_broker.host}:${google_redis_instance.celery_broker.port}/0"
    CELERY_RESULT_BACKEND = "redis://${google_redis_instance.celery_broker.host}:${google_redis_instance.celery_broker.port}/1"
    REDIS_URL            = "redis://${google_redis_instance.celery_broker.host}:${google_redis_instance.celery_broker.port}/2"
    REDIS_HOST           = google_redis_instance.celery_broker.host
    REDIS_PORT           = tostring(google_redis_instance.celery_broker.port)
    CACHE_REDIS_URL      = var.enable_cache_instance ? "redis://${google_redis_instance.cache[0].host}:${google_redis_instance.cache[0].port}/0" : null
  }
  sensitive = false
}

# Secure environment variables (with AUTH)
output "secure_environment_variables" {
  description = "Secure environment variables with authentication"
  value = var.auth_enabled ? {
    CELERY_BROKER_URL    = "redis://:${google_redis_instance.celery_broker.auth_string}@${google_redis_instance.celery_broker.host}:${google_redis_instance.celery_broker.port}/0"
    CELERY_RESULT_BACKEND = "redis://:${google_redis_instance.celery_broker.auth_string}@${google_redis_instance.celery_broker.host}:${google_redis_instance.celery_broker.port}/1"
    REDIS_URL            = "redis://:${google_redis_instance.celery_broker.auth_string}@${google_redis_instance.celery_broker.host}:${google_redis_instance.celery_broker.port}/2"
    REDIS_AUTH_STRING    = google_redis_instance.celery_broker.auth_string
    CACHE_REDIS_URL      = var.enable_cache_instance && var.auth_enabled ? "redis://:${google_redis_instance.cache[0].auth_string}@${google_redis_instance.cache[0].host}:${google_redis_instance.cache[0].port}/0" : null
  } : null
  sensitive = true
}
