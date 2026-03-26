# Document Ingestion: From Upload to Searchable Vector

## The Ingestion Pipeline

When a user uploads a document to their project's knowledge base, Etherion runs an asynchronous pipeline to transform raw bytes into searchable semantic vectors. This process is coordinated by the ingestion service and executed through a series of well-defined stages.

```
┌─────────────────────┐
│  File Upload UI     │
│  (or API)           │
└────────┬────────────┘
         │
         v
┌─────────────────────────────────────────┐
│ MinIO Upload                            │
│ (S3-compatible storage)                 │
│ → Returns storage_uri: s3://bucket/key  │
└────────┬────────────────────────────────┘
         │
         v
┌─────────────────────────────────────────┐
│ Create ProjectKBFile Record             │
│ status = "processing"                   │
│ file_uri = storage_uri                  │
│ file_size, mime_type, retention_policy  │
└────────┬────────────────────────────────┘
         │
         v
┌─────────────────────────────────────────┐
│ Background Job: Extract Text            │
│ 1. Download file from MinIO             │
│ 2. Parse PDF/docx/text                  │
│ 3. Split into chunks (configurable)     │
└────────┬────────────────────────────────┘
         │
         v
┌─────────────────────────────────────────┐
│ Generate Embeddings                     │
│ (Embedding API: OpenAI, local model)    │
│ 1 chunk = 1 embedding vector            │
└────────┬────────────────────────────────┘
         │
         v
┌─────────────────────────────────────────┐
│ Store in PostgreSQL + pgvector          │
│ CREATE Document records:                │
│ - doc_id (unique per chunk)             │
│ - text_chunk (the actual text)          │
│ - embedding (1536-dim vector)           │
│ - metadata_json (source, filename, etc) │
│ - storage_uri (MinIO reference)         │
│ - tenant_id, kb_id (for isolation)      │
└────────┬────────────────────────────────┘
         │
         v
┌─────────────────────────────────────────┐
│ Update ProjectKBFile Record             │
│ status = "available" (success)          │
│ OR status = "failed" + error_message    │
└─────────────────────────────────────────┘
```

## ProjectKBFile Lifecycle

Each uploaded file is tracked by a `ProjectKBFile` record. Understanding its status transitions is key to debugging ingestion issues.

```python
class ProjectKBFile(SQLModel, table=True, extend_existing=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    file_name: str                          # Original filename
    file_uri: str                           # S3 URI: s3://bucket/key
    file_size: int = Field(default=0)       # Bytes
    mime_type: str = Field(default="...")
    status: str = Field(default="processing")  # processing | available | failed
    error_message: Optional[str] = None     # If status=failed
    retention_policy_days: int = 365        # How long to keep
    archive_after: Optional[datetime] = None
    created_at: datetime
    project_id: int                         # Which project
    tenant_id: int                          # Tenant isolation
```

### Status Transitions

**processing** → *initial state after upload*
- The file has been stored in MinIO but text extraction and embedding haven't started yet.
- The background ingestion job is queued (typically runs within seconds).

**processing** → **available** → *ingestion succeeded*
- Text was successfully extracted.
- Embeddings were generated.
- Document records were inserted into PostgreSQL.
- At this point, agents can search and retrieve chunks from this file.

**processing** → **failed** → *ingestion failed*
- Text extraction failed (corrupted PDF, unsupported format).
- Embedding API returned an error.
- Database insertion failed.
- The `error_message` field contains the failure reason (e.g., "PDF parsing failed: invalid stream").
- The file remains in MinIO but is not searchable.

Polling the `ProjectKBFile` record tells you the ingestion status in real time.

## Chunk Creation and Metadata

During text extraction, Etherion doesn't store one embedding per file — it splits the text into semantically meaningful chunks. This strategy has several benefits:

1. **Smaller vector indexes**: A 100-page PDF might produce 500-1000 chunks instead of one large embedding.
2. **Better retrieval**: A query matches against the most relevant section, not a summary of the whole document.
3. **Traceable sources**: Each chunk references its source file and page/section.

Chunks are typically ~300-500 tokens (configurable), with overlap to preserve context across boundaries.

Each chunk becomes a separate `Document` record:

```python
class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    doc_id: str = Field(unique=True, index=True)  # e.g., "proj-123_chunk-45"
    kb_id: int                                     # Which knowledge base
    text_chunk: str                                # The actual text (e.g., 300-500 tokens)
    embedding: Optional[Any]                       # 1536-dim vector
    metadata_json: Optional[str]                   # {"filename": "sales.pdf", "page": 2, "section": "Q3"}
    storage_uri: Optional[str]                     # s3://bucket/sales.pdf (file source)
    filename: Optional[str]                        # For quick reference
    created_at: datetime
    tenant_id: int                                 # Multi-tenant isolation
```

The `metadata_json` is a JSON object that tracks:
- `filename`: Original file name
- `page`: Page number (for PDFs)
- `section`: Named section (for documents with structure)
- `chunk_index`: Sequential chunk number within the file
- Any custom metadata provided at upload time

This metadata is preserved and returned with search results, allowing agents to know the source of retrieved information.

## Storage Duplication and Retention

The system intentionally stores data in two places to separate concerns:

**MinIO (Object Storage)**
- Keeps the original file forever (or per retention policy)
- Used for downloading the complete file if needed
- Scales cheaply for large files

**PostgreSQL (Index + Chunks)**
- Stores text chunks and embeddings
- Optimized for vector search
- Smaller dataset (just the chunks, not the original bytes)
- Supports fast HNSW index lookups

When a document is deleted, both are cleaned up: the `Document` records are removed from PostgreSQL, and the original file is deleted from MinIO.

## Error Handling and Retry

If ingestion fails at any stage, the `ProjectKBFile.status` is set to `failed` with an explanatory `error_message`. Common failure modes:

**Parsing errors**: The text extraction library couldn't decode the file (corrupted PDF, unsupported format).

**Embedding API errors**: The embedding service returned an error, possibly due to rate limits or token limits (e.g., PDF too large to embed all chunks).

**Database errors**: Insertion failed, perhaps due to storage quota or constraint violations.

Retries are typically manual — the user sees the failed status and can re-upload, or an administrator can trigger a retry job. Etherion does not automatically retry; failed ingestions are observable and require investigation.

## Multi-Tenancy

All ingestion respects tenant boundaries. The `tenant_id` is set on both `ProjectKBFile` and `Document` records, and queries are always filtered by tenant. This means:

- Tenant A's PDFs never appear in Tenant B's searches.
- Each tenant's embeddings are stored securely.
- Scaling the knowledge base across tenants is transparent — the index grows per tenant, not globally.

## Configuration

Ingestion behavior is controlled via environment variables:

- `KB_EMBEDDING_DIM`: Dimension of embedding vectors (default: 1536)
- `EMBEDDING_API`: Which service to use for embeddings (e.g., "openai")
- `KB_CHUNK_SIZE`: Approximate chunk size in tokens (default: 300)
- `KB_CHUNK_OVERLAP`: Overlap between chunks (default: 50)
- `STORAGE_BACKEND`: Where files are stored (default: "minio")
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, etc.: MinIO configuration

Changes to these values typically only affect new ingestions; existing chunks are left as-is.
