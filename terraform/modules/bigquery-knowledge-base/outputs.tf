output "platform_dataset_id" {
  description = "Platform knowledge base dataset ID"
  value       = google_bigquery_dataset.platform_kb.dataset_id
}

output "documents_table_id" {
  description = "Documents table ID"
  value       = google_bigquery_table.documents.table_id
}

output "ai_assets_table_id" {
  description = "AI assets table ID"
  value       = google_bigquery_table.ai_assets.table_id
}

output "execution_costs_table_id" {
  description = "Execution costs table ID"
  value       = google_bigquery_table.execution_costs.table_id
}

output "tenant_datasets" {
  description = "Tenant-specific dataset IDs"
  value       = { for k, v in google_bigquery_dataset.tenant_kb : k => v.dataset_id }
}

output "tenant_tables" {
  description = "Tenant-specific table IDs"
  value       = { for k, v in google_bigquery_table.tenant_documents : k => v.table_id }
}

output "tenant_staging_datasets" {
  description = "Tenant-specific staging dataset IDs"
  value       = try({ for k, v in google_bigquery_dataset.tenant_kb_staging : k => v.dataset_id }, {})
}
