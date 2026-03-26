# Knowledge Base Documentation

Welcome to the Etherion AI knowledge base architecture guide. This section explains how the platform stores and searches through tenant documents using semantic vector search instead of traditional full-text search.

## What Is the Knowledge Base?

In Etherion, each tenant maintains a private **knowledge base** — a searchable document store where agents can retrieve relevant context before reasoning or generating responses. Unlike traditional keyword-based search, the knowledge base finds documents based on *semantic meaning*: when an agent needs information, it searches for documents whose *meaning* aligns with the query, not just documents that contain the same words.

The knowledge base is organized by projects. Each project can ingest files (PDFs, text documents, etc.), and Etherion extracts and stores text chunks with their vector embeddings — compressed numerical representations that capture the semantic content. When an agent searches, it translates the query into the same embedding space and retrieves the nearest neighbors.

## Why Vector Search Instead of Full-Text Search?

Full-text search matches keywords. If you search for "troubleshoot login", it returns only documents containing those exact words. But a document titled "How to fix authentication errors" might be the perfect answer, yet it gets missed because it uses different vocabulary.

Semantic search solves this by embedding documents and queries as vectors in a high-dimensional space. Similar concepts live near each other in this space. When you query "troubleshoot login", the embedding captures the *meaning* (user authentication problems), and the search retrieves documents about authentication, credential errors, session timeouts — anything semantically related, even if the wording differs.

This is especially powerful for Etherion agents, which reason over retrieved context. Instead of forcing agents to work around keyword mismatches, semantic search gives them the most relevant information, regardless of terminology.

## Architecture Overview

```
┌──────────────────┐
│  File Upload     │
│  (MinIO)         │
└────────┬─────────┘
         │
         v
┌──────────────────────┐
│ Text Extraction      │
│ & Chunking           │
└────────┬─────────────┘
         │
         v
┌──────────────────────┐
│ Embedding Service    │
│ (Vector Generation)  │
└────────┬─────────────┘
         │
         v
┌──────────────────────────────────┐
│ PostgreSQL + pgvector            │
│ (Vector Storage & Search)        │
└────────────────────────────────────┘
```

The flow is simple: upload a file → extract text → generate embeddings → store vectors in PostgreSQL. When agents search, queries go through the same embedding pipeline and retrieve nearest neighbors.

## Key Concepts

**Knowledge Base (KnowledgeBase)**: A per-tenant, per-project document store. Each KnowledgeBase has a unique identifier and tracks creation timestamp, type (project or personal), and description.

**Document (Document)**: A text chunk with its corresponding embedding vector. Each document stores the original text, its embedding, metadata (like source filename), and a storage URI pointing to MinIO where the original file lives.

**Embedding**: A list of 1536 floating-point numbers (configurable via `KB_EMBEDDING_DIM`) that represents the semantic meaning of text. Two documents with similar embeddings should have similar meaning.

**KBBackend**: An abstract interface that handles vector search and document storage. The default implementation uses PostgreSQL with pgvector; a legacy BigQuery path is retained for backward compatibility but not the primary path.

## Storage

Documents are stored in two places:

1. **PostgreSQL with pgvector**: The embedding vector and text chunk live here, indexed for fast similarity search. This is the primary store for semantic queries.

2. **MinIO object storage**: The original uploaded file persists here. Each document record has a `storage_uri` (e.g., `s3://documents/project-123/file.pdf`) for retrieval if needed.

The split keeps the search index lightweight while retaining full file history.

## Tenant Isolation

All knowledge base operations respect tenant boundaries. Every KnowledgeBase and Document record carries a `tenant_id`, ensuring that one tenant cannot query or modify another tenant’s documents. This is critical for multi-tenant SaaS security.

## Next Steps

To understand how this system works in detail, read:

- **how-vectors-work.md** — How embeddings represent meaning and why they enable similarity search.
- **document-ingestion.md** — The full pipeline from file upload to searchable document.
- **vector-search.md** — How agents retrieve documents at query time.
- **kb-backend-abstraction.md** — The KBBackend interface and factory pattern.
