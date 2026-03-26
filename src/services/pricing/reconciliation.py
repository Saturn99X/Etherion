import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from src.core.celery import celery_app
from src.services.pricing.ledger import PricingLedger
from src.core.redis import get_redis_client
import os

logger = logging.getLogger(__name__)


def _billing_table_fqn() -> Optional[str]:
    project = os.getenv("GCP_BILLING_EXPORT_PROJECT")
    dataset = os.getenv("GCP_BILLING_EXPORT_DATASET")
    table = os.getenv("GCP_BILLING_EXPORT_TABLE")
    if not (project and dataset and table):
        return None
    return f"{project}.{dataset}.{table}"


def _time_bounds(hours: int = 24) -> Dict[str, str]:
    end = datetime.utcnow()
    start = end - timedelta(hours=hours)
    return {"start": start.isoformat(timespec="seconds") + "Z", "end": end.isoformat(timespec="seconds") + "Z"}


@celery_app.task(name="src.services.pricing.reconciliation.run_reconciliation", bind=True)
def run_reconciliation(self) -> Dict[str, Any]:
    """Reconcile internal ledger with Cloud Billing export (last 24h).

    - Summarizes GCP actual costs by label tenant_id (if present) and by service.
    - Stores summaries in Redis for dashboards/alerts.
    - Does not mutate credits; credits remain deducted at usage time. This is for auditing.
    """
    table = _billing_table_fqn()
    if not table:
        logger.info("Billing export not configured; skipping reconciliation")
        return {"status": "skipped", "reason": "no_billing_export"}

    from google.cloud import bigquery
    tb = _time_bounds(24)
    client = bigquery.Client(project=os.getenv("GCP_BILLING_EXPORT_PROJECT") or None)

    # Labels can be either labels or system_labels in export schema. We try both.
    sql = f"""
    WITH base AS (
      SELECT
        service.description AS service_desc,
        cost AS cost_usd,
        (SELECT value FROM UNNEST(labels) WHERE key = 'tenant_id') AS tenant_id_label,
        (SELECT value FROM UNNEST(system_labels) WHERE key = 'tenant_id') AS tenant_id_sys,
        usage_start_time
      FROM `{table}`
      WHERE usage_start_time >= TIMESTAMP(@start)
        AND usage_start_time < TIMESTAMP(@end)
    )
    SELECT
      COALESCE(tenant_id_label, tenant_id_sys, 'unknown') AS tenant_id,
      service_desc,
      ROUND(SUM(cost_usd), 6) AS total_cost_usd
    FROM base
    GROUP BY tenant_id, service_desc
    ORDER BY tenant_id, service_desc
    """

    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("start", "STRING", tb["start"]),
        bigquery.ScalarQueryParameter("end", "STRING", tb["end"]),
    ]))
    rows = job.result()

    # Store per-tenant/service costs in Redis
    redis = get_redis_client()
    totals_by_tenant: Dict[str, float] = {}
    per_service: Dict[str, Dict[str, float]] = {}
    for r in rows:
        tenant = str(r.get("tenant_id"))
        service_desc = r.get("service_desc") or "unknown"
        cost = float(r.get("total_cost_usd") or 0.0)
        totals_by_tenant[tenant] = totals_by_tenant.get(tenant, 0.0) + cost
        per_service.setdefault(tenant, {})[service_desc] = cost

    # Persist snapshots (expire in 48h)
    async def _persist():
        for tenant, total in totals_by_tenant.items():
            await redis.set(f"pricing:recon:tenant:{tenant}:last24h_total_usd", total, expire=172800)
            await redis.set(f"pricing:recon:tenant:{tenant}:last24h_by_service", per_service.get(tenant, {}), expire=172800)

    import asyncio
    try:
        asyncio.get_event_loop().run_until_complete(_persist())
    except RuntimeError:
        # If not in an event loop (worker context), run a new loop
        asyncio.run(_persist())

    logger.info("Pricing reconciliation completed for last 24h")
    return {"status": "ok", "tenants": len(totals_by_tenant)}
