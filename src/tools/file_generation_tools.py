from typing import Dict, Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.tools.file_generation.file_generation_service import (
    create_file_generation_service,
    FileType,
)


@tool
async def generate_pdf_file(
    tenant_id: str,
    job_id: str,
    agent_id: str = "platform_orchestrator",
    template: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a PDF using the FileGenerationService.

    Expected input_data keys:
    - tenant_id (str, required)
    - job_id (str, required)
    - agent_id (str, optional; defaults to "platform_orchestrator")
    - template (str, optional)
    - data (dict, optional)
    - other kwargs forwarded to PDF generator
    """
    data = data or {}
    kwargs = kwargs or {}

    svc = create_file_generation_service(
        tenant_id=tenant_id, agent_id=agent_id, job_id=job_id
    )
    return await svc.generate_file(
        file_type=FileType.PDF, template_name=template, data=data, **kwargs
    )


@tool
async def generate_excel_file(
    tenant_id: str,
    job_id: str,
    agent_id: str = "platform_orchestrator",
    template: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate an Excel file using the FileGenerationService.

    Expected input_data keys similar to generate_pdf_file.
    """
    data = data or {}
    kwargs = kwargs or {}

    svc = create_file_generation_service(
        tenant_id=tenant_id, agent_id=agent_id, job_id=job_id
    )
    return await svc.generate_file(
        file_type=FileType.EXCEL, template_name=template, data=data, **kwargs
    )


@tool
async def generate_presentation_file(
    tenant_id: str,
    job_id: str,
    agent_id: str = "platform_orchestrator",
    template: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a PowerPoint presentation using the FileGenerationService.

    Expected input_data keys similar to generate_pdf_file.
    """
    data = data or {}
    kwargs = kwargs or {}

    svc = create_file_generation_service(
        tenant_id=tenant_id, agent_id=agent_id, job_id=job_id
    )
    return await svc.generate_file(
        file_type=FileType.POWERPOINT, template_name=template, data=data, **kwargs
    )


@tool
async def generate_image_file(
    tenant_id: str,
    job_id: str,
    agent_id: str = "platform_orchestrator",
    data: Optional[Dict[str, Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate an image using the FileGenerationService's image generator.

    Expected input_data keys similar to generate_pdf_file.
    The `data` dict should include a `prompt` and optional image-specific args.
    """
    data = data or {}
    kwargs = kwargs or {}

    svc = create_file_generation_service(
        tenant_id=tenant_id, agent_id=agent_id, job_id=job_id
    )
    return await svc.generate_file(
        file_type=FileType.IMAGE, template_name=None, data=data, **kwargs
    )


class FileGenerationInput(BaseModel):
    tenant_id: str = Field(
        ...,
        description="Tenant identifier for multi-tenancy isolation",
    )
    job_id: str = Field(
        ...,
        description="Job identifier for tracing and cost tracking",
    )
    agent_id: str = Field(
        "platform_orchestrator",
        description="Logical agent initiating file generation",
    )
    template: Optional[str] = Field(
        None,
        description="Optional template name to drive layout and structure",
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Template-specific data payload for the generated file",
    )
    kwargs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional generator-specific options forwarded as keyword args",
    )


def _generate_pdf_file_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    try:
        schema = FileGenerationInput.model_json_schema()
    except Exception:
        schema = FileGenerationInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Generate a PDF using a template and data. Provide tenant_id, job_id, "
            "optional agent_id, template, data, and kwargs for PDFGeneratorTool."
        ),
        "examples": [
            {
                "name": "invoice_pdf",
                "input": {
                    "tenant_id": "tnt_123",
                    "job_id": "job_abc",
                    "agent_id": "platform_orchestrator",
                    "template": "invoice_standard",
                    "data": {
                        "invoice_number": "INV-2025-001",
                        "from_info": {"name": "Acme Inc."},
                        "to_info": {"name": "Customer Co."},
                        "line_items": [
                            {
                                "description": "Service A",
                                "quantity": 10,
                                "rate": 100.0,
                                "amount": 1000.0,
                            }
                        ],
                    },
                },
            },
            {
                "name": "simple_report_pdf",
                "input": {
                    "tenant_id": "tnt_123",
                    "job_id": "job_abc",
                    "template": "report_basic",
                    "data": {
                        "title": "Q1 2025 Summary",
                        "content": [
                            {"type": "heading", "text": "Overview"},
                            {
                                "type": "paragraph",
                                "text": "Summary of key results.",
                            },
                        ],
                    },
                },
            },
        ],
    }


def _generate_excel_file_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    try:
        schema = FileGenerationInput.model_json_schema()
    except Exception:
        schema = FileGenerationInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Generate an Excel workbook using a template and data. Provide tenant_id, job_id, "
            "optional agent_id, template, data, and kwargs for ExcelGeneratorTool."
        ),
        "examples": [
            {
                "name": "financial_report_excel",
                "input": {
                    "tenant_id": "tnt_123",
                    "job_id": "job_finance",
                    "template": "financial_report_quarterly",
                    "data": {
                        "title": "Q1 2025 Financials",
                        "period": "Q1 2025",
                        "summary_data": {
                            "revenue": 1000000.0,
                            "profit": 250000.0,
                        },
                        "detail_data": [
                            {"account": "Revenue", "amount": 1000000.0},
                            {"account": "Expenses", "amount": 750000.0},
                        ],
                    },
                },
            },
            {
                "name": "data_table_excel",
                "input": {
                    "tenant_id": "tnt_123",
                    "job_id": "job_finance",
                    "template": "data_table",
                    "data": {
                        "data": [
                            {"metric": "users", "value": 1200},
                            {"metric": "sessions", "value": 4500},
                        ],
                        "headers": ["metric", "value"],
                    },
                },
            },
        ],
    }


def _generate_presentation_file_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    try:
        schema = FileGenerationInput.model_json_schema()
    except Exception:
        schema = FileGenerationInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Generate a PowerPoint presentation using a template and data. Provide tenant_id, job_id, "
            "optional agent_id, template, data, and kwargs for PresentationGeneratorTool."
        ),
        "examples": [
            {
                "name": "business_deck",
                "input": {
                    "tenant_id": "tnt_123",
                    "job_id": "job_exec",
                    "template": "business_deck_default",
                    "data": {
                        "title": "Q1 Strategy Review",
                        "sections": [
                            {"type": "section_header", "title": "Overview"},
                            {
                                "type": "bullet_points",
                                "title": "Highlights",
                                "content": {
                                    "points": [
                                        "Revenue up 20%",
                                        "Launched new product line",
                                    ]
                                },
                            },
                        ],
                    },
                },
            },
            {
                "name": "report_presentation",
                "input": {
                    "tenant_id": "tnt_123",
                    "job_id": "job_exec",
                    "template": "report_presentation",
                    "data": {
                        "title": "Usage Report",
                        "executive_summary": "Overall strong engagement across teams.",
                        "data_sections": [],
                        "conclusions": [
                            "Maintain current strategy",
                            "Invest in onboarding",
                        ],
                    },
                },
            },
        ],
    }


def _generate_image_file_get_schema_hints(max_ops: Optional[int] = None) -> Dict[str, Any]:
    try:
        schema = FileGenerationInput.model_json_schema()
    except Exception:
        schema = FileGenerationInput.schema()
    return {
        "input_schema": schema,
        "usage": (
            "Generate an image via the FileGenerationService image pipeline. Provide tenant_id, job_id, "
            "optional agent_id, and a data object with at least a prompt and optional type/edit parameters."
        ),
        "examples": [
            {
                "name": "text_to_image",
                "input": {
                    "tenant_id": "tnt_123",
                    "job_id": "job_design",
                    "data": {
                        "prompt": "Futuristic office with autonomous AI assistants",
                    },
                },
            },
            {
                "name": "image_variations",
                "input": {
                    "tenant_id": "tnt_123",
                    "job_id": "job_design",
                    "data": {
                        "type": "variations",
                        "base_image": "<base-image-bytes-or-handle>",
                        "num_variations": 3,
                    },
                },
            },
        ],
    }
