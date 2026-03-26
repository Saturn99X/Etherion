output "service_name" {
  description = "Cloud Run service name"
  value       = google_cloud_run_v2_service.api.name
}

output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.api.uri
}

output "service_account_email" {
  description = "Service account email"
  value       = google_service_account.api_service.email
}

output "service_id" {
  description = "Cloud Run service ID"
  value       = google_cloud_run_v2_service.api.id
}

output "location" {
  description = "Cloud Run service location"
  value       = google_cloud_run_v2_service.api.location
}
