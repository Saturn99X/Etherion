# Monitoring Module for Multi-Tenant Platform

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

locals {
  service_filter = "(resource.labels.service_name=\"etherion-api\" OR resource.labels.service_name=\"etherion-worker\")"
}

# Log-based metric: Stripe webhook failures
resource "google_logging_metric" "stripe_webhook_errors" {
  name        = "stripe_webhook_errors"
  description = "Counts Stripe webhook handler errors"
  filter      = <<EOF
resource.type="cloud_run_revision"
(httpRequest.requestUrl=~"/api/stripe/webhook" OR jsonPayload.webhook="stripe")
severity>=ERROR
EOF
}

resource "google_monitoring_alert_policy" "stripe_webhook_failure" {
  count       = 0
  display_name = "Stripe Webhook Failures"
  combiner     = "OR"

  conditions {
    display_name = "Stripe webhook error count > 0"
    condition_threshold {
      filter          = "resource.type=\"global\" AND metric.type=\"logging.googleapis.com/user/stripe_webhook_errors\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = var.notification_channels
  alert_strategy { auto_close = var.alert_auto_close_duration }
}

# Log-based metric: Redis connection errors
resource "google_logging_metric" "redis_connection_errors" {
  name        = "redis_connection_errors"
  description = "Counts Redis connection issues in services"
  filter      = <<EOF
resource.type="cloud_run_revision"
(textPayload:("Redis" AND ("ECONNREFUSED" OR "timeout" OR "Connection refused")) OR jsonPayload.redis_error=true)
EOF
}

resource "google_monitoring_alert_policy" "redis_connection_issue" {
  count       = 0
  display_name = "Redis Connection Issues"
  combiner     = "OR"

  conditions {
    display_name = "Redis errors > 0"
    condition_threshold {
      filter          = "resource.type=\"global\" AND metric.type=\"logging.googleapis.com/user/redis_connection_errors\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = var.notification_channels
  alert_strategy { auto_close = var.alert_auto_close_duration }
}

# Logging sink for application logs
resource "google_logging_project_sink" "application_logs" {
  name        = "etherion-application-logs"
  destination = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${var.logging_dataset_id}"
  
  filter = <<EOF
resource.type="cloud_run_revision"
(${local.service_filter})
severity>=INFO
EOF
  
  unique_writer_identity = true
}

# Logging sink for cost tracking logs
resource "google_logging_project_sink" "cost_tracking_logs" {
  name        = "etherion-cost-tracking-logs"
  destination = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${var.logging_dataset_id}"
  
  filter = <<EOF
resource.type="cloud_run_revision"
(${local.service_filter})
jsonPayload.cost_tracking=true
EOF
  
  unique_writer_identity = true
}

# Logging sink for security logs
resource "google_logging_project_sink" "security_logs" {
  name        = "etherion-security-logs"
  destination = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${var.logging_dataset_id}"
  
  filter = <<EOF
resource.type="cloud_run_revision"
(${local.service_filter})
jsonPayload.security_event=true
EOF
  
  unique_writer_identity = true
}

# Monitoring dashboard
resource "google_monitoring_dashboard" "etherion_dashboard" {
  count = 0
  dashboard_json = jsonencode({
    displayName = "Etherion Platform Dashboard"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          width  = 6
          height = 4
          widget = {
            title = "API Request Rate"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloud_run_revision\" AND ${local.service_filter}"
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["resource.labels.service_name"]
                      }
                    }
                  }
                  plotType = "LINE"
                }
              ]
            }
          }
        },
        {
          width  = 6
          height = 4
          widget = {
            title = "Error Rate"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloud_run_revision\" AND ${local.service_filter} AND severity>=ERROR"
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["resource.labels.service_name"]
                      }
                    }
                  }
                  plotType = "LINE"
                }
              ]
            }
          }
        },
        {
          width  = 6
          height = 4
          widget = {
            title = "Response Time"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloud_run_revision\" AND ${local.service_filter}"
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_MEAN"
                        crossSeriesReducer = "REDUCE_MEAN"
                        groupByFields      = ["resource.labels.service_name"]
                      }
                    }
                  }
                  plotType = "LINE"
                }
              ]
            }
          }
        },
        {
          width  = 6
          height = 4
          widget = {
            title = "Cost Tracking"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloud_run_revision\" AND ${local.service_filter} AND jsonPayload.cost_tracking=true"
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_SUM"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["jsonPayload.tenant_id"]
                      }
                    }
                  }
                  plotType = "LINE"
                }
              ]
            }
          }
        }
        ,
        {
          width  = 6
          height = 4
          widget = {
            title = "Latency Percentiles (p50/p95/p99)"
            xyChart = {
              dataSets = [
                {
                  plotType = "LINE"
                  legendTemplate = "p50"
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"run.googleapis.com/request_latencies\" AND resource.type=\"cloud_run_revision\" AND ${local.service_filter}"
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_50"
                        crossSeriesReducer = "REDUCE_MEAN"
                        groupByFields      = ["resource.labels.service_name"]
                      }
                    }
                  }
                },
                {
                  plotType = "LINE"
                  legendTemplate = "p95"
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"run.googleapis.com/request_latencies\" AND resource.type=\"cloud_run_revision\" AND ${local.service_filter}"
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_95"
                        crossSeriesReducer = "REDUCE_MEAN"
                        groupByFields      = ["resource.labels.service_name"]
                      }
                    }
                  }
                },
                {
                  plotType = "LINE"
                  legendTemplate = "p99"
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"run.googleapis.com/request_latencies\" AND resource.type=\"cloud_run_revision\" AND ${local.service_filter}"
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_99"
                        crossSeriesReducer = "REDUCE_MEAN"
                        groupByFields      = ["resource.labels.service_name"]
                      }
                    }
                  }
                }
              ]
            }
          }
        }
      ]
    }
  })
}

# Alerting policy for high error rate
resource "google_monitoring_alert_policy" "high_error_rate" {
  count       = 0
  display_name = "High Error Rate"
  combiner    = "OR"
  
  conditions {
    display_name = "Error rate > 5%"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND ${local.service_filter}"
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.error_rate_threshold
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields    = ["resource.labels.service_name"]
      }
    }
  }
  
  notification_channels = var.notification_channels
  
  alert_strategy {
    auto_close = var.alert_auto_close_duration
  }
}

# Alerting policy for high response time
resource "google_monitoring_alert_policy" "high_response_time" {
  display_name = "High Response Time"
  combiner    = "OR"
  
  conditions {
    display_name = "Response time > 5s"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_latencies\" AND resource.type=\"cloud_run_revision\" AND ${local.service_filter}"
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.response_time_threshold
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MEAN"
        group_by_fields    = ["resource.labels.service_name"]
      }
    }
  }
  
  notification_channels = var.notification_channels
  
  alert_strategy {
    auto_close = var.alert_auto_close_duration
  }
}

# Alerting policy for cost threshold
resource "google_monitoring_alert_policy" "cost_threshold" {
  count       = 0
  display_name = "Cost Threshold Exceeded"
  combiner    = "OR"
  
  conditions {
    display_name = "Cost > $100/hour"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND ${local.service_filter} AND jsonPayload.cost_tracking=true"
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.cost_threshold_usd
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields    = ["jsonPayload.tenant_id"]
      }
    }
  }
  
  notification_channels = var.notification_channels
  
  alert_strategy {
    auto_close = var.alert_auto_close_duration
  }
}

# Alerting policy for low credit balance
resource "google_monitoring_alert_policy" "low_credit_balance" {
  count       = 0
  display_name = "Low Credit Balance"
  combiner    = "OR"
  
  conditions {
    display_name = "Credit balance < $10"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND ${local.service_filter} AND jsonPayload.credit_balance<${var.credit_low_threshold}"
      duration        = "60s"
      comparison      = "COMPARISON_LT"
      threshold_value = var.credit_low_threshold
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
        group_by_fields    = ["jsonPayload.tenant_id"]
      }
    }
  }
  
  notification_channels = var.notification_channels
  
  alert_strategy {
    auto_close = var.alert_auto_close_duration
  }
}

# Alerting policy for Too Many Requests (429)
resource "google_monitoring_alert_policy" "too_many_requests_429" {
  display_name = "Too Many Requests (429) Rate"
  combiner    = "OR"

  conditions {
    display_name = "429 per-minute > threshold"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND ${local.service_filter} AND metric.labels.response_code=\"429\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.too_many_requests_per_minute_threshold

      aggregations {
        alignment_period    = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }
    }
  }

  notification_channels = var.notification_channels

  alert_strategy {
    auto_close = var.alert_auto_close_duration
  }
}

# Uptime check for API
resource "google_monitoring_uptime_check_config" "api_uptime" {
  count        = 0
  display_name = "API Uptime Check"
  timeout      = "10s"
  period       = "60s"
  
  http_check {
    path         = "/health"
    port         = "443"
    use_ssl      = true
    request_method = "GET"
  }
  
  monitored_resource {
    type = "uptime_url"
    labels = {
      host = "example.com"
    }
  }
  
  content_matchers {
    content = "OK"
    matcher = "CONTAINS_STRING"
  }
}

# Configure default logging bucket retention
resource "google_logging_project_bucket_config" "default_bucket" {
  project        = var.project_id
  location       = "global"
  bucket_id      = "_Default"
  retention_days = var.logs_retention_days
}

# High request rate alert (proxy for CPU saturation)
resource "google_monitoring_alert_policy" "high_request_rate" {
  count        = var.enable_service_load_alerts ? 1 : 0
  display_name = "High Request Rate"
  combiner     = "OR"

  conditions {
    display_name = "Requests per second > threshold"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND ${local.service_filter}"
      duration        = "120s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.high_request_rate_per_second_threshold
      aggregations {
        alignment_period    = "60s"
        per_series_aligner  = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }
    }
  }

  notification_channels = var.notification_channels
  alert_strategy { auto_close = var.alert_auto_close_duration }
}

# High concurrency alert (proxy for memory saturation)
resource "google_monitoring_alert_policy" "high_concurrency" {
  count        = 0
  display_name = "High Concurrent Requests"
  combiner     = "OR"

  conditions {
    display_name = "Concurrent requests > threshold"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/concurrent_requests\" AND resource.type=\"cloud_run_revision\" AND ${local.service_filter}"
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.high_concurrency_threshold
      aggregations {
        alignment_period    = "60s"
        per_series_aligner  = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }
    }
  }

  notification_channels = var.notification_channels
  alert_strategy { auto_close = var.alert_auto_close_duration }
}

# Uptime check for Worker
resource "google_monitoring_uptime_check_config" "worker_uptime" {
  count        = 0
  display_name = "Worker Uptime Check"
  timeout      = "10s"
  period       = "60s"
  
  http_check {
    path         = "/health"
    port         = "443"
    use_ssl      = true
    request_method = "GET"
  }
  
  monitored_resource {
    type = "uptime_url"
    labels = {
      host = "example.com"
    }
  }
  
  content_matchers {
    content = "OK"
    matcher = "CONTAINS_STRING"
  }
}
