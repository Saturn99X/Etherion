# Google Cloud Load Balancer with Certificate Manager for multi-tenant subdomains

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Reserve global static IP address
resource "google_compute_global_address" "default" {
  name = "${var.name_prefix}-global-ip"
}

# Create SSL certificate using Certificate Manager
resource "google_certificate_manager_certificate" "default" {
  name = "${var.name_prefix}-ssl-cert"
  
  managed {
    domains = var.domains
  }
}

# Create certificate map
resource "google_certificate_manager_certificate_map" "default" {
  name = "${var.name_prefix}-cert-map"
}

# Add certificate to map
resource "google_certificate_manager_certificate_map_entry" "default" {
  name     = "${var.name_prefix}-cert-map-entry"
  map      = google_certificate_manager_certificate_map.default.name
  hostname = var.primary_domain
  
  certificates = [google_certificate_manager_certificate.default.id]
}

# Create backend service for Cloud Run
resource "google_compute_backend_service" "default" {
  name                  = "${var.name_prefix}-backend"
  protocol              = "HTTP"
  port_name             = "http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  timeout_sec           = 30

  backend {
    group = google_compute_region_network_endpoint_group.cloud_run_neg.id
  }

  # Health check
  health_checks = [google_compute_health_check.default.id]

  # Enable CDN
  enable_cdn = true
  cdn_policy {
    cache_mode                   = "CACHE_ALL_STATIC"
    default_ttl                  = 3600
    client_ttl                   = 3600
    max_ttl                      = 86400
    negative_caching             = true
    serve_while_stale            = 86400
    signed_url_cache_max_age_sec = 0
  }

  # Security policy
  security_policy = google_compute_security_policy.default.id

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# Create Network Endpoint Group for Cloud Run
resource "google_compute_region_network_endpoint_group" "cloud_run_neg" {
  name                  = "${var.name_prefix}-cloud-run-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = var.cloud_run_service_name
  }
}

# Health check for backend service
resource "google_compute_health_check" "default" {
  name               = "${var.name_prefix}-health-check"
  check_interval_sec = 10
  timeout_sec        = 5
  healthy_threshold  = 2
  unhealthy_threshold = 3

  http_health_check {
    port         = 8080
    request_path = "/health"
  }
}

# Security policy for DDoS protection and rate limiting
resource "google_compute_security_policy" "default" {
  name = "${var.name_prefix}-security-policy"

  # Default rule - allow all
  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "default rule"
  }

  # Rate limiting rule
  rule {
    action   = "throttle"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 100
        interval_sec = 60
      }
    }
    description = "Rate limiting rule"
  }

  # DDoS protection
  rule {
    action   = "deny(403)"
    priority = "100"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(403)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 1000
        interval_sec = 60
      }
    }
    description = "DDoS protection rule"
  }
}

# URL map for routing
resource "google_compute_url_map" "default" {
  name            = "${var.name_prefix}-url-map"
  default_service = google_compute_backend_service.default.id

  # Host rules for subdomain routing
  dynamic "host_rule" {
    for_each = var.subdomains
    content {
      hosts        = ["${host_rule.value}.${var.primary_domain}"]
      path_matcher = "${host_rule.value}-matcher"
    }
  }

  # Path matchers for each subdomain
  dynamic "path_matcher" {
    for_each = var.subdomains
    content {
      name            = "${path_matcher.value}-matcher"
      default_service = google_compute_backend_service.default.id

      path_rule {
        paths   = ["/*"]
        service = google_compute_backend_service.default.id
      }
    }
  }
}

# HTTPS proxy
resource "google_compute_target_https_proxy" "default" {
  name             = "${var.name_prefix}-https-proxy"
  url_map          = google_compute_url_map.default.id
  certificate_map  = "//certificatemanager.googleapis.com/${google_certificate_manager_certificate_map.default.id}"
}

# HTTP proxy (redirects to HTTPS)
resource "google_compute_target_http_proxy" "default" {
  name    = "${var.name_prefix}-http-proxy"
  url_map = google_compute_url_map.default.id
}

# Global forwarding rule for HTTPS
resource "google_compute_global_forwarding_rule" "https" {
  name       = "${var.name_prefix}-https-forwarding-rule"
  target     = google_compute_target_https_proxy.default.id
  port_range = "443"
  ip_address = google_compute_global_address.default.address
}

# Global forwarding rule for HTTP (redirects to HTTPS)
resource "google_compute_global_forwarding_rule" "http" {
  name       = "${var.name_prefix}-http-forwarding-rule"
  target     = google_compute_target_http_proxy.default.id
  port_range = "80"
  ip_address = google_compute_global_address.default.address
}

# DNS record for the primary domain
resource "google_dns_record_set" "default" {
  name         = "${var.primary_domain}."
  type         = "A"
  ttl          = 300
  managed_zone = var.dns_zone_name

  rrdatas = [google_compute_global_address.default.address]
}

# DNS records for subdomains
resource "google_dns_record_set" "subdomains" {
  for_each = toset(var.subdomains)
  
  name         = "${each.value}.${var.primary_domain}."
  type         = "CNAME"
  ttl          = 300
  managed_zone = var.dns_zone_name

  rrdatas = ["${var.primary_domain}."]
}
