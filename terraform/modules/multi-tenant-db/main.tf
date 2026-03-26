# Multi-tenant database with Row-Level Security

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Cloud SQL Instance with RLS support
resource "google_sql_database_instance" "main" {
  name             = var.instance_name
  database_version = "POSTGRES_17"
  region           = var.region
  
  settings {
    tier = var.tier
    availability_type = var.availability_type
    
    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 30
        retention_unit   = "COUNT"
      }
    }
    
    ip_configuration {
      ipv4_enabled    = false
      private_network = var.vpc_id
      ssl_mode        = "ENCRYPTED_ONLY"
    }
    
    database_flags {
      name  = "log_statement"
      value = "all"
    }
    
    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"
    }
    
    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = true
    }
  }
  
  deletion_protection = var.deletion_protection
}

# Database
resource "google_sql_database" "main" {
  name     = var.database_name
  instance = google_sql_database_instance.main.name
}

# Database User
resource "google_sql_user" "main" {
  name     = var.database_user
  instance = google_sql_database_instance.main.name
  password = random_password.db_password.result
  
  lifecycle {
    # When importing an existing user, avoid forcing a password rotation
    # unless we explicitly bump password_rotation_id.
    ignore_changes = [password]
  }
}

# Generate secure password
resource "random_password" "db_password" {
  length  = 32
  special = true
  keepers = {
    rotation_id = var.password_rotation_id
  }
}

# RLS Setup (via null_resource)
resource "null_resource" "setup_rls" {
  count = var.enable_rls ? 1 : 0
  
  provisioner "local-exec" {
    command = <<-EOT
      # Wait for database to be ready
      sleep 30
      
      # Setup RLS policies
      PGPASSWORD="${random_password.db_password.result}" psql \
        -h ${google_sql_database_instance.main.private_ip_address} \
        -U ${var.database_user} \
        -d ${var.database_name} \
        -c "
        -- Enable RLS on all tenant-aware tables
        ALTER TABLE users ENABLE ROW LEVEL SECURITY;
        ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
        ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE execution_costs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ai_assets ENABLE ROW LEVEL SECURITY;
        
        -- Create tenant isolation policies
        CREATE POLICY tenant_isolation_users ON users 
          USING (tenant_id = current_setting('app.tenant_id'));
          
        CREATE POLICY tenant_isolation_tenants ON tenants 
          USING (id = current_setting('app.tenant_id'));
          
        CREATE POLICY tenant_isolation_jobs ON jobs 
          USING (tenant_id = current_setting('app.tenant_id'));
          
        CREATE POLICY tenant_isolation_costs ON execution_costs 
          USING (tenant_id = current_setting('app.tenant_id'));
          
        CREATE POLICY tenant_isolation_assets ON ai_assets 
          USING (tenant_id = current_setting('app.tenant_id'));
        "
    EOT
  }
  
  depends_on = [
    google_sql_database.main,
    google_sql_user.main
  ]
}
