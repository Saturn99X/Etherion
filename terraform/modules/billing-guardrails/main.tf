# Billing Guardrails: Budget + Pub/Sub + Email channel + BigQuery dataset (export target)

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# BigQuery dataset to host Cloud Billing export (cost & pricing)
resource "google_bigquery_dataset" "billing_export" {
  project    = var.project_id
  dataset_id = var.billing_export_dataset_id
  location   = var.billing_export_location

  labels = {
    purpose     = "billing-export"
    environment = "production"
  }
}

# Email notification channel for Cloud Monitoring & Budgets
resource "google_monitoring_notification_channel" "email" {
  display_name = "Billing & Ops Alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

# Pub/Sub topic for programmatic budget notifications
resource "google_pubsub_topic" "billing_budgets" {
  name    = var.pubsub_topic_name
  project = var.project_id
}

# Budget (monthly) with thresholds and notifications
resource "google_billing_budget" "monthly_budget" {
  count           = var.enable_budget ? 1 : 0
  billing_account = var.billing_account_id
  display_name    = "prod-guardrails-budget"

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount_monthly_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }

  all_updates_rule {
    pubsub_topic                      = google_pubsub_topic.billing_budgets.id
    schema_version                    = "1.0"
    monitoring_notification_channels  = [google_monitoring_notification_channel.email.name]
    disable_default_iam_recipients    = false
  }
}

# Optional: Spend guard resources (deployed only when an image URL is provided)
data "google_project" "current" {}

resource "google_service_account" "spend_guard" {
  count        = var.spend_guard_image_url != "" ? 1 : 0
  account_id   = "spend-guard"
  display_name = "Spend Guard"
}

# Permissions for spend guard to read BigQuery and update Cloud Armor
resource "google_project_iam_member" "spend_guard_bq_job_user" {
  count   = var.spend_guard_image_url != "" ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.spend_guard[0].email}"
}

resource "google_project_iam_member" "spend_guard_bq_user" {
  count   = var.spend_guard_image_url != "" ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${google_service_account.spend_guard[0].email}"
}

resource "google_project_iam_member" "spend_guard_compute_sec_admin" {
  count   = var.spend_guard_image_url != "" ? 1 : 0
  project = var.project_id
  role    = "roles/compute.securityAdmin"
  member  = "serviceAccount:${google_service_account.spend_guard[0].email}"
}

resource "google_cloud_run_v2_service" "spend_guard" {
  count    = var.spend_guard_image_url != "" ? 1 : 0
  name     = "spend-guard"
  project  = var.project_id
  location = "us-central1"

  template {
    service_account = google_service_account.spend_guard[0].email

    containers {
      image = var.spend_guard_image_url
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "BILLING_ACCOUNT_ID"
        value = var.billing_account_id
      }
      env {
        name  = "BQ_DATASET"
        value = var.billing_export_dataset_id
      }
      env {
        name  = "THRESHOLD_USD"
        value = tostring(var.threshold_usd)
      }
      env {
        name  = "LOOKBACK_HOURS"
        value = tostring(var.lookback_hours)
      }
      env {
        name  = "SECURITY_POLICY_ID"
        value = var.security_policy_id
      }
    }
  }

  # Allow public ingress but protect with IAM run.invoker + OIDC from Cloud Scheduler
  ingress = "INGRESS_TRAFFIC_ALL"

  depends_on = [
    google_project_iam_member.spend_guard_bq_job_user,
    google_project_iam_member.spend_guard_bq_user,
    google_project_iam_member.spend_guard_compute_sec_admin
  ]
}

# Allow Cloud Scheduler service agent to mint OIDC tokens with the spend-guard SA
resource "google_service_account_iam_member" "scheduler_token_creator" {
  count              = var.spend_guard_image_url != "" ? 1 : 0
  service_account_id = google_service_account.spend_guard[0].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
}

# Allow Scheduler to invoke the Cloud Run service via OIDC
resource "google_cloud_run_service_iam_member" "spend_guard_invoker" {
  count    = var.spend_guard_image_url != "" ? 1 : 0
  location = google_cloud_run_v2_service.spend_guard[0].location
  project  = var.project_id
  service  = google_cloud_run_v2_service.spend_guard[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.spend_guard[0].email}"
}

resource "google_cloud_scheduler_job" "spend_guard" {
  count    = var.spend_guard_image_url != "" ? 1 : 0
  project  = var.project_id
  region   = "us-central1"
  name     = "spend-guard-job"
  schedule = var.schedule_cron
  time_zone = var.schedule_time_zone

  http_target {
    http_method = "POST"
    uri         = google_cloud_run_v2_service.spend_guard[0].uri

    oidc_token {
      service_account_email = google_service_account.spend_guard[0].email
      audience              = google_cloud_run_v2_service.spend_guard[0].uri
    }
  }

  depends_on = [
    google_service_account_iam_member.scheduler_token_creator,
    google_cloud_run_service_iam_member.spend_guard_invoker
  ]
}
