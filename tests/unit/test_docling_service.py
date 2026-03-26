"""Unit tests for DoclingService (chapter detection, essence extraction, file splitting)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestChapterDetection:
    """Test chapter boundary detection from Markdown headings."""

    def test_detect_h1_and_h2_chapters(self):
        from src.services.docling_service import DoclingService

        svc = DoclingService()
        markdown = """# Introduction

This is the intro paragraph with some content.

## Background

Some background information here.

## Methods

Description of methods used.

# Results

The results section starts here.
"""
        chapters = svc._detect_chapters(markdown)

        assert len(chapters) == 4
        assert chapters[0].heading == "Introduction"
        assert chapters[0].level == 1
        assert chapters[1].heading == "Background"
        assert chapters[1].level == 2
        assert chapters[2].heading == "Methods"
        assert chapters[2].level == 2
        assert chapters[3].heading == "Results"
        assert chapters[3].level == 1

    def test_empty_markdown_creates_document_chapter(self):
        from src.services.docling_service import DoclingService

        svc = DoclingService()
        markdown = "Some plain text without any headings."
        chapters = svc._detect_chapters(markdown)

        assert len(chapters) == 1
        assert chapters[0].heading == "Document"
        assert chapters[0].level == 1

    def test_essence_extraction_truncates(self):
        from src.services.docling_service import DoclingService

        svc = DoclingService()
        long_content = "A" * 1000
        essence = svc._extract_essence("Test Heading", long_content)

        # Should contain heading + truncated content
        assert "Test Heading" in essence
        assert len(essence) < 600  # ~512 chars max for content + heading


class TestFileSplitting:
    """Test large file splitting into parts."""

    def test_should_split_large_document(self):
        from src.services.docling_service import should_split_document

        assert should_split_document(300_000) is True
        assert should_split_document(299_999) is False
        assert should_split_document(500_000) is True

    def test_split_chapters_into_parts(self):
        from src.services.docling_service import (
            ChapterEssence,
            split_chapters_into_parts,
        )

        # Create chapters that would exceed max tokens if combined
        chapters = [
            ChapterEssence(
                heading=f"Chapter {i}",
                level=1,
                start_line=i * 100,
                essence_text="X" * 100_000,  # 100k chars each
                full_content="Full content",
                images=[],
            )
            for i in range(5)
        ]

        # With 300k token limit (1.2M chars), each chapter of 100k chars
        # should fit ~12 per part, but we have only 5
        parts = split_chapters_into_parts(
            chapters,
            filename="report.pdf",
            max_tokens_per_part=50_000,  # Lower limit for test
            chars_per_token=4,
        )

        # Each part can hold ~200k chars, so 2 chapters per part
        assert len(parts) >= 2
        assert parts[0]["part_number"] == 1
        assert parts[-1]["total_parts"] == len(parts)
        assert "report_001.pdf" in parts[0]["part_name"]


class TestMimeTypeGuessing:
    """Test MIME type detection from filename."""

    def test_common_mime_types(self):
        from src.services.docling_service import DoclingService

        svc = DoclingService()

        assert svc._guess_mime_type("doc.pdf") == "application/pdf"
        assert svc._guess_mime_type("data.xlsx") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert svc._guess_mime_type("slides.pptx") == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        assert svc._guess_mime_type("page.html") == "text/html"
        assert svc._guess_mime_type("image.png") == "image/png"
        assert svc._guess_mime_type("unknown.xyz") == "application/octet-stream"
