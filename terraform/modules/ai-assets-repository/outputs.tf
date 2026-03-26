output "ai_assets_bucket_name" {
  description = "AI assets bucket name"
  value       = google_storage_bucket.ai_assets.name
}

output "tenant_ai_assets_buckets" {
  description = "Tenant AI assets bucket names"
  value       = { for k, v in google_storage_bucket.tenant_ai_assets : k => v.name }
}

output "asset_processor_function_url" {
  description = "Asset processor function URL"
  value       = var.enable_asset_processing ? google_cloudfunctions2_function.asset_processor[0].service_config[0].uri : null
}

output "asset_search_function_url" {
  description = "Asset search function URL"
  value       = var.enable_asset_search ? google_cloudfunctions2_function.asset_search[0].service_config[0].uri : null
}

output "asset_cleanup_function_url" {
  description = "Asset cleanup function URL"
  value       = var.enable_asset_cleanup ? google_cloudfunctions2_function.asset_cleanup[0].service_config[0].uri : null
}

output "asset_cleanup_job_id" {
  description = "Asset cleanup job ID"
  value       = var.enable_asset_cleanup ? google_cloud_scheduler_job.asset_cleanup[0].id : null
}
