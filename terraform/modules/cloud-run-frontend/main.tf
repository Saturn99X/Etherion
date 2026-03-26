terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_service_account" "fe_service" {
  account_id   = "${var.environment}-fe-svc"
  display_name = "Frontend Service Account"
  description  = "Service account for Etherion Frontend service"
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = var.service_name
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.fe_service.email

    containers {
      image = var.image_url

      ports {
        container_port = var.container_port
      }

      dynamic "env" {
        for_each = var.environment_variables
        content {
          name  = env.key
          value = env.value
        }
      }

      # Secret environment variables (GSM)
      dynamic "env" {
        for_each = var.secret_env_vars
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.name
              version = env.value.key
            }
          }
        }
      }

      resources {
        limits = {
          cpu    = var.cpu_limit
          memory = var.memory_limit
        }
        cpu_idle         = true
        startup_cpu_boost = true
      }
    }

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
    timeout               = "300s"
  }

  # Behind External HTTPS LB via Serverless NEG — allow external LB proxy traffic
  ingress = "INGRESS_TRAFFIC_ALL"

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  labels = {
    environment = var.environment
    purpose     = "frontend-service"
    platform    = "etherion"
  }
}

resource "google_cloud_run_service_iam_member" "fe_invoker" {
  count    = var.enable_public_access ? 1 : 0
  location = google_cloud_run_v2_service.frontend.location
  project  = google_cloud_run_v2_service.frontend.project
  service  = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Allow the frontend service account to read secrets from GSM at runtime
resource "google_project_iam_member" "fe_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.fe_service.email}"
}
