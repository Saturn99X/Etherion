# BigQuery Knowledge Base Module for Multi-Tenant Platform

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# BigQuery dataset for platform-wide knowledge base
resource "google_bigquery_dataset" "platform_kb" {
  dataset_id = var.platform_dataset_name
  location   = var.region
  project    = var.project_id
  
  description = "Platform-wide knowledge base for ${var.platform_name}"
  
  labels = merge(var.common_labels, {
    purpose = "knowledge-base"
  })

  # CMEK (optional)
  dynamic "default_encryption_configuration" {
    for_each = var.kms_key_name != "" ? [1] : []
    content {
      kms_key_name = var.kms_key_name
    }
  }
}

# BigQuery table for knowledge base documents
resource "google_bigquery_table" "documents" {
  dataset_id = google_bigquery_dataset.platform_kb.dataset_id
  table_id   = "documents"
  project    = var.project_id
  
  description = "Knowledge base documents with vector embeddings"
  
  schema = jsonencode([
    {
      name = "doc_id"
      type = "STRING"
      mode = "REQUIRED"
      description = "Unique document identifier (UUID v4)"
    },
    {
      name = "tenant_id"
      type = "STRING"
      mode = "REQUIRED"
      description = "Tenant identifier for multi-tenant isolation"
    },
    {
      name = "project_id"
      type = "STRING"
      mode = "NULLABLE"
      description = "Optional project sub-scope"
    },
    {
      name = "chunk_hash"
      type = "STRING"
      mode = "REQUIRED"
      description = "SHA-256 hash of text chunk for deduplication"
    },
    {
      name = "text_chunk"
      type = "STRING"
      mode = "REQUIRED"
      description = "Text content (max 10,000 characters)"
    },
    {
      name = "vector_embedding"
      type = "FLOAT"
      mode = "REPEATED"
      description = "768-dimensional vector embedding"
    },
    {
      name = "metadata"
      type = "JSON"
      mode = "NULLABLE"
      description = "Structured metadata (doc_type, lang, acl_tag, etc.)"
    },
    {
      name = "file_uri"
      type = "STRING"
      mode = "NULLABLE"
      description = "GCS URI or Drive file ID"
    },
    {
      name = "created_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
      description = "Creation timestamp"
    },
    {
      name = "updated_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
      description = "Last update timestamp"
    }
  ])
  
  # Partitioning by date for cost optimization
  dynamic "time_partitioning" {
    for_each = var.enable_partitioning ? [1] : []
    content {
      type  = "DAY"
      field = "created_at"
    }
  }
  
  # Clustering for performance
  clustering = var.enable_clustering ? ["tenant_id", "project_id"] : []

  # Row-level security for tenant isolation
  deletion_protection = true

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      schema,
      time_partitioning,
      clustering,
      encryption_configuration,
      labels,
      resource_tags,
      require_partition_filter,
      deletion_protection,
    ]
  }
}

# Shared analytics view over platform documents (RLS enforced at table)
resource "google_bigquery_table" "analytics_documents_shared" {
  dataset_id = google_bigquery_dataset.platform_kb.dataset_id
  table_id   = "analytics_documents_shared"
  project    = var.project_id

  view {
    query = <<-SQL
      SELECT doc_id, tenant_id, project_id, chunk_hash, text_chunk, metadata, created_at
      FROM `${var.project_id}.${google_bigquery_dataset.platform_kb.dataset_id}.${google_bigquery_table.documents.table_id}`
    SQL
    use_legacy_sql = false
  }

  deletion_protection = false
}

# BigQuery table for AI-generated assets
resource "google_bigquery_table" "ai_assets" {
  dataset_id = google_bigquery_dataset.platform_kb.dataset_id
  table_id   = "ai_assets"
  project    = var.project_id
  
  description = "AI-generated assets with provenance metadata"
  
  schema = jsonencode([
    {
      name = "asset_id"
      type = "STRING"
      mode = "REQUIRED"
      description = "Unique asset identifier"
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
      description = "Job that created this asset"
    },
    {
      name = "agent_name"
      type = "STRING"
      mode = "REQUIRED"
      description = "Agent that generated the asset"
    },
    {
      name = "mime_type"
      type = "STRING"
      mode = "REQUIRED"
      description = "MIME type of the asset"
    },
    {
      name = "gcs_uri"
      type = "STRING"
      mode = "REQUIRED"
      description = "GCS URI for the asset"
    },
    {
      name = "size_bytes"
      type = "INTEGER"
      mode = "REQUIRED"
      description = "Asset size in bytes"
    },
    {
      name = "text_extract"
      type = "STRING"
      mode = "NULLABLE"
      description = "Extracted text content"
    },
    {
      name = "vector_embedding"
      type = "FLOAT"
      mode = "REPEATED"
      description = "Vector embedding for search"
    },
    {
      name = "origin"
      type = "STRING"
      mode = "REQUIRED"
      description = "Origin type (ai, human)"
    },
    {
      name = "created_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
      description = "Creation timestamp"
    }
  ])
  
  # Partitioning by date
  dynamic "time_partitioning" {
    for_each = var.enable_partitioning ? [1] : []
    content {
      type  = "DAY"
      field = "created_at"
    }
  }
  
  # Clustering for performance
  clustering = var.enable_clustering ? ["tenant_id", "job_id"] : []

  deletion_protection = true

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      schema,
      time_partitioning,
      clustering,
      encryption_configuration,
      labels,
      resource_tags,
      require_partition_filter,
      deletion_protection,
    ]
  }
}

# BigQuery table for execution costs
resource "google_bigquery_table" "execution_costs" {
  dataset_id = google_bigquery_dataset.platform_kb.dataset_id
  table_id   = "execution_costs"
  project    = var.project_id
  
  description = "Real-time cost tracking for all operations"
  
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
  
  # Partitioning by date
  dynamic "time_partitioning" {
    for_each = var.enable_partitioning ? [1] : []
    content {
      type  = "DAY"
      field = "created_at"
    }
  }
  
  # Clustering for performance
  clustering = var.enable_clustering ? ["tenant_id", "job_id"] : null

  deletion_protection = true

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      schema,
      time_partitioning,
      clustering,
      encryption_configuration,
      labels,
      resource_tags,
      require_partition_filter,
      deletion_protection,
    ]
  }
}

# BigQuery dataset for tenant-specific knowledge bases
resource "google_bigquery_dataset" "tenant_kb" {
  for_each = var.enable_tenant_datasets ? toset(var.tenant_ids) : []
  
  dataset_id = replace(var.tenant_dataset_prefix, "{tenant_id}", each.key)
  location   = var.region
  project    = var.project_id
  
  description = "Knowledge base for tenant ${each.key}"
  
  labels = merge(var.common_labels, {
    purpose   = "tenant-knowledge-base"
    tenant_id = each.key
  })
  
  # CMEK (optional)
  dynamic "default_encryption_configuration" {
    for_each = var.kms_key_name != "" ? [1] : []
    content {
      kms_key_name = var.kms_key_name
    }
  }
  
  # Access control for tenant isolation
  access {
    role   = "OWNER"
    user_by_email = var.dataset_owner_email
  }
  # Ensure project-level principals can manage tables
  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }
  access {
    role          = "WRITER"
    special_group = "projectWriters"
  }
  access {
    role          = "READER"
    special_group = "projectReaders"
  }
}

# Grant per-tenant SA write access on tenant datasets
resource "google_bigquery_dataset_iam_member" "tenant_dataset_writer" {
  for_each  = var.enable_tenant_datasets ? toset(var.tenant_ids) : []

  dataset_id = google_bigquery_dataset.tenant_kb[each.key].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:sa-tenant-${each.key}@${var.project_id}.iam.gserviceaccount.com"
}

# Grant API service account write access on tenant datasets (required for ingestion and queries)
resource "google_bigquery_dataset_iam_member" "api_dataset_writer" {
  for_each  = var.enable_tenant_datasets ? toset(var.tenant_ids) : []

  dataset_id = google_bigquery_dataset.tenant_kb[each.key].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${coalesce(var.api_service_account_email, var.dataset_owner_email)}"
}

# Grant Worker service account write access on tenant datasets (required for Celery ingestion)
resource "google_bigquery_dataset_iam_member" "worker_dataset_writer" {
  # Note: for_each must depend only on values known at plan time. We rely on
  # enable_tenant_datasets + tenant_ids here; worker_service_account_email is
  # allowed to be an apply-time value and is used only in the member binding.
  for_each  = var.enable_tenant_datasets ? toset(var.tenant_ids) : []

  dataset_id = google_bigquery_dataset.tenant_kb[each.key].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.worker_service_account_email}"
}

# Grant per-tenant SA write access on tenant staging datasets
resource "google_bigquery_dataset_iam_member" "tenant_staging_writer" {
  for_each  = var.enable_staging_datasets && var.enable_tenant_datasets ? toset(var.tenant_ids) : []

  dataset_id = google_bigquery_dataset.tenant_kb_staging[each.key].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:sa-tenant-${each.key}@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_bigquery_dataset_iam_member" "api_staging_writer" {
  for_each  = (var.enable_staging_datasets && var.enable_tenant_datasets) ? toset(var.tenant_ids) : []

  dataset_id = google_bigquery_dataset.tenant_kb_staging[each.key].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${coalesce(var.api_service_account_email, var.dataset_owner_email)}"
}

resource "google_bigquery_dataset_iam_member" "worker_staging_writer" {
  for_each  = (var.enable_staging_datasets && var.enable_tenant_datasets) ? toset(var.tenant_ids) : []

  dataset_id = google_bigquery_dataset.tenant_kb_staging[each.key].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.worker_service_account_email}"
}

# Create/refresh Row Access Policies per tenant on platform documents
resource "null_resource" "rls_policy_tenant" {
  for_each = var.tenant_row_access_members

  triggers = {
    tenant_id  = each.key
    grantees   = join(",", each.value)
    dataset_id = google_bigquery_dataset.platform_kb.dataset_id
    table_id   = google_bigquery_table.documents.table_id
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-lc"]
    command     = <<-EOT
      bq query --use_legacy_sql=false <<'SQL'
      CREATE OR REPLACE ROW ACCESS POLICY rlp_tenant_${each.key}
      ON `${var.project_id}.${google_bigquery_dataset.platform_kb.dataset_id}.${google_bigquery_table.documents.table_id}`
      GRANT TO (${join(", ", [for m in each.value : format("\"%s\"", m)])})
      FILTER USING (tenant_id = '${each.key}');
      SQL
    EOT
  }

  depends_on = [google_bigquery_table.documents]
}

# BigQuery dataset for tenant staging (connector landings)
resource "google_bigquery_dataset" "tenant_kb_staging" {
  for_each = var.enable_staging_datasets && var.enable_tenant_datasets ? toset(var.tenant_ids) : []

  dataset_id = "${replace(var.tenant_dataset_prefix, "{tenant_id}", each.key)}${var.staging_suffix}"
  location   = var.region
  project    = var.project_id

  description = "Staging dataset for tenant ${each.key} (connector landings)"

  labels = merge(var.common_labels, {
    purpose   = "tenant-staging"
    tenant_id = each.key
  })

  # TTL for staging tables (cleanup)
  default_table_expiration_ms = var.staging_default_table_ttl_days * 24 * 60 * 60 * 1000

  # CMEK (optional)
  dynamic "default_encryption_configuration" {
    for_each = var.kms_key_name != "" ? [1] : []
    content {
      kms_key_name = var.kms_key_name
    }
  }

  # Access similar to tenant dataset (owners/writers/readers + API owner)
  access {
    role         = "OWNER"
    user_by_email = var.dataset_owner_email
  }
  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }
  access {
    role          = "WRITER"
    special_group = "projectWriters"
  }
  access {
    role          = "READER"
    special_group = "projectReaders"
  }
}

# BigQuery table for tenant documents
resource "google_bigquery_table" "tenant_documents" {
  for_each = var.enable_tenant_datasets ? toset(var.tenant_ids) : []
  
  dataset_id = google_bigquery_dataset.tenant_kb[each.key].dataset_id
  table_id   = "documents"
  project    = var.project_id
  
  description = "Documents for tenant ${each.key}"
  
  schema = jsonencode([
    {
      name = "doc_id"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "text_chunk"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "vector_embedding"
      type = "FLOAT"
      mode = "REPEATED"
    },
    {
      name = "metadata"
      type = "JSON"
      mode = "NULLABLE"
    },
    {
      name = "created_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    }
  ])
  
  dynamic "time_partitioning" {
    for_each = var.enable_partitioning ? [1] : []
    content {
      type  = "DAY"
      field = "created_at"
    }
  }
  
  clustering = var.enable_clustering ? ["doc_id"] : []
  
  deletion_protection = true
}

# Optional bootstrap: create VECTOR INDEXes for documents tables
# Note: local-exec runs bq CLI; prefer running in CI with ADC or via a Cloud Run Job in env root.
resource "null_resource" "create_vector_index_platform" {
  count = var.create_vector_indexes ? 1 : 0

  triggers = {
    platform_dataset = google_bigquery_dataset.platform_kb.dataset_id
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-lc"]
    command     = <<-EOT
      bq query --use_legacy_sql=false "CREATE VECTOR INDEX IF NOT EXISTS idx_docs_vec ON `"${var.project_id}.${google_bigquery_dataset.platform_kb.dataset_id}.documents"`(vector_embedding) OPTIONS(distance_type='COSINE')"
    EOT
  }
}

resource "null_resource" "create_vector_index_tenant" {
  for_each = var.create_vector_indexes && var.enable_tenant_datasets ? google_bigquery_dataset.tenant_kb : {}

  triggers = {
    tenant_dataset = each.value.dataset_id
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-lc"]
    command     = <<-EOT
      bq query --use_legacy_sql=false "CREATE VECTOR INDEX IF NOT EXISTS idx_docs_vec ON `"${var.project_id}.${each.value.dataset_id}.documents"`(vector_embedding) OPTIONS(distance_type='COSINE')"
    EOT
  }
}
