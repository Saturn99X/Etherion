output "ingestion_bucket_name" {
  description = "Name of the data ingestion GCS bucket"
  value       = google_storage_bucket.ingestion_bucket.name
}

output "ingestion_bucket_url" {
  description = "URL of the data ingestion GCS bucket"
  value       = google_storage_bucket.ingestion_bucket.url
}

output "pubsub_topic_name" {
  description = "Name of the Pub/Sub topic for completion events"
  value       = google_pubsub_topic.ingestion_complete.name
}

output "pubsub_subscription_name" {
  description = "Name of the Pub/Sub subscription for completion events"
  value       = google_pubsub_subscription.ingestion_complete.name
}

output "cloud_function_name" {
  description = "Name of the data ingestion Cloud Function"
  value       = google_cloudfunctions2_function.data_ingestion.name
}

output "cloud_function_url" {
  description = "URL of the data ingestion Cloud Function"
  value       = google_cloudfunctions2_function.data_ingestion.service_config[0].uri
}

output "manual_function_name" {
  description = "Name of the manual ingestion Cloud Function"
  value       = google_cloudfunctions2_function.manual_ingestion.name
}

output "manual_function_url" {
  description = "URL of the manual ingestion Cloud Function"
  value       = google_cloudfunctions2_function.manual_ingestion.service_config[0].uri
}

output "service_account_email" {
  description = "Email of the Cloud Function service account"
  value       = google_service_account.ingestion_function.email
}

output "tenant_puller_function_name" {
  description = "Name of the tenant puller Cloud Function"
  value       = google_cloudfunctions2_function.tenant_puller.name
}

output "tenant_puller_function_url" {
  description = "URL of the tenant puller Cloud Function"
  value       = google_cloudfunctions2_function.tenant_puller.service_config[0].uri
}
