"""
Production-ready file generation tools for Etherion AI Platform.

This module provides comprehensive file generation capabilities including:
- PDF generation with reportlab
- Excel generation with openpyxl
- PowerPoint generation with python-pptx
- Image generation with Gemini 2.5 Flash Image (Nano Banana)

All generated files are:
1. Saved to private GCS buckets (tnt-{tenant_id}-assets)
2. Indexed in BigQuery for metadata and searchability
3. Vectorized and indexed in Vertex AI Search
4. Accessible via signed URLs (5-min expiry) or base64 encoding

Quick Start:
    >>> from src.tools.file_generation import FileGenerationService
    >>> service = FileGenerationService(
    ...     tenant_id="acme_corp",
    ...     agent_id="agent_001",
    ...     job_id="job_12345"
    ... )
    >>> result = await service.generate_invoice(
    ...     invoice_number="INV-001",
    ...     from_info={...},
    ...     to_info={...},
    ...     line_items=[...]
    ... )

Author: Etherion AI Platform Team
Date: September 30, 2025
"""

from .base_file_generator import BaseFileGenerator
from .image_generator_tool import ImageGeneratorTool
from .pdf_generator_tool import PDFGeneratorTool
from .excel_generator_tool import ExcelGeneratorTool
from .presentation_generator_tool import PresentationGeneratorTool
from .file_generation_service import (
    FileGenerationService,
    FileType,
    create_file_generation_service,
)
from .template_manager import TemplateManager, get_template_manager

__all__ = [
    # Base classes
    "BaseFileGenerator",
    # Specialized generators
    "ImageGeneratorTool",
    "PDFGeneratorTool",
    "ExcelGeneratorTool",
    "PresentationGeneratorTool",
    # Service layer
    "FileGenerationService",
    "FileType",
    "create_file_generation_service",
    # Template system
    "TemplateManager",
    "get_template_manager",
]

__version__ = "1.0.0"
__author__ = "Etherion AI Platform Team"
__license__ = "Proprietary"

# Supported file types
SUPPORTED_FILE_TYPES = ["pdf", "excel", "powerpoint", "image"]

# Default configuration
DEFAULT_CONFIG = {
    "gcs_bucket_prefix": "tnt-",
    "gcs_bucket_suffix": "-assets",
    "bigquery_dataset_prefix": "tnt_",
    "default_region": "us-central1",
    "signed_url_expiration_minutes": 5,
    "base64_preview_threshold_bytes": 5 * 1024 * 1024,  # 5MB
}
