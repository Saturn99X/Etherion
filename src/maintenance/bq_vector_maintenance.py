from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List, Optional

from google.cloud import bigquery

from src.services.bigquery_service import BigQueryService
from src.services.embedding_service import EmbeddingService


class BQVectorMaintenance:
    def __init__(self, project_id: Optional[str] = None) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required")
        self.bq = BigQueryService(project_id=self.project_id)
        self.embedder = EmbeddingService(project_id=self.project_id)

    def create_vector_index(self, tenant_id: str) -> None:
        dataset = f"tnt_{tenant_id}"
        table = f"{self.project_id}.{dataset}.docs"
        sql = f"""
        CREATE VECTOR INDEX IF NOT EXISTS idx_docs_vec
        ON `{table}` (vector_embedding)
        OPTIONS(distance_type='COSINE')
        """
        # Labels enforce audit trail
        self.bq.query(sql, labels={"tenant_id": str(tenant_id), "component": "vector_index_create"})

    def backfill_missing_vectors(self, tenant_id: str, limit: Optional[int] = None, batch_size: int = 64, dry_run: bool = False) -> int:
        dataset = f"tnt_{tenant_id}"
        table = f"{self.project_id}.{dataset}.docs"
        lim_clause = ""
        if limit is not None and int(limit) > 0:
            lim_clause = "\nLIMIT @limit"
        sql_missing = f"""
        SELECT doc_id, text_chunk
        FROM `{table}`
        WHERE (vector_embedding IS NULL OR ARRAY_LENGTH(vector_embedding) = 0)
        {lim_clause}
        """
        params: Dict[str, Any] = {}
        if lim_clause:
            params["limit"] = int(limit)
        rows = list(self.bq.query(sql_missing, params=params, labels={"tenant_id": str(tenant_id), "component": "vector_backfill_scan"}))
        if not rows:
            return 0

        total = 0
        # Batch embed to minimize API calls
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            texts = [r.get("text_chunk") for r in batch]
            vectors = self.embedder.embed_texts(texts)
            for r, vec in zip(batch, vectors):
                doc_id = r.get("doc_id")
                if not doc_id or dry_run:
                    continue
                upd_sql = f"""
                UPDATE `{table}`
                SET vector_embedding = @vec, updated_at = CURRENT_TIMESTAMP()
                WHERE doc_id = @doc_id
                """
                self.bq.query(
                    upd_sql,
                    params={"vec": [float(x) for x in (vec or [])], "doc_id": str(doc_id)},
                    labels={"tenant_id": str(tenant_id), "component": "vector_backfill_update"},
                )
                total += 1
        return total

    def _list_tenant_ids(self, dataset_prefix: str = "tnt_") -> List[str]:
        client = self.bq.client
        tids: List[str] = []
        for ds in client.list_datasets(self.project_id):
            dsid = getattr(ds, "dataset_id", "")
            if dsid.startswith(dataset_prefix) and len(dsid) > len(dataset_prefix):
                tids.append(dsid[len(dataset_prefix):])
        return tids

    def create_vector_index_all(self, dataset_prefix: str = "tnt_") -> List[str]:
        processed: List[str] = []
        for tid in self._list_tenant_ids(dataset_prefix=dataset_prefix):
            try:
                self.create_vector_index(tid)
                processed.append(tid)
            except Exception:
                # continue to next tenant
                pass
        return processed

    def backfill_all(self, limit: Optional[int] = None, batch_size: int = 64, dry_run: bool = False, dataset_prefix: str = "tnt_") -> Dict[str, int]:
        result: Dict[str, int] = {}
        for tid in self._list_tenant_ids(dataset_prefix=dataset_prefix):
            try:
                cnt = self.backfill_missing_vectors(tid, limit=limit, batch_size=batch_size, dry_run=dry_run)
                result[tid] = cnt
            except Exception:
                result[tid] = -1
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="BigQuery vector maintenance utilities")
    parser.add_argument("--project", dest="project_id", default=os.getenv("GOOGLE_CLOUD_PROJECT"), help="GCP project id")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cvi = sub.add_parser("create-index", help="Create vector index on tnt_{tenant}.docs")
    cvi.add_argument("tenant_id", help="Target tenant id (e.g., 123)")

    cvia = sub.add_parser("create-index-all", help="Create vector indexes for all tenants (prefix scan)")
    cvia.add_argument("--dataset-prefix", default="tnt_", help="Dataset prefix to detect tenants (default: tnt_)")

    bfv = sub.add_parser("backfill", help="Backfill missing embeddings for tnt_{tenant}.docs")
    bfv.add_argument("tenant_id", help="Target tenant id (e.g., 123)")
    bfv.add_argument("--limit", type=int, default=None, help="Max rows to backfill")
    bfv.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    bfv.add_argument("--dry-run", action="store_true", help="Scan only, do not update")

    bfva = sub.add_parser("backfill-all", help="Backfill missing embeddings for all tenants (prefix scan)")
    bfva.add_argument("--limit", type=int, default=None, help="Max rows per tenant to backfill")
    bfva.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    bfva.add_argument("--dry-run", action="store_true", help="Scan only, do not update")
    bfva.add_argument("--dataset-prefix", default="tnt_", help="Dataset prefix to detect tenants (default: tnt_)")

    args = parser.parse_args()
    maint = BQVectorMaintenance(project_id=args.project_id)

    if args.cmd == "create-index":
        maint.create_vector_index(args.tenant_id)
        print("Vector index create requested.")
    elif args.cmd == "create-index-all":
        tids = maint.create_vector_index_all(dataset_prefix=args.dataset_prefix)
        print(f"Vector index create requested for tenants: {', '.join(tids) if tids else '(none)'}")
    elif args.cmd == "backfill":
        total = maint.backfill_missing_vectors(args.tenant_id, limit=args.limit, batch_size=args.batch_size, dry_run=args.dry_run)
        print(f"Backfill completed: {total} rows updated.")
    elif args.cmd == "backfill-all":
        out = maint.backfill_all(limit=args.limit, batch_size=args.batch_size, dry_run=args.dry_run, dataset_prefix=args.dataset_prefix)
        print("Backfill per-tenant:")
        for tid, cnt in out.items():
            print(f"  {tid}: {'error' if cnt < 0 else cnt}")


if __name__ == "__main__":
    main()
