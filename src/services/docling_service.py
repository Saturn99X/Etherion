"""Docling-based unified document parsing service.

Converts PDF, DOCX, PPTX, XLSX, HTML, images, and more into structured Markdown
with chapter detection and image extraction for multimodal embedding ingestion.

References:
- https://github.com/docling-project/docling
- https://docling-project.github.io/docling/
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not available, falling back to char-based estimation")


def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base for GPT-4).
    
    Falls back to char-based estimation if tiktoken unavailable.
    """
    if _TIKTOKEN_AVAILABLE:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            pass
    # Fallback: ~4 chars per token
    return len(text) // 4


# Lazy imports for docling to avoid boot-time weight
# Cache the converter INSTANCE (not just class) - initialization is heavy (~seconds)
_converter_instance: Any = None

# Environment flag to use fast pypdf parser (bypasses Docling which requires HF models)
# Set USE_PYPDF_PARSER=1 when VPC egress blocks HuggingFace downloads
_USE_PYPDF = os.getenv("USE_PYPDF_PARSER", "0") == "1"


def _parse_pdf_fast(file_bytes: bytes) -> str:
    """Fast PDF text extraction using pypdf - NO network required."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"## Page {i + 1}\n\n{text}")
    return "\n\n".join(pages)


def _get_converter() -> Any:
    """Get a DETERMINISTIC DocumentConverter - NO AI models, NO HuggingFace downloads.
    
    Uses DoclingParseV2DocumentBackend for PDF parsing which is pure rule-based.
    Disables OCR, VLM picture descriptions, and all ML-based enrichments.
    """
    global _converter_instance
    if _converter_instance is None:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        
        # Configure for FULLY DETERMINISTIC parsing - NO downloads, NO models
        pdf_options = PdfPipelineOptions(
            do_ocr=False,
            do_table_structure=False,
            generate_page_images=False,
            generate_picture_images=False,  # DISABLED - triggers HuggingFace downloads
        )
        
        _converter_instance = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pdf_options,
                )
            }
        )
    return _converter_instance


@dataclass
class ChapterEssence:
    """Represents a chapter boundary with its semantic essence for embedding."""
    heading: str
    level: int  # 1 = #, 2 = ##
    start_line: int
    essence_text: str  # heading + first ~128 tokens
    full_content: str  # full chapter content for GCS storage
    images: List["ExtractedImage"] = field(default_factory=list)


@dataclass
class ExtractedImage:
    """Represents an image extracted from a document."""
    image_bytes: bytes
    mime_type: str
    chapter_heading: Optional[str] = None
    page_number: Optional[int] = None
    description: Optional[str] = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.image_bytes).hexdigest()[:16]


@dataclass
class DoclingParseResult:
    """Result of parsing a document with Docling."""
    markdown: str
    chapters: List[ChapterEssence]
    images: List[ExtractedImage]
    total_chars: int
    estimated_tokens: int
    source_filename: str
    mime_type: str
    metadata: dict = field(default_factory=dict)


class DoclingService:
    """Unified document parsing using Docling.
    
    Converts any supported file type into structured Markdown with:
    - Chapter boundary detection (# and ## headings)
    - Chapter essence extraction (heading + first ~128 tokens)
    - Inline image extraction with parent chapter metadata
    
    Supported formats: PDF, DOCX, PPTX, XLSX, HTML, images (PNG, JPEG, etc.)
    NOT supported: plain text files (.txt, .log, .json, .xml, .yaml, etc.)
    """

    # Rough token estimate: ~4 chars per token
    CHARS_PER_TOKEN = 4
    MAX_ESSENCE_TOKENS = 128
    MAX_ESSENCE_CHARS = MAX_ESSENCE_TOKENS * CHARS_PER_TOKEN  # ~512 chars
    
    # File extensions that Docling actually supports
    SUPPORTED_EXTENSIONS = {
        ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
        ".html", ".htm", ".md", ".csv",
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff", ".bmp",
    }

    def __init__(self) -> None:
        self._converter: Any = None
        self._timeout_seconds = int(os.getenv("DOCLING_PARSE_TIMEOUT_SECONDS", "60"))

    @property
    def converter(self) -> Any:
        if self._converter is None:
            self._converter = _get_converter()
        return self._converter

    def parse_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: Optional[str] = None,
    ) -> DoclingParseResult:
        """Parse document bytes into structured Markdown with chapter detection.
        
        Args:
            file_bytes: Raw document bytes
            filename: Original filename (used for format detection)
            mime_type: Optional MIME type hint
            
        Returns:
            DoclingParseResult with markdown, chapters, images, and metadata
            
        Raises:
            ValueError: If file format is not supported by Docling
        """
        # Fail-fast: check if format is supported BEFORE doing any heavy work
        suffix = os.path.splitext(filename)[1].lower() if "." in filename else ""
        if suffix and suffix not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"File format not supported by Docling: {suffix}. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )
        
        # FAST PATH: Use pypdf when USE_PYPDF_PARSER=1 (VPC blocks HuggingFace)
        if _USE_PYPDF and suffix == ".pdf":
            logger.info(f"Using pypdf fast parser for {filename}")
            markdown = _parse_pdf_fast(file_bytes)
            chapters = self._detect_chapters(markdown)
            total_chars = len(markdown)
            estimated_tokens = _count_tokens(markdown)
            return DoclingParseResult(
                markdown=markdown,
                chapters=chapters,
                images=[],
                total_chars=total_chars,
                estimated_tokens=estimated_tokens,
                source_filename=filename,
                mime_type=mime_type or self._guess_mime_type(filename),
                metadata={"parser": "pypdf", "chapter_count": len(chapters), "image_count": 0},
            )
        
        # Write to temp file for Docling (it needs a file path or URL)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            result = self._convert_with_timeout(tmp_path, filename)
            markdown = result.document.export_to_markdown()
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        # Detect chapters from markdown headings
        chapters = self._detect_chapters(markdown)

        # Extract images from document (if available in result)
        images = self._extract_images(result, chapters)

        total_chars = len(markdown)
        estimated_tokens = _count_tokens(markdown)  # Use tiktoken, not char estimate

        return DoclingParseResult(
            markdown=markdown,
            chapters=chapters,
            images=images,
            total_chars=total_chars,
            estimated_tokens=estimated_tokens,
            source_filename=filename,
            mime_type=mime_type or self._guess_mime_type(filename),
            metadata={
                "parser": "docling",
                "chapter_count": len(chapters),
                "image_count": len(images),
            },
        )

    def parse_gcs_uri(
        self,
        gcs_uri: str,
        local_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
    ) -> DoclingParseResult:
        """Parse a document from GCS URI.
        
        If local_bytes is provided, uses those directly.
        Otherwise downloads from GCS first.
        """
        if local_bytes is None:
            from src.core.gcs_client import download_blob_to_bytes
            local_bytes = download_blob_to_bytes(gcs_uri)
        
        fname = filename or gcs_uri.split("/")[-1]
        return self.parse_bytes(local_bytes, fname)

    def _detect_chapters(self, markdown: str) -> List[ChapterEssence]:
        """Detect chapter boundaries from Markdown headings (# and ##)."""
        chapters: List[ChapterEssence] = []
        pattern = r"^(#{1,2})\s+(.+)$"
        
        lines = markdown.split("\n")
        current_chapter: Optional[dict] = None
        
        for i, line in enumerate(lines):
            match = re.match(pattern, line)
            if match:
                # Finalize previous chapter
                if current_chapter:
                    chapters.append(self._finalize_chapter(current_chapter))
                
                level = len(match.group(1))
                heading = match.group(2).strip()
                current_chapter = {
                    "level": level,
                    "heading": heading,
                    "start_line": i,
                    "content_lines": [],
                }
            elif current_chapter:
                current_chapter["content_lines"].append(line)
        
        # Finalize last chapter
        if current_chapter:
            chapters.append(self._finalize_chapter(current_chapter))
        
        # If no chapters detected, create a single "Document" chapter
        if not chapters and markdown.strip():
            chapters.append(ChapterEssence(
                heading="Document",
                level=1,
                start_line=0,
                essence_text=self._truncate_to_essence(markdown),
                full_content=markdown,
                images=[],
            ))
        
        return chapters

    def _finalize_chapter(self, chapter_dict: dict) -> ChapterEssence:
        """Convert chapter dict to ChapterEssence with essence extraction."""
        heading = chapter_dict["heading"]
        full_content = "\n".join(chapter_dict["content_lines"])
        
        # Extract essence: heading + first ~128 tokens of content
        essence_text = self._extract_essence(heading, full_content)
        
        return ChapterEssence(
            heading=heading,
            level=chapter_dict["level"],
            start_line=chapter_dict["start_line"],
            essence_text=essence_text,
            full_content=full_content,
            images=[],
        )

    def _extract_essence(self, heading: str, content: str) -> str:
        """Extract chapter essence: heading + first ~128 tokens."""
        # Take first N characters of content
        content_preview = content[:self.MAX_ESSENCE_CHARS].strip()
        
        # Try to end at a sentence boundary
        last_period = content_preview.rfind(".")
        if last_period > self.MAX_ESSENCE_CHARS // 2:
            content_preview = content_preview[: last_period + 1]
        
        return f"{heading}\n\n{content_preview}".strip()

    def _convert_with_timeout(self, tmp_path: str, filename: str) -> Any:
        """Convert document with timeout protection using ThreadPoolExecutor.
        
        Args:
            tmp_path: Path to temporary file
            filename: Original filename for error messages
            
        Returns:
            Docling conversion result
            
        Raises:
            TimeoutError: If conversion exceeds timeout
        """
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.converter.convert, tmp_path)
            try:
                result = future.result(timeout=self._timeout_seconds)
                return result
            except FutureTimeoutError:
                logger.error(f"Docling parsing timeout for {filename} after {self._timeout_seconds}s")
                future.cancel()
                raise TimeoutError(f"Docling parsing exceeded {self._timeout_seconds}s timeout for {filename}")

    def _truncate_to_essence(self, text: str) -> str:
        """Truncate text to essence length."""
        if len(text) <= self.MAX_ESSENCE_CHARS:
            return text
        truncated = text[: self.MAX_ESSENCE_CHARS]
        last_period = truncated.rfind(".")
        if last_period > self.MAX_ESSENCE_CHARS // 2:
            return truncated[: last_period + 1]
        return truncated + "..."

    def _extract_images(
        self, docling_result: Any, chapters: List[ChapterEssence]
    ) -> List[ExtractedImage]:
        """Extract images from Docling result and associate with chapters."""
        images: List[ExtractedImage] = []
        
        try:
            doc = docling_result.document
            # Docling exposes images via document.pictures or similar
            if hasattr(doc, "pictures"):
                for pic in doc.pictures:
                    img_bytes = getattr(pic, "data", None) or getattr(pic, "image", None)
                    if img_bytes:
                        if isinstance(img_bytes, str):
                            import base64
                            img_bytes = base64.b64decode(img_bytes)
                        
                        # Determine parent chapter by page number if available
                        page_num = getattr(pic, "page_number", None)
                        chapter_heading = None
                        if chapters:
                            chapter_heading = chapters[0].heading  # Default to first
                        
                        images.append(ExtractedImage(
                            image_bytes=img_bytes,
                            mime_type="image/png",  # Docling typically exports as PNG
                            chapter_heading=chapter_heading,
                            page_number=page_num,
                            description=getattr(pic, "caption", None),
                        ))
        except Exception as e:
            logger.warning(f"Failed to extract images from Docling result: {e}")
        
        return images

    def _guess_mime_type(self, filename: str) -> str:
        """Guess MIME type from filename extension."""
        ext = os.path.splitext(filename)[1].lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".html": "text/html",
            ".htm": "text/html",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".tiff": "image/tiff",
            ".bmp": "image/bmp",
        }
        return mime_map.get(ext, "application/octet-stream")


def should_split_document(estimated_tokens: int, max_tokens: int = 300_000) -> bool:
    """Check if document exceeds token limit and should be split."""
    return estimated_tokens >= max_tokens


def split_chapters_into_parts(
    chapters: List[ChapterEssence],
    filename: str,
    max_tokens_per_part: int = 300_000,
    chars_per_token: int = 4,
) -> List[dict]:
    """Split chapters into parts, each under max_tokens_per_part.
    
    Returns list of dicts with:
    - part_name: e.g., "report_001.pdf"
    - part_number: 1-indexed
    - total_parts: total count
    - chapters: list of ChapterEssence in this part
    - char_count: total chars in this part
    """
    max_chars = max_tokens_per_part * chars_per_token
    parts: List[dict] = []
    current_part = {"chapters": [], "char_count": 0}
    part_number = 1

    for chapter in chapters:
        chapter_chars = len(chapter.essence_text)
        
        if current_part["char_count"] + chapter_chars > max_chars and current_part["chapters"]:
            # Finalize current part
            base_name = filename.rsplit(".", 1)[0] if "." in filename else filename
            ext = filename.rsplit(".", 1)[1] if "." in filename else ""
            current_part["part_name"] = f"{base_name}_{part_number:03d}.{ext}" if ext else f"{base_name}_{part_number:03d}"
            parts.append(current_part)
            
            # Start new part
            part_number += 1
            current_part = {"chapters": [], "char_count": 0}
        
        current_part["chapters"].append(chapter)
        current_part["char_count"] += chapter_chars

    # Finalize last part
    if current_part["chapters"]:
        base_name = filename.rsplit(".", 1)[0] if "." in filename else filename
        ext = filename.rsplit(".", 1)[1] if "." in filename else ""
        current_part["part_name"] = f"{base_name}_{part_number:03d}.{ext}" if ext else f"{base_name}_{part_number:03d}"
        parts.append(current_part)

    # Add total_parts and part_number to each
    total = len(parts)
    for i, part in enumerate(parts):
        part["part_number"] = i + 1
        part["total_parts"] = total

    return parts
