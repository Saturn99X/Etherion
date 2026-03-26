#!/usr/bin/env python3
"""Migrate KB data from BigQuery to PostgreSQL + pgvector.

Reads each of the 6 KB tables from BigQuery per-tenant datasets and
upserts them into the corresponding pgvector PostgreSQL tables.

Usage:
    python scripts/migrate_bq_to_pgvector.py --dry-run
    python scripts/migrate_bq_to_pgvector.py --tenant 42
    python scripts/migrate_bq_to_pgvector.py  # all tenants

Environment:
    GOOGLE_CLOUD_PROJECT  — BQ project (required)
    DATABASE_URL          — pgvector target database (required)
    KB_MIGRATION_BATCH    — rows per batch (default: 500)

Schema transformations:
    gcs_uri → storage_uri
    BQ FLOAT64[] → Python list (pgvector handles the conversion)
    BQ JSON → Python dict (JSONB)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = int(os.getenv("KB_MIGRATION_BATCH", "500"))


# ── Table migration specs ──────────────────────────────────────────────────

TABLE_SPECS = [
    {
        "bq_table": "docs",
        "pg_table": "docs",
        "rename": {"file_uri": "file_uri"},  # no rename needed
        "skip_columns": [],
    },
    {
        "bq_table": "multimodal_docs",
        "pg_table": "multimodal_docs",
        "rename": {"gcs_uri": "storage_uri"},
        "skip_columns": [],
    },
    {
        "bq_table": "assets",
        "pg_table": "assets",
        "rename": {"gcs_uri": "storage_uri"},
        "skip_columns": [],
    },
    {
        "bq_table": "feedback",
        "pg_table": "feedback",
        "rename": {"id": "feedback_id"},
        "skip_columns": [],
    },
    {
        "bq_table": "media_object_embeddings",
        "pg_table": "media_object_embeddings",
        "rename": {"gcs_uri": "storage_uri"},
        "skip_columns": [],
    },
    {
        "bq_table": "ai_assets_object_embeddings",
        "pg_table": "ai_assets_object_embeddings",
        "rename": {"gcs_uri": "storage_uri"},
        "skip_columns": [],
    },
]


def get_tenants(bq) -> List[str]:
    """Return all tenant IDs by listing tnt_* datasets."""
    from google.cloud import bigquery
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    datasets = list(bq.list_datasets(project=project))
    tenant_ids = []
    for ds in datasets:
        name = ds.dataset_id
        if name.startswith("tnt_") and name[4:].isdigit():
            tenant_ids.append(name[4:])
    logger.info("Found %d tenant datasets", len(tenant_ids))
    return sorted(tenant_ids)


def migrate_table(
    bq,
    kb_backend,
    tenant_id: str,
    spec: Dict[str, Any],
    dry_run: bool = False,
) -> int:
    """Migrate one table for one tenant. Returns number of rows migrated."""
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    bq_table_ref = f"{project}.tnt_{tenant_id}.{spec['bq_table']}"
    rename = spec.get("rename", {})
    skip = set(spec.get("skip_columns", []))

    logger.info("  %s → %s ...", bq_table_ref, spec["pg_table"])

    try:
        rows = list(bq.list_rows(bq_table_ref))
    except Exception as exc:
        logger.warning("    Skipped (table not found or error): %s", exc)
        return 0

    total = len(rows)
    migrated = 0

    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        pg_rows = []
        for row in batch:
            d: Dict[str, Any] = {}
            for col, val in row.items():
                if col in skip:
                    continue
                pg_col = rename.get(col, col)
                # Coerce BQ types → Python types
                if col == "metadata" and isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except Exception:
                        val = {"raw": val}
                if col == "vector_embedding" and val is not None:
                    # BQ returns as list of Decimal — convert to float
                    val = [float(x) for x in val]
                d[pg_col] = val
            d["tenant_id"] = int(tenant_id)
            pg_rows.append(d)

        if not dry_run:
            try:
                kb_backend.insert_docs(
                    tenant_id=str(tenant_id),
                    table=spec["pg_table"],
                    rows=pg_rows,
                )
            except Exception as exc:
                logger.error("    Batch insert failed: %s", exc)
                continue

        migrated += len(pg_rows)
        logger.info(
            "    %d / %d rows (%s)",
            min(i + BATCH_SIZE, total),
            total,
            "(dry-run)" if dry_run else "inserted",
        )

    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate BigQuery KB → pgvector")
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing")
    parser.add_argument("--tenant", type=str, help="Migrate a single tenant ID")
    parser.add_argument("--table", type=str, help="Migrate a single table (e.g. multimodal_docs)")
    args = parser.parse_args()

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        sys.exit("GOOGLE_CLOUD_PROJECT is required")

    from google.cloud import bigquery
    bq = bigquery.Client(project=project)

    # Force pgvector backend for destination
    os.environ["KB_VECTOR_BACKEND"] = "pgvector"
    from src.services.kb_backend import get_kb_backend
    kb = get_kb_backend(force_new=True)

    tenant_ids = [args.tenant] if args.tenant else get_tenants(bq)
    specs = [s for s in TABLE_SPECS if not args.table or s["pg_table"] == args.table]

    total_rows = 0
    for tenant_id in tenant_ids:
        logger.info("Tenant %s:", tenant_id)
        for spec in specs:
            n = migrate_table(bq, kb, tenant_id, spec, dry_run=args.dry_run)
            total_rows += n

    logger.info("Migration complete: %d rows total%s", total_rows, " (dry-run)" if args.dry_run else "")


if __name__ == "__main__":
    main()
