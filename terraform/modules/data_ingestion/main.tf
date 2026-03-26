# Data Ingestion Cloud Function with GCS trigger

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Project data to compute service account emails
data "google_project" "current" {}

# Cloud Function for tenant data pulling (HTTP trigger)
resource "google_cloudfunctions2_function" "tenant_puller" {
  name     = "${var.name_prefix}-tenant-puller"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "pull_tenant_data"

    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 10
    min_instance_count    = 0
    available_memory      = "512Mi"
    timeout_seconds       = 300
    service_account_email = google_service_account.ingestion_function.email

    environment_variables = {
      GOOGLE_CLOUD_PROJECT = var.project_id
      PUBSUB_TOPIC         = google_pubsub_topic.ingestion_complete.name
      INGESTION_BUCKET     = google_storage_bucket.ingestion_bucket.name
      SOURCE_VERSION       = data.archive_file.function_source.output_md5
    }
  }

  depends_on = [
    google_storage_bucket_iam_member.function_source_gcf_admin_viewer
  ]
}

# GCS bucket for data ingestion
resource "google_storage_bucket" "ingestion_bucket" {
  name          = "${var.name_prefix}-data-ingestion"
  location      = var.region
  force_destroy = var.force_destroy

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD", "PUT", "POST", "DELETE"]
    response_header = ["*"]
    max_age_seconds = 3600
  }
}

# Grant Eventarc service agent access to validate and consume GCS events from the bucket
resource "google_storage_bucket_iam_member" "eventarc_bucket_admin" {
  bucket = google_storage_bucket.ingestion_bucket.name
  role   = "roles/storage.admin"
  member = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-eventarc.iam.gserviceaccount.com"
}

# Allow Cloud Storage service agent to publish to Eventarc-created Pub/Sub topics
resource "google_project_iam_member" "gcs_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.current.number}@gs-project-accounts.iam.gserviceaccount.com"
}

# Pub/Sub topic for completion events
resource "google_pubsub_topic" "ingestion_complete" {
  name = "${var.name_prefix}-ingestion-complete"
}

# Pub/Sub subscription for completion events
resource "google_pubsub_subscription" "ingestion_complete" {
  name  = "${var.name_prefix}-ingestion-complete-sub"
  topic = google_pubsub_topic.ingestion_complete.name

  message_retention_duration = "600s"
  ack_deadline_seconds       = 20

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

# Service account for Cloud Function
resource "google_service_account" "ingestion_function" {
  # SA account_id must be 6-30 chars. Truncate prefix and use shorter suffix.
  account_id   = "${substr(var.name_prefix, 0, 16)}-ing-fn"
  display_name = "Data Ingestion Cloud Function Service Account"
  description  = "Service account for data ingestion Cloud Function"
}

# IAM roles for the service account
resource "google_project_iam_member" "ingestion_function_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.ingestion_function.email}"
}

resource "google_project_iam_member" "ingestion_function_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.ingestion_function.email}"
}

resource "google_project_iam_member" "ingestion_function_secretmanager" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.ingestion_function.email}"
}

# Allow Cloud Function to call Vertex AI for embeddings
resource "google_project_iam_member" "ingestion_function_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.ingestion_function.email}"
}

# Cloud Function source code bucket
resource "google_storage_bucket" "function_source" {
  name          = "${var.name_prefix}-function-source"
  location      = var.region
  force_destroy = true
}

# Archive the function source code
data "archive_file" "function_source" {
  type        = "zip"
  source_dir  = "${path.module}/function_src"
  output_path = "${path.module}/function_source.zip"
}

# Upload function source code
resource "google_storage_bucket_object" "function_source" {
  name   = "function_source-${data.archive_file.function_source.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.function_source.output_path
}

# Allow Cloud Functions Admin Robot to read function source from bucket
resource "google_storage_bucket_iam_member" "function_source_gcf_admin_viewer" {
  bucket = google_storage_bucket.function_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:service-${data.google_project.current.number}@gcf-admin-robot.iam.gserviceaccount.com"
}

# Cloud Function
resource "google_cloudfunctions2_function" "data_ingestion" {
  name     = "${var.name_prefix}-data-ingestion"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "process_uploaded_file"
    
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 10
    min_instance_count    = 0
    available_memory      = "1Gi"
    timeout_seconds       = 540
    service_account_email = google_service_account.ingestion_function.email
    
    environment_variables = {
      GOOGLE_CLOUD_PROJECT     = var.project_id
      PUBSUB_TOPIC            = google_pubsub_topic.ingestion_complete.name
      INGESTION_BUCKET        = google_storage_bucket.ingestion_bucket.name
      SOURCE_VERSION          = data.archive_file.function_source.output_md5
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.storage.object.v1.finalized"
    event_filters {
      attribute = "bucket"
      value     = google_storage_bucket.ingestion_bucket.name
    }
  }

  depends_on = [
    google_storage_bucket_iam_member.function_source_gcf_admin_viewer
  ]
}

# Cloud Function for manual processing (HTTP trigger)
resource "google_cloudfunctions2_function" "manual_ingestion" {
  name     = "${var.name_prefix}-manual-ingestion"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "manual_process"
    
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 5
    min_instance_count    = 0
    available_memory      = "512Mi"
    timeout_seconds       = 300
    service_account_email = google_service_account.ingestion_function.email
    
    environment_variables = {
      GOOGLE_CLOUD_PROJECT     = var.project_id
      PUBSUB_TOPIC            = google_pubsub_topic.ingestion_complete.name
      INGESTION_BUCKET        = google_storage_bucket.ingestion_bucket.name
      SOURCE_VERSION          = data.archive_file.function_source.output_md5
    }
  }

  depends_on = [
    google_storage_bucket_iam_member.function_source_gcf_admin_viewer
  ]
}

# IAM binding for Cloud Function invocation
resource "google_cloudfunctions2_function_iam_member" "ingestion_invoker" {
  project        = var.project_id
  location       = var.region
  cloud_function = google_cloudfunctions2_function.data_ingestion.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_service_account.ingestion_function.email}"
}

# IAM binding for manual ingestion function
resource "google_cloudfunctions2_function_iam_member" "manual_invoker" {
  project        = var.project_id
  location       = var.region
  cloud_function = google_cloudfunctions2_function.manual_ingestion.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_service_account.ingestion_function.email}"
}

# IAM binding for tenant puller function
resource "google_cloudfunctions2_function_iam_member" "tenant_puller_invoker" {
  project        = var.project_id
  location       = var.region
  cloud_function = google_cloudfunctions2_function.tenant_puller.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_service_account.ingestion_function.email}"
}

# Cloud Scheduler job for cleanup
resource "google_cloud_scheduler_job" "cleanup_job" {
  name        = "${var.name_prefix}-ingestion-cleanup"
  description = "Cleanup old processed files from ingestion bucket"
  schedule    = "0 2 * * *"  # Daily at 2 AM
  time_zone   = "UTC"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-${var.project_id}.cloudfunctions.net/${google_cloudfunctions2_function.manual_ingestion.name}"
    
    headers = {
      "Content-Type" = "application/json"
    }
    
    body = base64encode(jsonencode({
      bucket_name = google_storage_bucket.ingestion_bucket.name
      file_name   = "cleanup/cleanup.json"
      tenant_id   = "system"
    }))
  }
}

# Service account for Cloud Scheduler
resource "google_service_account" "scheduler" {
  # SA account_id must be 6-30 chars. Truncate prefix and use shorter suffix.
  account_id   = "${substr(var.name_prefix, 0, 16)}-sched"
  display_name = "Cloud Scheduler Service Account"
}

# IAM binding for Cloud Scheduler
resource "google_project_iam_member" "scheduler_cloudfunctions" {
  project = var.project_id
  role    = "roles/cloudfunctions.invoker"
  member  = "serviceAccount:${google_service_account.scheduler.email}"
}
