output "vpc_id" {
  description = "VPC network ID"
  value       = google_compute_network.main.id
}

output "subnet_id" {
  description = "Subnet ID"
  value       = google_compute_subnetwork.main.id
}

output "vpc_connector_id" {
  description = "VPC Access Connector ID"
  value       = google_vpc_access_connector.connector.id
}

output "private_ip_range_name" {
  description = "Private IP range name for Cloud SQL"
  value       = google_compute_global_address.private_ip_alloc.name
}
