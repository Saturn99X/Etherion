terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

resource "google_compute_instance" "redis_stack" {
  count        = var.enable_redis_stack_vm ? 1 : 0
  name         = "redis-stack-instance"
  machine_type = "e2-standard-2"
  zone         = "${var.region}-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
    }
  }

  network_interface {
    network = var.vpc_network
    access_config {}
  }

  metadata_startup_script = <<-EOT
#!/bin/bash
set -euxo pipefail
apt-get update
apt-get install -y curl gnupg lsb-release
curl -fsSL https://packages.redis.io/gpg | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/redis.list
apt-get update
apt-get install -y redis-stack-server
systemctl enable redis-stack-server
systemctl start redis-stack-server
EOT

  tags = ["redis", "redis-stack"]
}

output "redis_ip" {
  value = var.enable_redis_stack_vm ? google_compute_instance.redis_stack[0].network_interface[0].access_config[0].nat_ip : null
}
# Redis Memorystore Terraform Module for Etherion AI Platform
# This module creates a Google Cloud Memorystore Redis instance for Celery broker

# Redis instance for Celery broker
resource "google_redis_instance" "celery_broker" {
  name           = "${var.environment}-etherion-redis-celery"
  tier           = var.redis_tier
  memory_size_gb = var.memory_size_gb
  region         = var.region

  # Network configuration
  authorized_network   = var.vpc_network
  connect_mode        = "DIRECT_PEERING"
  redis_version       = var.redis_version

  # Security and performance settings
  auth_enabled               = var.auth_enabled
  transit_encryption_mode    = var.transit_encryption_mode
  redis_configs = {
    maxmemory-policy = "allkeys-lru"
    notify-keyspace-events = "Ex"
    timeout = "120"
  }

  # Backup configuration
  persistence_config {
    persistence_mode    = var.persistence_enabled ? "RDB" : "DISABLED"
    rdb_snapshot_period = var.persistence_enabled ? "ONE_HOUR" : null
  }

  # Maintenance window
  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 2
        minutes = 0
        seconds = 0
        nanos   = 0
      }
    }
  }

  # Labels for resource management
  labels = merge(var.common_labels, {
    component = "redis-broker"
    purpose   = "celery-backend"
  })

  # Lifecycle management
  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      redis_configs
    ]
  }
}

# Redis instance for general caching (optional)
resource "google_redis_instance" "cache" {
  count = var.enable_cache_instance ? 1 : 0

  name           = "${var.environment}-etherion-redis-cache"
  tier           = "BASIC"
  memory_size_gb = var.cache_memory_size_gb
  region         = var.region

  # Network configuration
  authorized_network   = var.vpc_network
  connect_mode        = "DIRECT_PEERING"
  redis_version       = var.redis_version

  # Cache-optimized settings
  auth_enabled = var.auth_enabled
  redis_configs = {
    maxmemory-policy = "allkeys-lru"
    timeout = "300"
  }

  # Labels for resource management
  labels = merge(var.common_labels, {
    component = "redis-cache"
    purpose   = "application-cache"
  })
}

# Private service connection for Redis
resource "google_compute_global_address" "redis_private_ip" {
  count = var.enable_private_services_access ? 1 : 0

  name          = "${var.environment}-redis-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = var.vpc_network
}

resource "google_service_networking_connection" "redis_private_vpc_connection" {
  count = var.enable_private_services_access ? 1 : 0

  network                 = var.vpc_network
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.redis_private_ip[0].name]
  deletion_policy = "ABANDON"
}

# Monitoring alerts for Redis
resource "google_monitoring_alert_policy" "redis_memory_usage" {
  count        = var.enable_monitoring ? 1 : 0
  display_name = "${var.environment} Redis Memory Usage Alert"
  combiner     = "OR"

  conditions {
    display_name = "Redis Memory Usage High"
    condition_threshold {
      filter          = "resource.type=\"gce_instance\" AND metric.type=\"redis.googleapis.com/stats/memory/usage_ratio\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = var.notification_channels

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "redis_connection_count" {
  count        = var.enable_monitoring ? 1 : 0
  display_name = "${var.environment} Redis Connection Count Alert"
  combiner     = "OR"

  conditions {
    display_name = "Redis Connection Count High"
    condition_threshold {
      filter          = "resource.type=\"gce_instance\" AND metric.type=\"redis.googleapis.com/stats/connections/total\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.max_connections_threshold
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = var.notification_channels

  alert_strategy {
    auto_close = "1800s"
  }
}

# IAM binding for Redis access
resource "google_project_iam_member" "redis_access" {
  count = length(var.redis_access_members)

  project = var.project_id
  role    = "roles/redis.editor"
  member  = var.redis_access_members[count.index]
}

# Firewall rules for Redis access
resource "google_compute_firewall" "redis_access" {
  count = var.create_firewall_rules ? 1 : 0

  name    = "${var.environment}-redis-access"
  network = var.vpc_network

  allow {
    protocol = "tcp"
    ports    = ["6379"]
  }

  source_ranges = var.redis_source_ranges
  target_tags   = ["redis-client"]

  description = "Allow Redis access for Etherion AI platform"
}
