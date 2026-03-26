# Tenant Storage Module for Multi-Tenant GCS Buckets

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# GCS bucket for tenant media storage
resource "google_storage_bucket" "tenant_media" {
  for_each = var.enable_tenant_buckets ? toset(var.tenant_ids) : []
  
  name          = "${var.bucket_prefix}-${each.key}-media"
  location      = var.region
  project       = var.project_id
  storage_class = "STANDARD"
  
  # Uniform bucket-level access (no public ACLs)
  uniform_bucket_level_access = true
  
  # Lifecycle management
  lifecycle_rule {
    condition {
      age = var.media_retention_days
    }
    action {
      type = "Delete"
    }
  }
  
  # Versioning for data protection
  versioning {
    enabled = true
  }
  
  # Encryption
  encryption {
    default_kms_key_name = var.kms_key_name
  }
  
  labels = {
    environment = var.environment
    purpose     = "tenant-media"
    tenant_id   = each.key
    platform    = "etherion"
  }
  
  # Prevent accidental deletion
  force_destroy = false
}

# GCS bucket for tenant AI assets
resource "google_storage_bucket" "tenant_assets" {
  for_each = var.enable_tenant_buckets ? toset(var.tenant_ids) : []
  
  name          = "${var.bucket_prefix}-${each.key}-assets"
  location      = var.region
  project       = var.project_id
  storage_class = "STANDARD"
  
  # Uniform bucket-level access (no public ACLs)
  uniform_bucket_level_access = true
  
  # Lifecycle management for assets
  lifecycle_rule {
    condition {
      age = var.assets_retention_days
    }
    action {
      type = "Delete"
    }
  }
  
  # Versioning for data protection
  versioning {
    enabled = true
  }
  
  # Encryption
  encryption {
    default_kms_key_name = var.kms_key_name
  }
  
  labels = {
    environment = var.environment
    purpose     = "tenant-assets"
    tenant_id   = each.key
    platform    = "etherion"
  }
  
  # Prevent accidental deletion
  force_destroy = false
}

# GCS bucket for tenant webhooks
resource "google_storage_bucket" "tenant_webhooks" {
  for_each = var.enable_tenant_buckets ? toset(var.tenant_ids) : []
  
  name          = "${var.bucket_prefix}-${each.key}-webhooks"
  location      = var.region
  project       = var.project_id
  storage_class = "STANDARD"
  
  # Uniform bucket-level access (no public ACLs)
  uniform_bucket_level_access = true
  
  # Short retention for webhook data
  lifecycle_rule {
    condition {
      age = var.webhook_retention_days
    }
    action {
      type = "Delete"
    }
  }
  
  # Versioning for data protection
  versioning {
    enabled = true
  }
  
  # Encryption
  encryption {
    default_kms_key_name = var.kms_key_name
  }
  
  labels = {
    environment = var.environment
    purpose     = "tenant-webhooks"
    tenant_id   = each.key
    platform    = "etherion"
  }
  
  # Prevent accidental deletion
  force_destroy = false
}

# IAM binding for tenant service accounts
resource "google_storage_bucket_iam_member" "tenant_media_access" {
  for_each = var.enable_tenant_buckets ? toset(var.tenant_ids) : []
  
  bucket = google_storage_bucket.tenant_media[each.key].name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.tenant_service_account_email}"
}

resource "google_storage_bucket_iam_member" "tenant_assets_access" {
  for_each = var.enable_tenant_buckets ? toset(var.tenant_ids) : []
  
  bucket = google_storage_bucket.tenant_assets[each.key].name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.tenant_service_account_email}"
}

resource "google_storage_bucket_iam_member" "tenant_webhooks_access" {
  for_each = var.enable_tenant_buckets ? toset(var.tenant_ids) : []
  
  bucket = google_storage_bucket.tenant_webhooks[each.key].name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.tenant_service_account_email}"
}

# Cloud Function for signed URL generation
resource "google_cloudfunctions2_function" "signed_url_generator" {
  count = var.enable_signed_url_generator ? 1 : 0
  
  name     = "signed-url-generator"
  location = var.region
  project  = var.project_id
  
  build_config {
    runtime     = "python311"
    entry_point = "generate_signed_url"
    
    source {
      storage_source {
        bucket = var.function_source_bucket
        object = var.function_source_object
      }
    }
  }
  
  service_config {
    max_instance_count = 10
    min_instance_count = 0
    available_memory   = "256M"
    timeout_seconds    = 60
    
    environment_variables = {
      PROJECT_ID = var.project_id
      REGION     = var.region
    }
    
    service_account_email = var.tenant_service_account_email
  }
  
  labels = {
    environment = var.environment
    purpose     = "signed-url-generation"
    platform    = "etherion"
  }
}

# Cloud Function IAM binding
resource "google_cloudfunctions2_function_iam_member" "signed_url_invoker" {
  count = var.enable_signed_url_generator ? 1 : 0
  
  location   = google_cloudfunctions2_function.signed_url_generator[0].location
  project    = google_cloudfunctions2_function.signed_url_generator[0].project
  cloud_function = google_cloudfunctions2_function.signed_url_generator[0].name
  role       = "roles/cloudfunctions.invoker"
  member     = "serviceAccount:${var.tenant_service_account_email}"
}
