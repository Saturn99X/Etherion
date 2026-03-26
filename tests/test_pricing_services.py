import math
import pytest

from src.services.pricing.services import (
    estimate_bigquery_cost,
    estimate_vertex_search_cost,
    estimate_exa_cost,
    estimate_compute_cost,
    estimate_network_cost,
    estimate_gcs_cost,
)


def test_bigquery_cost_1tb_scan():
    one_tb = 1024 ** 4
    costs = estimate_bigquery_cost(bytes_scanned=one_tb, active_gb_month=0.0, long_term_gb_month=0.0, slot_hours=0.0)
    assert costs["query"] == pytest.approx(5.0, rel=1e-6)
    assert costs["total"] == pytest.approx(5.0, rel=1e-6)


def test_vertex_ai_search_costs():
    costs = estimate_vertex_search_cost(
        standard_q=1000,
        enterprise_q=1000,
        advanced_q=1000,
        index_gib_month=20.0,
    )
    # 1k std = 1.5, 1k ent = 4.0, 1k adv = 4.0, index (20-10)*5=50 => total 59.5
    assert costs["total"] == pytest.approx(59.5, rel=1e-6)


def test_exa_costs():
    costs = estimate_exa_cost(
        search_auto_fast_1_25=500,
        search_auto_fast_26_100=500,
        search_neural_1_25=2000,
        search_neural_26_100=1000,
        contents_text_pages=2000,
        contents_highlights_pages=1000,
        contents_summary_pages=1000,
        answers=2000,
        research_agent_ops=1000,
        research_page_reads_standard=1000,
        research_page_reads_pro=1000,
        research_reasoning_tokens=1_000_000,
    )
    # Search: 0.5*5 + 0.5*25 + 2*5 + 1*25 = 2.5 + 12.5 + 10 + 25 = 50
    # Contents: 2*1 + 1*1 + 1*1 = 4
    # Answers: 2*5 = 10
    # Research: 1*5 + 1*5 + 1*10 + 1*5 = 25
    # Total: 89
    assert costs["total"] == pytest.approx(89.0, rel=1e-6)


def test_compute_network_gcs():
    comp = estimate_compute_cost(vcpu_hours=10.0, ram_gb_hours=100.0, gpu_hours=1.0)
    net = estimate_network_cost(egress_gib=10.0)
    gcs = estimate_gcs_cost(standard_gb_month=100.0, nearline_gb_month=100.0, coldline_gb_month=100.0, archive_gb_month=100.0, ops_a=2000, ops_b=20000)

    assert comp["total"] == pytest.approx(1.95, rel=1e-6)
    assert net["total"] == pytest.approx(0.85, rel=1e-6)
    # Storage: 2.0 + 1.0 + 0.4 + 0.22 = 3.62; Ops: 0.02 + 0.02 = 0.04 => 3.66
    assert gcs["total"] == pytest.approx(3.66, rel=1e-6)
