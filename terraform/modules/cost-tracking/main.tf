# Cost Tracking Module for Real-Time Cost Management

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# BigQuery dataset for cost tracking
resource "google_bigquery_dataset" "cost_tracking" {
  dataset_id = "etherion_cost_tracking"
  location   = var.region
  project    = var.project_id
  
  description = "Cost tracking dataset for Etherion AI platform"
  
  labels = {
    environment = var.environment
    purpose     = "cost-tracking"
    platform    = "etherion"
  }
}

# BigQuery table for execution costs
resource "google_bigquery_table" "execution_costs" {
  dataset_id = google_bigquery_dataset.cost_tracking.dataset_id
  table_id   = "execution_costs"
  project    = var.project_id
  
  description = "Real-time execution cost tracking"
  
  schema = jsonencode([
    {
      name = "cost_id"
      type = "STRING"
      mode = "REQUIRED"
      description = "Unique cost record identifier"
    },
    {
      name = "tenant_id"
      type = "STRING"
      mode = "REQUIRED"
      description = "Tenant identifier"
    },
    {
      name = "job_id"
      type = "STRING"
      mode = "REQUIRED"
      description = "Job identifier"
    },
    {
      name = "operation_type"
      type = "STRING"
      mode = "REQUIRED"
      description = "Type of operation (llm_call, api_call, etc.)"
    },
    {
      name = "model_name"
      type = "STRING"
      mode = "NULLABLE"
      description = "AI model used"
    },
    {
      name = "input_tokens"
      type = "INTEGER"
      mode = "REQUIRED"
      description = "Number of input tokens"
    },
    {
      name = "output_tokens"
      type = "INTEGER"
      mode = "REQUIRED"
      description = "Number of output tokens"
    },
    {
      name = "cost_usd"
      type = "FLOAT"
      mode = "REQUIRED"
      description = "Cost in USD"
    },
    {
      name = "created_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
      description = "Cost record timestamp"
    }
  ])
  
  # Partitioning by date for cost optimization
  time_partitioning {
    type  = "DAY"
    field = "created_at"
  }
  
  # Clustering for performance
  clustering = ["tenant_id", "job_id"]
  
  deletion_protection = true
}

# BigQuery table for tenant credit balances
resource "google_bigquery_table" "tenant_credits" {
  dataset_id = google_bigquery_dataset.cost_tracking.dataset_id
  table_id   = "tenant_credits"
  project    = var.project_id
  
  description = "Tenant credit balance tracking"
  
  schema = jsonencode([
    {
      name = "tenant_id"
      type = "STRING"
      mode = "REQUIRED"
      description = "Tenant identifier"
    },
    {
      name = "credit_balance"
      type = "FLOAT"
      mode = "REQUIRED"
      description = "Current credit balance"
    },
    {
      name = "total_spent"
      type = "FLOAT"
      mode = "REQUIRED"
      description = "Total amount spent"
    },
    {
      name = "last_updated"
      type = "TIMESTAMP"
      mode = "REQUIRED"
      description = "Last update timestamp"
    }
  ])
  
  # Partitioning by date
  time_partitioning {
    type  = "DAY"
    field = "last_updated"
  }
  
  # Clustering for performance
  clustering = ["tenant_id"]
  
  deletion_protection = true
}

# Cloud Function for cost calculation
resource "google_cloudfunctions2_function" "cost_calculator" {
  count = var.enable_real_time_tracking ? 1 : 0
  
  name     = "cost-calculator"
  location = var.region
  project  = var.project_id
  
  build_config {
    runtime     = "python311"
    entry_point = "calculate_cost"
    
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
      DATASET_ID = google_bigquery_dataset.cost_tracking.dataset_id
      TABLE_ID   = google_bigquery_table.execution_costs.table_id
    }
    
    service_account_email = var.service_account_email
  }
  
  labels = {
    environment = var.environment
    purpose     = "cost-calculation"
    platform    = "etherion"
  }
}

# Cloud Function for credit management
resource "google_cloudfunctions2_function" "credit_manager" {
  count = var.enable_credit_management ? 1 : 0
  
  name     = "credit-manager"
  location = var.region
  project  = var.project_id
  
  build_config {
    runtime     = "python311"
    entry_point = "manage_credits"
    
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
      DATASET_ID = google_bigquery_dataset.cost_tracking.dataset_id
      CREDITS_TABLE_ID = google_bigquery_table.tenant_credits.table_id
    }
    
    service_account_email = var.service_account_email
  }
  
  labels = {
    environment = var.environment
    purpose     = "credit-management"
    platform    = "etherion"
  }
}

# Cloud Scheduler for cost aggregation
resource "google_cloud_scheduler_job" "cost_aggregation" {
  count = var.enable_cost_aggregation ? 1 : 0
  
  name     = "cost-aggregation"
  schedule = "0 */6 * * *"  # Every 6 hours
  time_zone = "UTC"
  region   = var.region
  project  = var.project_id
  
  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.cost_calculator[0].service_config[0].uri
    
    headers = {
      "Content-Type" = "application/json"
    }
    
    body = base64encode(jsonencode({
      operation = "aggregate_costs"
      tenant_id = "all"
    }))
  }
  
  # labels unsupported in scheduler job by provider; removed
}

# Cloud Scheduler for credit balance updates
resource "google_cloud_scheduler_job" "credit_balance_update" {
  count = var.enable_credit_management ? 1 : 0
  
  name     = "credit-balance-update"
  schedule = "0 */1 * * *"  # Every hour
  time_zone = "UTC"
  region   = var.region
  project  = var.project_id
  
  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.credit_manager[0].service_config[0].uri
    
    headers = {
      "Content-Type" = "application/json"
    }
    
    body = base64encode(jsonencode({
      operation = "update_balances"
    }))
  }
  
  # labels unsupported in scheduler job by provider; removed
}

# IAM binding for cost tracking functions
resource "google_cloudfunctions2_function_iam_member" "cost_calculator_invoker" {
  count = var.enable_real_time_tracking ? 1 : 0
  
  location   = google_cloudfunctions2_function.cost_calculator[0].location
  project    = google_cloudfunctions2_function.cost_calculator[0].project
  cloud_function = google_cloudfunctions2_function.cost_calculator[0].name
  role       = "roles/cloudfunctions.invoker"
  member     = "serviceAccount:${var.service_account_email}"
}

resource "google_cloudfunctions2_function_iam_member" "credit_manager_invoker" {
  count = var.enable_credit_management ? 1 : 0
  
  location   = google_cloudfunctions2_function.credit_manager[0].location
  project    = google_cloudfunctions2_function.credit_manager[0].project
  cloud_function = google_cloudfunctions2_function.credit_manager[0].name
  role       = "roles/cloudfunctions.invoker"
  member     = "serviceAccount:${var.service_account_email}"
}
