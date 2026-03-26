# Cloud Armor Security Policy for Etherion Platform (prod)

resource "google_compute_security_policy" "platform_security_policy" {
  count       = var.enable_security_policy ? 1 : 0
  name        = "${local.platform_name}-security-policy"
  description = "Minimal Cloud Armor policy to avoid advanced rules quota"

  # Default allow (keep last priority)
  rule {
    priority    = 2147483647
    description = "Default allow"
    action      = "allow"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}
