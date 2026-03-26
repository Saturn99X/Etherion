# Vector Search: Retrieving Documents at Query Time

## The Search Pipeline

When an agent or user queries the knowledge base, Etherion follows a straightforward semantic search pipeline:

```
┌──────────────────────────┐
│ Query String             │
│ e.g., "How to reset      │
│  password?"              │
└────────┬─────────────────┘
         │
         v
┌──────────────────────────────────────────┐
│ Embed Query                              │
│ (same embedding model as ingestion)      │
│ → Query vector: [0.12, 0.81, -0.19, ...] │
└────────┬─────────────────────────────────┘
         │
         v
┌──────────────────────────────────────────┐
│ PostgreSQL Vector Search                 │
│ SELECT documents WHERE tenant_id=:tid    │
│ ORDER BY embedding <=> :query_vec        │
│ LIMIT :top_k                             │
└────────┬─────────────────────────────────┘
         │
         v
┌──────────────────────────────────────────┐
│ Rank by Similarity Score                 │
│ (1 - cosine_distance)                    │
│ Returns top_k results:                   │
│ [{doc_id, text_chunk, score, metadata}] │
└──────────────────────────────────────────┘
```

## The SQL Query

The actual PostgreSQL query that retrieves documents is elegant and efficient:

```sql
SELECT d.doc_id, d.text_chunk, d.metadata_json, d.storage_uri,
       1 - (d.embedding <=> CAST(:vec AS vector)) AS score
FROM document d
JOIN knowledgebase kb ON kb.id = d.kb_id
WHERE d.tenant_id = :tid
  AND kb.project_id = :project_id  -- Optional: filter by project
  AND kb.kb_type = :kb_type        -- Optional: filter by KB type
ORDER BY score DESC
LIMIT :k
```

Let's break down what's happening:

**CAST(:vec AS vector)**: Converts the incoming query embedding (a string representation like `"[0.12, 0.81, -0.19, ...]"`) into pgvector's native vector type.

**d.embedding <=> CAST(:vec AS vector)**: This is the cosine distance operator. It computes the distance between the stored embedding and the query embedding. The result is 0 for identical vectors, up to 2 for opposite vectors.

**1 - (...)**: Converts distance to similarity, so that higher values are better. A similarity of 1.0 means identical, 0.0 means orthogonal, and -1.0 means opposite.

**JOIN knowledgebase kb**: Ensures we only retrieve documents from knowledge bases that belong to the searched project or meet filter criteria.

**WHERE d.tenant_id = :tid**: Critical for multi-tenancy — only rows belonging to this tenant are returned.

**ORDER BY score DESC LIMIT :k**: Returns the top k most similar documents, sorted from highest to lowest similarity.

## Real Python Implementation

The `PgvectorKBBackend` class executes this search logic:

```python
from sqlalchemy import text
from src.database.db import get_session

class PgvectorKBBackend(KBBackend):
    async def search(
        self,
        tenant_id: str,
        query: str,
        query_embedding: List[float],  # Pre-computed embedding
        top_k: int = 10,
        project_id: Optional[str] = None,
        kb_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return top_k documents with similarity scores."""

        async for session in get_session():
            params: Dict[str, Any] = {
                "tid": tenant_id,
                "vec": str(query_embedding),  # Convert list to string
                "k": top_k,
            }

            sql = """
                SELECT d.doc_id, d.text_chunk, d.metadata_json, d.storage_uri,
                       1 - (d.embedding <=> CAST(:vec AS vector)) AS score
                FROM document d
                JOIN knowledgebase kb ON kb.id = d.kb_id
                WHERE d.tenant_id = :tid
            """

            # Optional filters
            if project_id:
                sql += " AND kb.project_id = :project_id"
                params["project_id"] = project_id
            if kb_type:
                sql += " AND kb.kb_type = :kb_type"
                params["kb_type"] = kb_type

            sql += " ORDER BY score DESC LIMIT :k"

            # Execute and fetch results
            result = await session.execute(text(sql), params)
            rows = result.fetchall()

            # Transform rows into dictionaries
            return [
                {
                    "doc_id": r.doc_id,
                    "text_chunk": r.text_chunk,
                    "score": float(r.score),
                    "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
                    "storage_uri": r.storage_uri,
                }
                for r in rows
            ]
        return []
```

Key observations:

- **Pre-computed embedding**: The query embedding is passed as `query_embedding: List[float]`, not the raw query string. This means the embedding computation happens *before* the database query.
- **String conversion**: The embedding list is converted to a string for the SQL parameter (`str(query_embedding)`). pgvector understands this format.
- **Async/await**: The search runs asynchronously using SQLAlchemy's async session, allowing high concurrency.
- **JSON parsing**: Metadata is stored as JSON text in the database and parsed back into Python dicts.

## Ranking by Similarity Score

Results are ranked by the computed similarity score (0 to 1, where 1 is most similar). This is a simple numerical ranking — no custom re-ranking or ML models are applied at this stage. The assumption is that cosine similarity in embedding space accurately reflects semantic relevance.

In practice, you'll see results like:

```
Doc 1: "Resetting your password step by step..."
  → Score: 0.987 (almost identical meaning to query)

Doc 2: "Forgot your password? Use the recovery link..."
  → Score: 0.954 (very similar, slightly different wording)

Doc 3: "Account security best practices..."
  → Score: 0.812 (related but broader topic)

Doc 4: "What's the weather today?"
  → Score: 0.023 (completely unrelated, returned by chance)
```

With `top_k=3`, only the first three results are returned to the agent. Setting a higher `top_k` gives more context but increases noise. Setting it too low misses relevant documents.

## Performance: HNSW Index

With millions of documents, comparing every document's embedding to the query embedding would be slow. PostgreSQL's pgvector extension supports Hierarchical Navigable Small World (HNSW) indexes, which dramatically speed up similarity search:

```sql
CREATE INDEX idx_document_embedding_hnsw
  ON document USING hnsw (embedding vector_cosine_ops)
  WITH (m=16, ef_construction=200);
```

HNSW is a graph-based index where each vector has ~16 neighbors, connected in a hierarchy. To search:

1. Start at the top layer's entry point
2. Move to the nearest neighbor to the query
3. Drop down a layer and repeat
4. Return the k-nearest neighbors found

This reduces search complexity from O(n) to O(log n), making queries against billion-sized indexes practical.

## Filtering by Project and KB Type

The search query supports optional filtering to narrow results:

**Filter by project**: `project_id` restricts results to documents in a specific project's knowledge bases.

**Filter by KB type**: `kb_type` (e.g., "project" vs. "personal") allows searching different knowledge base categories separately.

These filters are baked into the SQL WHERE clause and are evaluated *before* the similarity computation, so they don't impact performance.

## Agent Usage

Agents call the knowledge base search through the `KBBackend` interface:

```python
backend = get_kb_backend()  # Factory returns PgvectorKBBackend by default

results = await backend.search(
    tenant_id="tenant-12345",
    query="How do I reset my password?",
    query_embedding=embedding_vector,  # Pre-computed by embedding service
    top_k=5,
    project_id="proj-456",  # Optional: search only this project
)

for result in results:
    context = result["text_chunk"]
    score = result["score"]
    metadata = result["metadata"]

    # Agent uses context in its reasoning
    agent.reason_with_context(context, score)
```

The agent receives up to 5 ranked documents and uses the highest-scoring ones as context for reasoning. This dramatically improves answer quality compared to retrieval-free prompting.

## Practical Considerations

**Embedding consistency**: Query embeddings must be computed by the *same* embedding model as the ingestion pipeline. Switching models invalidates the entire index.

**Similarity thresholds**: You might want to discard results below a certain score (e.g., < 0.5) to avoid hallucination on unrelated documents. The scoring is open-ended — no hard lower bound.

**Latency**: A single search typically takes 10-50ms on a well-indexed table, even with millions of documents. Embedding the query (calling the embedding API) often takes longer than the database query.

**Cost**: Each search requires embedding the query. This cost is per-query, not per-document, so it scales linearly with query volume, not knowledge base size.
