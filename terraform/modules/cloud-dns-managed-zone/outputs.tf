output "zone_name" {
  description = "Managed zone name"
  value       = google_dns_managed_zone.primary.name
}

output "name_servers" {
  description = "List of Cloud DNS nameservers for the zone"
  value       = google_dns_managed_zone.primary.name_servers
}
