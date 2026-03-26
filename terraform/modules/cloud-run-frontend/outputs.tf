output "service_name" {
  value = google_cloud_run_v2_service.frontend.name
}

output "service_account_email" {
  value = google_service_account.fe_service.email
}
