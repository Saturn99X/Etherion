output "media_buckets" {
  description = "Tenant media bucket names"
  value       = { for k, v in google_storage_bucket.tenant_media : k => v.name }
}

output "assets_buckets" {
  description = "Tenant assets bucket names"
  value       = { for k, v in google_storage_bucket.tenant_assets : k => v.name }
}

output "webhook_buckets" {
  description = "Tenant webhook bucket names"
  value       = { for k, v in google_storage_bucket.tenant_webhooks : k => v.name }
}

output "signed_url_function_url" {
  description = "Cloud Function URL for signed URL generation"
  value       = var.enable_signed_url_generator ? google_cloudfunctions2_function.signed_url_generator[0].service_config[0].uri : null
}

output "signed_url_function_name" {
  description = "Cloud Function name for signed URL generation"
  value       = var.enable_signed_url_generator ? google_cloudfunctions2_function.signed_url_generator[0].name : null
}
