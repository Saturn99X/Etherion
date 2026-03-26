output "search_engine_id" {
  description = "Platform search engine ID"
  value       = google_discovery_engine_search_engine.platform_search.engine_id
}

output "platform_datastore_id" {
  description = "Platform datastore ID"
  value       = google_discovery_engine_data_store.platform_datastore.data_store_id
}

output "tenant_datastores" {
  description = "Tenant-specific datastore IDs"
  value       = { for k, v in google_discovery_engine_data_store.tenant_datastore : k => v.data_store_id }
}

