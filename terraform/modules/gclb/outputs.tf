output "global_ip_address" {
  description = "Global static IP address"
  value       = google_compute_global_address.default.address
}

output "ssl_certificate_id" {
  description = "SSL certificate ID"
  value       = google_certificate_manager_certificate.default.id
}

output "certificate_map_id" {
  description = "Certificate map ID"
  value       = google_certificate_manager_certificate_map.default.id
}

output "backend_service_id" {
  description = "Backend service ID"
  value       = google_compute_backend_service.default.id
}

output "url_map_id" {
  description = "URL map ID"
  value       = google_compute_url_map.default.id
}

output "https_proxy_id" {
  description = "HTTPS proxy ID"
  value       = google_compute_target_https_proxy.default.id
}

output "security_policy_id" {
  description = "Security policy ID"
  value       = google_compute_security_policy.default.id
}
