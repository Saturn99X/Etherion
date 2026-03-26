#!/usr/bin/env python3
"""Migrate object storage from Google Cloud Storage to local filesystem (or MinIO).

Downloads all objects from tenant GCS buckets and places them under
STORAGE_LOCAL_ROOT, maintaining the same bucket/key directory structure.
Also updates storage_uri references in the pgvector KB tables from
gs://... to file://... (or s3://...).

Usage:
    python scripts/migrate_gcs_to_local.py --dry-run
    python scripts/migrate_gcs_to_local.py --tenant 42
    python scripts/migrate_gcs_to_local.py  # all tenants

Environment:
    GOOGLE_CLOUD_PROJECT   — GCS source project (required)
    STORAGE_BACKEND        — destination: "local" (default) or "minio"
    STORAGE_LOCAL_ROOT     — local root path (default: /var/lib/etherion/storage)
    DATABASE_URL           — pgvector DB to update storage_uri refs (required)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BUCKET_SUFFIXES = ["media", "assets"]


def list_tenant_ids(storage_client, project: str) -> List[str]:
    """Return tenant IDs by listing tnt-*-media buckets."""
    tenant_ids = []
    for bucket in storage_client.list_buckets(project=project):
        name = bucket.name
        if name.startswith("tnt-") and name.endswith("-media"):
            parts = name.split("-")
            if len(parts) >= 3:
                tenant_ids.append(parts[1])
    return sorted(set(tenant_ids))


def migrate_bucket(
    storage_client,
    dest_backend,
    tenant_id: str,
    bucket_suffix: str,
    dry_run: bool = False,
) -> int:
    """Download all objects from one GCS bucket and upload to dest_backend."""
    src_bucket_name = f"tnt-{tenant_id}-{bucket_suffix}"
    dest_bucket = f"tnt-{tenant_id}-{bucket_suffix}"

    try:
        src_bucket = storage_client.bucket(src_bucket_name)
        blobs = list(storage_client.list_blobs(src_bucket_name))
    except Exception as exc:
        logger.warning("  Bucket %s not found: %s", src_bucket_name, exc)
        return 0

    migrated = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        for blob in blobs:
            local_tmp = os.path.join(tmpdir, blob.name.replace("/", "_"))
            if dry_run:
                logger.info("  [dry-run] gs://%s/%s → %s/%s", src_bucket_name, blob.name, dest_bucket, blob.name)
                migrated += 1
                continue
            try:
                blob.download_to_filename(local_tmp)
                dest_backend.upload(
                    local_path=local_tmp,
                    storage_key=blob.name,
                    bucket=dest_bucket,
                    content_type=blob.content_type,
                )
                migrated += 1
                logger.info("  gs://%s/%s → %s/%s", src_bucket_name, blob.name, dest_bucket, blob.name)
            except Exception as exc:
                logger.error("  Failed gs://%s/%s: %s", src_bucket_name, blob.name, exc)

    return migrated


def update_storage_uris(tenant_id: str, backend_name: str, dry_run: bool = False) -> None:
    """Update storage_uri column in pgvector KB tables from gs:// to file:// or s3://."""
    from sqlalchemy import create_engine, text
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        logger.warning("DATABASE_URL not set, skipping storage_uri update")
        return

    if backend_name == "local":
        from src.core.storage_backend_local import _local_root
        root = _local_root()
        # gs://tnt-{t}-{suffix}/{key} → file://{root}/tnt-{t}-{suffix}/{key}
        old_prefix = f"gs://tnt-{tenant_id}-"
        new_prefix = f"file://{root}/tnt-{tenant_id}-"
    elif backend_name == "minio":
        old_prefix = f"gs://tnt-{tenant_id}-"
        new_prefix = f"s3://tnt-{tenant_id}-"
    else:
        return

    tables_with_uri = [
        "kb_multimodal_docs",
        "kb_assets",
        "kb_media_object_embeddings",
        "kb_ai_assets_object_embeddings",
    ]

    if dry_run:
        for t in tables_with_uri:
            logger.info("  [dry-run] UPDATE %s SET storage_uri = replace(storage_uri, '%s', '%s') WHERE tenant_id = %s",
                        t, old_prefix, new_prefix, tenant_id)
        return

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(f"SET app.tenant_id = :tid"), {"tid": str(tenant_id)})
        for table in tables_with_uri:
            result = conn.execute(
                text(f"UPDATE {table} SET storage_uri = replace(storage_uri, :old, :new) WHERE tenant_id = :tid AND storage_uri LIKE :pattern"),
                {"old": old_prefix, "new": new_prefix, "tid": int(tenant_id), "pattern": f"{old_prefix}%"},
            )
            if result.rowcount > 0:
                logger.info("  Updated %d rows in %s", result.rowcount, table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate GCS → local/MinIO storage")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tenant", type=str, help="Single tenant ID")
    parser.add_argument("--skip-db-update", action="store_true", help="Skip storage_uri DB update")
    args = parser.parse_args()

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        sys.exit("GOOGLE_CLOUD_PROJECT is required")

    dest_backend_name = os.getenv("STORAGE_BACKEND", "local").lower()

    from google.cloud import storage as gcs
    src_client = gcs.Client(project=project)

    from src.core.storage_backend import get_storage_backend
    dest = get_storage_backend()

    tenant_ids = [args.tenant] if args.tenant else list_tenant_ids(src_client, project)
    logger.info("Migrating %d tenants: %s", len(tenant_ids), tenant_ids)

    total = 0
    for tenant_id in tenant_ids:
        logger.info("Tenant %s:", tenant_id)
        for suffix in BUCKET_SUFFIXES:
            n = migrate_bucket(src_client, dest, tenant_id, suffix, dry_run=args.dry_run)
            total += n
        if not args.skip_db_update:
            update_storage_uris(tenant_id, dest_backend_name, dry_run=args.dry_run)

    logger.info("Storage migration complete: %d objects%s", total, " (dry-run)" if args.dry_run else "")


if __name__ == "__main__":
    main()
