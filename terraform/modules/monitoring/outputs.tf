output "dashboard_id" {
  description = "Monitoring dashboard ID"
  value       = length(google_monitoring_dashboard.etherion_dashboard) > 0 ? google_monitoring_dashboard.etherion_dashboard[0].id : null
}

output "high_error_rate_policy_id" {
  description = "High error rate alert policy ID"
  value       = length(google_monitoring_alert_policy.high_error_rate) > 0 ? google_monitoring_alert_policy.high_error_rate[0].id : null
}

output "high_response_time_policy_id" {
  description = "High response time alert policy ID"
  value       = google_monitoring_alert_policy.high_response_time.id
}

output "cost_threshold_policy_id" {
  description = "Cost threshold alert policy ID"
  value       = length(google_monitoring_alert_policy.cost_threshold) > 0 ? google_monitoring_alert_policy.cost_threshold[0].id : null
}

output "low_credit_balance_policy_id" {
  description = "Low credit balance alert policy ID"
  value       = length(google_monitoring_alert_policy.low_credit_balance) > 0 ? google_monitoring_alert_policy.low_credit_balance[0].id : null
}

output "api_uptime_check_id" {
  description = "API uptime check ID"
  value       = length(google_monitoring_uptime_check_config.api_uptime) > 0 ? google_monitoring_uptime_check_config.api_uptime[0].id : null
}

output "worker_uptime_check_id" {
  description = "Worker uptime check ID"
  value       = length(google_monitoring_uptime_check_config.worker_uptime) > 0 ? google_monitoring_uptime_check_config.worker_uptime[0].id : null
}

output "application_logs_sink_id" {
  description = "Application logs sink ID"
  value       = google_logging_project_sink.application_logs.id
}

output "cost_tracking_logs_sink_id" {
  description = "Cost tracking logs sink ID"
  value       = google_logging_project_sink.cost_tracking_logs.id
}

output "security_logs_sink_id" {
  description = "Security logs sink ID"
  value       = google_logging_project_sink.security_logs.id
}
