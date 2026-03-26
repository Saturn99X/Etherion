# Multi-Tenant Load Balancer Module with Custom Subdomains

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

# Kill switch removed - Cloud Armor not used (Cloudflare handles security)

# Reserve global static IP address
resource "google_compute_global_address" "default" {
  name = "${var.lb_name}-global-ip"
}

# Generate self-signed certificate for internal encryption (Cloudflare -> GCP)
# This allows Cloudflare "Full" SSL mode
resource "tls_private_key" "default" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_self_signed_cert" "default" {
  private_key_pem = tls_private_key.default.private_key_pem

  subject {
    common_name  = "*.${var.primary_domain}"
    organization = "Etherion AI Platform"
  }

  validity_period_hours = 87600 # 10 years

  allowed_uses = [
    "key_encipherment",
    "digital_signature",
    "server_auth",
  ]
}

resource "google_compute_ssl_certificate" "default" {
  name_prefix = "${var.lb_name}-self-signed-"
  private_key = tls_private_key.default.private_key_pem
  certificate = tls_self_signed_cert.default.cert_pem

  lifecycle {
    create_before_destroy = true
  }
}

# Create backend service for API
resource "google_compute_backend_service" "api" {
  name                  = "${var.project_id}-api-backend"
  protocol              = "HTTP"
  port_name             = "http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  timeout_sec           = 30

  backend {
    group = google_compute_region_network_endpoint_group.api_neg.id
  }

  # No health checks for serverless NEGs

  # Disable CDN for dynamic API traffic
  enable_cdn = false

  # No Cloud Armor - Cloudflare handles DDoS protection

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# Create backend service for Worker (internal only)
resource "google_compute_backend_service" "worker" {
  name                  = "${var.project_id}-worker-backend"
  protocol              = "HTTP"
  port_name             = "http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  timeout_sec           = 30

  backend {
    group = google_compute_region_network_endpoint_group.worker_neg.id
  }

  # No health checks for serverless NEGs

  # No CDN for worker service
  enable_cdn = false

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# Network Endpoint Group for API
resource "google_compute_region_network_endpoint_group" "api_neg" {
  name                  = "${var.project_id}-api-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = var.api_service_name
  }
}

# Network Endpoint Group for Worker
resource "google_compute_region_network_endpoint_group" "worker_neg" {
  name                  = "${var.project_id}-worker-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = var.worker_service_name
  }
}

# Network Endpoint Group for Frontend
resource "google_compute_region_network_endpoint_group" "frontend_neg" {
  name                  = "${var.project_id}-frontend-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = var.frontend_service_name
  }
}

# Health check for API
resource "google_compute_health_check" "api" {
  name               = "${var.project_id}-api-health-check"
  check_interval_sec = 10
  timeout_sec        = 5
  healthy_threshold  = 2
  unhealthy_threshold = 3

  http_health_check {
    port         = 8000
    request_path = "/health"
  }
}

# Health check for Worker
resource "google_compute_health_check" "worker" {
  name               = "${var.project_id}-worker-health-check"
  check_interval_sec = 10
  timeout_sec        = 5
  healthy_threshold  = 2
  unhealthy_threshold = 3

  http_health_check {
    port         = 8000
    request_path = "/health"
  }
}

# Backend service for Frontend
resource "google_compute_backend_service" "frontend" {
  name                  = "${var.project_id}-frontend-backend"
  protocol              = "HTTP"
  port_name             = "http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  timeout_sec           = 30

  backend {
    group = google_compute_region_network_endpoint_group.frontend_neg.id
  }

  # No health checks for serverless NEGs

  # Enable CDN for static content
  enable_cdn = true
  cdn_policy {
    cache_mode                   = "CACHE_ALL_STATIC"
    default_ttl                  = 3600
    client_ttl                   = 3600
    max_ttl                      = 86400
    negative_caching             = true
    serve_while_stale            = 86400
    signed_url_cache_max_age_sec = 0
    
    cache_key_policy {
      include_host         = true
      include_protocol     = true
      include_query_string = false
    }
  }

  # No Cloud Armor - Cloudflare handles DDoS protection

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# Health check for Frontend
resource "google_compute_health_check" "frontend" {
  name               = "${var.project_id}-frontend-health-check"
  check_interval_sec = 10
  timeout_sec        = 5
  healthy_threshold  = 2
  unhealthy_threshold = 3

  http_health_check {
    port         = 3000
    request_path = "/"
  }
}

# Cloud Armor removed - quota is 0 in project
# Cloudflare handles DDoS protection, rate limiting, and WAF

# URL map for routing
resource "google_compute_url_map" "default" {
  name            = "${var.project_id}-url-map"
  default_service = google_compute_backend_service.frontend.id  # Default to frontend for wildcard

  # Host rule for API subdomain
  host_rule {
    hosts        = ["api.${var.primary_domain}"]
    path_matcher = "api-matcher"
  }

  # Host rule for Auth subdomain (routes to API)
  host_rule {
    hosts        = ["auth.${var.primary_domain}"]
    path_matcher = "auth-matcher"
  }

  # Host rule for MCP subdomain (routes to API)
  host_rule {
    hosts        = ["mcp.${var.primary_domain}"]
    path_matcher = "mcp-matcher"
  }

  # Host rule for App subdomain (routes to Frontend)
  host_rule {
    hosts        = ["app.${var.primary_domain}"]
    path_matcher = "app-matcher"
  }

  # Host rule for wildcard tenant subdomains (routes to Frontend)
  host_rule {
    hosts        = ["*.${var.primary_domain}"]
    path_matcher = "wildcard-matcher"
  }

  # Path matcher for API
  path_matcher {
    name            = "api-matcher"
    default_service = google_compute_backend_service.api.id
  }

  # Path matcher for Auth (API backend)
  path_matcher {
    name            = "auth-matcher"
    default_service = google_compute_backend_service.api.id
  }

  # Path matcher for MCP (API backend)
  path_matcher {
    name            = "mcp-matcher"
    default_service = google_compute_backend_service.api.id
  }

  # Path matcher for App (Frontend backend)
  path_matcher {
    name            = "app-matcher"
    default_service = google_compute_backend_service.frontend.id
  }

  # Path matcher for wildcard (Frontend backend)
  path_matcher {
    name            = "wildcard-matcher"
    default_service = google_compute_backend_service.frontend.id
  }
}

# HTTP-only proxy (Cloudflare handles HTTPS)
# Cloudflare forwards traffic to this HTTP endpoint

# HTTP proxy (redirects to HTTPS)
resource "google_compute_target_http_proxy" "default" {
  name    = "${var.project_id}-http-proxy"
  url_map = google_compute_url_map.default.id
}

# HTTPS Proxy (uses self-signed cert)
resource "google_compute_target_https_proxy" "default" {
  name             = "${var.project_id}-https-proxy"
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_ssl_certificate.default.id]
}

# Global forwarding rule for HTTPS (Port 443)
resource "google_compute_global_forwarding_rule" "https" {
  name       = "${var.project_id}-https-forwarding-rule"
  target     = google_compute_target_https_proxy.default.id
  port_range = "443"
  ip_address = google_compute_global_address.default.address
}

# Global forwarding rule for HTTP (redirects to HTTPS)
resource "google_compute_global_forwarding_rule" "http" {
  name       = "${var.project_id}-http-forwarding-rule"
  target     = google_compute_target_http_proxy.default.id
  port_range = "80"
  ip_address = google_compute_global_address.default.address
}

# NOTE: DNS records are managed in Cloudflare, not Google Cloud DNS
# After deployment, update Cloudflare with:
#   - api.etherionai.com → A → ${google_compute_global_address.default.address}
#   - app.etherionai.com → A → ${google_compute_global_address.default.address}
#   - auth.etherionai.com → A → ${google_compute_global_address.default.address} 
#   - mcp.etherionai.com → A → ${google_compute_global_address.default.address}
#   - *.etherionai.com → A → ${google_compute_global_address.default.address}

