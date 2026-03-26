# src/services/pricing/pricing_secrets_loader.py
"""
Loads platform pricing secrets from Google Secret Manager at module init time.
These are platform-level (not tenant-specific) secrets used for cost calculation.

This module fetches all pricing-related secrets from GSM and populates os.environ
so that services.py can use consistent os.getenv() pattern.
"""

import os
import logging
from typing import Dict, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# List of all pricing secret names that should be loaded from GSM
PRICING_SECRET_NAMES = [
    # EXA AI Search
    "EXA_SEARCH_AUTO_FAST_1_25_PER_1K",
    "EXA_SEARCH_AUTO_FAST_26_100_PER_1K",
    "EXA_SEARCH_NEURAL_PER_1K",
    "EXA_SEARCH_NEURAL_26_100_PER_1K",
    "EXA_SEARCH_KEYWORD_PER_1K",
    "EXA_CONTENTS_TEXT_PER_1K_PAGES",
    "EXA_CONTENTS_HIGHLIGHTS_PER_1K_PAGES",
    "EXA_CONTENTS_SUMMARY_PER_1K_PAGES",
    "EXA_ANSWER_PER_1K",
    "EXA_RESEARCH_AGENT_OPS_PER_1K",
    "EXA_RESEARCH_PAGE_READS_STANDARD_PER_1K",
    "EXA_RESEARCH_PAGE_READS_PRO_PER_1K",
    "EXA_RESEARCH_REASONING_TOKENS_PER_1M",
    
    # BigQuery
    "BQ_PRICE_QUERY_PER_TB",
    "BQ_PRICE_ACTIVE_STORAGE_PER_GB_MONTH",
    "BQ_PRICE_LONGTERM_STORAGE_PER_GB_MONTH",
    "BQ_PRICE_SLOT_PER_HOUR",
    
    # Vertex AI Search
    "VS_PRICE_STANDARD_PER_1K_Q",
    "VS_PRICE_ENTERPRISE_PER_1K_Q",
    "VS_PRICE_ADVANCED_ADDON_PER_1K_Q",
    "VS_INDEX_PRICE_PER_GIB_MONTH",
    "VS_INDEX_FREE_GIB",
    
    # GCS Storage
    "GCS_PRICE_STANDARD_PER_GB_MONTH",
    "GCS_PRICE_NEARLINE_PER_GB_MONTH",
    "GCS_PRICE_COLDLINE_PER_GB_MONTH",
    "GCS_PRICE_ARCHIVE_PER_GB_MONTH",
    "GCS_OPS_CLASS_A_PER_1K",
    "GCS_OPS_CLASS_B_PER_10K",
    
    # Compute
    "COM_PRICE_VCPU_PER_HOUR",
    "COM_PRICE_RAM_GB_PER_HOUR",
    "COM_PRICE_GPU_PER_HOUR",
    
    # Network
    "NET_EGRESS_PRICE_PER_GIB_US_CENTRAL1",
    
    # Generic token pricing (fallback)
    "PRICE_PER_1K_INPUT_TOKENS",
    "PRICE_PER_1K_OUTPUT_TOKENS",
    "PRICE_PER_API_CALL",
    "PRICE_PER_MB_INBOUND",
    "PRICE_PER_MB_OUTBOUND",
    "PRICE_PER_MS_COMPUTE",
    
    # Currency
    "PRICING_CURRENCY",

    # LLM per-model overrides (consumed by llm_pricing via os.getenv)
    "LLM_PRICE_VERTEX_GEMINI_2_5_FLASH_INPUT_PER_1M",
    "LLM_PRICE_VERTEX_GEMINI_2_5_FLASH_OUTPUT_PER_1M",
    "LLM_PRICE_VERTEX_GEMINI_2_5_PRO_INPUT_PER_1M",
    "LLM_PRICE_VERTEX_GEMINI_2_5_PRO_OUTPUT_PER_1M",
    "LLM_PRICE_VERTEX_GEMINI_3_PRO_PREVIEW_INPUT_PER_1M",
    "LLM_PRICE_VERTEX_GEMINI_3_PRO_PREVIEW_OUTPUT_PER_1M",
]


@lru_cache(maxsize=1)
def _get_secret_manager_client():
    """Get or create Secret Manager client (cached)."""
    try:
        from google.cloud import secretmanager
        return secretmanager.SecretManagerServiceClient()
    except Exception as e:
        logger.warning(f"Failed to create Secret Manager client: {e}")
        return None


def _fetch_secret_from_gsm(secret_name: str, project_id: str) -> Optional[str]:
    """Fetch a single secret from Google Secret Manager."""
    client = _get_secret_manager_client()
    if not client:
        return None
    
    try:
        secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": secret_path})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        # Secret not found or access denied - this is expected for some secrets
        logger.debug(f"Secret {secret_name} not found in GSM: {e}")
        return None


def load_pricing_secrets_from_gsm() -> Dict[str, str]:
    """
    Load all pricing secrets from Google Secret Manager and populate os.environ.
    
    This should be called once at application startup. It will:
    1. Attempt to fetch each pricing secret from GSM
    2. If found, set it in os.environ (overriding any existing value)
    3. Return a dict of loaded secrets for debugging
    
    Returns:
        Dict mapping secret names to "loaded" or "default" status
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.warning("GOOGLE_CLOUD_PROJECT not set, skipping GSM pricing secrets load")
        return {"error": "GOOGLE_CLOUD_PROJECT not set"}
    
    loaded = {}
    for secret_name in PRICING_SECRET_NAMES:
        # Skip if already set in environment (allows local override)
        if os.getenv(secret_name) is not None:
            loaded[secret_name] = "env_override"
            continue
        
        value = _fetch_secret_from_gsm(secret_name, project_id)
        if value is not None:
            os.environ[secret_name] = value
            loaded[secret_name] = "loaded"
            logger.info(f"Loaded pricing secret from GSM: {secret_name}")
        else:
            loaded[secret_name] = "default"
    
    # Log summary
    loaded_count = sum(1 for v in loaded.values() if v == "loaded")
    default_count = sum(1 for v in loaded.values() if v == "default")
    override_count = sum(1 for v in loaded.values() if v == "env_override")
    
    logger.info(
        f"Pricing secrets loader complete: {loaded_count} from GSM, "
        f"{default_count} using defaults, {override_count} env overrides"
    )
    
    return loaded


def ensure_pricing_secrets_loaded():
    """
    Ensure pricing secrets are loaded. Safe to call multiple times.
    Uses module-level flag to prevent duplicate loads.
    """
    global _pricing_secrets_loaded
    if not _pricing_secrets_loaded:
        load_pricing_secrets_from_gsm()
        _pricing_secrets_loaded = True


# Module-level flag to track if secrets have been loaded
_pricing_secrets_loaded = False

# Auto-load on import if in production environment
if os.getenv("GOOGLE_CLOUD_PROJECT") and not os.getenv("SKIP_PRICING_SECRETS_LOAD"):
    try:
        load_pricing_secrets_from_gsm()
        _pricing_secrets_loaded = True
    except Exception as e:
        logger.error(f"Failed to auto-load pricing secrets: {e}")
