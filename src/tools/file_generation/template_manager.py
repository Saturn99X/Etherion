"""
Template Manager for File Generation Tools.

Provides reusable templates for:
- PDF documents (reports, invoices, forms)
- Excel spreadsheets (financial reports, data tables)
- PowerPoint presentations (business decks, reports)

Templates are stored in the templates/ directory and can be customized
per tenant or globally.
"""

import os
import json
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class TemplateManager:
    """
    Manages document templates for file generation.

    Features:
    - Template storage and retrieval
    - Per-tenant customization
    - Template validation
    - Version control
    """

    def __init__(self, templates_dir: Optional[str] = None):
        """
        Initialize the template manager.

        Args:
            templates_dir: Directory containing templates (default: ./templates)
        """
        if templates_dir:
            self.templates_dir = Path(templates_dir)
        else:
            # Default to templates directory relative to this file
            self.templates_dir = Path(__file__).parent / "templates"

        # Ensure templates directory exists
        self.templates_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories for each document type
        (self.templates_dir / "pdf").mkdir(exist_ok=True)
        (self.templates_dir / "excel").mkdir(exist_ok=True)
        (self.templates_dir / "powerpoint").mkdir(exist_ok=True)

        logger.info(
            f"Initialized TemplateManager with templates_dir={self.templates_dir}"
        )

    def get_pdf_template(
        self, template_name: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get a PDF template configuration.

        Args:
            template_name: Name of the template
            tenant_id: Optional tenant ID for tenant-specific templates

        Returns:
            Template configuration dictionary
        """
        template_path = self._get_template_path("pdf", template_name, tenant_id)

        if not template_path.exists():
            logger.warning(f"Template not found: {template_path}, using default")
            return self._get_default_pdf_template(template_name)

        with open(template_path, "r") as f:
            return json.load(f)

    def get_excel_template(
        self, template_name: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get an Excel template configuration.

        Args:
            template_name: Name of the template
            tenant_id: Optional tenant ID for tenant-specific templates

        Returns:
            Template configuration dictionary
        """
        template_path = self._get_template_path("excel", template_name, tenant_id)

        if not template_path.exists():
            logger.warning(f"Template not found: {template_path}, using default")
            return self._get_default_excel_template(template_name)

        with open(template_path, "r") as f:
            return json.load(f)

    def get_powerpoint_template(
        self, template_name: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get a PowerPoint template configuration.

        Args:
            template_name: Name of the template
            tenant_id: Optional tenant ID for tenant-specific templates

        Returns:
            Template configuration dictionary
        """
        template_path = self._get_template_path("powerpoint", template_name, tenant_id)

        if not template_path.exists():
            logger.warning(f"Template not found: {template_path}, using default")
            return self._get_default_powerpoint_template(template_name)

        with open(template_path, "r") as f:
            return json.load(f)

    def save_template(
        self,
        doc_type: str,
        template_name: str,
        template_config: Dict[str, Any],
        tenant_id: Optional[str] = None,
    ):
        """
        Save a template configuration.

        Args:
            doc_type: Document type (pdf, excel, powerpoint)
            template_name: Name of the template
            template_config: Template configuration dictionary
            tenant_id: Optional tenant ID for tenant-specific templates
        """
        template_path = self._get_template_path(doc_type, template_name, tenant_id)

        # Ensure parent directory exists
        template_path.parent.mkdir(parents=True, exist_ok=True)

        with open(template_path, "w") as f:
            json.dump(template_config, f, indent=2)

        logger.info(f"Saved template: {template_path}")

    def list_templates(
        self, doc_type: str, tenant_id: Optional[str] = None
    ) -> List[str]:
        """
        List available templates.

        Args:
            doc_type: Document type (pdf, excel, powerpoint)
            tenant_id: Optional tenant ID for tenant-specific templates

        Returns:
            List of template names
        """
        template_dir = self.templates_dir / doc_type

        if tenant_id:
            tenant_dir = template_dir / tenant_id
            if tenant_dir.exists():
                template_dir = tenant_dir

        if not template_dir.exists():
            return []

        templates = []
        for file_path in template_dir.glob("*.json"):
            templates.append(file_path.stem)

        return sorted(templates)

    def _get_template_path(
        self, doc_type: str, template_name: str, tenant_id: Optional[str] = None
    ) -> Path:
        """
        Get the file path for a template.

        Args:
            doc_type: Document type
            template_name: Template name
            tenant_id: Optional tenant ID

        Returns:
            Path to template file
        """
        base_path = self.templates_dir / doc_type

        if tenant_id:
            # Check tenant-specific template first
            tenant_path = base_path / tenant_id / f"{template_name}.json"
            if tenant_path.exists():
                return tenant_path

        # Return global template path
        return base_path / f"{template_name}.json"

    def _get_default_pdf_template(self, template_name: str) -> Dict[str, Any]:
        """
        Get default PDF template configuration.

        Args:
            template_name: Template name

        Returns:
            Default template configuration
        """
        if template_name == "invoice":
            return {
                "type": "invoice",
                "page_size": "LETTER",
                "margins": {"top": 72, "bottom": 72, "left": 72, "right": 72},
                "header": {"show": True, "height": 100, "style": "bold"},
                "footer": {
                    "show": True,
                    "height": 50,
                    "text": "Thank you for your business!",
                },
                "sections": [
                    {
                        "type": "header",
                        "fields": ["invoice_number", "date", "due_date"],
                    },
                    {"type": "billing_info", "fields": ["from", "to"]},
                    {"type": "line_items", "table": True},
                    {"type": "totals", "fields": ["subtotal", "tax", "total"]},
                    {"type": "notes", "optional": True},
                ],
            }

        elif template_name == "report":
            return {
                "type": "report",
                "page_size": "LETTER",
                "margins": {"top": 72, "bottom": 72, "left": 72, "right": 72},
                "styles": {
                    "title": {"font_size": 24, "bold": True, "color": "#1a1a1a"},
                    "heading": {"font_size": 16, "bold": True, "color": "#4a4a4a"},
                    "body": {"font_size": 11, "color": "#333333"},
                },
                "sections": [
                    {"type": "title", "required": True},
                    {"type": "metadata", "fields": ["author", "date", "version"]},
                    {"type": "content", "blocks": ["paragraph", "table", "image"]},
                ],
            }

        elif template_name == "form":
            return {
                "type": "form",
                "page_size": "LETTER",
                "margins": {"top": 72, "bottom": 72, "left": 72, "right": 72},
                "fields": [
                    {
                        "name": "name",
                        "type": "text",
                        "label": "Full Name",
                        "required": True,
                    },
                    {
                        "name": "email",
                        "type": "text",
                        "label": "Email Address",
                        "required": True,
                    },
                    {
                        "name": "phone",
                        "type": "text",
                        "label": "Phone Number",
                        "required": False,
                    },
                    {
                        "name": "address",
                        "type": "textarea",
                        "label": "Address",
                        "required": False,
                    },
                ],
            }

        else:
            # Generic document template
            return {
                "type": "document",
                "page_size": "LETTER",
                "margins": {"top": 72, "bottom": 72, "left": 72, "right": 72},
                "styles": {
                    "title": {"font_size": 24, "bold": True},
                    "body": {"font_size": 11},
                },
            }

    def _get_default_excel_template(self, template_name: str) -> Dict[str, Any]:
        """
        Get default Excel template configuration.

        Args:
            template_name: Template name

        Returns:
            Default template configuration
        """
        if template_name == "financial_report":
            return {
                "type": "financial_report",
                "sheets": [
                    {
                        "name": "Summary",
                        "type": "report",
                        "sections": [
                            {"type": "title", "style": "header"},
                            {"type": "metrics", "layout": "key_value"},
                            {"type": "charts", "chart_types": ["bar", "line"]},
                        ],
                    },
                    {
                        "name": "Details",
                        "type": "table",
                        "formatting": {
                            "header_style": True,
                            "freeze_panes": True,
                            "auto_filter": True,
                        },
                    },
                ],
                "styles": {
                    "header": {"font_size": 14, "bold": True, "bg_color": "366092"},
                    "metric": {"font_size": 12, "number_format": "$#,##0.00"},
                },
            }

        elif template_name == "data_table":
            return {
                "type": "data_table",
                "sheets": [
                    {
                        "name": "Data",
                        "type": "table",
                        "formatting": {
                            "header_style": True,
                            "freeze_panes": True,
                            "auto_filter": True,
                            "table_style": "TableStyleMedium9",
                        },
                    }
                ],
                "styles": {
                    "header": {
                        "font_size": 11,
                        "bold": True,
                        "bg_color": "366092",
                        "font_color": "FFFFFF",
                    }
                },
            }

        elif template_name == "pivot_report":
            return {
                "type": "pivot_report",
                "sheets": [
                    {"name": "Data", "type": "raw", "hidden": False},
                    {
                        "name": "Pivot",
                        "type": "pivot",
                        "source_sheet": "Data",
                        "rows": [],
                        "columns": [],
                        "values": [],
                    },
                ],
            }

        else:
            return {
                "type": "workbook",
                "sheets": [
                    {
                        "name": "Sheet1",
                        "type": "table",
                        "formatting": {"header_style": True},
                    }
                ],
            }

    def _get_default_powerpoint_template(self, template_name: str) -> Dict[str, Any]:
        """
        Get default PowerPoint template configuration.

        Args:
            template_name: Template name

        Returns:
            Default template configuration
        """
        if template_name == "business_deck":
            return {
                "type": "business_deck",
                "aspect_ratio": "16:9",
                "theme": {
                    "primary_color": "#366092",
                    "secondary_color": "#4F81BD",
                    "accent_color": "#C0504D",
                    "text_color": "#333333",
                },
                "slide_layouts": [
                    {"type": "title", "required": True},
                    {"type": "agenda", "optional": True},
                    {"type": "section_header", "repeatable": True},
                    {"type": "content", "repeatable": True},
                    {"type": "conclusion", "required": True},
                ],
                "fonts": {
                    "title": {"name": "Arial", "size": 44, "bold": True},
                    "heading": {"name": "Arial", "size": 32, "bold": True},
                    "body": {"name": "Arial", "size": 18},
                },
            }

        elif template_name == "report_presentation":
            return {
                "type": "report_presentation",
                "aspect_ratio": "16:9",
                "theme": {
                    "primary_color": "#366092",
                    "secondary_color": "#4F81BD",
                    "accent_color": "#C0504D",
                },
                "slide_layouts": [
                    {"type": "title", "required": True},
                    {"type": "executive_summary", "required": True},
                    {"type": "data_table", "repeatable": True},
                    {"type": "chart", "repeatable": True},
                    {"type": "conclusions", "required": True},
                ],
            }

        elif template_name == "pitch_deck":
            return {
                "type": "pitch_deck",
                "aspect_ratio": "16:9",
                "theme": {
                    "primary_color": "#000000",
                    "secondary_color": "#4A4A4A",
                    "accent_color": "#FF6B6B",
                },
                "slide_layouts": [
                    {"type": "title", "required": True},
                    {"type": "problem", "required": True},
                    {"type": "solution", "required": True},
                    {"type": "market", "required": True},
                    {"type": "product", "required": True},
                    {"type": "business_model", "required": True},
                    {"type": "competition", "required": True},
                    {"type": "team", "required": True},
                    {"type": "financials", "required": True},
                    {"type": "ask", "required": True},
                ],
            }

        else:
            return {
                "type": "presentation",
                "aspect_ratio": "16:9",
                "theme": {"primary_color": "#366092", "text_color": "#333333"},
                "slide_layouts": [
                    {"type": "title", "required": True},
                    {"type": "content", "repeatable": True},
                ],
            }

    def initialize_default_templates(self):
        """
        Initialize default templates in the templates directory.

        This creates JSON files for common templates that can be
        customized by users.
        """
        # PDF templates
        for template_name in ["invoice", "report", "form"]:
            template_path = self.templates_dir / "pdf" / f"{template_name}.json"
            if not template_path.exists():
                template_config = self._get_default_pdf_template(template_name)
                with open(template_path, "w") as f:
                    json.dump(template_config, f, indent=2)
                logger.info(f"Created default PDF template: {template_name}")

        # Excel templates
        for template_name in ["financial_report", "data_table", "pivot_report"]:
            template_path = self.templates_dir / "excel" / f"{template_name}.json"
            if not template_path.exists():
                template_config = self._get_default_excel_template(template_name)
                with open(template_path, "w") as f:
                    json.dump(template_config, f, indent=2)
                logger.info(f"Created default Excel template: {template_name}")

        # PowerPoint templates
        for template_name in ["business_deck", "report_presentation", "pitch_deck"]:
            template_path = self.templates_dir / "powerpoint" / f"{template_name}.json"
            if not template_path.exists():
                template_config = self._get_default_powerpoint_template(template_name)
                with open(template_path, "w") as f:
                    json.dump(template_config, f, indent=2)
                logger.info(f"Created default PowerPoint template: {template_name}")

        logger.info("Default templates initialized")


# Singleton instance
_template_manager = None


def get_template_manager(templates_dir: Optional[str] = None) -> TemplateManager:
    """
    Get the global TemplateManager instance.

    Args:
        templates_dir: Optional templates directory path

    Returns:
        TemplateManager instance
    """
    global _template_manager

    if _template_manager is None:
        _template_manager = TemplateManager(templates_dir)
        # Initialize default templates on first access
        _template_manager.initialize_default_templates()

    return _template_manager
