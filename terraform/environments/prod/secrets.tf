# Secret Manager resources managed by the prod root

locals {
  # Compose DB URLs for secrets using the managed Cloud SQL instance
  database_url       = "postgresql://${module.multi_tenant_db.database_user}:${module.multi_tenant_db.database_password}@/${module.multi_tenant_db.database_name}?host=/cloudsql/${module.multi_tenant_db.connection_name}"
  async_database_url = "postgresql+asyncpg://${module.multi_tenant_db.database_user}:${module.multi_tenant_db.database_password}@/${module.multi_tenant_db.database_name}?host=/cloudsql/${module.multi_tenant_db.connection_name}"
}

# DATABASE_URL secret
resource "google_secret_manager_secret" "database_url" {
  count     = var.manage_secrets ? 1 : 0
  project   = var.project_id
  secret_id = "etherion-database-url-prod"
  replication {
    auto {}
  }
  labels = local.common_labels
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret_version" "database_url_latest" {
  count       = var.manage_secrets ? 1 : 0
  secret      = google_secret_manager_secret.database_url[0].id
  secret_data = local.database_url
  lifecycle {
    create_before_destroy = true
    prevent_destroy       = true
  }
}

# Additional pricing- and usage-related secrets referenced by Cloud Run services
# Define containers only and disable versions to avoid writing secret data via Terraform
locals {
  additional_secret_ids = [
    "PRICE_PER_1K_INPUT_TOKENS",
    "PRICE_PER_1K_OUTPUT_TOKENS",
    "PRICE_PER_API_CALL",
    "PRICE_PER_MB_INBOUND",
    "PRICE_PER_MB_OUTBOUND",
    "PRICE_PER_MS_COMPUTE",
    "PRICING_CURRENCY",
    "VS_INDEX_FREE_GIB",
    "VS_INDEX_PRICE_PER_GIB_MONTH",
    "VS_PRICE_ADVANCED_ADDON_PER_1K_Q",
    "VS_PRICE_ENTERPRISE_PER_1K_Q",
    "VS_PRICE_STANDARD_PER_1K_Q",
    "OAUTH_STATE_SECRET",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "PRICE_ID_STARTER",
    "app-secret-key",
    "RLS_SQL_B64",
    # OAuth provider client IDs/secrets used by API
    # Generic provider IDs (legacy)
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    # Optional providers
    # Frontend public OAuth IDs (safe to expose but stored in GSM per policy)
    "NEXT_PUBLIC_GOOGLE_CLIENT_ID",
    "NEXT_PUBLIC_GITHUB_CLIENT_ID",
    # Web search provider (Exa)
    "EXA_API_KEY",
    # Pricing seed used by services
    "BQ_PRICE_SLOT_PER_HOUR",
    "BQ_PRICE_ACTIVE_STORAGE_PER_GB_MONTH",
    "BQ_PRICE_LONGTERM_STORAGE_PER_GB_MONTH",
    "BQ_PRICE_QUERY_PER_TB",
    "COM_PRICE_GPU_PER_HOUR",
    "COM_PRICE_RAM_GB_PER_HOUR",
    "COM_PRICE_VCPU_PER_HOUR",
    # DOCAI removed - no longer used
    "NET_EGRESS_PRICE_PER_GIB_US_CENTRAL1",
    
    # Gemini Pricing (Per 1M Tokens)
    "LLM_PRICE_VERTEX_GEMINI_2_5_FLASH_INPUT_PER_1M",
    "LLM_PRICE_VERTEX_GEMINI_2_5_FLASH_OUTPUT_PER_1M",
    "LLM_PRICE_VERTEX_GEMINI_2_5_PRO_INPUT_PER_1M",
    "LLM_PRICE_VERTEX_GEMINI_2_5_PRO_OUTPUT_PER_1M",
    "LLM_PRICE_VERTEX_GEMINI_3_PRO_PREVIEW_INPUT_PER_1M",
    "LLM_PRICE_VERTEX_GEMINI_3_PRO_PREVIEW_OUTPUT_PER_1M",

    # Exa Pricing & Config
    "EXA_ANSWER_PER_1K",
    "EXA_CONTENTS_HIGHLIGHTS_PER_1K_PAGES",
    "EXA_CONTENTS_SUMMARY_PER_1K_PAGES",
    "EXA_CONTENTS_TEXT_PER_1K_PAGES",
    "EXA_RESEARCH_AGENT_OPS_PER_1K",
    "EXA_RESEARCH_PAGE_READS_PRO_PER_1K",
    "EXA_RESEARCH_PAGE_READS_STANDARD_PER_1K",
    "EXA_RESEARCH_REASONING_TOKENS_PER_1M",
    "EXA_SEARCH_AUTO_FAST_1_25_PER_1K",
    "EXA_SEARCH_AUTO_FAST_26_100_PER_1K",
    "EXA_SEARCH_KEYWORD_PER_1K",
    "EXA_SEARCH_NEURAL_26_100_PER_1K",
    "EXA_SEARCH_NEURAL_PER_1K",

    # GCS Pricing
    "GCS_OPS_CLASS_A_PER_1K",
    "GCS_OPS_CLASS_B_PER_10K",
    "GCS_PRICE_ARCHIVE_PER_GB_MONTH",
    "GCS_PRICE_COLDLINE_PER_GB_MONTH",
    "GCS_PRICE_NEARLINE_PER_GB_MONTH",
    "GCS_PRICE_STANDARD_PER_GB_MONTH",

    # Integrations (HubSpot, Jira, Notion, Shopify, Slack)
    "HUBSPOT_OAUTH_CLIENT_ID",
    "HUBSPOT_OAUTH_CLIENT_SECRET",
    "JIRA_API_TOKEN",
    "JIRA_CLOUD_ID",
    "JIRA_DOMAIN",
    "JIRA_EMAIL",
    "JIRA_WEBHOOK_SECRET",
    "NOTION_OAUTH_CLIENT_ID",
    "NOTION_OAUTH_CLIENT_SECRET",
    "NOTION_WEBHOOK_SECRET",
    "SHOPIFY_OAUTH_CLIENT_ID",
    "SHOPIFY_OAUTH_CLIENT_SECRET",
    "SHOPIFY_WEBHOOK_SHARED_SECRET",
    "SLACK_BOT_TOKEN",
    "SLACK_SIGNING_SECRET",
    "SLACK_USER_OAUTH_CLIENT_ID",
    "GSM_11__SLACK__BOT_TOKEN",

    # Redis
    "ETHERION_REDIS_URL",

    # Core & Misc
    "APP_SECRET_KEY",
    "MASTER_ENCRYPTION_KEY",
    "ETHERION_ADMIN_INGEST_SECRET",
    "ETHERION_ASYNC_DATABASE_URL_PROD",
    "ETHERION_DATABASE_URL_PROD",
  ]
}

# Seed versions for NEXT_PUBLIC_* secrets only, if values are provided via variables
resource "google_secret_manager_secret_version" "next_public" {
  for_each = var.manage_secrets ? {
    for k, v in {
      NEXT_PUBLIC_GOOGLE_CLIENT_ID    = var.next_public_google_client_id
      NEXT_PUBLIC_GITHUB_CLIENT_ID    = var.next_public_github_client_id
    } : k => v if length(trimspace(v)) > 0
  } : {}

  secret      = google_secret_manager_secret.additional[each.key].id
  secret_data = each.value

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [secret_data]
  }
}

resource "google_secret_manager_secret" "additional" {
  for_each  = var.manage_secrets ? toset(local.additional_secret_ids) : toset([])
  project   = var.project_id
  secret_id = each.key
  replication {
    auto {}
  }
  labels = local.common_labels
  lifecycle {
    prevent_destroy = true
  }
}

# Seed a version for app-secret-key to ensure versions/latest exists
resource "random_password" "app_secret_key" {
  count   = var.manage_secrets && !(contains(keys(var.secret_seed_values), "app-secret-key")) ? 1 : 0
  length  = 64
  special = true
}

resource "google_secret_manager_secret_version" "app_secret_key_latest" {
  count       = var.manage_secrets && !(contains(keys(var.secret_seed_values), "app-secret-key")) ? 1 : 0
  secret      = google_secret_manager_secret.additional["app-secret-key"].id
  secret_data = random_password.app_secret_key[0].result

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [secret_data]
  }
}

# Wait briefly to allow Secret Manager replication before services reference versions/latest
resource "time_sleep" "wait_for_app_secret_version" {
  count           = var.manage_secrets && !(contains(keys(var.secret_seed_values), "app-secret-key")) ? 1 : 0
  depends_on      = [google_secret_manager_secret_version.app_secret_key_latest]
  create_duration = "30s"
}
# ASYNC_DATABASE_URL secret
resource "google_secret_manager_secret" "async_database_url" {
  count     = var.manage_secrets ? 1 : 0
  project   = var.project_id
  secret_id = "etherion-async-database-url-prod"
  replication {
    auto {}
  }
  labels = local.common_labels
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret_version" "async_database_url_latest" {
  count       = var.manage_secrets ? 1 : 0
  secret      = google_secret_manager_secret.async_database_url[0].id
  secret_data = local.async_database_url
  lifecycle {
    create_before_destroy = true
    prevent_destroy       = true
    ignore_changes        = [secret_data]
  }
}

## Generic seeding of secrets when manage_secrets=true
# Predefined secret ids from resources in this module
locals {
  predefined_secret_ids = var.manage_secrets ? merge(
    { for k, s in google_secret_manager_secret.additional : k => s.id },
    length(google_secret_manager_secret.database_url) > 0 ? { "etherion-database-url-prod" = google_secret_manager_secret.database_url[0].id } : {},
    length(google_secret_manager_secret.async_database_url) > 0 ? { "etherion-async-database-url-prod" = google_secret_manager_secret.async_database_url[0].id } : {},
    length(google_secret_manager_secret.admin_ingest_secret) > 0 ? { "etherion-admin-ingest-secret" = google_secret_manager_secret.admin_ingest_secret[0].id } : {}
  ) : {}
}

# Non-sensitive view for for_each keys only
locals {
  seed_values_nonsensitive = var.manage_secrets ? try(nonsensitive(var.secret_seed_values), {}) : {}
  seed_keys_nonempty       = var.manage_secrets ? toset([for k, v in local.seed_values_nonsensitive : k if length(trimspace(v)) > 0]) : toset([])
}

# Create containers for any extra keys provided in secret_seed_values not already predefined
resource "google_secret_manager_secret" "seed_extra" {
  for_each  = var.manage_secrets ? { for k in local.seed_keys_nonempty : k => k if !contains(keys(local.predefined_secret_ids), k) } : {}
  project   = var.project_id
  secret_id = each.key
  replication {
    auto {}
  }
  labels = local.common_labels
  lifecycle { prevent_destroy = true }
}

# Final map of seedable ids = predefined + extras created above
locals {
  seedable_secret_ids = var.manage_secrets ? merge(
    local.predefined_secret_ids,
    { for k, s in google_secret_manager_secret.seed_extra : k => s.id }
  ) : {}
}

resource "google_secret_manager_secret_version" "seed_values" {
  for_each = var.manage_secrets ? toset([for k in local.seed_keys_nonempty : k if contains(keys(local.seedable_secret_ids), k)]) : toset([])

  secret      = local.seedable_secret_ids[each.key]
  secret_data = var.secret_seed_values[each.key]

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [secret_data]
  }
}

# Admin ingestion secret (for CDC smoke tests / admin ops)
resource "random_password" "admin_ingest_secret" {
  count   = 0
  length  = 32
  special = false
}

resource "google_secret_manager_secret" "admin_ingest_secret" {
  count     = var.manage_secrets ? 1 : 0
  project   = var.project_id
  secret_id = "etherion-admin-ingest-secret"
  replication {
    auto {}
  }
  labels = local.common_labels
  lifecycle {
    prevent_destroy = true
  }
}

// Removed obsolete admin_ingest_secret_latest; seeding handled via seed_values
