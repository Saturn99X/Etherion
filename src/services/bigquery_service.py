from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence
import json
import asyncio
import os
from src.services.pricing.cost_tracker import CostTracker

class BigQueryService:
    def __init__(self, project_id: str, client: Optional[Any] = None) -> None:
        if not project_id:
            raise ValueError("project_id is required")
        self.project_id = project_id
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google.cloud import bigquery
            self._client = bigquery.Client(project=self.project_id)
        return self._client

    # Dataset operations
    def ensure_dataset(self, dataset_id: str, location: str = "US") -> Any:
        from google.cloud import bigquery
        from google.cloud.exceptions import NotFound
        dataset_ref = bigquery.Dataset(f"{self.project_id}.{dataset_id}")
        try:
            return self.client.get_dataset(dataset_ref)
        except NotFound:
            dataset_ref.location = location
            return self.client.create_dataset(dataset_ref)

    def dataset_exists(self, dataset_id: str) -> bool:
        try:
            self.client.get_dataset(f"{self.project_id}.{dataset_id}")
            return True
        except Exception:
            return False

    # Table operations
    def ensure_table(
        self,
        dataset_id: str,
        table_id: str,
        schema: Sequence[Any],
        partition_field: Optional[str] = None,
        partition_type: Any = None,
        cluster_fields: Optional[Sequence[str]] = None,
        location: str = "US",
    ) -> Any:
        from google.cloud import bigquery
        from google.cloud.exceptions import NotFound
        if partition_type is None:
            partition_type = bigquery.TimePartitioningType.DAY

        self.ensure_dataset(dataset_id, location=location)
        table_ref = bigquery.Table(f"{self.project_id}.{dataset_id}.{table_id}", schema=schema)
        # Partitioning
        if partition_field:
            table_ref.time_partitioning = bigquery.TimePartitioning(type_=partition_type, field=partition_field)
        # Clustering
        if cluster_fields:
            table_ref.clustering_fields = list(cluster_fields)

        try:
            return self.client.get_table(table_ref)
        except NotFound:
            return self.client.create_table(table_ref)

    def table_exists(self, dataset_id: str, table_id: str) -> bool:
        try:
            self.client.get_table(f"{self.project_id}.{dataset_id}.{table_id}")
            return True
        except Exception:
            return False

    # Data operations
    def insert_rows_json(
        self,
        dataset_id: str,
        table_id: str,
        rows: List[Dict[str, Any]],
        *,
        job_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        if not rows:
            return
        table_ref = f"{self.project_id}.{dataset_id}.{table_id}"
        # Inspect table schema to adapt 'metadata' field type
        metadata_field_type: Optional[str] = None
        try:
            table = self.client.get_table(table_ref)
            for f in table.schema:
                if f.name == "metadata":
                    metadata_field_type = getattr(f, "field_type", None)
                    break
        except Exception:
            # If we can't fetch the schema, proceed without adaptation
            metadata_field_type = None

        adapted_rows: List[Dict[str, Any]] = []
        for r in rows:
            new_r = dict(r)
            if "metadata" in new_r:
                val = new_r["metadata"]
                if metadata_field_type in ("JSON", "RECORD"):
                    # Ensure dict for JSON/RECORD columns
                    if isinstance(val, str):
                        try:
                            new_r["metadata"] = json.loads(val)  # type: ignore[name-defined]
                        except Exception:
                            # Leave as-is; let BQ return a clear error
                            pass
                elif metadata_field_type is not None:
                    # Ensure string for non-JSON columns
                    if isinstance(val, dict):
                        try:
                            new_r["metadata"] = json.dumps(val)  # type: ignore[name-defined]
                        except Exception:
                            pass
            adapted_rows.append(new_r)

        errors = self.client.insert_rows_json(table_ref, adapted_rows)

        if job_id:
            try:
                payload_bytes = len(json.dumps(adapted_rows, ensure_ascii=False).encode("utf-8"))

                async def _record() -> None:
                    tracker = CostTracker()
                    await tracker.record_api_call(job_id, "bigquery", tenant_id=tenant_id)
                    gb = float(payload_bytes) / (1024.0 ** 3)
                    if gb > 0:
                        await tracker.record_bigquery_storage(job_id, active_gb_month=gb, tenant_id=tenant_id)

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_record())
                except RuntimeError:
                    asyncio.run(_record())
            except Exception:
                pass
        if errors and metadata_field_type is not None:
            # Inspect errors for metadata field issues and retry once with alternate representation
            def _has_metadata_error(errs: List[Dict[str, Any]]) -> bool:
                try:
                    for e in errs:
                        for d in e.get("errors", []):
                            loc = (d.get("location") or "").lower()
                            msg = (d.get("message") or "").lower()
                            if loc == "metadata" or "metadata" in msg:
                                return True
                except Exception:
                    pass
                return False

            if _has_metadata_error(errors):
                retry_rows: List[Dict[str, Any]] = []
                for r in adapted_rows:
                    new_r = dict(r)
                    val = new_r.get("metadata")
                    try:
                        if metadata_field_type in ("JSON", "RECORD"):
                            # If we inserted dict and it failed, try string
                            if isinstance(val, dict):
                                new_r["metadata"] = json.dumps(val)
                            # If string failed, try parsed dict
                            elif isinstance(val, str):
                                new_r["metadata"] = json.loads(val)
                        else:
                            # Non-JSON column: ensure string
                            if isinstance(val, dict):
                                new_r["metadata"] = json.dumps(val)
                    except Exception:
                        pass
                    retry_rows.append(new_r)
                errors = self.client.insert_rows_json(table_ref, retry_rows)

        if errors:
            raise RuntimeError(f"BigQuery insert errors: {errors}")

    def query(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        labels: Optional[Dict[str, str]] = None,
        job_id: Optional[str] = None,
        location: Optional[str] = None,
        maximum_bytes_billed: Optional[int] = None,
    ) -> Any:
        """Execute a parameterized query enforcing tenant_id label.

        WHY: All BigQuery jobs must include a tenant_id label for auditing and reconciliation.
        """
        from google.cloud import bigquery
        if not labels or "tenant_id" not in labels or not str(labels["tenant_id"]).strip():
            raise ValueError("BigQuery query requires labels with 'tenant_id'.")

        job_config = bigquery.QueryJobConfig()

        effective_max_bytes = maximum_bytes_billed
        if effective_max_bytes is None:
            raw = (os.getenv("BIGQUERY_MAX_BYTES_BILLED") or "").strip()
            if raw:
                try:
                    effective_max_bytes = int(raw)
                except Exception:
                    effective_max_bytes = None
        if effective_max_bytes is not None and int(effective_max_bytes) > 0:
            try:
                job_config.maximum_bytes_billed = int(effective_max_bytes)
            except Exception:
                pass

        if location:
            try:
                job_config.location = location
            except Exception:
                pass
        if params:
            bq_params = []
            for k, v in params.items():
                # Support ARRAY<FLOAT64> parameters (e.g., query vectors)
                if isinstance(v, list) and all(isinstance(x, (int, float)) for x in v):
                    bq_params.append(bigquery.ArrayQueryParameter(k, "FLOAT64", [float(x) for x in v]))
                else:
                    bq_params.append(bigquery.ScalarQueryParameter(k, self._infer_bq_type(v), v))
            job_config.query_parameters = bq_params
        job_config.labels = labels
        job = self.client.query(sql, job_config=job_config)
        result = job.result()
        # Record bytes scanned if job_id provided and loop is running
        if job_id:
            try:
                bytes_scanned = int(getattr(job, "total_bytes_processed", 0) or 0)
                metering_tenant_id: Optional[str] = None
                try:
                    if labels and labels.get("tenant_id"):
                        metering_tenant_id = str(labels.get("tenant_id"))
                except Exception:
                    metering_tenant_id = None
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(
                        CostTracker().record_bigquery_scan(job_id, bytes_scanned=bytes_scanned, tenant_id=metering_tenant_id)
                    )
                else:
                    asyncio.run(
                        CostTracker().record_bigquery_scan(job_id, bytes_scanned=bytes_scanned, tenant_id=metering_tenant_id)
                    )
            except Exception:
                pass
        return result

    @staticmethod
    def _infer_bq_type(value: Any) -> str:
        if isinstance(value, bool):
            return "BOOL"
        if isinstance(value, int):
            return "INT64"
        if isinstance(value, float):
            return "FLOAT64"
        return "STRING"
