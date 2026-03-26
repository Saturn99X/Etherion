# Shared database module for multi-tenant architecture
# This module creates a single Cloud SQL PostgreSQL instance that serves all tenants

terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# Random password for the database
resource "random_password" "db_password" {
  length  = 32
  special = true
}

# Store the password in Secret Manager
resource "google_secret_manager_secret" "db_password" {
  project   = var.project_id
  secret_id = "shared-db-password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}

# Cloud SQL instance for shared database
resource "google_sql_database_instance" "shared_db" {
  project          = var.project_id
  name             = var.instance_name
  database_version = "POSTGRES_17"
  region           = var.region

  settings {
    tier                        = var.tier
    availability_type           = var.availability_type
    disk_type                  = "PD_SSD"
    disk_size                  = var.disk_size
    disk_autoresize            = true
    disk_autoresize_limit      = var.disk_autoresize_limit
    
    # Enable point-in-time recovery
    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      location                       = var.region
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }

    # binary_log_enabled is for MySQL; not applicable to Postgres provider schema

    # IP configuration - private IP only
    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = "projects/${var.project_id}/global/networks/${var.vpc_network}"
      enable_private_path_for_google_cloud_services = true
    }

    # Database flags for performance and security
    database_flags {
      name  = "log_statement"
      value = "all"
    }
    
    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"
    }

    database_flags {
      name  = "shared_preload_libraries"
      value = "pg_stat_statements"
    }

    # Maintenance window
    maintenance_window {
      day          = 7  # Sunday
      hour         = 3  # 3 AM
      update_track = "stable"
    }

    # Deletion protection
    deletion_protection_enabled = var.deletion_protection
  }

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

# Create the main database
resource "google_sql_database" "main_db" {
  project   = var.project_id
  name      = "etherion"
  instance  = google_sql_database_instance.shared_db.name
  charset   = "UTF8"
  collation = "en_US.UTF8"
}

# Create the database user
resource "google_sql_user" "db_user" {
  project  = var.project_id
  name     = "etherionai"
  instance = google_sql_database_instance.shared_db.name
  password = random_password.db_password.result
}

# Private VPC connection for Cloud SQL
resource "google_compute_global_address" "private_ip_address" {
  project       = var.project_id
  name          = "${var.instance_name}-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = var.vpc_network
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = var.vpc_network
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_address.name]
}