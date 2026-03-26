resource "google_cloud_run_v2_job" "job" {
  name     = var.job_name
  location = var.region
  project  = var.project_id

  labels = var.labels

  template {
    template {
      service_account = var.service_account_email

      dynamic "volumes" {
        for_each = var.cloud_sql_connection != "" ? [1] : []
        content {
          name = "cloudsql"
          cloud_sql_instance {
            instances = [var.cloud_sql_connection]
          }
        }
      }

      containers {
        image   = var.image_url
        command = var.command
        args    = var.args

        dynamic "env" {
          for_each = var.env_vars
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

        dynamic "volume_mounts" {
          for_each = var.cloud_sql_connection != "" ? [1] : []
          content {
            name       = "cloudsql"
            mount_path = "/cloudsql"
          }
        }
        working_dir = var.working_dir != "" ? var.working_dir : null
      }

      dynamic "vpc_access" {
        for_each = var.vpc_connector_id != "" ? [1] : []
        content {
          connector = var.vpc_connector_id
          egress    = "ALL_TRAFFIC"
        }
      }
    }
  }
}

# Minimal IAM for the job's service account
resource "google_project_iam_member" "sa_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${var.service_account_email}"
}

resource "google_project_iam_member" "sa_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${var.service_account_email}"
}

resource "google_project_iam_member" "sa_logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${var.service_account_email}"
}

resource "google_project_iam_member" "sa_vpcaccess_user" {
  project = var.project_id
  role    = "roles/vpcaccess.user"
  member  = "serviceAccount:${var.service_account_email}"
}
