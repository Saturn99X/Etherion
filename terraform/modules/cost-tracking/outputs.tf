output "cost_tracking_dataset_id" {
  description = "Cost tracking dataset ID"
  value       = google_bigquery_dataset.cost_tracking.dataset_id
}

output "execution_costs_table_id" {
  description = "Execution costs table ID"
  value       = google_bigquery_table.execution_costs.table_id
}

output "tenant_credits_table_id" {
  description = "Tenant credits table ID"
  value       = google_bigquery_table.tenant_credits.table_id
}

output "cost_calculator_function_url" {
  description = "Cost calculator function URL"
  value       = var.enable_real_time_tracking ? google_cloudfunctions2_function.cost_calculator[0].service_config[0].uri : null
}

output "credit_manager_function_url" {
  description = "Credit manager function URL"
  value       = var.enable_credit_management ? google_cloudfunctions2_function.credit_manager[0].service_config[0].uri : null
}

output "cost_aggregation_job_id" {
  description = "Cost aggregation job ID"
  value       = var.enable_cost_aggregation ? google_cloud_scheduler_job.cost_aggregation[0].id : null
}

output "credit_balance_job_id" {
  description = "Credit balance update job ID"
  value       = var.enable_credit_management ? google_cloud_scheduler_job.credit_balance_update[0].id : null
}
