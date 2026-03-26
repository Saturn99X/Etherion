"""Multimodal vector search service for 1408-D embeddings.

the same query embedding, enabling cross-modal retrieval (text query
can retrieve relevant images and vice versa).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

from src.services.bigquery_service import BigQueryService
from src.services.multimodal_embedding_service import MultimodalEmbeddingService
from src.services.bq_schema_manager import ensure_tenant_multimodal_kb


def _coerce_metadata(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


@dataclass
class MultimodalSearchResult:
    """A single search result from multimodal vector search."""
    result_type: str  # "doc" or "image"
    id: str  # doc_id or image_id
    gcs_uri: str
    distance: float
    filename: Optional[str] = None
    part_number: Optional[int] = None
    total_parts: Optional[int] = None
    chapter_heading: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MultimodalSearchService:
    """BigQuery VECTOR_SEARCH for multimodal KB (1408-D embeddings).
    
    Searches both:
    - multimodal_docs: file-level chapter embeddings
    
    Both tables use the same 1408-D vector space from multimodalembedding@001,
    enabling cross-modal retrieval.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        bq: Optional[BigQueryService] = None,
        embedder: Optional[MultimodalEmbeddingService] = None,
    ) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required")
        self.bq = bq or BigQueryService(project_id=self.project_id)
        self._embedder = embedder

    @property
    def embedder(self) -> MultimodalEmbeddingService:
        if self._embedder is None:
            self._embedder = MultimodalEmbeddingService(project_id=self.project_id)
        return self._embedder

    def search_docs(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 10,
        project_id_filter: Optional[str] = None,
    ) -> List[MultimodalSearchResult]:
        """Search multimodal_docs table using text query.
        
        Args:
            tenant_id: Tenant isolation key
            query: Text query to embed and search
            top_k: Number of results to return
            project_id_filter: Optional project scope filter
            
        Returns:
            List of MultimodalSearchResult ordered by distance (ascending)
        """
        # Ensure tables exist
        try:
            ensure_tenant_multimodal_kb(self.bq.client, str(tenant_id))
        except Exception:
            pass

        # Embed query with multimodal embedder (1408-D)
        query_vec = self.embedder.embed_text(query)
        if not query_vec or all(v == 0.0 for v in query_vec):
            return []

        # Build VECTOR_SEARCH query
        table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
        cols = "doc_id, gcs_uri, filename, part_number, total_parts, source_doc_id, mime_type, metadata, vector_embedding"
        
        # Single-table design: docs have source_doc_id == NULL
        filters = ["source_doc_id IS NULL"]
        params: Dict[str, Any] = {
            "query_vec": [float(x) for x in query_vec],
            "top_k": int(top_k),
        }
        
        if project_id_filter:
            filters.append("project_id = @project_id")
            params["project_id"] = str(project_id_filter)
        
        where_clause = (" WHERE " + " AND ".join(filters)) if filters else ""

        sql = f"""
        SELECT base.*, distance
        FROM VECTOR_SEARCH(
          (SELECT {cols} FROM `{table_ref}`{where_clause}),
          'vector_embedding',
          (SELECT @query_vec AS query_embedding),
          'query_embedding',
          top_k => @top_k
        )
        ORDER BY distance ASC
        """

        try:
            rows = self.bq.query(
                sql,
                params=params,
                labels={"tenant_id": str(tenant_id), "component": "multimodal_search_docs"},
            )
        except Exception as e:
            logger.error(f"Multimodal docs search failed: {e}")
            return []

        results: List[MultimodalSearchResult] = []
        for r in rows:
            results.append(MultimodalSearchResult(
                result_type="doc",
                id=r.get("doc_id", ""),
                gcs_uri=r.get("gcs_uri", ""),
                distance=float(r.get("distance", 1.0)),
                filename=r.get("filename"),
                part_number=r.get("part_number"),
                total_parts=r.get("total_parts"),
                metadata=_coerce_metadata(r.get("metadata")),
            ))
        
        return results

    def search_images(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 10,
    ) -> List[MultimodalSearchResult]:
        """Search multimodal_images table using text query.

        Cross-modal: text query retrieves relevant images because
        both text and images are in the same 1408-D vector space.
        """
        # Ensure tables exist
        try:
            ensure_tenant_multimodal_kb(self.bq.client, str(tenant_id))
        except Exception:
            pass

        # Embed query
        query_vec = self.embedder.embed_text(query)
        if not query_vec or all(v == 0.0 for v in query_vec):
            return []

        # Single-table design: images are stored as rows in multimodal_docs with mime_type=image/*.
        table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
        cols = "doc_id, gcs_uri, filename, source_doc_id, mime_type, metadata, vector_embedding"

        sql = f"""
        SELECT base.*, distance
        FROM VECTOR_SEARCH(
          (SELECT {cols} FROM `{table_ref}` WHERE STARTS_WITH(mime_type, 'image/')),
          'vector_embedding',
          (SELECT @query_vec AS query_embedding),
          'query_embedding',
          top_k => @top_k
        )
        ORDER BY distance ASC
        """

        params = {
            "query_vec": [float(x) for x in query_vec],
            "top_k": int(top_k),
        }

        try:
            rows = self.bq.query(
                sql,
                params=params,
                labels={"tenant_id": str(tenant_id), "component": "multimodal_search_images"},
            )
        except Exception as e:
            logger.error(f"Multimodal images search failed: {e}")
            return []

        results: List[MultimodalSearchResult] = []
        for r in rows:
            md = _coerce_metadata(r.get("metadata"))
            results.append(MultimodalSearchResult(
                result_type="image",
                id=r.get("doc_id", ""),
                gcs_uri=r.get("gcs_uri", ""),
                distance=float(r.get("distance", 1.0)),
                filename=r.get("filename"),
                chapter_heading=(md.get("chapter_heading") if isinstance(md, dict) else None),
                metadata=md,
            ))
        
        return results

    def search_all(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 10,
        project_id_filter: Optional[str] = None,
        include_images: bool = True,
    ) -> List[MultimodalSearchResult]:
        """Search both docs and images, merge results by distance.
        
        Args:
            tenant_id: Tenant isolation key
            query: Text query
            top_k: Results per table (total may be 2x)
            project_id_filter: Optional project scope for docs
            include_images: Whether to include image results
            
        Returns:
            Combined results from both tables, sorted by distance
        """
        results: List[MultimodalSearchResult] = []
        
        # Search docs
        doc_results = self.search_docs(
            tenant_id=tenant_id,
            query=query,
            top_k=top_k,
            project_id_filter=project_id_filter,
        )
        results.extend(doc_results)
        
        # Search images
        if include_images:
            img_results = self.search_images(
                tenant_id=tenant_id,
                query=query,
                top_k=top_k,
            )
            results.extend(img_results)
        
        # Sort by distance (ascending = most similar first)
        results.sort(key=lambda r: r.distance)
        
        return results

    def search_by_image(
        self,
        tenant_id: str,
        image_bytes: bytes,
        top_k: int = 10,
        search_docs: bool = True,
        search_images: bool = True,
    ) -> List[MultimodalSearchResult]:
        """Search using an image as query (reverse image search + doc retrieval).
        
        Because docs and images are in the same vector space, an image query
        can retrieve both similar images AND relevant documents.
        """
        # Embed image
        query_vec = self.embedder.embed_image(image_bytes)
        if not query_vec or all(v == 0.0 for v in query_vec):
            return []

        results: List[MultimodalSearchResult] = []

        if search_docs:
            table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
            cols = "doc_id, gcs_uri, filename, part_number, total_parts, metadata, vector_embedding"
            
            sql = f"""
            SELECT base.*, distance
            FROM VECTOR_SEARCH(
              (SELECT {cols} FROM `{table_ref}` WHERE source_doc_id IS NULL),
              'vector_embedding',
              (SELECT @query_vec AS query_embedding),
              'query_embedding',
              top_k => @top_k
            )
            ORDER BY distance ASC
            """
            
            try:
                rows = self.bq.query(
                    sql,
                    params={"query_vec": [float(x) for x in query_vec], "top_k": int(top_k)},
                    labels={"tenant_id": str(tenant_id), "component": "multimodal_search_by_image_docs"},
                )
                for r in rows:
                    results.append(MultimodalSearchResult(
                        result_type="doc",
                        id=r.get("doc_id", ""),
                        gcs_uri=r.get("gcs_uri", ""),
                        distance=float(r.get("distance", 1.0)),
                        filename=r.get("filename"),
                        part_number=r.get("part_number"),
                        total_parts=r.get("total_parts"),
                        metadata=_coerce_metadata(r.get("metadata")),
                    ))
            except Exception as e:
                logger.error(f"Image-to-docs search failed: {e}")

        if search_images:
            table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
            cols = "doc_id, gcs_uri, filename, source_doc_id, mime_type, metadata, vector_embedding"
            
            sql = f"""
            SELECT base.*, distance
            FROM VECTOR_SEARCH(
              (SELECT {cols} FROM `{table_ref}` WHERE STARTS_WITH(mime_type, 'image/')),
              'vector_embedding',
              (SELECT @query_vec AS query_embedding),
              'query_embedding',
              top_k => @top_k
            )
            ORDER BY distance ASC
            """
            
            try:
                rows = self.bq.query(
                    sql,
                    params={"query_vec": [float(x) for x in query_vec], "top_k": int(top_k)},
                    labels={"tenant_id": str(tenant_id), "component": "multimodal_search_by_image_images"},
                )
                for r in rows:
                    md = _coerce_metadata(r.get("metadata"))
                    results.append(MultimodalSearchResult(
                        result_type="image",
                        id=r.get("doc_id", ""),
                        gcs_uri=r.get("gcs_uri", ""),
                        distance=float(r.get("distance", 1.0)),
                        filename=r.get("filename"),
                        chapter_heading=(md.get("chapter_heading") if isinstance(md, dict) else None),
                        metadata=md,
                    ))
            except Exception as e:
                logger.error(f"Image-to-images search failed: {e}")

        results.sort(key=lambda r: r.distance)
        return results


def fetch_gcs_content(gcs_uri: str, project_id: Optional[str] = None) -> bytes:
    """On-demand fetch of file content from GCS.
    
    Used to retrieve full document content after vector search returns
    only the gcs_uri (no raw text stored in BigQuery).
    """
    from google.cloud import storage
    
    project = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    client = storage.Client(project=project)
    
    bucket_name, blob_path = gcs_uri.replace("gs://", "").split("/", 1)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    
    return blob.download_as_bytes()


def fetch_and_parse_gcs_content(
    gcs_uri: str,
    filename: str,
    project_id: Optional[str] = None,
) -> str:
    """Fetch from GCS and parse deterministically to get text content."""
    from src.services.pymupdf_parser_service import PyMuPDFParserService

    content = fetch_gcs_content(gcs_uri, project_id)
    parser = PyMuPDFParserService()
    result = parser.parse_bytes(content, filename)
    return result.markdown
