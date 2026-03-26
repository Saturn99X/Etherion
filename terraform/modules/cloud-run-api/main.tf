# Cloud Run API Module for Multi-Tenant Platform

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Cloud Run Service for API (no background processing)
resource "google_cloud_run_v2_service" "api" {
  name     = var.service_name
  location = var.region
  project  = var.project_id
  
  template {
    service_account = google_service_account.api_service.email
    
    # Mount Cloud SQL connection to /cloudsql for unix socket connectivity
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [var.database_connection_name]
      }
    }

    containers {
      image   = var.image_url
      command = var.disable_custom_entrypoint ? null : ["/bin/sh", "-c"]
      args    = var.disable_custom_entrypoint ? null : [
        "mkdir -p /tmp/logs && exec uvicorn src.etherion_ai.app:app --host 0.0.0.0 --port $PORT"
      ]
      
      ports {
        container_port = var.container_port
      }
      
      # Environment variables
      # Conditionally inject inline DB URLs only when not using Secret Manager
      dynamic "env" {
        for_each = var.use_secret_database_url ? [] : [1]
        content {
          name  = "DATABASE_URL"
          value = "postgresql://${var.database_user}:${var.database_password}@/${var.database_name}?host=/cloudsql/${var.database_connection_name}"
        }
      }

      # Provide explicit async driver URL when not using secrets
      dynamic "env" {
        for_each = var.use_secret_database_url ? [] : [1]
        content {
          name  = "ASYNC_DATABASE_URL"
          value = "postgresql+asyncpg://${var.database_user}:${var.database_password}@/${var.database_name}?host=/cloudsql/${var.database_connection_name}"
        }
      }
      
      env {
        name  = "REDIS_URL"
        value = var.redis_auth_string != "" ? "rediss://:${var.redis_auth_string}@${var.redis_host}:${var.redis_port}?ssl_cert_reqs=none" : "rediss://${var.redis_host}:${var.redis_port}?ssl_cert_reqs=none"
      }
      # Celery broker URL for dispatching background tasks to worker
      env {
        name  = "CELERY_BROKER_URL"
        value = var.redis_auth_string != "" ? "rediss://:${var.redis_auth_string}@${var.redis_host}:${var.redis_port}/0?ssl_cert_reqs=none" : "rediss://${var.redis_host}:${var.redis_port}/0?ssl_cert_reqs=none"
      }

      # No-rebuild runtime settings (DISABLE_ASYNC_DB removed to enable async DB)
      env {
        name  = "PYTHONPATH"
        value = "/tmp/pypkg"
      }
      env {
        name  = "AUDIT_LOG_FILE"
        value = "/tmp/logs/audit.log"
      }

      # (async DB enabled; using ASYNC_DATABASE_URL to set driver explicitly)

      
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      
      env {
        name  = "VERTEX_AI_LOCATION"
        value = var.vertex_ai_location
      }
      
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      # Base URLs for OAuth/MCP callbacks
      env {
        name  = "AUTH_BASE_URL"
        value = var.auth_base_url != "" ? var.auth_base_url : "https://auth.${var.primary_domain}"
      }
      env {
        name  = "MCP_BASE_URL"
        value = var.mcp_base_url != "" ? var.mcp_base_url : "https://mcp.${var.primary_domain}"
      }
      # Primary domain for app defaults (e.g., Stripe success/cancel URLs)
      env {
        name  = "PRIMARY_DOMAIN"
        value = var.primary_domain
      }
      
      env {
        name  = "ENABLE_MULTI_TENANT"
        value = var.enable_multi_tenant ? "true" : "false"
      }
      env {
        name  = "ENABLE_RLS"
        value = var.enable_rls ? "true" : "false"
      }

      # Invite enforcement for multi-tenant onboarding
      env {
        name  = "MULTI_TENANT_ENFORCE_INVITE"
        value = var.multi_tenant_enforce_invite ? "true" : "false"
      }

      env {
        name  = "ENABLE_COST_TRACKING"
        value = var.enable_cost_tracking ? "true" : "false"
      }

      env {
        name  = "ENABLE_AI_ASSETS"
        value = var.enable_ai_assets ? "true" : "false"
      }

      # Per-service rate limit
      env {
        name  = "RATE_LIMIT_PER_MINUTE"
        value = tostring(var.rate_limit_per_minute)
      }

      # Force new revision on configuration changes (e.g., DB password rotation)
      env {
        name  = "CONFIG_ROLLOUT_TOKEN"
        value = var.rollout_token
      }
      
      # Secret environment variables
      dynamic "env" {
        for_each = toset(sort(keys(var.secret_env_vars)))
        content {
          name = env.value
          value_source {
            secret_key_ref {
              secret  = var.secret_env_vars[env.value].name
              version = var.secret_env_vars[env.value].key
            }
          }
        }
      }

      # Mount the Cloud SQL volume inside the container
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      # Resource limits
      resources {
        limits = {
          cpu    = var.cpu_limit
          memory = var.memory_limit
        }
        cpu_idle = true
        startup_cpu_boost = true
      }
      
      # Health checks
      startup_probe {
        http_get {
          path = var.health_check_path
          port = var.container_port
        }
        initial_delay_seconds = 60
        timeout_seconds      = 10
        period_seconds       = 10
        failure_threshold    = 3
      }
      
      liveness_probe {
        http_get {
          path = var.health_check_path
          port = var.container_port
        }
        initial_delay_seconds = 90
        timeout_seconds      = 10
        period_seconds       = 30
        failure_threshold    = 3
      }
    }
    
    # Scaling configuration
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }
    
    # VPC connectivity
    vpc_access {
      connector = var.vpc_connector_id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    
    # Execution environment
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
    
    # Timeout
    timeout = "3600s"
  }
  
  # Ingress mode is configurable by caller (default internal+LB)
  ingress = var.ingress
  
  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }
  
  labels = {
    environment = var.environment
    purpose     = "api-service"
    platform    = "etherion"
  }

  # Ensure IAM bindings (incl. Secret Accessor) are in place before creating a new revision
  depends_on = [
    google_project_iam_member.api_secret_accessor,
    google_project_iam_member.api_sql_client,
    google_project_iam_member.api_logging_writer,
    google_project_iam_member.api_monitoring_writer,
    google_project_iam_member.api_bigquery_user,
    google_project_iam_member.api_bigquery_resource_admin,
    google_project_iam_member.api_bigquery_job_user,
    time_sleep.wait_for_api_secret_iam
  ]
}

# Allow a brief delay for IAM propagation before service revision
resource "time_sleep" "wait_for_api_secret_iam" {
  depends_on      = [google_project_iam_member.api_secret_accessor]
  create_duration = "30s"
}

# IAM binding for Cloud Run service
resource "google_cloud_run_service_iam_member" "api_invoker" {
  count = var.enable_public_access ? 1 : 0
  
  location = google_cloud_run_v2_service.api.location
  project  = google_cloud_run_v2_service.api.project
  service  = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# IAM binding for authenticated access
resource "google_cloud_run_service_iam_member" "api_authenticated_invoker" {
  count    = var.enable_authenticated_invoker ? 1 : 0
  location = google_cloud_run_v2_service.api.location
  project  = google_cloud_run_v2_service.api.project
  service  = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allAuthenticatedUsers"
}

# IAM binding for HTTPS load balancer serverless NEG identity
resource "google_cloud_run_service_iam_member" "api_lb_invoker" {
  count   = var.lb_invoker_service_account != "" ? 1 : 0
  location = google_cloud_run_v2_service.api.location
  project  = google_cloud_run_v2_service.api.project
  service  = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.lb_invoker_service_account}"
}

# Service account for API service
resource "google_service_account" "api_service" {
  account_id   = "${var.environment}-api-svc"
  display_name = "API Service Account"
  description  = "Service account for Etherion API service"
}

# IAM bindings for service account
resource "google_project_iam_member" "api_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}

resource "google_project_iam_member" "api_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}

resource "google_project_iam_member" "api_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}

resource "google_project_iam_member" "api_ai_platform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}

resource "google_project_iam_member" "api_documentai_user" {
  project = var.project_id
  role    = "roles/documentai.apiUser"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}

resource "google_project_iam_member" "api_bigquery_user" {
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}

# Allow dataset and table creation/management at project level
resource "google_project_iam_member" "api_bigquery_resource_admin" {
  project = var.project_id
  role    = "roles/bigquery.resourceAdmin"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}

# Allow running BigQuery jobs
resource "google_project_iam_member" "api_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}



resource "google_project_iam_member" "api_logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}

resource "google_project_iam_member" "api_monitoring_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}
