terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Media bucket: tnt-{tenant_id}-media
resource "google_storage_bucket" "media" {
  for_each                    = toset(var.tenant_ids)

  name                        = "tnt-${each.key}-media"
  project                     = var.project_id
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  labels = merge(var.common_labels, {
    tenant_id = each.key
    purpose   = "tenant-media"
  })

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  dynamic "encryption" {
    for_each = var.kms_key_name != null && var.kms_key_name != "" ? [1] : []
    content {
      default_kms_key_name = var.kms_key_name
    }
  }
}

# Assets bucket: tnt-{tenant_id}-assets
resource "google_storage_bucket" "assets" {
  for_each                    = toset(var.tenant_ids)

  name                        = "tnt-${each.key}-assets"
  project                     = var.project_id
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = var.enable_versioning_for_assets
  }

  labels = merge(var.common_labels, {
    tenant_id = each.key
    purpose   = "tenant-assets"
  })

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }

  dynamic "encryption" {
    for_each = var.kms_key_name != null && var.kms_key_name != "" ? [1] : []
    content {
      default_kms_key_name = var.kms_key_name
    }
  }
}
