# Cloud DNS managed zone for primary domain

resource "google_dns_managed_zone" "primary" {
  name        = var.dns_zone_name
  dns_name    = "${var.primary_domain}."
  project     = var.project_id
  description = var.description
  visibility  = "public"
}
