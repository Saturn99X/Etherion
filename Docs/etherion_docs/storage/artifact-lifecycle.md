# Artifact Lifecycle: From Upload to Cleanup

## The Complete Journey

Every artifact in Etherion follows a predictable path: creation, storage, retrieval, optional expiry, and cleanup. Understanding this lifecycle is essential for diagnosing storage issues, optimizing performance, and designing retention policies.

## Stage 1: User Upload

A user attaches a file to a knowledge base, uploads an artifact for a job, or sends a document to an agent. The web or mobile client sends the file to an API endpoint, typically a GraphQL or REST mutation. The backend receives the file as a multipart form upload or binary payload.

The backend creates a unique key for the file, usually based on tenant ID, artifact type, and a timestamp or UUID. For example, a knowledge base document might be stored as:

```
kb-source-docs/tenant-abc123/doc-20260326-xyz789/original-filename.pdf
```

The key structure serves multiple purposes. The prefix (`kb-source-docs`) groups related files. The tenant ID ensures multi-tenant isolation—tenant isolation is enforced at the filesystem/bucket level, not just in metadata. The timestamp and UUID make the key unique and sortable.

## Stage 2: Storage Persistence

The backend calls `storage.upload(bucket, key, file_bytes, content_type)`. The storage backend (MinIO, local, or GCS) writes the bytes and returns a storage URI. The URI encodes the backend type and location:

- MinIO: `s3://etherion-kb/kb-source-docs/tenant-abc123/doc-20260326-xyz789/original-filename.pdf`
- Local: `file:///tmp/etherion-storage/etherion-kb/kb-source-docs/tenant-abc123/doc-20260326-xyz789/original-filename.pdf`
- GCS: `gs://etherion-kb/kb-source-docs/tenant-abc123/doc-20260326-xyz789/original-filename.pdf`

This URI is stored in PostgreSQL alongside metadata:

```sql
INSERT INTO artifacts (
  id, tenant_id, artifact_type, original_filename, file_size,
  content_hash, storage_uri, created_at, expires_at
) VALUES (
  'art-123', 'tenant-abc', 'knowledge-base-doc', 'document.pdf', 1024000,
  'sha256-abc...', 's3://etherion-kb/kb-source-docs/...', NOW(), NULL
);
```

The storage URI is immutable. If it changes (due to backend migration or storage policy), a separate migration process updates all affected records.

## Stage 3: Agent Processing

When an agent runs a job that references this artifact, it calls `storage.download(bucket, key)`, which retrieves the bytes from MinIO or the local filesystem. The agent processes the artifact—extracting text, generating embeddings, analyzing content—and may produce output artifacts.

Job outputs are also stored as artifacts. The job orchestrator creates a temporary file manager for the job and writes traces and outputs to local disk, then uploads them to storage:

```python
from src.core.temp_file_manager import TempFileManager

manager = TempFileManager(tenant_id=job.tenant_id, job_id=job.id)

# Job writes traces and outputs locally
with manager.trace_file_writer() as append_trace:
    append_trace({"step": "initialize", "timestamp": "2026-03-26T10:30:00Z"})
    append_trace({"step": "process", "result": "success"})

# After job completes, upload to storage
trace_content = manager.read_trace_file_content()
trace_uri = storage.upload("etherion-artifacts",
                           f"job-traces/{job.id}/trace.jsonl",
                           io.BytesIO(trace_content.encode()),
                           content_type="application/x-jsonl")

# Store in database
job.trace_uri = trace_uri
job.save()

# Clean up temp files
manager.cleanup()
```

The temporary file manager creates isolated directories for each job, preventing file conflicts and simplifying cleanup. After upload to persistent storage, local temp files are deleted.

## Stage 4: Client Access via Presigned URLs

When a user wants to download an artifact from the UI, they click a download button. The frontend calls a backend API that:

1. Looks up the artifact in PostgreSQL
2. Parses the storage URI to extract bucket and key
3. Calls `storage.get_url(bucket, key, expiry_seconds=3600)`
4. Returns the presigned URL to the client

```python
async def get_artifact_download_link(artifact_id: str) -> str:
    artifact = await Artifact.get(artifact_id)

    # Parse URI
    # s3://bucket/key → (bucket, key)
    bucket, key = parse_storage_uri(artifact.storage_uri)

    # Generate presigned URL, valid for 1 hour
    url = storage.get_url(bucket, key, expiry_seconds=3600)

    return url
```

The presigned URL is cryptographically signed by MinIO using the secret key. Anyone with the URL can download the object for the next hour, but they cannot forge a URL to access a different object or bypass expiry. The browser downloads directly from MinIO, bypassing the backend, which reduces load.

## Stage 5: Expiry and Cleanup

Artifacts may have finite lifetimes. A temporary analysis output might be valid for 7 days, while a knowledge base document is permanent. This is controlled by the `expires_at` field in PostgreSQL.

A background task (Celery, a systemd timer, or the job orchestrator) runs periodically and scans for expired artifacts:

```sql
SELECT * FROM artifacts WHERE expires_at < NOW() AND deleted_at IS NULL;
```

For each expired artifact, the cleanup process:

1. Calls `storage.delete(bucket, key)` to remove the bytes from MinIO
2. Marks the database record as deleted (`UPDATE artifacts SET deleted_at = NOW()`)
3. Optionally archives metadata to a separate table for audit trails

```python
def cleanup_expired_artifacts():
    expired = await db.query("""
        SELECT id, storage_uri FROM artifacts
        WHERE expires_at < NOW() AND deleted_at IS NULL
        LIMIT 1000
    """)

    for artifact in expired:
        bucket, key = parse_storage_uri(artifact.storage_uri)
        try:
            storage.delete(bucket, key)
            await db.execute("""
                UPDATE artifacts SET deleted_at = NOW()
                WHERE id = %s
            """, [artifact.id])
        except Exception as e:
            logger.error(f"Failed to delete {artifact.id}: {e}")
            # Don't fail the whole batch; continue
            pass
```

This approach is resilient. If storage deletion fails, the database is not updated, and the cleanup process tries again later. If database update fails, the artifact remains in storage (wasteful but not broken). Over time, with retries, the system reaches consistency.

## Stage 6: Tenant Deletion

When a tenant is deleted (rare, but essential for data privacy), all their artifacts must be removed. The system scans for all artifacts associated with the tenant and marks them for deletion:

```python
async def delete_tenant(tenant_id: str):
    # Find all artifacts
    artifacts = await db.query("""
        SELECT id, storage_uri FROM artifacts WHERE tenant_id = %s
    """, [tenant_id])

    # Delete from storage
    for artifact in artifacts:
        bucket, key = parse_storage_uri(artifact.storage_uri)
        try:
            storage.delete(bucket, key)
        except Exception as e:
            logger.error(f"Failed to delete {artifact.id} for tenant {tenant_id}: {e}")

    # Mark in database
    await db.execute("""
        UPDATE artifacts SET deleted_at = NOW()
        WHERE tenant_id = %s AND deleted_at IS NULL
    """, [tenant_id])
```

The bucket-level isolation (all of tenant-abc's files in a prefix) also allows batch operations. Future versions could add lifecycle rules to MinIO that automatically delete files older than X days, reducing the need for manual cleanup.

## Monitoring the Lifecycle

Operators should monitor key metrics:

**Storage usage by tenant.** Query PostgreSQL to sum file sizes by tenant, trending over time. Identify runaway tenants uploading excessive data.

**Cleanup success rate.** Track how many expired artifacts are successfully deleted vs. failed. Failed cleanups accumulate as storage waste.

**Presigned URL generation latency.** MinIO should generate URLs in milliseconds. If this spikes, MinIO might be overloaded or unhealthy.

**Health checks.** The storage backend's `health_check()` method is called at startup and periodically during runtime. If it fails, alert operators.

**Stale temp files.** The `TempFileManager.cleanup_stale_temp_files()` method cleans up local temporary files older than 24 hours. Run this periodically to prevent disk fill.

By understanding this lifecycle, you can design retention policies, optimize storage costs, debug missing files, and ensure data privacy at scale.
