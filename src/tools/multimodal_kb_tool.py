"""Multimodal Knowledge Base tools for agent usage.

Exposes multimodal ingestion and search services with proper schema
exposition for LLM agents to understand and use correctly.

Key capabilities:
- Cross-modal search (text query retrieves relevant images and vice versa)
- Chapter-level document retrieval with on-demand content fetch
- Image search and reverse image lookup
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.services.multimodal_search_service import (
    MultimodalSearchService,
    MultimodalSearchResult,
    fetch_gcs_content,
    fetch_and_parse_gcs_content,
)


# -----------------------------------------------------------------------------
# Multimodal Search Tool
# -----------------------------------------------------------------------------

class MultimodalSearchInput(BaseModel):
    """Input schema for multimodal knowledge base search."""
    tenant_id: str = Field(..., description="Tenant identifier for multi-tenancy isolation")
    query: str = Field(..., description="Search query text - can find both documents AND images")
    top_k: int = Field(10, description="Maximum number of results per type (docs, images)")
    project_id: Optional[str] = Field(None, description="Optional project scope filter")
    include_images: bool = Field(True, description="Whether to include image results in search")
    search_type: str = Field(
        "all",
        description="Search scope: 'all' (docs+images), 'docs' (documents only), 'images' (images only)",
    )


@tool
async def multimodal_kb_search(
    tenant_id: str,
    query: str,
    top_k: int = 10,
    project_id: Optional[str] = None,
    include_images: bool = True,
    search_type: str = "all",
) -> Dict[str, Any]:
    """
    Search the multimodal knowledge base using 1408-D embeddings.
    
    This tool enables CROSS-MODAL search: a text query can retrieve relevant
    images, and vice versa. Documents and images are embedded in the same
    vector space using Vertex AI multimodalembedding@001.

    Input:
      - tenant_id (str, required): Tenant isolation key
      - query (str, required): Natural language search query
      - top_k (int, optional, default 10): Max results per type
      - project_id (str, optional): Scope to specific project
      - include_images (bool, optional, default True): Include image results
      - search_type (str, optional): 'all' | 'docs' | 'images'

    Output:
      {
        "results": [
          {
            "type": "doc" | "image",
            "id": "unique-id",
            "gcs_uri": "gs://bucket/path",
            "distance": 0.15,  # lower = more relevant
            "filename": "report.pdf",
            "essence_text": "Chapter summary...",
            "chapter_heading": "For images: parent chapter"
          }
        ],
        "query": "original query",
        "total_results": 15
      }

    Examples:
      - Query "revenue chart" may return both the PDF with revenue data AND
        the actual chart image extracted from that PDF.
      - Query "show me the architecture diagram" will find diagrams even if
        the word "architecture" only appears in the surrounding text.
    """
    tenant_id = str(tenant_id or "").strip()
    query = str(query or "").strip()
    if not tenant_id:
        raise ValueError("multimodal_kb_search requires 'tenant_id'.")
    if not query:
        raise ValueError("multimodal_kb_search requires 'query'.")

    top_k = int(top_k or 10)
    svc = MultimodalSearchService()

    if search_type == "docs":
        results = svc.search_docs(
            tenant_id=tenant_id,
            query=query,
            top_k=top_k,
            project_id_filter=str(project_id) if project_id else None,
        )
    elif search_type == "images":
        results = svc.search_images(
            tenant_id=tenant_id,
            query=query,
            top_k=top_k,
        )
    else:
        results = svc.search_all(
            tenant_id=tenant_id,
            query=query,
            top_k=top_k,
            project_id_filter=str(project_id) if project_id else None,
            include_images=include_images,
        )

    return {
        "results": [_result_to_dict(r) for r in results],
        "query": query,
        "total_results": len(results),
        "provider": "multimodal_bigquery",
    }


def _result_to_dict(r: MultimodalSearchResult) -> Dict[str, Any]:
    """Convert search result to dict for agent consumption."""
    return {
        "type": r.result_type,
        "id": r.id,
        "gcs_uri": r.gcs_uri,
        "distance": r.distance,
        "filename": r.filename,
        "part_number": r.part_number,
        "total_parts": r.total_parts,
        "chapter_heading": r.chapter_heading,
        "essence_text": r.essence_text,
    }


def multimodal_kb_search_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    """Schema hints for agent tool discovery and usage."""
    try:
        schema = MultimodalSearchInput.model_json_schema()
    except Exception:
        schema = MultimodalSearchInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Use this tool to search the multimodal knowledge base. It can find "
            "documents AND images using the same query. Results are ranked by "
            "semantic similarity (distance). Lower distance = more relevant."
        ),
        "capabilities": [
            "Text-to-document search",
            "Text-to-image search (cross-modal)",
            "Chapter-level retrieval",
            "Project-scoped filtering",
        ],
        "examples": [
            {
                "name": "find_revenue_data",
                "description": "Find documents and charts about revenue",
                "input": {
                    "tenant_id": "tnt_123",
                    "query": "Q4 revenue breakdown by region",
                    "top_k": 10,
                    "include_images": True,
                },
            },
            {
                "name": "find_architecture_diagrams",
                "description": "Find only images/diagrams",
                "input": {
                    "tenant_id": "tnt_123",
                    "query": "system architecture diagram",
                    "search_type": "images",
                    "top_k": 5,
                },
            },
            {
                "name": "project_scoped_search",
                "description": "Search within a specific project",
                "input": {
                    "tenant_id": "tnt_123",
                    "query": "marketing campaign results",
                    "project_id": "proj_marketing_2024",
                    "search_type": "docs",
                },
            },
        ],
    }


# -----------------------------------------------------------------------------
# Fetch Document Content Tool
# -----------------------------------------------------------------------------

class FetchDocumentContentInput(BaseModel):
    """Input schema for fetching full document content."""
    gcs_uri: str = Field(..., description="GCS URI from search results (gs://bucket/path)")
    filename: str = Field(..., description="Original filename for parser selection")
    parse_content: bool = Field(
        True,
        description="If True, parse deterministically (PyMuPDF) and return markdown. If False, return raw bytes.",
    )


@tool
async def fetch_document_content(
    gcs_uri: str,
    filename: str,
    parse_content: bool = True,
) -> Dict[str, Any]:
    """
    Fetch full document content from GCS after vector search.
    
    The multimodal KB stores only embeddings and gcs_uri in BigQuery.
    Use this tool to retrieve the actual document content when needed.

    Input:
      - gcs_uri (str, required): GCS URI from search result
      - filename (str, required): Original filename
      - parse_content (bool, optional, default True): Parse to markdown

    Output:
      {
        "content": "Full document text...",
        "gcs_uri": "gs://...",
        "content_type": "markdown" | "raw_bytes_base64"
      }

    Usage pattern:
      1. Use multimodal_kb_search to find relevant documents
      2. Use fetch_document_content to get full text for specific results
      3. Present the content to the user or use for further analysis
    """
    gcs_uri = str(gcs_uri or "").strip()
    filename = str(filename or "").strip()
    if not gcs_uri:
        raise ValueError("fetch_document_content requires 'gcs_uri'.")
    if not gcs_uri.startswith("gs://"):
        raise ValueError("gcs_uri must be a GCS path starting with 'gs://'")

    if parse_content:
        content = fetch_and_parse_gcs_content(gcs_uri, filename)
        return {
            "content": content,
            "gcs_uri": gcs_uri,
            "content_type": "markdown",
        }
    else:
        raw_bytes = fetch_gcs_content(gcs_uri)
        return {
            "content": base64.b64encode(raw_bytes).decode("utf-8"),
            "gcs_uri": gcs_uri,
            "content_type": "raw_bytes_base64",
            "size_bytes": len(raw_bytes),
        }


def fetch_document_content_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    """Schema hints for fetch document content tool."""
    try:
        schema = FetchDocumentContentInput.model_json_schema()
    except Exception:
        schema = FetchDocumentContentInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Use this tool AFTER multimodal_kb_search to fetch the full content "
            "of a document. The search only returns embeddings and URIs - this "
            "tool retrieves the actual text."
        ),
        "examples": [
            {
                "name": "fetch_pdf_content",
                "input": {
                    "gcs_uri": "gs://tnt-123-media/uploads/abc123/report.pdf",
                    "filename": "report.pdf",
                    "parse_content": True,
                },
            },
        ],
    }


# -----------------------------------------------------------------------------
# Image Search by Image Tool
# -----------------------------------------------------------------------------

class ImageSearchByImageInput(BaseModel):
    """Input schema for reverse image search."""
    tenant_id: str = Field(..., description="Tenant identifier")
    image_base64: str = Field(..., description="Base64-encoded image bytes")
    top_k: int = Field(10, description="Maximum results")
    search_docs: bool = Field(True, description="Also search for related documents")
    search_images: bool = Field(True, description="Search for similar images")


@tool
async def image_search_by_image(
    tenant_id: str,
    image_base64: str,
    top_k: int = 10,
    search_docs: bool = True,
    search_images: bool = True,
) -> Dict[str, Any]:
    """
    Search using an image as query (reverse image search).
    
    Because documents and images are in the same 1408-D vector space,
    an image query can find:
    - Similar images (visual similarity)
    - Related documents (semantic similarity to image content)

    Input:
      - tenant_id (str, required): Tenant isolation key
      - image_base64 (str, required): Base64-encoded image
      - top_k (int, optional, default 10): Max results
      - search_docs (bool, optional, default True): Find related docs
      - search_images (bool, optional, default True): Find similar images

    Output:
      {
        "results": [...],
        "query_type": "image",
        "total_results": 15
      }

    Use case examples:
      - User uploads a chart, find the source document
      - Find all similar diagrams across the knowledge base
      - Find documents that discuss the content shown in an image
    """
    tenant_id = str(tenant_id or "").strip()
    if not tenant_id:
        raise ValueError("image_search_by_image requires 'tenant_id'.")
    if not image_base64:
        raise ValueError("image_search_by_image requires 'image_base64'.")

    image_bytes = base64.b64decode(image_base64)
    svc = MultimodalSearchService()

    results = svc.search_by_image(
        tenant_id=tenant_id,
        image_bytes=image_bytes,
        top_k=int(top_k or 10),
        search_docs=search_docs,
        search_images=search_images,
    )

    return {
        "results": [_result_to_dict(r) for r in results],
        "query_type": "image",
        "total_results": len(results),
        "provider": "multimodal_bigquery",
    }


def image_search_by_image_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    """Schema hints for image search tool."""
    try:
        schema = ImageSearchByImageInput.model_json_schema()
    except Exception:
        schema = ImageSearchByImageInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Use this tool for reverse image search. Upload an image to find "
            "similar images AND related documents in the knowledge base."
        ),
        "capabilities": [
            "Reverse image search",
            "Image-to-document retrieval",
            "Cross-modal semantic matching",
        ],
        "examples": [
            {
                "name": "find_chart_source",
                "description": "Find the document containing this chart",
                "input": {
                    "tenant_id": "tnt_123",
                    "image_base64": "<base64 encoded image>",
                    "search_docs": True,
                    "search_images": False,
                },
            },
        ],
    }


# -----------------------------------------------------------------------------
# Tool Registry for Dynamic Loading
# -----------------------------------------------------------------------------

MULTIMODAL_KB_TOOLS = [
    {
        "name": "multimodal_kb_search",
        "function": multimodal_kb_search,
        "schema_hints": multimodal_kb_search_get_schema_hints,
        "description": "Search multimodal KB for documents and images using text query",
        "category": "knowledge_base",
    },
    {
        "name": "fetch_document_content",
        "function": fetch_document_content,
        "schema_hints": fetch_document_content_get_schema_hints,
        "description": "Fetch full document content from GCS after search",
        "category": "knowledge_base",
    },
    {
        "name": "image_search_by_image",
        "function": image_search_by_image,
        "schema_hints": image_search_by_image_get_schema_hints,
        "description": "Reverse image search to find similar images and related docs",
        "category": "knowledge_base",
    },
]


def get_multimodal_kb_tools() -> List[Dict[str, Any]]:
    """Get all multimodal KB tools with schema hints for agent discovery."""
    return MULTIMODAL_KB_TOOLS


def get_tool_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Get a specific tool by name."""
    for tool in MULTIMODAL_KB_TOOLS:
        if tool["name"] == name:
            return tool
    return None
