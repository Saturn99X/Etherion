# src/services/pricing/services.py
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Dict

# Load pricing secrets from GSM before reading module-level env vars
from src.services.pricing.pricing_secrets_loader import ensure_pricing_secrets_loaded
ensure_pricing_secrets_loaded()

def _must_env_float(name: str, default: str | None = None) -> float:
    val = os.environ.get(name, default)
    if val is None or str(val).strip() == "":
        raise RuntimeError(f"Missing required pricing environment variable: {name}")
    try:
        return float(val)
    except Exception as e:
        raise RuntimeError(f"Invalid float for env {name}: {val}") from e

# ------------------------------
# BigQuery
# ------------------------------

# Defaults (USD) 
BQ_PRICE_QUERY_PER_TB = float(os.getenv("BQ_PRICE_QUERY_PER_TB", "5.0"))
BQ_PRICE_ACTIVE_STORAGE_PER_GB_MONTH = float(os.getenv("BQ_PRICE_ACTIVE_STORAGE_PER_GB_MONTH", "0.02"))
BQ_PRICE_LONGTERM_STORAGE_PER_GB_MONTH = float(os.getenv("BQ_PRICE_LONGTERM_STORAGE_PER_GB_MONTH", "0.01"))
BQ_PRICE_SLOT_PER_HOUR = float(os.getenv("BQ_PRICE_SLOT_PER_HOUR", "0.0"))


def estimate_bigquery_cost(*, bytes_scanned: int = 0, active_gb_month: float = 0.0, long_term_gb_month: float = 0.0, slot_hours: float = 0.0) -> Dict[str, float]:
    tb_scanned = float(bytes_scanned) / (1024.0 ** 4)  # 1 TB = 2^40 bytes
    query_cost = tb_scanned * BQ_PRICE_QUERY_PER_TB
    active_cost = active_gb_month * BQ_PRICE_ACTIVE_STORAGE_PER_GB_MONTH
    long_cost = long_term_gb_month * BQ_PRICE_LONGTERM_STORAGE_PER_GB_MONTH
    slots_cost = slot_hours * BQ_PRICE_SLOT_PER_HOUR
    total = float(query_cost + active_cost + long_cost + slots_cost)
    return {
        "query": query_cost,
        "active_storage": active_cost,
        "long_term_storage": long_cost,
        "slots": slots_cost,
        "total": total,
    }

# ------------------------------
# Vertex AI Search (Enterprise by default per user)
# ------------------------------
VS_PRICE_STANDARD_PER_1K_Q = float(os.getenv("VS_PRICE_STANDARD_PER_1K_Q", "1.5"))
VS_PRICE_ENTERPRISE_PER_1K_Q = float(os.getenv("VS_PRICE_ENTERPRISE_PER_1K_Q", "4.0"))
VS_PRICE_ADVANCED_ADDON_PER_1K_Q = float(os.getenv("VS_PRICE_ADVANCED_ADDON_PER_1K_Q", "4.0"))
VS_INDEX_PRICE_PER_GIB_MONTH = float(os.getenv("VS_INDEX_PRICE_PER_GIB_MONTH", "5.0"))
VS_INDEX_FREE_GIB = float(os.getenv("VS_INDEX_FREE_GIB", "10.0"))


def estimate_vertex_search_cost(*, standard_q: int = 0, enterprise_q: int = 0, advanced_q: int = 0, index_gib_month: float = 0.0) -> Dict[str, float]:
    std_cost = (standard_q / 1000.0) * VS_PRICE_STANDARD_PER_1K_Q
    ent_cost = (enterprise_q / 1000.0) * VS_PRICE_ENTERPRISE_PER_1K_Q
    adv_cost = (advanced_q / 1000.0) * VS_PRICE_ADVANCED_ADDON_PER_1K_Q
    chargeable_gib = max(index_gib_month - VS_INDEX_FREE_GIB, 0.0)
    index_cost = chargeable_gib * VS_INDEX_PRICE_PER_GIB_MONTH
    total = float(std_cost + ent_cost + adv_cost + index_cost)
    return {
        "standard_queries": std_cost,
        "enterprise_queries": ent_cost,
        "advanced_addon": adv_cost,
        "index_storage": index_cost,
        "total": total,
    }

# ------------------------------
# EXA AI
# ------------------------------
EXA_SEARCH_AUTO_FAST_1_25_PER_1K = float(os.getenv("EXA_SEARCH_AUTO_FAST_1_25_PER_1K", "5.0"))
EXA_SEARCH_AUTO_FAST_26_100_PER_1K = float(os.getenv("EXA_SEARCH_AUTO_FAST_26_100_PER_1K", "25.0"))
EXA_SEARCH_NEURAL_PER_1K = float(os.getenv("EXA_SEARCH_NEURAL_PER_1K", "5.0"))
EXA_SEARCH_NEURAL_26_100_PER_1K = float(os.getenv("EXA_SEARCH_NEURAL_26_100_PER_1K", "25.0"))
EXA_SEARCH_KEYWORD_PER_1K = float(os.getenv("EXA_SEARCH_KEYWORD_PER_1K", "2.5"))

EXA_CONTENTS_TEXT_PER_1K_PAGES = float(os.getenv("EXA_CONTENTS_TEXT_PER_1K_PAGES", "1.0"))
EXA_CONTENTS_HIGHLIGHTS_PER_1K_PAGES = float(os.getenv("EXA_CONTENTS_HIGHLIGHTS_PER_1K_PAGES", "1.0"))
EXA_CONTENTS_SUMMARY_PER_1K_PAGES = float(os.getenv("EXA_CONTENTS_SUMMARY_PER_1K_PAGES", "1.0"))

EXA_ANSWER_PER_1K = float(os.getenv("EXA_ANSWER_PER_1K", "5.0"))

EXA_RESEARCH_AGENT_OPS_PER_1K = float(os.getenv("EXA_RESEARCH_AGENT_OPS_PER_1K", "5.0"))
EXA_RESEARCH_PAGE_READS_STANDARD_PER_1K = float(os.getenv("EXA_RESEARCH_PAGE_READS_STANDARD_PER_1K", "5.0"))
EXA_RESEARCH_PAGE_READS_PRO_PER_1K = float(os.getenv("EXA_RESEARCH_PAGE_READS_PRO_PER_1K", "10.0"))
EXA_RESEARCH_REASONING_TOKENS_PER_1M = float(os.getenv("EXA_RESEARCH_REASONING_TOKENS_PER_1M", "5.0"))


def estimate_exa_cost(*,
                      search_auto_fast_1_25: int = 0,
                      search_auto_fast_26_100: int = 0,
                      search_neural: int = 0,
                      search_neural_1_25: int = 0,
                      search_neural_26_100: int = 0,
                      search_keyword: int = 0,
                      contents_text_pages: int = 0,
                      contents_highlights_pages: int = 0,
                      contents_summary_pages: int = 0,
                      answers: int = 0,
                      research_agent_ops: int = 0,
                      research_page_reads_standard: int = 0,
                      research_page_reads_pro: int = 0,
                      research_reasoning_tokens: int = 0) -> Dict[str, float]:
    # Support both legacy 'search_neural' (counted as 1-25) and explicit buckets
    if search_neural and not (search_neural_1_25 or search_neural_26_100):
        search_neural_1_25 = search_neural

    cost_search = (
        (search_auto_fast_1_25 / 1000.0) * EXA_SEARCH_AUTO_FAST_1_25_PER_1K +
        (search_auto_fast_26_100 / 1000.0) * EXA_SEARCH_AUTO_FAST_26_100_PER_1K +
        (search_neural_1_25 / 1000.0) * EXA_SEARCH_NEURAL_PER_1K +
        (search_neural_26_100 / 1000.0) * EXA_SEARCH_NEURAL_26_100_PER_1K +
        (search_keyword / 1000.0) * EXA_SEARCH_KEYWORD_PER_1K
    )
    cost_contents = (
        (contents_text_pages / 1000.0) * EXA_CONTENTS_TEXT_PER_1K_PAGES +
        (contents_highlights_pages / 1000.0) * EXA_CONTENTS_HIGHLIGHTS_PER_1K_PAGES +
        (contents_summary_pages / 1000.0) * EXA_CONTENTS_SUMMARY_PER_1K_PAGES
    )
    cost_answer = (answers / 1000.0) * EXA_ANSWER_PER_1K
    cost_research = (
        (research_agent_ops / 1000.0) * EXA_RESEARCH_AGENT_OPS_PER_1K +
        (research_page_reads_standard / 1000.0) * EXA_RESEARCH_PAGE_READS_STANDARD_PER_1K +
        (research_page_reads_pro / 1000.0) * EXA_RESEARCH_PAGE_READS_PRO_PER_1K +
        (research_reasoning_tokens / 1_000_000.0) * EXA_RESEARCH_REASONING_TOKENS_PER_1M
    )
    total = float(cost_search + cost_contents + cost_answer + cost_research)
    return {
        "search": cost_search,
        "contents": cost_contents,
        "answer": cost_answer,
        "research": cost_research,
        "total": total,
    }

# ------------------------------
# Compute, Network, GCS
# ------------------------------
COM_PRICE_VCPU_PER_HOUR = float(os.getenv("COM_PRICE_VCPU_PER_HOUR", "0.045"))
COM_PRICE_RAM_GB_PER_HOUR = float(os.getenv("COM_PRICE_RAM_GB_PER_HOUR", "0.005"))
COM_PRICE_GPU_PER_HOUR = float(os.getenv("COM_PRICE_GPU_PER_HOUR", "1.0"))


def estimate_compute_cost(*, vcpu_hours: float = 0.0, ram_gb_hours: float = 0.0, gpu_hours: float = 0.0) -> Dict[str, float]:
    cpu_cost = vcpu_hours * COM_PRICE_VCPU_PER_HOUR
    ram_cost = ram_gb_hours * COM_PRICE_RAM_GB_PER_HOUR
    gpu_cost = gpu_hours * COM_PRICE_GPU_PER_HOUR
    total = float(cpu_cost + ram_cost + gpu_cost)
    return {"cpu": cpu_cost, "ram": ram_cost, "gpu": gpu_cost, "total": total}

NET_EGRESS_PRICE_PER_GIB_US_CENTRAL1 = float(os.getenv("NET_EGRESS_PRICE_PER_GIB_US_CENTRAL1", "0.085"))


def estimate_network_cost(*, egress_gib: float = 0.0) -> Dict[str, float]:
    # Ingress is free; only charging egress
    cost = float(egress_gib) * NET_EGRESS_PRICE_PER_GIB_US_CENTRAL1
    return {"egress": cost, "total": cost}

GCS_PRICE_STANDARD_PER_GB_MONTH = float(os.getenv("GCS_PRICE_STANDARD_PER_GB_MONTH", "0.020"))
GCS_PRICE_NEARLINE_PER_GB_MONTH = float(os.getenv("GCS_PRICE_NEARLINE_PER_GB_MONTH", "0.010"))
GCS_PRICE_COLDLINE_PER_GB_MONTH = float(os.getenv("GCS_PRICE_COLDLINE_PER_GB_MONTH", "0.004"))
GCS_PRICE_ARCHIVE_PER_GB_MONTH = float(os.getenv("GCS_PRICE_ARCHIVE_PER_GB_MONTH", "0.0022"))

GCS_OPS_CLASS_A_PER_1K = float(os.getenv("GCS_OPS_CLASS_A_PER_1K", "0.01"))
GCS_OPS_CLASS_B_PER_10K = float(os.getenv("GCS_OPS_CLASS_B_PER_10K", "0.01"))


def estimate_gcs_cost(*, standard_gb_month: float = 0.0, nearline_gb_month: float = 0.0, coldline_gb_month: float = 0.0, archive_gb_month: float = 0.0, ops_a: int = 0, ops_b: int = 0) -> Dict[str, float]:
    storage = (
        standard_gb_month * GCS_PRICE_STANDARD_PER_GB_MONTH +
        nearline_gb_month * GCS_PRICE_NEARLINE_PER_GB_MONTH +
        coldline_gb_month * GCS_PRICE_COLDLINE_PER_GB_MONTH +
        archive_gb_month * GCS_PRICE_ARCHIVE_PER_GB_MONTH
    )
    ops = (ops_a / 1000.0) * GCS_OPS_CLASS_A_PER_1K + (ops_b / 10_000.0) * GCS_OPS_CLASS_B_PER_10K
    total = float(storage + ops)
    return {"storage": float(storage), "ops": float(ops), "total": total}
