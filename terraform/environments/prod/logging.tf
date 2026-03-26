# Audit Logging Sink to BigQuery (Wave 1)

resource "google_bigquery_dataset" "audit_logs" {
  dataset_id  = var.audit_logs_dataset_id
  project     = var.project_id
  location    = "US"
  description = "Centralized security/audit logs (Cloud Armor, LB)"

  default_table_expiration_ms = var.audit_logs_default_table_ttl_days * 24 * 60 * 60 * 1000

  labels = {
    environment = var.environment
    platform    = var.platform_name
    purpose     = "audit-logs"
    managed_by  = "terraform"
  }
}

# Sink only LB/Cloud Armor traffic logs initially (narrow scope, can extend later)
resource "google_logging_project_sink" "audit_sink" {
  name        = "audit-logs-sink"
  project     = var.project_id
  destination = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${google_bigquery_dataset.audit_logs.dataset_id}"

  # Create a unique SA writer identity for this sink
  unique_writer_identity = true

  # Capture LB/Cloud Armor logs (resource.type=http_load_balancer)
  filter = <<-EOT
    resource.type="http_load_balancer"
  EOT
}

# Grant sink SA permission to write into the dataset
resource "google_bigquery_dataset_iam_member" "audit_sink_writer" {
  dataset_id = google_bigquery_dataset.audit_logs.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = google_logging_project_sink.audit_sink.writer_identity
}
