output "service_name" {
  description = "Worker Cloud Run service name"
  value       = google_cloud_run_v2_service.celery_worker.name
}

output "service_url" {
  description = "Worker Cloud Run service URL"
  value       = google_cloud_run_v2_service.celery_worker.uri
}

output "service_account_email" {
  description = "Worker service account email"
  value       = google_service_account.worker_service.email
}
