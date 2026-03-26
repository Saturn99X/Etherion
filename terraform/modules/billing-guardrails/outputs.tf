output "notification_channel_id" {
  description = "Monitoring email notification channel resource name"
  value       = google_monitoring_notification_channel.email.name
}

output "billing_export_dataset_id" {
  description = "Billing export dataset id"
  value       = google_bigquery_dataset.billing_export.dataset_id
}

output "budget_pubsub_topic" {
  description = "Budget notifications Pub/Sub topic"
  value       = google_pubsub_topic.billing_budgets.name
}
