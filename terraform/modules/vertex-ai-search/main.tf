# Vertex AI Search Module for Multi-Tenant Vector Cache

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}

# Vertex AI Search Engine for platform-wide search
resource "google_discovery_engine_search_engine" "platform_search" {
  provider = google-beta
  
  location = var.region
  project  = var.project_id
  
  engine_id = var.search_engine_name
  display_name = "${var.platform_name} Platform Search Engine"
  collection_id = var.collection_id
  
  search_engine_config {
    search_tier = var.search_tier
  }

  # Attach platform and tenant datastores to the engine
  data_store_ids = concat(
    [google_discovery_engine_data_store.platform_datastore.data_store_id],
    [for k, v in google_discovery_engine_data_store.tenant_datastore : v.data_store_id]
  )
}

# Vertex AI Search Data Store for platform documents
resource "google_discovery_engine_data_store" "platform_datastore" {
  provider = google-beta
  
  location = var.region
  project  = var.project_id
  
  data_store_id = var.datastore_name
  display_name  = "${var.platform_name} Platform Data Store"
  
  content_config = "CONTENT_REQUIRED"
  solution_types = [var.solution_type]
  industry_vertical = var.industry_vertical
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [
      document_processing_config
    ]
  }
}

# Vertex AI Search Data Store for tenant-specific documents
resource "google_discovery_engine_data_store" "tenant_datastore" {
  for_each = var.enable_tenant_datastores ? toset(var.tenant_ids) : []
  
  provider = google-beta
  
  location = var.region
  project  = var.project_id
  
  data_store_id = "${var.tenant_datastore_prefix}-${each.key}"
  display_name  = "Tenant ${each.key} Data Store"
  
  content_config = "CONTENT_REQUIRED"
  solution_types = [var.solution_type]
  industry_vertical = var.industry_vertical
  lifecycle {
    prevent_destroy = true
  }
}
