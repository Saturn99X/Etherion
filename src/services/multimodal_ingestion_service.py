"""Multimodal ingestion service using deterministic parsing + multimodalembedding@001.

Implements chapter-level retrieval:
- Deterministic parser extracts text/images → structured Markdown
- Chapter essence extraction (heading + first 128 tokens)
- 1408-D multimodal embeddings for text and images
- One BigQuery row per file (or file-part if >300k tokens)
- No raw text in BigQuery (only gcs_uri for on-demand fetch)
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

try:
    from google.cloud import storage, bigquery
except Exception:
    storage = None
    bigquery = None

from src.services.bq_schema_manager import (
    ensure_tenant_dataset,
    ensure_tenant_multimodal_kb,
    multimodal_docs_schema,
)
from src.services.pymupdf_parser_service import (
    PyMuPDFParserService,
    DocumentParseResult,
    ChapterEssence,
    ExtractedImage,
    should_split_document,
    split_chapters_into_parts,
)
from src.services.multimodal_embedding_service import MultimodalEmbeddingService
from src.services.pricing.cost_tracker import CostTracker


@dataclass
class MultimodalIngestionResult:
    """Result of multimodal ingestion."""
    tenant_id: str
    gcs_uri: str
    filename: str
    mime_type: str
    size_bytes: int
    doc_ids: List[str]  # One per file-part
    image_ids: List[str]
    chapter_count: int
    part_count: int
    total_tokens: int
    job_id: Optional[str] = None
    errors: List[str] = field(default_factory=list)


class MultimodalIngestionService:
    """Ingest documents using deterministic parsing + multimodalembedding@001.
    
    Pipeline:
    1. Upload bytes to GCS
    2. Parse deterministically → Markdown + chapters + images
    3. Extract chapter essence (heading + first 128 tokens)
    4. Split if >300k tokens
    5. Embed with multimodalembedding@001 (1408-D)
    6. Insert to BigQuery (one row per file/part)
    """

    MAX_TOKENS_PER_PART = 300_000

    @staticmethod
    def _count_tokens_best_effort(content: bytes) -> int:
        try:
            import tiktoken

            enc = tiktoken.get_encoding("cl100k_base")
            text = content.decode("utf-8", errors="replace")
            return len(enc.encode(text))
        except Exception:
            return 0

    def __init__(self, project_id: Optional[str] = None) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required")
        if storage is None or bigquery is None:
            raise RuntimeError("google-cloud-storage and google-cloud-bigquery are required")

        self._storage_client: Any = None
        self._bq_client: Any = None
        self._parser: Optional[PyMuPDFParserService] = None
        self._embedder: Optional[MultimodalEmbeddingService] = None

    @property
    def storage(self) -> Any:
        if self._storage_client is None:
            if storage is None:
                raise RuntimeError("google-cloud-storage is required")
            self._storage_client = storage.Client(project=self.project_id)
        return self._storage_client

    @property
    def bq(self) -> Any:
        if self._bq_client is None:
            if bigquery is None:
                raise RuntimeError("google-cloud-bigquery is required")
            self._bq_client = bigquery.Client(project=self.project_id)
        return self._bq_client

    @property
    def parser(self) -> PyMuPDFParserService:
        if self._parser is None:
            self._parser = PyMuPDFParserService()
        return self._parser

    @property
    def embedder(self) -> MultimodalEmbeddingService:
        if self._embedder is None:
            self._embedder = MultimodalEmbeddingService(project_id=self.project_id)
        return self._embedder

    @property
    def docling(self) -> Any:
        raise RuntimeError("Docling pipeline is not available")

    def _parse_text_bytes(self, content: bytes, filename: str, mime_type: str) -> DocumentParseResult:
        text = content.decode("utf-8", errors="replace")
        heading = filename or "Document"
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            token_count = len(enc.encode(text))
            essence_body = enc.decode(enc.encode(text)[:128])
        except Exception:
            token_count = 0
            essence_body = text[:512]

        essence_text = (f"{heading}\n\n{essence_body}").strip()
        
        return DocumentParseResult(
            markdown=text,
            chapters=[
                ChapterEssence(
                    heading=heading,
                    level=1,
                    start_line=0,
                    essence_text=essence_text,
                    full_content=text,
                    images=[],
                )
            ],
            images=[],
            total_chars=len(text),
            estimated_tokens=token_count,
            source_filename=filename,
            mime_type=mime_type,
            metadata={"parser": "text_fallback"},
        )

    def _tenant_bucket(self, tenant_id: str, suffix: str = "media") -> Any:
        bucket_prefix = os.getenv("GCS_BUCKET_PREFIX", "tnt")
        bucket_name = f"{bucket_prefix}-{tenant_id}-{suffix}"
        return self.storage.bucket(bucket_name)

    def _ensure_bucket(self, bucket_name: str) -> None:
        bucket_location = os.getenv("GCS_BUCKET_LOCATION", "US")
        try:
            bucket = self.storage.create_bucket(bucket_name, location=bucket_location)
            bucket.iam_configuration.uniform_bucket_level_access_enabled = True
            bucket.patch()
        except Exception as e:
            msg = str(e).lower()
            if "already exists" in msg or "conflict" in msg or "409" in msg:
                return
            raise

    def upload_bytes(
        self,
        tenant_id: str,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> str:
        """Upload bytes to GCS and return gs:// URI."""
        content_hash = hashlib.sha256(content).hexdigest()
        object_name = f"uploads/{content_hash}/{filename}"
        bucket = self._tenant_bucket(tenant_id, "media")
        blob = bucket.blob(object_name)
        
        try:
            blob.upload_from_string(content, content_type=mime_type)
        except Exception as e:
            msg = str(e).lower()
            if "bucket does not exist" in msg or "the specified bucket does not exist" in msg:
                self._ensure_bucket(bucket.name)
                blob.upload_from_string(content, content_type=mime_type)
            else:
                raise
        
        try:
            job_id = None
            try:
                job_id = getattr(self, "_current_job_id", None)
            except Exception:
                job_id = None
            if job_id:
                import asyncio as _asyncio

                async def _record() -> None:
                    tracker = CostTracker()
                    await tracker.record_gcs_upload(str(job_id), bytes_uploaded=len(content), tenant_id=str(tenant_id))

                try:
                    loop = _asyncio.get_running_loop()
                    loop.create_task(_record())
                except RuntimeError:
                    _asyncio.run(_record())
        except Exception:
            pass

        return f"gs://{bucket.name}/{object_name}"

    def _ingest_pdf_streaming(
        self,
        *,
        tenant_id: str,
        gcs_uri: str,
        content: bytes,
        filename: str,
        mime_type: str,
        size_bytes: int,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        progress: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> MultimodalIngestionResult:
        errors: List[str] = []

        skip_embedding = os.getenv("SKIP_EMBEDDING", "").lower() in ("true", "1", "yes")

        try:
            import fitz  # PyMuPDF
        except ModuleNotFoundError as e:
            raise RuntimeError("PyMuPDF is required for PDF ingestion") from e

        try:
            import tiktoken
        except Exception:
            tiktoken = None

        try:
            max_pages_env = int(os.getenv("INGEST_MAX_DOC_CHUNKS", "0") or "0")
        except Exception:
            max_pages_env = 0

        extract_images = os.getenv("INGEST_PDF_EXTRACT_IMAGES", "0").lower() in {"1", "true", "yes"}

        try:
            if progress:
                progress("PARSE", {"substage": "START", "mode": "stream"})
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as e:
            errors.append(f"Parse error: {e}")
            return MultimodalIngestionResult(
                tenant_id=str(tenant_id),
                gcs_uri=str(gcs_uri),
                filename=str(filename),
                mime_type=str(mime_type),
                size_bytes=int(size_bytes),
                doc_ids=[],
                image_ids=[],
                chapter_count=0,
                part_count=0,
                total_tokens=0,
                job_id=job_id,
                errors=errors,
            )

        page_limit = doc.page_count
        if max_pages_env > 0:
            page_limit = min(page_limit, max_pages_env)

        enc = None
        if tiktoken is not None:
            try:
                enc = tiktoken.get_encoding("cl100k_base")
            except Exception:
                enc = None

        try:
            chars_per_token = int(os.getenv("INGEST_ESTIMATED_CHARS_PER_TOKEN", "4") or "4")
        except Exception:
            chars_per_token = 4

        try:
            bucket_name, blob_path = str(gcs_uri).replace("gs://", "").split("/", 1)
            bucket = self.storage.bucket(bucket_name)
            if blob_path.startswith("uploads/") and len(blob_path.split("/")) >= 3:
                prefix = "/".join(blob_path.split("/")[:2])
            else:
                prefix = f"uploads/{hashlib.sha256(content).hexdigest()}"
        except Exception:
            bucket = self._tenant_bucket(tenant_id, "media")
            prefix = f"uploads/{hashlib.sha256(content).hexdigest()}"

        base_name = filename.rsplit(".", 1)[0] if "." in filename else filename

        def _safe_upload_part(part_bytes: bytes, object_name: str, content_type: str) -> str:
            blob = bucket.blob(object_name)
            try:
                blob.upload_from_string(part_bytes, content_type=content_type)
            except Exception as e:
                msg = str(e).lower()
                if "bucket does not exist" in msg or "the specified bucket does not exist" in msg:
                    self._ensure_bucket(bucket.name)
                    blob.upload_from_string(part_bytes, content_type=content_type)
                else:
                    raise

            if job_id:
                try:
                    import asyncio as _asyncio

                    async def _record() -> None:
                        tracker = CostTracker()
                        await tracker.record_gcs_upload(str(job_id), bytes_uploaded=len(part_bytes), tenant_id=str(tenant_id))

                    try:
                        loop = _asyncio.get_running_loop()
                        loop.create_task(_record())
                    except RuntimeError:
                        _asyncio.run(_record())
                except Exception:
                    pass
            return f"gs://{bucket.name}/{object_name}"

        part_doc_ids: List[str] = []
        part_rows_doc_ids: List[str] = []
        part_number = 0
        total_tokens = 0
        total_pages = 0

        current_pages: List[int] = []
        current_token_count = 0
        current_essences: List[str] = []

        seen_hashes: set[str] = set()
        images: List[ExtractedImage] = []

        def _flush_part(*, is_final: bool) -> None:
            nonlocal part_number, current_pages, current_token_count, current_essences

            if not current_pages:
                return

            part_number += 1
            part_name = f"{base_name}_{part_number:03d}.pdf"

            try:
                from_page = int(min(current_pages)) - 1
                to_page = int(max(current_pages)) - 1
                part_doc = fitz.open()
                part_doc.insert_pdf(doc, from_page=from_page, to_page=to_page)
                part_bytes = part_doc.tobytes()
                part_doc.close()
            except Exception as e:
                errors.append(f"PDF part build error: {e}")
                part_bytes = b""

            vector: List[float]
            if skip_embedding:
                vector = [0.0] * self.embedder.DIMENSION
            else:
                try:
                    vectors = self.embedder.embed_texts(list(current_essences))
                except Exception as e:
                    errors.append(f"Embed error: {e}")
                    vectors = []
                if not vectors:
                    vector = [0.0] * self.embedder.DIMENSION
                else:
                    n = float(len(vectors))
                    acc = [0.0] * self.embedder.DIMENSION
                    for v in vectors:
                        if not v or len(v) != self.embedder.DIMENSION:
                            continue
                        for i in range(self.embedder.DIMENSION):
                            acc[i] += float(v[i])
                    vector = [x / n for x in acc]

            part_object_name = f"{prefix}/parts/{part_name}"
            try:
                part_gcs_uri = _safe_upload_part(part_bytes, part_object_name, "application/pdf")
            except Exception as e:
                errors.append(f"GCS part upload error: {e}")
                part_gcs_uri = str(gcs_uri)

            doc_id = str(uuid.uuid4())
            part_doc_ids.append(doc_id)
            part_rows_doc_ids.append(doc_id)

            row = {
                "doc_id": doc_id,
                "tenant_id": str(tenant_id),
                "project_id": str(project_id) if project_id else None,
                "gcs_uri": part_gcs_uri,
                "filename": filename,
                "part_name": part_name,
                "part_number": part_number,
                "total_parts": int(part_number) if is_final else None,
                "mime_type": "application/pdf",
                "size_bytes": int(len(part_bytes)),
                "source_doc_id": None,
                "chapter_count": int(len(current_pages)),
                "vector_embedding": vector,
                "metadata": json.dumps({
                    "parser": "pymupdf_stream",
                    "job_id": job_id,
                    "source_gcs_uri": str(gcs_uri),
                    "chapter_count": int(len(current_pages)),
                    "page_start": int(min(current_pages)),
                    "page_end": int(max(current_pages)),
                    "token_count": int(current_token_count),
                }),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

            table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
            try:
                self.bq.insert_rows_json(table_ref, [row])
                if job_id:
                    try:
                        import asyncio as _asyncio

                        async def _record() -> None:
                            tracker = CostTracker()
                            await tracker.record_api_call(str(job_id), "bigquery", tenant_id=str(tenant_id))
                            await tracker.record_bigquery_storage(
                                str(job_id),
                                active_gb_month=float(int(row.get("size_bytes") or 0)) / (1024.0 ** 3),
                                tenant_id=str(tenant_id),
                            )

                        try:
                            loop = _asyncio.get_running_loop()
                            loop.create_task(_record())
                        except RuntimeError:
                            _asyncio.run(_record())
                    except Exception:
                        pass
            except Exception as e:
                errors.append(f"BQ insert error: {e}")

            if progress:
                progress("PART_FLUSH", {"part": part_number, "pages": int(len(current_pages))})

            current_pages = []
            current_token_count = 0
            current_essences = []

        try:
            for page_idx in range(page_limit):
                page = doc.load_page(page_idx)
                page_number = page_idx + 1
                heading = f"Page {page_number}"

                text = (page.get_text("text") or "").strip()
                if enc is not None:
                    toks = enc.encode(text) if text else []
                    page_tokens = len(toks)
                    essence_body = enc.decode(toks[:128]).strip() if toks else ""
                else:
                    page_tokens = int(len(text) / max(1, chars_per_token)) if text else 0
                    essence_body = (text[:1024] or "").strip()

                if current_token_count + page_tokens > self.MAX_TOKENS_PER_PART and current_pages:
                    _flush_part(is_final=False)

                current_pages.append(page_number)
                total_pages += 1
                current_token_count += page_tokens
                total_tokens += page_tokens

                if extract_images:
                    try:
                        for img in page.get_images(full=True) or []:
                            xref = img[0]
                            base = doc.extract_image(xref)
                            if not base:
                                continue
                            img_bytes = base.get("image")
                            if not img_bytes:
                                continue
                            
                            # Skip "ghost images" (1x1 icons, transparency masks, etc)
                            # PyMuPDF base['width'] and base['height'] are available
                            width = base.get("width", 0)
                            height = base.get("height", 0)
                            if width < 40 or height < 40:
                                continue

                            ext = (base.get("ext") or "png").lower()
                            img_mime = f"image/{ext}" if ext else "image/png"
                            h = hashlib.sha256(img_bytes).hexdigest()[:16]
                            if h in seen_hashes:
                                continue
                            seen_hashes.add(h)
                            images.append(
                                ExtractedImage(
                                    image_bytes=img_bytes,
                                    mime_type=img_mime,
                                    chapter_heading=heading,
                                    page_number=page_number,
                                    description=None,
                                )
                            )
                    except Exception as e:
                        errors.append(f"Image extract error: {e}")

                essence_text = (essence_body or "").strip()
                current_essences.append(essence_text)

            _flush_part(is_final=True)
        finally:
            try:
                doc.close()
            except Exception:
                pass

        if progress:
            progress("PARSE", {"substage": "DONE", "pages": int(total_pages), "tokens": int(total_tokens)})

        if part_number > 1 and bigquery is not None:
            try:
                table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
                ddl_timeout_s = float(os.getenv("BIGQUERY_DDL_TIMEOUT_SECONDS", "30") or "30")
                sql = f"""
                UPDATE `{table_ref}`
                SET total_parts = @total_parts
                WHERE doc_id IN UNNEST(@doc_ids)
                """
                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("total_parts", "INT64", int(part_number)),
                        bigquery.ArrayQueryParameter("doc_ids", "STRING", list(part_rows_doc_ids)),
                    ]
                )
                # Streaming inserts can leave rows in the streaming buffer briefly; retry with backoff.
                for attempt in range(6):
                    try:
                        self.bq.query(sql, job_config=job_config).result(timeout=ddl_timeout_s)
                        break
                    except Exception as e:
                        msg = str(e)
                        if "streaming buffer" in msg.lower() and attempt < 5:
                            time.sleep(5 * (attempt + 1))
                            continue
                        raise
            except Exception as e:
                errors.append(f"BQ update total_parts error: {e}")

        image_ids: List[str] = []
        image_rows: List[Dict[str, Any]] = []
        if images:
            if progress:
                progress("EMBED_IMAGE", {"stage": "START", "count": len(images)})

            def _process_image(img: ExtractedImage) -> Optional[Dict[str, Any]]:
                try:
                    parent_doc_id = part_doc_ids[0] if part_doc_ids else str(uuid.uuid4())
                    img_gcs_uri = self.upload_image(tenant_id, img, parent_doc_id)
                    img_vector = self.embedder.embed_image(img.image_bytes, contextual_text=img.chapter_heading)
                    image_id = str(uuid.uuid4())
                    return {
                        "doc_id": image_id,
                        "tenant_id": str(tenant_id),
                        "project_id": str(project_id) if project_id else None,
                        "gcs_uri": img_gcs_uri,
                        "filename": f"{img.content_hash}.{img.mime_type.split('/')[-1] if '/' in img.mime_type else 'img'}",
                        "mime_type": img.mime_type,
                        "size_bytes": len(img.image_bytes),
                        "source_doc_id": parent_doc_id,
                        "chapter_count": None,
                        "vector_embedding": img_vector,
                        "metadata": json.dumps({
                            "source_doc_id": parent_doc_id,
                            "chapter_heading": img.chapter_heading,
                            "page_number": img.page_number,
                            "description": img.description,
                        }),
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                except Exception as e:
                    errors.append(f"Image process error: {e}")
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                futures = [ex.submit(_process_image, img) for img in images]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        image_rows.append(result)
                        image_ids.append(result["doc_id"])

            if image_rows:
                table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
                try:
                    errs = self.bq.insert_rows_json(table_ref, image_rows)
                    if errs:
                        errors.append(f"Image batch insert error: {errs}")
                    if job_id:
                        try:
                            import asyncio as _asyncio

                            total_bytes = 0
                            try:
                                total_bytes = sum(int(r.get("size_bytes") or 0) for r in image_rows)
                            except Exception:
                                total_bytes = 0

                            async def _record() -> None:
                                tracker = CostTracker()
                                await tracker.record_api_call(str(job_id), "bigquery", tenant_id=str(tenant_id))
                                if total_bytes > 0:
                                    await tracker.record_bigquery_storage(
                                        str(job_id),
                                        active_gb_month=float(total_bytes) / (1024.0 ** 3),
                                        tenant_id=str(tenant_id),
                                    )

                            try:
                                loop = _asyncio.get_running_loop()
                                loop.create_task(_record())
                            except RuntimeError:
                                _asyncio.run(_record())
                        except Exception:
                            pass
                except Exception as e:
                    errors.append(f"Image batch insert failed: {e}")

            if progress:
                progress("EMBED_IMAGE", {"stage": "DONE", "processed": len(image_rows)})

        return MultimodalIngestionResult(
            tenant_id=str(tenant_id),
            gcs_uri=str(gcs_uri),
            filename=str(filename),
            mime_type=str(mime_type),
            size_bytes=int(size_bytes),
            doc_ids=part_doc_ids,
            image_ids=image_ids,
            chapter_count=int(total_pages),
            part_count=int(part_number),
            total_tokens=int(total_tokens),
            job_id=job_id,
            errors=errors,
        )

    def upload_image(
        self,
        tenant_id: str,
        image: ExtractedImage,
        doc_id: str,
    ) -> str:
        """Upload extracted image to GCS."""
        image_hash = image.content_hash
        ext = "png" if image.mime_type == "image/png" else "jpg"
        object_name = f"images/{doc_id}/{image_hash}.{ext}"
        bucket = self._tenant_bucket(tenant_id, "media")
        blob = bucket.blob(object_name)
        
        try:
            blob.upload_from_string(image.image_bytes, content_type=image.mime_type)
        except Exception as e:
            msg = str(e).lower()
            if "bucket does not exist" in msg:
                self._ensure_bucket(bucket.name)
                blob.upload_from_string(image.image_bytes, content_type=image.mime_type)
            else:
                raise

        try:
            job_id = None
            try:
                job_id = getattr(self, "_current_job_id", None)
            except Exception:
                job_id = None
            if job_id:
                import asyncio as _asyncio

                async def _record() -> None:
                    tracker = CostTracker()
                    await tracker.record_gcs_upload(str(job_id), bytes_uploaded=len(image.image_bytes), tenant_id=str(tenant_id))

                try:
                    loop = _asyncio.get_running_loop()
                    loop.create_task(_record())
                except RuntimeError:
                    _asyncio.run(_record())
        except Exception:
            pass
        
        return f"gs://{bucket.name}/{object_name}"

    def ingest_bytes(
        self,
        tenant_id: str,
        content: bytes,
        filename: str,
        mime_type: str,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        progress: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> MultimodalIngestionResult:
        """Ingest document bytes using multimodal pipeline.
        
        Args:
            tenant_id: Tenant isolation key
            content: Raw file bytes
            filename: Original filename
            mime_type: MIME type
            project_id: Optional project scope
            job_id: Optional job tracking ID
            progress: Optional progress callback
            
        Returns:
            MultimodalIngestionResult with doc_ids, image_ids, stats
        """
        errors: List[str] = []
        
        # 1. Upload to GCS
        if progress:
            progress("UPLOAD", {"stage": "START"})
        self._current_job_id = job_id
        gcs_uri = self.upload_bytes(tenant_id, content, filename, mime_type)
        if progress:
            progress("UPLOAD", {"stage": "DONE", "gcs_uri": gcs_uri})

        # 2. Ensure multimodal KB tables exist (SKIP INDEX CREATION - done at tenant setup)
        if progress:
            progress("ENSURE_KB", {"stage": "START"})
        # NOTE: ensure_tenant_multimodal_kb is called during tenant creation, NOT here
        # Only ensure the table exists (fast) - index creation is SLOW and happens once at setup
        from src.services.bq_schema_manager import ensure_tenant_dataset, ensure_table, multimodal_docs_schema
        dataset = ensure_tenant_dataset(self.bq, tenant_id)
        ensure_table(self.bq, dataset.dataset_id, "multimodal_docs", multimodal_docs_schema())
        if progress:
            progress("ENSURE_KB", {"stage": "DONE"})

        mime_base = (mime_type or "").split(";", 1)[0].strip().lower()
        if mime_base == "application/pdf" or filename.lower().endswith(".pdf"):
            return self._ingest_pdf_streaming(
                tenant_id=str(tenant_id),
                gcs_uri=str(gcs_uri),
                content=content,
                filename=str(filename),
                mime_type=str(mime_type),
                size_bytes=int(len(content)),
                project_id=project_id,
                job_id=job_id,
                progress=progress,
            )

        # 3. Parse deterministically
        if progress:
            progress("PARSE", {"stage": "START"})
        try:
            if mime_base.startswith("text/"):
                parse_result = self._parse_text_bytes(content, filename, mime_base or "text/plain")
            else:
                parse_result = self.parser.parse_bytes(content, filename, mime_type)
        except Exception as e:
            logger.error(f"Deterministic parse failed: {e}")
            errors.append(f"Parse error: {e}")
            # Fallback: create a single "document" chapter with filename as essence
            mime_base = (mime_type or "").split(";", 1)[0].strip().lower()
            if mime_base.startswith("text/"):
                parse_result = self._parse_text_bytes(content, filename, mime_base or "text/plain")
            else:
                parse_result = DocumentParseResult(
                    markdown="",
                    chapters=[
                        ChapterEssence(
                            heading=filename,
                            level=1,
                            start_line=0,
                            essence_text=filename,
                            full_content="",
                            images=[],
                        )
                    ],
                    images=[],
                    total_chars=len(content),
                    estimated_tokens=self._count_tokens_best_effort(content),
                    source_filename=filename,
                    mime_type=mime_type,
                    metadata={"parser": "fallback"},
                )
        if progress:
            progress("PARSE", {
                "stage": "DONE",
                "chapters": len(parse_result.chapters),
                "images": len(parse_result.images),
                "tokens": parse_result.estimated_tokens,
            })

        # 4. Check if splitting needed
        parts: List[dict] = []
        if should_split_document(parse_result.estimated_tokens, self.MAX_TOKENS_PER_PART):
            if progress:
                progress("SPLIT", {"stage": "START"})
            parts = split_chapters_into_parts(
                parse_result.chapters,
                filename,
                max_tokens_per_part=self.MAX_TOKENS_PER_PART,
            )
            if progress:
                progress("SPLIT", {"stage": "DONE", "parts": len(parts)})
        else:
            # Single part
            parts = [{
                "part_name": filename,
                "part_number": 1,
                "total_parts": 1,
                "chapters": parse_result.chapters,
                "char_count": parse_result.total_chars,
            }]

        # 5. Embed and insert each part
        doc_ids: List[str] = []
        for part in parts:
            if progress:
                progress("EMBED_DOC", {"part": part["part_number"], "total": part["total_parts"]})
            
            # Combine chapter essences for embedding
            combined_essence = "\n\n".join(
                ch.essence_text for ch in part["chapters"]
            )
            
            # Embed chapter essence
            try:
                vector = self.embedder.embed_text(combined_essence)
            except Exception as e:
                logger.error(f"Embedding failed for part {part['part_number']}: {e}")
                errors.append(f"Embed error part {part['part_number']}: {e}")
                vector = [0.0] * self.embedder.DIMENSION
            
            # Insert to BigQuery
            doc_id = str(uuid.uuid4())
            doc_ids.append(doc_id)
            
            row = {
                "doc_id": doc_id,
                "tenant_id": str(tenant_id),
                "project_id": str(project_id) if project_id else None,
                "gcs_uri": gcs_uri,
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": len(content),
                "source_doc_id": None,
                "vector_embedding": vector,
                "metadata": {
                    "parser": parse_result.metadata.get("parser", "pymupdf"),
                    "job_id": job_id,
                    "chapter_count": len(part["chapters"]),
                },
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            
            table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
            try:
                errs = self.bq.insert_rows_json(table_ref, [row])
                if errs:
                    errors.append(f"BQ insert error: {errs}")
            except Exception as e:
                logger.error(f"BQ insert failed: {e}")
                errors.append(f"BQ insert error: {e}")

        # 6. Process and embed images
        image_ids: List[str] = []
        image_rows: List[Dict[str, Any]] = []
        
        if parse_result.images:
            if progress:
                progress("EMBED_IMAGE", {"stage": "START", "count": len(parse_result.images)})
            
            def _process_image(img: ExtractedImage) -> Optional[Dict[str, Any]]:
                try:
                    parent_doc_id = doc_ids[0] if doc_ids else str(uuid.uuid4())
                    
                    # Upload (IO bound)
                    img_gcs_uri = self.upload_image(tenant_id, img, parent_doc_id)
                    
                    # Embed (IO/Compute bound)
                    img_vector = self.embedder.embed_image(
                        img.image_bytes,
                        contextual_text=img.chapter_heading,
                    )
                    
                    image_id = str(uuid.uuid4())
                    
                    return {
                        "doc_id": image_id,
                        "tenant_id": str(tenant_id),
                        "project_id": str(project_id) if project_id else None,
                        "gcs_uri": img_gcs_uri,
                        "filename": f"{img.content_hash}.{img.mime_type.split('/')[-1] if '/' in img.mime_type else 'img'}",
                        "mime_type": img.mime_type,
                        "size_bytes": len(img.image_bytes),
                        "source_doc_id": parent_doc_id,
                        "vector_embedding": img_vector,
                        "metadata": {
                            "source_doc_id": parent_doc_id,
                            "chapter_heading": img.chapter_heading,
                            "page_number": img.page_number,
                            "description": img.description,
                        },
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                except Exception as e:
                    logger.error(f"Failed to process image {img.content_hash[:8]}: {e}")
                    return None

            # Parallel processing for images (Upload + Embed)
            # Limit workers to avoid hitting API rate limits or OOM
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(_process_image, img) for img in parse_result.images]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        image_rows.append(result)
                        image_ids.append(result["doc_id"])
                    else:
                        errors.append("One or more images failed to process")

            # Batch Insert to BigQuery
            if image_rows:
                table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
                try:
                    errs = self.bq.insert_rows_json(table_ref, image_rows)
                    if errs:
                        errors.append(f"Image batch insert error: {errs}")
                except Exception as e:
                    errors.append(f"Image batch insert failed: {e}")
            
            if progress:
                progress("EMBED_IMAGE", {"stage": "DONE", "processed": len(image_rows)})

        if progress:
            progress("DONE", {
                "doc_ids": doc_ids,
                "image_ids": image_ids,
                "errors": errors,
            })

        return MultimodalIngestionResult(
            tenant_id=str(tenant_id),
            gcs_uri=gcs_uri,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(content),
            doc_ids=doc_ids,
            image_ids=image_ids,
            chapter_count=len(parse_result.chapters),
            part_count=len(parts),
            total_tokens=parse_result.estimated_tokens,
            job_id=job_id,
            errors=errors,
        )

    def ingest_gcs_uri(
        self,
        tenant_id: str,
        gcs_uri: str,
        filename: str,
        mime_type: str,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        progress: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> MultimodalIngestionResult:
        """Ingest document from existing GCS URI."""
        # Download bytes
        bucket_name, blob_path = gcs_uri.replace("gs://", "").split("/", 1)
        bucket = self.storage.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        timeout_s = float(os.getenv("GCS_DOWNLOAD_TIMEOUT_SECONDS", "60") or "60")
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(blob.download_as_bytes, timeout=timeout_s)
            content = fut.result(timeout=timeout_s)
        size_bytes = blob.size or len(content)
        
        # Use bytes ingestion (skip re-upload)
        return self._ingest_with_content(
            tenant_id=tenant_id,
            gcs_uri=gcs_uri,
            content=content,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            project_id=project_id,
            job_id=job_id,
            progress=progress,
        )

    def _ingest_with_content(
        self,
        tenant_id: str,
        gcs_uri: str,
        content: bytes,
        filename: str,
        mime_type: str,
        size_bytes: int,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        progress: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> MultimodalIngestionResult:
        """Internal ingestion with pre-existing GCS URI and content."""
        import time as _time
        _t0 = _time.time()
        logger.info(f"[PERF] _ingest_with_content START: {filename}, {size_bytes}B")
        errors: List[str] = []

        # Ensure multimodal KB tables exist (SKIP INDEX CREATION - done at tenant setup)
        if progress:
            progress("ENSURE_KB", {"substage": "START"})
        # NOTE: ensure_tenant_multimodal_kb is called during tenant creation, NOT here
        # Only ensure the table exists (fast) - index creation is SLOW and happens once at setup
        _t_kb = _time.time()
        from src.services.bq_schema_manager import ensure_tenant_dataset, ensure_table, multimodal_docs_schema
        dataset = ensure_tenant_dataset(self.bq, tenant_id)
        ensure_table(self.bq, dataset.dataset_id, "multimodal_docs", multimodal_docs_schema())
        logger.info(f"[PERF] ensure_kb: {(_time.time() - _t_kb)*1000:.0f}ms")
        if progress:
            progress("ENSURE_KB", {"substage": "DONE"})

        # Parse deterministically
        if progress:
            progress("PARSE", {"substage": "START"})
        _t_parse = _time.time()
        try:
            mime_base = (mime_type or "").split(";", 1)[0].strip().lower()
            if mime_base.startswith("text/"):
                parse_result = self._parse_text_bytes(content, filename, mime_base or "text/plain")
            elif mime_base == "application/pdf" or filename.lower().endswith(".pdf"):
                return self._ingest_pdf_streaming(
                    tenant_id=str(tenant_id),
                    gcs_uri=str(gcs_uri),
                    content=content,
                    filename=str(filename),
                    mime_type=str(mime_type),
                    size_bytes=int(size_bytes),
                    project_id=project_id,
                    job_id=job_id,
                    progress=progress,
                )
            else:
                parse_result = self.parser.parse_bytes(content, filename, mime_type)
        except Exception as e:
            logger.error(f"Deterministic parse failed: {e}")
            errors.append(f"Parse error: {e}")
            mime_base = (mime_type or "").split(";", 1)[0].strip().lower()
            if mime_base.startswith("text/"):
                parse_result = self._parse_text_bytes(content, filename, mime_base or "text/plain")
            else:
                parse_result = DocumentParseResult(
                    markdown="",
                    chapters=[
                        ChapterEssence(
                            heading=filename,
                            level=1,
                            start_line=0,
                            essence_text=filename,
                            full_content="",
                            images=[],
                        )
                    ],
                    images=[],
                    total_chars=size_bytes,
                    estimated_tokens=self._count_tokens_best_effort(content),
                    source_filename=filename,
                    mime_type=mime_type,
                    metadata={"parser": "fallback"},
                )
        logger.info(f"[PERF] parse: {(_time.time() - _t_parse)*1000:.0f}ms, chapters={len(parse_result.chapters)}, tokens={parse_result.estimated_tokens}")
        if progress:
            progress("PARSE", {
                "substage": "DONE",
                "chapters": len(parse_result.chapters),
                "tokens": parse_result.estimated_tokens,
            })

        # Check if splitting needed
        parts: List[dict] = []
        if should_split_document(parse_result.estimated_tokens, self.MAX_TOKENS_PER_PART):
            parts = split_chapters_into_parts(
                parse_result.chapters,
                filename,
                max_tokens_per_part=self.MAX_TOKENS_PER_PART,
            )
        else:
            parts = [{
                "part_name": filename,
                "part_number": 1,
                "total_parts": 1,
                "chapters": parse_result.chapters,
                "char_count": parse_result.total_chars,
            }]

        # Embed and insert each part using multimodalembedding@001 REST API
        skip_embedding = os.getenv("SKIP_EMBEDDING", "").lower() in ("true", "1", "yes")
        
        doc_ids: List[str] = []
        for part_idx, part in enumerate(parts):
            combined_essence = "\n\n".join(ch.essence_text for ch in part["chapters"])
            
            _t_embed = _time.time()
            try:
                if skip_embedding:
                    # Skip Vertex AI entirely - use zero vector for testing
                    vector = [0.0] * 1408
                    logger.info(f"[PERF] embed SKIPPED (SKIP_EMBEDDING=true) part {part_idx+1}/{len(parts)}")
                else:
                    # Use multimodalembedding@001 REST API for all content (1408-D)
                    vector = self.embedder.embed_text(combined_essence)
                    logger.info(f"[PERF] embed_text part {part_idx+1}/{len(parts)}: {(_time.time() - _t_embed)*1000:.0f}ms")
            except Exception as e:
                logger.error(f"[PERF] embed_text FAILED after {(_time.time() - _t_embed)*1000:.0f}ms: {e}")
                errors.append(f"Embed error: {e}")
                vector = [0.0] * 1408  # Always use 1408-D for schema compatibility
            
            doc_id = str(uuid.uuid4())
            doc_ids.append(doc_id)
            
            row = {
                "doc_id": doc_id,
                "tenant_id": str(tenant_id),
                "project_id": str(project_id) if project_id else None,
                "gcs_uri": gcs_uri,
                "filename": filename,
                "part_name": part.get("part_name"),
                "part_number": part.get("part_number"),
                "total_parts": part.get("total_parts"),
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "source_doc_id": None,
                "chapter_count": len(part.get("chapters") or []),
                "vector_embedding": vector,
                "metadata": json.dumps({
                    "parser": "pymupdf",
                    "job_id": job_id,
                    "chapter_count": len(part["chapters"]),
                }),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            
            table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
            _t_bq = _time.time()
            try:
                self.bq.insert_rows_json(table_ref, [row])
                logger.info(f"[PERF] bq_insert part {part_idx+1}: {(_time.time() - _t_bq)*1000:.0f}ms")
            except Exception as e:
                logger.error(f"[PERF] bq_insert FAILED after {(_time.time() - _t_bq)*1000:.0f}ms: {e}")
                errors.append(f"BQ insert error: {e}")

        # Process images
        image_ids: List[str] = []
        image_rows: List[Dict[str, Any]] = []
        
        if parse_result.images:
            if progress:
                progress("EMBED_IMAGE", {"stage": "START", "count": len(parse_result.images)})
            
            def _process_image(img: ExtractedImage) -> Optional[Dict[str, Any]]:
                try:
                    parent_doc_id = doc_ids[0] if doc_ids else str(uuid.uuid4())
                    
                    # Upload (IO bound)
                    img_gcs_uri = self.upload_image(tenant_id, img, parent_doc_id)
                    
                    # Embed (IO/Compute bound)
                    img_vector = self.embedder.embed_image(
                        img.image_bytes,
                        contextual_text=img.chapter_heading,
                    )
                    
                    image_id = str(uuid.uuid4())
                    
                    return {
                        "doc_id": image_id,
                        "tenant_id": str(tenant_id),
                        "project_id": str(project_id) if project_id else None,
                        "gcs_uri": img_gcs_uri,
                        "filename": f"{img.content_hash}.{img.mime_type.split('/')[-1] if '/' in img.mime_type else 'img'}",
                        "mime_type": img.mime_type,
                        "size_bytes": len(img.image_bytes),
                        "source_doc_id": parent_doc_id,
                        "vector_embedding": img_vector,
                        "metadata": json.dumps({
                            "source_doc_id": parent_doc_id,
                            "chapter_heading": img.chapter_heading,
                            "page_number": img.page_number,
                            "description": img.description,
                        }),
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                except Exception as e:
                    logger.error(f"Failed to process image {img.content_hash[:8]}: {e}")
                    return None

            # Parallel processing for images (Upload + Embed)
            # Limit workers to avoid hitting API rate limits or OOM
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(_process_image, img) for img in parse_result.images]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        image_rows.append(result)
                        image_ids.append(result["doc_id"])
                    else:
                        errors.append("One or more images failed to process")

            # Batch Insert to BigQuery
            if image_rows:
                table_ref = f"{self.project_id}.tnt_{tenant_id}.multimodal_docs"
                try:
                    errs = self.bq.insert_rows_json(table_ref, image_rows)
                    if errs:
                        errors.append(f"Image batch insert error: {errs}")
                except Exception as e:
                    errors.append(f"Image batch insert failed: {e}")
            
            if progress:
                progress("EMBED_IMAGE", {"stage": "DONE", "processed": len(image_rows)})

        logger.info(f"[PERF] _ingest_with_content DONE: {(_time.time() - _t0)*1000:.0f}ms total, docs={len(doc_ids)}, images={len(image_ids)}, errors={len(errors)}")
        return MultimodalIngestionResult(
            tenant_id=str(tenant_id),
            gcs_uri=gcs_uri,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            doc_ids=doc_ids,
            image_ids=image_ids,
            chapter_count=len(parse_result.chapters),
            part_count=len(parts),
            total_tokens=parse_result.estimated_tokens,
            job_id=job_id,
            errors=errors,
        )
