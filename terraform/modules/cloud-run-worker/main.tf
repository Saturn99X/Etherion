# Cloud Run Worker Terraform Module for Etherion AI Platform
# This module creates Google Cloud Run services for Celery workers

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Service account for worker service
resource "google_service_account" "worker_service" {
  account_id   = var.service_account_id != "" ? var.service_account_id : "${var.environment}-worker-svc"
  display_name = "Worker Service Account"
  description  = "Service account for Etherion worker service"
}

# IAM bindings for worker service account
resource "google_project_iam_member" "worker_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.worker_service.email}"
}

resource "google_project_iam_member" "worker_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.worker_service.email}"
}

resource "google_project_iam_member" "worker_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.worker_service.email}"
}

resource "google_project_iam_member" "worker_logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.worker_service.email}"
}

resource "google_project_iam_member" "worker_monitoring_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.worker_service.email}"
}

resource "google_project_iam_member" "worker_bigquery_user" {
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${google_service_account.worker_service.email}"
}

resource "google_project_iam_member" "worker_bigquery_resource_admin" {
  project = var.project_id
  role    = "roles/bigquery.resourceAdmin"
  member  = "serviceAccount:${google_service_account.worker_service.email}"
}

resource "google_project_iam_member" "worker_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.worker_service.email}"
}

resource "google_project_iam_member" "worker_vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.worker_service.email}"
}

resource "google_project_iam_member" "worker_documentai_user" {
  project = var.project_id
  role    = "roles/documentai.apiUser"
  member  = "serviceAccount:${google_service_account.worker_service.email}"
}


# Cloud Run service for Celery workers
resource "google_cloud_run_v2_service" "celery_worker" {
  name     = var.service_name
  location = var.region
  project  = var.project_id

  template {
    # Cloud SQL volume for unix socket connectivity
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [var.database_connection_name]
      }
    }

    # Scaling configuration
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    # Service account
    service_account = google_service_account.worker_service.email

    # Container configuration
    containers {
      name  = "celery-worker"
      image = var.image_url
      ports {
        container_port = 8080
      }

      # Resource allocation
      resources {
        limits = {
          cpu    = var.cpu_limit
          memory = var.memory_limit
        }
        cpu_idle = false
      }

      # Environment variables
      dynamic "env" {
        for_each = var.environment_variables
        content {
          name  = env.key
          value = env.value
        }
      }

      # Secure environment variables from Secret Manager
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

      # Probes not supported with exec for v2 in current provider; omit for worker

      # No HTTP ports required for worker

      # Working directory (placeholder images may not have /app)
      working_dir = var.disable_custom_entrypoint ? null : "/app"

      # Mount Cloud SQL
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      # Ensure container listens on $PORT for Cloud Run while running Celery worker
      command = var.disable_custom_entrypoint ? null : ["/bin/sh", "-c"]
      args    = var.disable_custom_entrypoint ? null : [
        "mkdir -p /tmp/logs && python -m http.server $PORT & exec python -m src.celery_worker"
      ]
    }

    # VPC connectivity (if provided)
    dynamic "vpc_access" {
      for_each = length(var.vpc_connector_id) > 0 ? [1] : []
      content {
        connector = var.vpc_connector_id
        egress    = var.vpc_egress_setting
      }
    }

    # Execution environment
    execution_environment = var.execution_environment

    # Timeout configuration
    timeout = "${var.request_timeout}s"

    # Session affinity (not applicable for workers)
    session_affinity = false

    # Remove empty_dir volumes; not required for worker

    # Annotations for specific configurations
    annotations = merge(var.template_annotations, {
      "autoscaling.knative.dev/minScale"         = tostring(var.min_instances)
      "autoscaling.knative.dev/maxScale"         = tostring(var.max_instances)
      "run.googleapis.com/execution-environment" = var.execution_environment
      "run.googleapis.com/cpu-throttling"        = "false"
    })

    # Labels
    labels = merge(var.common_labels, {
      component = "celery-worker"
      tier      = "worker"
    })
  }

  # Traffic configuration
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  # Service-level annotations
  annotations = var.service_annotations

  # Labels for the service
  labels = merge(var.common_labels, {
    component = "celery-worker"
    role      = "background-processor"
  })
  # Ensure IAM bindings are in place before rolling a new revision
  depends_on = [
    google_project_iam_member.worker_secret_accessor,
    google_project_iam_member.worker_sql_client,
    google_project_iam_member.worker_logging_writer,
    google_project_iam_member.worker_monitoring_writer,
    time_sleep.wait_for_worker_secret_iam
  ]

  # Lifecycle management (ignore provider-injected annotations)
  lifecycle {
    ignore_changes = [
      template[0].annotations["run.googleapis.com/operation-id"],
      template[0].annotations["client.knative.dev/user-image"],
    ]
  }
}

# Allow a brief delay for IAM propagation before creating service revision
resource "time_sleep" "wait_for_worker_secret_iam" {
  depends_on      = [google_project_iam_member.worker_secret_accessor]
  create_duration = "30s"
}

# IAM binding for Cloud Run invoker (if needed for internal communication)
resource "google_cloud_run_v2_service_iam_member" "invoker" {
  count = length(var.invoker_members)

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.celery_worker.name
  role     = "roles/run.invoker"
  member   = var.invoker_members[count.index]
}

# VPC connector for private networking
resource "google_vpc_access_connector" "worker_connector" {
  count = var.create_vpc_connector ? 1 : 0

  name          = "${var.environment}-worker-connector"
  region        = var.region
  network       = var.vpc_network
  ip_cidr_range = var.connector_ip_cidr_range

  min_throughput = var.connector_min_throughput
  max_throughput = var.connector_max_throughput

  # Subnet configuration
  subnet {
    name = var.connector_subnet_name
  }
}

# Update Cloud Run service to use VPC connector
resource "google_cloud_run_v2_service" "celery_worker_with_vpc" {
  count = var.create_vpc_connector ? 1 : 0

  name     = "${var.service_name}-vpc"
  location = var.region
  project  = var.project_id

  template {
    # VPC access
    vpc_access {
      connector = google_vpc_access_connector.worker_connector[0].id
      egress    = var.vpc_egress_setting
    }

    # Same configuration as above but with VPC
    # (This would be refactored in real implementation to avoid duplication)
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    service_account = google_service_account.worker_service.email

    containers {
      name  = "celery-worker"
      image = var.image_url
      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cpu_limit
          memory = var.memory_limit
        }
        cpu_idle = false
      }

      dynamic "env" {
        for_each = var.environment_variables
        content {
          name  = env.key
          value = env.value
        }
      }

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

      command = var.disable_custom_entrypoint ? null : ["/bin/sh", "-c"]
      args    = var.disable_custom_entrypoint ? null : [
        "exec python -m src.celery_worker"
      ]
    }

  }

  depends_on = [google_vpc_access_connector.worker_connector]
}

# Monitoring and alerting
resource "google_monitoring_alert_policy" "worker_cpu_usage" {
  count = var.enable_monitoring ? 1 : 0

  display_name = "${var.environment} Celery Worker CPU Usage Alert"
  combiner     = "OR"

  conditions {
    display_name = "Worker Request Rate High (temporary)"

    condition_threshold {
      # Temporary: use request_count until CPU utilization metric type is confirmed for this project
      filter          = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.celery_worker.name}\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.cpu_alert_threshold

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = var.notification_channels

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "worker_memory_usage" {
  count = var.enable_monitoring ? 1 : 0

  display_name = "${var.environment} Celery Worker Memory Usage Alert"
  combiner     = "OR"

  conditions {
    display_name = "Worker Concurrency High (temporary)"

    condition_threshold {
      # Use request_count metric to avoid 404 for unavailable metrics in some projects
      filter          = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.celery_worker.name}\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.memory_alert_threshold

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = var.notification_channels

  alert_strategy {
    auto_close = "1800s"
  }
}
