"""
File Generation Service for Etherion AI Platform.

This service integrates all file generation tools (PDF, Excel, PowerPoint, Image)
with the MCP (Model Context Protocol) for agent-based file generation.

Features:
- Unified interface for all file generation types
- MCP protocol integration
- Template support
- Multi-tenant isolation
- BigQuery indexing and Vertex AI Search integration
- Secure storage with signed URLs

Author: Etherion AI Platform Team
Date: September 30, 2025
"""

import os
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum

from .base_file_generator import BaseFileGenerator
from .pdf_generator_tool import PDFGeneratorTool
from .excel_generator_tool import ExcelGeneratorTool
from .presentation_generator_tool import PresentationGeneratorTool
from .image_generator_tool import ImageGeneratorTool
from .template_manager import get_template_manager

logger = logging.getLogger(__name__)


class FileType(str, Enum):
    """Supported file generation types."""

    PDF = "pdf"
    EXCEL = "excel"
    POWERPOINT = "powerpoint"
    IMAGE = "image"


class FileGenerationService:
    """
    Unified service for all file generation operations.

    This service provides a single entry point for generating files
    of all supported types, with proper tenant isolation, storage,
    indexing, and access control.
    """

    def __init__(
        self,
        tenant_id: str,
        agent_id: str,
        job_id: str,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        """
        Initialize the file generation service.

        Args:
            tenant_id: Tenant ID for multi-tenancy isolation
            agent_id: Agent ID performing the generation
            job_id: Job ID for tracking
            user_id: Optional user ID
            project_id: GCP project ID
        """
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.job_id = job_id
        self.user_id = user_id
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")

        # Initialize generators (lazy loading)
        self._pdf_generator = None
        self._excel_generator = None
        self._presentation_generator = None
        self._image_generator = None

        # Get template manager
        self.template_manager = get_template_manager()

        logger.info(
            f"Initialized FileGenerationService for tenant={tenant_id}, "
            f"agent={agent_id}, job={job_id}"
        )

    @property
    def pdf_generator(self) -> PDFGeneratorTool:
        """Get or create PDF generator instance."""
        if self._pdf_generator is None:
            self._pdf_generator = PDFGeneratorTool(
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                job_id=self.job_id,
                user_id=self.user_id,
                project_id=self.project_id,
            )
        return self._pdf_generator

    @property
    def excel_generator(self) -> ExcelGeneratorTool:
        """Get or create Excel generator instance."""
        if self._excel_generator is None:
            self._excel_generator = ExcelGeneratorTool(
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                job_id=self.job_id,
                user_id=self.user_id,
                project_id=self.project_id,
            )
        return self._excel_generator

    @property
    def presentation_generator(self) -> PresentationGeneratorTool:
        """Get or create PowerPoint generator instance."""
        if self._presentation_generator is None:
            self._presentation_generator = PresentationGeneratorTool(
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                job_id=self.job_id,
                user_id=self.user_id,
                project_id=self.project_id,
            )
        return self._presentation_generator

    @property
    def image_generator(self) -> ImageGeneratorTool:
        """Get or create Image generator instance."""
        if self._image_generator is None:
            self._image_generator = ImageGeneratorTool(
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                job_id=self.job_id,
                user_id=self.user_id,
                project_id=self.project_id,
            )
        return self._image_generator

    async def generate_file(
        self,
        file_type: FileType,
        template_name: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate a file of the specified type.

        Args:
            file_type: Type of file to generate
            template_name: Optional template name
            data: Data for the file generation
            **kwargs: Additional arguments specific to the file type

        Returns:
            Dictionary containing asset info with download URL
        """
        try:
            if file_type == FileType.PDF:
                return await self._generate_pdf(template_name, data, **kwargs)
            elif file_type == FileType.EXCEL:
                return await self._generate_excel(template_name, data, **kwargs)
            elif file_type == FileType.POWERPOINT:
                return await self._generate_powerpoint(template_name, data, **kwargs)
            elif file_type == FileType.IMAGE:
                return await self._generate_image(data, **kwargs)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")

        except Exception as e:
            logger.error(f"Error generating {file_type} file: {e}", exc_info=True)
            raise

    async def _generate_pdf(
        self,
        template_name: Optional[str],
        data: Optional[Dict[str, Any]],
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate a PDF file."""
        if template_name:
            template = self.template_manager.get_pdf_template(
                template_name, self.tenant_id
            )
            template_type = template.get("type", "document")

            if template_type == "invoice":
                return await self.pdf_generator.generate_invoice(
                    invoice_number=data.get("invoice_number", "INV-0001"),
                    invoice_date=data.get(
                        "invoice_date", datetime.utcnow().strftime("%Y-%m-%d")
                    ),
                    due_date=data.get("due_date", ""),
                    from_info=data.get("from_info", {}),
                    to_info=data.get("to_info", {}),
                    line_items=data.get("line_items", []),
                    notes=data.get("notes"),
                    **kwargs,
                )
            elif template_type == "report":
                return await self.pdf_generator.generate_report(
                    title=data.get("title", "Report"),
                    content=data.get("content", []),
                    **kwargs,
                )
            else:
                # Generic document
                return await self.pdf_generator.generate_simple_document(
                    title=data.get("title", "Document"),
                    paragraphs=data.get("paragraphs", []),
                    **kwargs,
                )
        else:
            # No template - use data directly
            if "invoice_number" in data:
                return await self.pdf_generator.generate_invoice(**data, **kwargs)
            elif "content" in data:
                return await self.pdf_generator.generate_report(**data, **kwargs)
            else:
                return await self.pdf_generator.generate_simple_document(
                    **data, **kwargs
                )

    async def _generate_excel(
        self,
        template_name: Optional[str],
        data: Optional[Dict[str, Any]],
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate an Excel file."""
        if template_name:
            template = self.template_manager.get_excel_template(
                template_name, self.tenant_id
            )
            template_type = template.get("type", "workbook")

            if template_type == "financial_report":
                return await self.excel_generator.generate_financial_report(
                    report_title=data.get("title", "Financial Report"),
                    period=data.get("period", ""),
                    summary_data=data.get("summary_data", {}),
                    detail_data=data.get("detail_data", []),
                    **kwargs,
                )
            elif template_type == "data_table":
                return await self.excel_generator.generate_data_table(
                    data=data.get("data", []),
                    headers=data.get("headers"),
                    **kwargs,
                )
            else:
                # Generic workbook
                return await self.excel_generator.generate_workbook(
                    sheets=data.get("sheets", []), **kwargs
                )
        else:
            # No template - infer from data structure
            if "summary_data" in data and "detail_data" in data:
                return await self.excel_generator.generate_financial_report(
                    **data, **kwargs
                )
            elif "data" in data and isinstance(data["data"], list):
                return await self.excel_generator.generate_data_table(**data, **kwargs)
            else:
                return await self.excel_generator.generate_workbook(**data, **kwargs)

    async def _generate_powerpoint(
        self,
        template_name: Optional[str],
        data: Optional[Dict[str, Any]],
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate a PowerPoint presentation."""
        if template_name:
            template = self.template_manager.get_powerpoint_template(
                template_name, self.tenant_id
            )
            template_type = template.get("type", "presentation")

            if template_type == "business_deck":
                return await self.presentation_generator.generate_business_presentation(
                    title=data.get("title", "Business Presentation"),
                    sections=data.get("sections", []),
                    **kwargs,
                )
            elif template_type == "report_presentation":
                return await self.presentation_generator.generate_report_presentation(
                    title=data.get("title", "Report"),
                    executive_summary=data.get("executive_summary", ""),
                    data_sections=data.get("data_sections", []),
                    conclusions=data.get("conclusions", []),
                    **kwargs,
                )
            else:
                # Generic presentation
                return await self.presentation_generator.generate_presentation(
                    slides=data.get("slides", []), **kwargs
                )
        else:
            # No template - infer from data
            if "executive_summary" in data:
                return await self.presentation_generator.generate_report_presentation(
                    **data, **kwargs
                )
            elif "sections" in data:
                return await self.presentation_generator.generate_business_presentation(
                    **data, **kwargs
                )
            else:
                return await self.presentation_generator.generate_presentation(
                    **data, **kwargs
                )

    async def _generate_image(
        self, data: Optional[Dict[str, Any]], **kwargs
    ) -> Dict[str, Any]:
        """Generate an image using Gemini 2.5 Flash Image."""
        generation_type = data.get("type", "generate")

        if generation_type == "edit":
            return await self.image_generator.edit_image(
                base_image_bytes=data.get("base_image"),
                edit_prompt=data.get("prompt", ""),
                **kwargs,
            )
        elif generation_type == "style_transfer":
            return await self.image_generator.generate_with_style_reference(
                prompt=data.get("prompt", ""),
                style_image_bytes=data.get("style_image"),
                **kwargs,
            )
        elif generation_type == "variations":
            return await self.image_generator.generate_variations(
                base_image_bytes=data.get("base_image"),
                num_variations=data.get("num_variations", 3),
                **kwargs,
            )
        else:
            # Standard generation
            result = await self.image_generator.generate_image(
                prompt=data.get("prompt", ""),
                reference_images=data.get("reference_images"),
                **kwargs,
            )
            # Return first image if list
            return result[0] if isinstance(result, list) else result

    async def generate_invoice(
        self,
        invoice_number: str,
        from_info: Dict[str, str],
        to_info: Dict[str, str],
        line_items: List[Dict[str, Any]],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate an invoice PDF.

        Args:
            invoice_number: Invoice number
            from_info: Sender information
            to_info: Recipient information
            line_items: List of invoice line items
            **kwargs: Additional arguments

        Returns:
            Asset info dictionary
        """
        return await self.pdf_generator.generate_invoice(
            invoice_number=invoice_number,
            invoice_date=kwargs.get(
                "invoice_date", datetime.utcnow().strftime("%Y-%m-%d")
            ),
            due_date=kwargs.get("due_date", ""),
            from_info=from_info,
            to_info=to_info,
            line_items=line_items,
            **kwargs,
        )

    async def generate_financial_report(
        self,
        title: str,
        period: str,
        summary_data: Dict[str, float],
        detail_data: List[Dict[str, Any]],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate a financial report Excel file.

        Args:
            title: Report title
            period: Reporting period
            summary_data: Summary metrics
            detail_data: Detailed transaction data
            **kwargs: Additional arguments

        Returns:
            Asset info dictionary
        """
        return await self.excel_generator.generate_financial_report(
            report_title=title,
            period=period,
            summary_data=summary_data,
            detail_data=detail_data,
            **kwargs,
        )

    async def generate_presentation(
        self, title: str, slides: List[Dict[str, Any]], **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a PowerPoint presentation.

        Args:
            title: Presentation title
            slides: List of slide configurations
            **kwargs: Additional arguments

        Returns:
            Asset info dictionary
        """
        return await self.presentation_generator.generate_presentation(
            slides=slides, title=title, **kwargs
        )

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate an image using Gemini 2.5 Flash Image.

        Args:
            prompt: Image generation prompt
            **kwargs: Additional arguments (reference_images, negative_prompt, etc.)

        Returns:
            Asset info dictionary
        """
        result = await self.image_generator.generate_image(prompt=prompt, **kwargs)
        # Return first image if list
        return result[0] if isinstance(result, list) else result

    def list_templates(self, file_type: FileType) -> List[str]:
        """
        List available templates for a file type.

        Args:
            file_type: Type of file

        Returns:
            List of template names
        """
        doc_type = file_type.value
        return self.template_manager.list_templates(doc_type, self.tenant_id)

    def get_template(self, file_type: FileType, template_name: str) -> Dict[str, Any]:
        """
        Get a specific template configuration.

        Args:
            file_type: Type of file
            template_name: Name of template

        Returns:
            Template configuration dictionary
        """
        doc_type = file_type.value

        if doc_type == "pdf":
            return self.template_manager.get_pdf_template(template_name, self.tenant_id)
        elif doc_type == "excel":
            return self.template_manager.get_excel_template(
                template_name, self.tenant_id
            )
        elif doc_type == "powerpoint":
            return self.template_manager.get_powerpoint_template(
                template_name, self.tenant_id
            )
        else:
            raise ValueError(f"Templates not supported for file type: {file_type}")

    async def batch_generate(
        self, requests: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple files in batch.

        Args:
            requests: List of generation requests, each with file_type, template, and data

        Returns:
            List of asset info dictionaries
        """
        results = []

        for request in requests:
            try:
                file_type = FileType(request.get("file_type"))
                template_name = request.get("template")
                data = request.get("data", {})
                kwargs = request.get("kwargs", {})

                result = await self.generate_file(
                    file_type=file_type,
                    template_name=template_name,
                    data=data,
                    **kwargs,
                )
                results.append({"success": True, "result": result})

            except Exception as e:
                logger.error(f"Error in batch generation: {e}", exc_info=True)
                results.append({"success": False, "error": str(e), "request": request})

        return results


def create_file_generation_service(
    tenant_id: str,
    agent_id: str,
    job_id: str,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> FileGenerationService:
    """
    Factory function to create a FileGenerationService instance.

    Args:
        tenant_id: Tenant ID
        agent_id: Agent ID
        job_id: Job ID
        user_id: Optional user ID
        project_id: Optional GCP project ID

    Returns:
        FileGenerationService instance
    """
    return FileGenerationService(
        tenant_id=tenant_id,
        agent_id=agent_id,
        job_id=job_id,
        user_id=user_id,
        project_id=project_id,
    )
