terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_kms_key_ring" "this" {
  name     = var.key_ring_name
  location = var.location
  project  = var.project_id
}

resource "google_kms_crypto_key" "this" {
  name            = var.crypto_key_name
  key_ring        = google_kms_key_ring.this.id
  rotation_period = "2592000s" # 30 days

  lifecycle {
    prevent_destroy = true
  }
}
