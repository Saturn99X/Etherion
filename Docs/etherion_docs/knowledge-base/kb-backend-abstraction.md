# The KBBackend Abstraction: Pluggable Vector Search

## Why an Abstraction?

Etherion's knowledge base could theoretically use many vector search engines: PostgreSQL with pgvector, Pinecone, Weaviate, BigQuery, or Milvus. To avoid locking into a single backend and to support gradual migration, Etherion defines an abstract `KBBackend` interface. This allows different implementations to coexist, and the system chooses which one to use based on configuration.

The abstraction also ensures that ingestion code doesn't need to know about storage details, and agents don't need to know which search engine is running. They all talk to the same interface.

## The KBBackend Interface

The abstract base class defines four core operations:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class KBBackend(ABC):
    @abstractmethod
    async def search(
        self,
        tenant_id: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        project_id: Optional[str] = None,
        kb_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return top_k documents with keys:
        - doc_id: unique document identifier
        - text_chunk: the actual text content
        - score: similarity score (0-1)
        - metadata: JSON metadata dict
        - storage_uri: S3 URI to original file
        """

    @abstractmethod
    async def upsert(
        self,
        tenant_id: str,
        doc_id: str,
        text: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        """Insert or update a document with its embedding."""

    @abstractmethod
    async def delete(
        self,
        tenant_id: str,
        doc_id: str,
    ) -> None:
        """Delete a document by ID."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the backend is reachable and healthy."""
```

### Search

Retrieves documents by semantic similarity. Takes a pre-computed query embedding and returns ranked results. Implementations must respect `tenant_id` for security and support optional filtering by `project_id` and `kb_type`.

### Upsert

Stores or updates a document. Called during ingestion when text chunks are embedded and ready to store. If a document with the same `doc_id` already exists, it should be replaced.

### Delete

Removes a document from the index. Called when files are deleted or documents are retracted.

### Health Check

A simple probe to verify the backend is operational. Used for monitoring and diagnostics.

## Factory Pattern: Choosing the Backend

A factory function reads the `KB_VECTOR_BACKEND` environment variable to decide which implementation to instantiate:

```python
def get_kb_backend() -> KBBackend:
    """Factory — reads KB_VECTOR_BACKEND env var. Default: pgvector."""
    backend = os.getenv("KB_VECTOR_BACKEND", "pgvector").lower()

    if backend == "bigquery":
        from .kb_backend_bq import BigQueryKBBackend
        return BigQueryKBBackend()
    else:
        from .kb_backend_pgvector import PgvectorKBBackend
        return PgvectorKBBackend()
```

At startup, this factory is called once and the backend is cached. All subsequent search, upsert, and delete operations use the selected backend.

### Default Behavior

If `KB_VECTOR_BACKEND` is not set or is set to "pgvector", the system uses PostgreSQL with pgvector (recommended for new deployments).

### Legacy BigQuery Path

For backward compatibility, a `BigQueryKBBackend` implementation is maintained. It uses BigQuery's native `VECTOR_SEARCH` capability to perform similarity queries on documents stored in BigQuery tables. However, this path is deprecated in favor of pgvector and not used in the primary deployment.

## The pgvector Implementation

The primary implementation for new deployments. It leverages PostgreSQL's pgvector extension for fast, reliable vector search:

```python
from src.services.kb_backend import KBBackend


class PgvectorKBBackend(KBBackend):
    async def search(
        self,
        tenant_id: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        project_id: Optional[str] = None,
        kb_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute pgvector similarity search via PostgreSQL."""
        from sqlalchemy import text
        from src.database.db import get_session

        async for session in get_session():
            # Build and execute SQL query (see vector-search.md for details)
            sql = """
                SELECT d.doc_id, d.text_chunk, d.metadata_json, d.storage_uri,
                       1 - (d.embedding <=> CAST(:vec AS vector)) AS score
                FROM document d
                JOIN knowledgebase kb ON kb.id = d.kb_id
                WHERE d.tenant_id = :tid
            """
            # ... (filters and ordering omitted for brevity)

            result = await session.execute(text(sql), params)
            rows = result.fetchall()
            return [/* format results */]

    async def upsert(
        self,
        tenant_id: str,
        doc_id: str,
        text: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        """Upsert a document into PostgreSQL."""
        from sqlalchemy import text
        from src.database.db import get_session

        async for session in get_session():
            sql = """
                INSERT INTO document (doc_id, tenant_id, text_chunk, embedding, metadata_json, updated_at)
                VALUES (:doc_id, :tid, :text, CAST(:vec AS vector), :meta, NOW())
                ON CONFLICT (doc_id) DO UPDATE
                SET text_chunk = EXCLUDED.text_chunk,
                    embedding = EXCLUDED.embedding,
                    metadata_json = EXCLUDED.metadata_json,
                    updated_at = NOW()
            """
            await session.execute(text(sql), {
                "doc_id": doc_id,
                "tid": tenant_id,
                "text": text,
                "vec": str(embedding),
                "meta": json.dumps(metadata),
            })
            await session.commit()

    async def delete(self, tenant_id: str, doc_id: str) -> None:
        """Delete a document from PostgreSQL."""
        from sqlalchemy import text
        from src.database.db import get_session

        async for session in get_session():
            await session.execute(
                text("DELETE FROM document WHERE doc_id = :doc_id AND tenant_id = :tid"),
                {"doc_id": doc_id, "tid": tenant_id},
            )
            await session.commit()

    async def health_check(self) -> bool:
        """Check PostgreSQL connectivity."""
        from sqlalchemy import text
        from src.database.db import get_session

        try:
            async for session in get_session():
                await session.execute(text("SELECT 1"))
                return True
        except Exception:
            return False
        return False
```

Key characteristics:

- Uses PostgreSQL's native vector type and operators
- Supports HNSW indexing for performance
- Scales to billions of documents
- Supports multi-tenancy via `tenant_id` filtering
- Completely open source (no vendor lock-in)

## Adding a New Backend

To support a new vector search engine (e.g., Pinecone), follow these steps:

1. **Create a new file**: `src/services/kb_backend_pinecone.py`

2. **Implement the interface**:
   ```python
   class PineconeKBBackend(KBBackend):
       def __init__(self):
           # Initialize Pinecone client
           self.client = Pinecone(...)

       async def search(self, tenant_id, query, query_embedding, ...):
           # Call Pinecone API
           results = self.client.query(vector=query_embedding, top_k=top_k)
           return [/* format results */]

       async def upsert(self, tenant_id, doc_id, text, embedding, metadata):
           self.client.upsert(id=doc_id, values=embedding, metadata=metadata)

       async def delete(self, tenant_id, doc_id):
           self.client.delete(id=doc_id)

       async def health_check(self):
           return self.client.describe_index_stats() is not None
   ```

3. **Update the factory**:
   ```python
   def get_kb_backend() -> KBBackend:
       backend = os.getenv("KB_VECTOR_BACKEND", "pgvector").lower()
       if backend == "pinecone":
           from .kb_backend_pinecone import PineconeKBBackend
           return PineconeKBBackend()
       # ... other backends
   ```

4. **Set the environment variable**: `KB_VECTOR_BACKEND=pinecone`

## Design Rationale

**Separation of concerns**: Backend selection is decoupled from business logic. Ingestion and search code only interact with the `KBBackend` interface.

**Testability**: Mock backends can be swapped in for unit tests without a real database.

**Gradual migration**: If moving from BigQuery to PostgreSQL, you can run both backends in parallel and migrate data incrementally.

**Future flexibility**: New vector engines (like Milvus or LanceDB) can be added without touching existing code.

The abstraction is simple — four async methods — but powerful enough to support any vector search backend that understands embeddings, similarity scoring, and multi-tenancy.
