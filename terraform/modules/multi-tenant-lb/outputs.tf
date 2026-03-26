# Outputs for Multi-Tenant Load Balancer

output "global_ip_address" {
  description = "Global IP address of the load balancer - Update Cloudflare DNS to point to this IP"
  value       = google_compute_global_address.default.address
}

output "global_ip_name" {
  description = "Name of the global IP address resource"
  value       = google_compute_global_address.default.name
}

# Certificate managed by Cloudflare, not Google Certificate Manager
# Cloud Armor not used - Cloudflare handles security

output "url_map_id" {
  description = "ID of the URL map"
  value       = google_compute_url_map.default.id
}
