# AI Assets Repository Module for Multi-Tenant Asset Management

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# GCS bucket for AI-generated assets
resource "google_storage_bucket" "ai_assets" {
  name          = "${var.project_id}-ai-assets"
  location      = var.region
  project       = var.project_id
  storage_class = "STANDARD"
  
  # Uniform bucket-level access (no public ACLs)
  uniform_bucket_level_access = true
  
  # Lifecycle management for cost optimization
  lifecycle_rule {
    condition {
      age = var.asset_retention_days
    }
    action {
      type = "Delete"
    }
  }
  
  # Versioning for data protection
  versioning {
    enabled = true
  }
  
  # Encryption (conditional)
  dynamic "encryption" {
    for_each = var.kms_key_name != null && var.kms_key_name != "" ? [var.kms_key_name] : []
    content {
      default_kms_key_name = encryption.value
    }
  }
  
  labels = {
    environment = var.environment
    purpose     = "ai-assets"
    platform    = "etherion"
  }
  
  # Prevent accidental deletion
  force_destroy = false
}

# GCS bucket for tenant-specific AI assets
resource "google_storage_bucket" "tenant_ai_assets" {
  for_each = var.enable_tenant_buckets ? toset(var.tenant_ids) : []
  
  name          = "tnt-${each.key}-ai-assets"
  location      = var.region
  project       = var.project_id
  storage_class = "STANDARD"
  
  # Uniform bucket-level access (no public ACLs)
  uniform_bucket_level_access = true
  
  # Lifecycle management
  lifecycle_rule {
    condition {
      age = var.asset_retention_days
    }
    action {
      type = "Delete"
    }
  }
  
  # Versioning for data protection
  versioning {
    enabled = true
  }

  # Encryption (conditional)
  dynamic "encryption" {
    for_each = var.kms_key_name != null && var.kms_key_name != "" ? [var.kms_key_name] : []
    content {
      default_kms_key_name = encryption.value
    }
  }
  
  labels = {
    environment = var.environment
    purpose     = "tenant-ai-assets"
    tenant_id   = each.key
    platform    = "etherion"
  }
  
  # Prevent accidental deletion
  force_destroy = false
}

# Cloud Function for asset processing
resource "google_cloudfunctions2_function" "asset_processor" {
  count = var.enable_asset_processing ? 1 : 0
  
  name     = "asset-processor"
  location = var.region
  project  = var.project_id
  
  build_config {
    runtime     = "python311"
    entry_point = "process_asset"
    
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
    available_memory   = "1Gi"
    timeout_seconds    = 300
    
    environment_variables = {
      PROJECT_ID = var.project_id
      REGION      = var.region
      BUCKET_NAME = google_storage_bucket.ai_assets.name
    }
    
    service_account_email = var.service_account_email
  }
  
  labels = {
    environment = var.environment
    purpose     = "asset-processing"
    platform    = "etherion"
  }
}

# Cloud Function for asset search
resource "google_cloudfunctions2_function" "asset_search" {
  count = var.enable_asset_search ? 1 : 0
  
  name     = "asset-search"
  location = var.region
  project  = var.project_id
  
  build_config {
    runtime     = "python311"
    entry_point = "search_assets"
    
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
    available_memory   = "512M"
    timeout_seconds    = 60
    
    environment_variables = {
      PROJECT_ID = var.project_id
      REGION     = var.region
    }
    
    service_account_email = var.service_account_email
  }
  
  labels = {
    environment = var.environment
    purpose     = "asset-search"
    platform    = "etherion"
  }
}

# Cloud Function for asset cleanup
resource "google_cloudfunctions2_function" "asset_cleanup" {
  count = var.enable_asset_cleanup ? 1 : 0
  
  name     = "asset-cleanup"
  location = var.region
  project  = var.project_id
  
  build_config {
    runtime     = "python311"
    entry_point = "cleanup_assets"
    
    source {
      storage_source {
        bucket = var.function_source_bucket
        object = var.function_source_object
      }
    }
  }
  
  service_config {
    max_instance_count = 5
    min_instance_count = 0
    available_memory   = "256M"
    timeout_seconds    = 300
    
    environment_variables = {
      PROJECT_ID = var.project_id
      REGION     = var.region
    }
    
    service_account_email = var.service_account_email
  }
  
  # labels unsupported by provider in this resource; removed
}

# Cloud Scheduler for asset cleanup
resource "google_cloud_scheduler_job" "asset_cleanup" {
  count = var.enable_asset_cleanup ? 1 : 0
  
  name     = "asset-cleanup"
  schedule = "0 2 * * *"  # Daily at 2 AM
  time_zone = "UTC"
  region   = var.region
  project  = var.project_id
  
  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.asset_cleanup[0].service_config[0].uri
    
    headers = {
      "Content-Type" = "application/json"
    }
    
    body = base64encode(jsonencode({
      operation = "cleanup_expired_assets"
    }))
  }

}

# IAM bindings for asset processing functions
resource "google_cloudfunctions2_function_iam_member" "asset_processor_invoker" {
  count = var.enable_asset_processing ? 1 : 0
  
  location   = google_cloudfunctions2_function.asset_processor[0].location
  project    = google_cloudfunctions2_function.asset_processor[0].project
  cloud_function = google_cloudfunctions2_function.asset_processor[0].name
  role       = "roles/cloudfunctions.invoker"
  member     = "serviceAccount:${var.service_account_email}"
}

resource "google_cloudfunctions2_function_iam_member" "asset_search_invoker" {
  count = var.enable_asset_search ? 1 : 0
  
  location   = google_cloudfunctions2_function.asset_search[0].location
  project    = google_cloudfunctions2_function.asset_search[0].project
  cloud_function = google_cloudfunctions2_function.asset_search[0].name
  role       = "roles/cloudfunctions.invoker"
  member     = "serviceAccount:${var.service_account_email}"
}

resource "google_cloudfunctions2_function_iam_member" "asset_cleanup_invoker" {
  count = var.enable_asset_cleanup ? 1 : 0
  
  location   = google_cloudfunctions2_function.asset_cleanup[0].location
  project    = google_cloudfunctions2_function.asset_cleanup[0].project
  cloud_function = google_cloudfunctions2_function.asset_cleanup[0].name
  role       = "roles/cloudfunctions.invoker"
  member     = "serviceAccount:${var.service_account_email}"
}

# IAM binding for asset buckets
resource "google_storage_bucket_iam_member" "ai_assets_access" {
  bucket = google_storage_bucket.ai_assets.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_account_email}"
}

resource "google_storage_bucket_iam_member" "tenant_ai_assets_access" {
  for_each = var.enable_tenant_buckets ? toset(var.tenant_ids) : []
  
  bucket = google_storage_bucket.tenant_ai_assets[each.key].name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_account_email}"
}
