import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import os
from src.core.redis import get_redis_client

logger = logging.getLogger(__name__)


class PricingLedger:
    """
    Append-only usage and credit ledger stored in Redis (tenant-isolated keys).
    Structure is compatible with future export to BigQuery when enabled.
    """

    def __init__(self):
        self.redis = get_redis_client()

    async def append_usage_event(
        self,
        user_id: int,
        job_id: str,
        usage_summary: Dict[str, Any],
        credit_delta: int,
        currency: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "job_id": job_id,
            "usage_summary": usage_summary,
            "credit_delta": credit_delta,
            "currency": currency,
            "tenant_id": tenant_id,
            "retention_months": int(os.getenv("LEDGER_RETENTION_MONTHS", "0") or 0),
        }
        if tenant_id:
            key = f"pricing:ledger:{tenant_id}:user:{user_id}"
        else:
            key = f"pricing:ledger:user:{user_id}"
        await self.redis.lpush(key, json.dumps(entry))

        enable_bq_export = str(os.getenv("ENABLE_BIGQUERY_EXPORT", "")).lower() in ("1", "true", "yes")
        if enable_bq_export:
            try:
                # Placeholder for future export integration
                logger.debug("BigQuery export enabled; entry staged for export")
            except Exception as e:
                logger.error(f"BigQuery export staging failed: {e}")


