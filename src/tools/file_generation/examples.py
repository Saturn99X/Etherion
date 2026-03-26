"""
Example Usage Scripts for File Generation Module.

This file demonstrates how to use all the file generation tools
in the Etherion AI Platform.

Run with:
    python -m src.tools.file_generation.examples

Author: Etherion AI Platform Team
Date: September 30, 2025
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, List, Any

from .file_generation_service import FileGenerationService, FileType


async def example_pdf_invoice():
    """Example: Generate a professional invoice PDF."""
    print("\n=== PDF Invoice Generation ===")

    service = FileGenerationService(
        tenant_id="demo_tenant",
        agent_id="agent_demo",
        job_id="job_invoice_001",
        user_id="user_demo",
    )

    result = await service.generate_invoice(
        invoice_number="INV-2025-001",
        from_info={
            "name": "Etherion AI Inc.",
            "address": "123 AI Street, Tech Valley, CA 94000",
            "email": "billing@etherion.ai",
            "phone": "+1 (555) 123-4567",
        },
        to_info={
            "name": "Acme Corporation",
            "address": "456 Business Ave, Corporate City, NY 10001",
            "email": "ap@acme.com",
            "phone": "+1 (555) 987-6543",
        },
        line_items=[
            {
                "description": "AI Consulting Services - January 2025",
                "quantity": 40,
                "rate": 200.00,
                "amount": 8000.00,
            },
            {
                "description": "Platform Subscription - Q1 2025",
                "quantity": 1,
                "rate": 5000.00,
                "amount": 5000.00,
            },
            {
                "description": "Custom Integration Development",
                "quantity": 20,
                "rate": 250.00,
                "amount": 5000.00,
            },
        ],
        notes="Payment due within 30 days. Late payments subject to 1.5% monthly interest.",
        filename="invoice_2025_001.pdf",
        description="Professional invoice for Q1 2025 services",
    )

    print(f"✓ Invoice generated successfully!")
    print(f"  Asset ID: {result['asset_id']}")
    print(f"  Filename: {result['filename']}")
    print(f"  GCS URI: {result['gcs_uri']}")
    print(f"  Download URL: {result['download_url'][:80]}...")
    print(f"  Size: {result['size_bytes'] / 1024:.2f} KB")

    return result


async def example_pdf_report():
    """Example: Generate a detailed report PDF."""
    print("\n=== PDF Report Generation ===")

    service = FileGenerationService(
        tenant_id="demo_tenant", agent_id="agent_demo", job_id="job_report_001"
    )

    result = await service.pdf_generator.generate_report(
        title="Q1 2025 Business Performance Report",
        content=[
            {"type": "heading", "text": "Executive Summary", "level": 2},
            {
                "type": "paragraph",
                "text": "This report presents a comprehensive analysis of our business performance "
                "during the first quarter of 2025. Key highlights include significant revenue "
                "growth, expansion into new markets, and successful product launches.",
            },
            {"type": "spacer", "height": 20},
            {"type": "heading", "text": "Financial Performance", "level": 2},
            {
                "type": "paragraph",
                "text": "Our financial performance exceeded expectations across all key metrics:",
            },
            {
                "type": "table",
                "data": [
                    ["Metric", "Q1 2025", "Q4 2024", "Change"],
                    ["Revenue", "$2.5M", "$2.0M", "+25%"],
                    ["Gross Profit", "$1.8M", "$1.4M", "+29%"],
                    ["Operating Income", "$650K", "$500K", "+30%"],
                    ["Net Income", "$500K", "$380K", "+32%"],
                ],
            },
            {"type": "spacer", "height": 20},
            {"type": "heading", "text": "Market Expansion", "level": 2},
            {
                "type": "paragraph",
                "text": "We successfully expanded into five new geographic markets, increasing our "
                "total addressable market by 40%. Customer acquisition in these new markets "
                "exceeded projections by 15%.",
            },
            {"type": "page_break"},
            {"type": "heading", "text": "Product Development", "level": 2},
            {
                "type": "paragraph",
                "text": "Three major product releases were completed on schedule, each receiving "
                "positive customer feedback and strong adoption rates.",
            },
        ],
        author="Business Intelligence Team",
        subject="Quarterly Business Review",
        filename="q1_2025_report.pdf",
        description="Comprehensive Q1 2025 business performance report",
        tags=["report", "quarterly", "business-performance"],
    )

    print(f"✓ Report generated successfully!")
    print(f"  Asset ID: {result['asset_id']}")
    print(f"  Download URL: {result['download_url'][:80]}...")

    return result


async def example_excel_data_table():
    """Example: Generate an Excel data table."""
    print("\n=== Excel Data Table Generation ===")

    service = FileGenerationService(
        tenant_id="demo_tenant", agent_id="agent_demo", job_id="job_excel_001"
    )

    # Sample customer data
    customer_data = [
        {
            "Customer ID": "C001",
            "Name": "Alice Johnson",
            "Email": "alice@example.com",
            "City": "New York",
            "Total Orders": 15,
            "Revenue": 4500.00,
            "Status": "Active",
        },
        {
            "Customer ID": "C002",
            "Name": "Bob Smith",
            "Email": "bob@example.com",
            "City": "Los Angeles",
            "Total Orders": 8,
            "Revenue": 2400.00,
            "Status": "Active",
        },
        {
            "Customer ID": "C003",
            "Name": "Carol White",
            "Email": "carol@example.com",
            "City": "Chicago",
            "Total Orders": 22,
            "Revenue": 6800.00,
            "Status": "Premium",
        },
        {
            "Customer ID": "C004",
            "Name": "David Brown",
            "Email": "david@example.com",
            "City": "Houston",
            "Total Orders": 3,
            "Revenue": 900.00,
            "Status": "Active",
        },
        {
            "Customer ID": "C005",
            "Name": "Eve Martinez",
            "Email": "eve@example.com",
            "City": "Phoenix",
            "Total Orders": 31,
            "Revenue": 9500.00,
            "Status": "Premium",
        },
    ]

    result = await service.excel_generator.generate_data_table(
        data=customer_data,
        filename="customer_data_2025.xlsx",
        sheet_name="Customers",
        description="Customer database export with revenue metrics",
        tags=["excel", "customers", "data-export"],
    )

    print(f"✓ Excel table generated successfully!")
    print(f"  Asset ID: {result['asset_id']}")
    print(f"  Rows: {len(customer_data)}")
    print(f"  Download URL: {result['download_url'][:80]}...")

    return result


async def example_excel_financial_report():
    """Example: Generate a financial report Excel file."""
    print("\n=== Excel Financial Report Generation ===")

    service = FileGenerationService(
        tenant_id="demo_tenant", agent_id="agent_demo", job_id="job_financial_001"
    )

    result = await service.generate_financial_report(
        title="Q1 2025 Financial Report",
        period="January - March 2025",
        summary_data={
            "Total Revenue": 2500000.00,
            "Cost of Goods Sold": 700000.00,
            "Gross Profit": 1800000.00,
            "Operating Expenses": 1150000.00,
            "Operating Income": 650000.00,
            "Net Income": 500000.00,
            "Profit Margin": 0.20,
        },
        detail_data=[
            {
                "Date": "2025-01-15",
                "Category": "Product Sales",
                "Amount": 850000.00,
                "Customer": "Enterprise Client A",
                "Payment Status": "Paid",
            },
            {
                "Date": "2025-01-22",
                "Category": "Services",
                "Amount": 250000.00,
                "Customer": "Mid-Market Client B",
                "Payment Status": "Paid",
            },
            {
                "Date": "2025-02-05",
                "Category": "Product Sales",
                "Amount": 600000.00,
                "Customer": "Enterprise Client C",
                "Payment Status": "Paid",
            },
            {
                "Date": "2025-02-18",
                "Category": "Subscriptions",
                "Amount": 150000.00,
                "Customer": "Various SMB Clients",
                "Payment Status": "Paid",
            },
            {
                "Date": "2025-03-10",
                "Category": "Services",
                "Amount": 400000.00,
                "Customer": "Enterprise Client D",
                "Payment Status": "Pending",
            },
            {
                "Date": "2025-03-25",
                "Category": "Product Sales",
                "Amount": 250000.00,
                "Customer": "Mid-Market Client E",
                "Payment Status": "Paid",
            },
        ],
        filename="financial_report_q1_2025.xlsx",
        description="Comprehensive Q1 2025 financial performance report",
        tags=["excel", "financial-report", "quarterly"],
    )

    print(f"✓ Financial report generated successfully!")
    print(f"  Asset ID: {result['asset_id']}")
    print(f"  Download URL: {result['download_url'][:80]}...")

    return result


async def example_powerpoint_business_presentation():
    """Example: Generate a business PowerPoint presentation."""
    print("\n=== PowerPoint Business Presentation ===")

    service = FileGenerationService(
        tenant_id="demo_tenant", agent_id="agent_demo", job_id="job_ppt_001"
    )

    result = await service.presentation_generator.generate_business_presentation(
        title="Product Launch Strategy 2025",
        sections=[
            {"type": "section_header", "title": "Market Opportunity"},
            {
                "type": "bullet_points",
                "title": "Market Analysis",
                "content": {
                    "points": [
                        "Total Addressable Market: $50B",
                        "Serviceable Market: $15B",
                        "Target Market Share: 5% by 2027",
                        "Annual Growth Rate: 25%",
                    ]
                },
            },
            {"type": "section_header", "title": "Product Strategy"},
            {
                "type": "bullet_points",
                "title": "Key Features",
                "content": {
                    "points": [
                        "AI-powered automation reducing costs by 40%",
                        "Real-time analytics and insights",
                        "Seamless integration with existing systems",
                        "Enterprise-grade security and compliance",
                    ]
                },
            },
            {
                "type": "comparison",
                "title": "Competitive Advantage",
                "content": {
                    "left": [
                        "Our Solution:",
                        "• 40% cost reduction",
                        "• 10x faster processing",
                        "• 99.9% uptime SLA",
                        "• 24/7 support",
                    ],
                    "right": [
                        "Competitors:",
                        "• 15% cost reduction",
                        "• 3x faster processing",
                        "• 99.5% uptime SLA",
                        "• Business hours support",
                    ],
                },
            },
            {
                "type": "table",
                "title": "Launch Timeline",
                "content": {
                    "data": [
                        ["Phase", "Timeline", "Key Milestone"],
                        ["Alpha", "Q2 2025", "Feature Complete"],
                        ["Beta", "Q3 2025", "100 Beta Users"],
                        ["Launch", "Q4 2025", "General Availability"],
                        ["Scale", "Q1 2026", "10K+ Active Users"],
                    ]
                },
            },
            {"type": "section_header", "title": "Financial Projections"},
            {
                "type": "table",
                "title": "Revenue Forecast",
                "content": {
                    "data": [
                        ["Year", "Users", "Revenue", "Profit"],
                        ["2025", "1,000", "$500K", "$50K"],
                        ["2026", "10,000", "$5M", "$1M"],
                        ["2027", "50,000", "$25M", "$7.5M"],
                        ["2028", "150,000", "$75M", "$25M"],
                    ]
                },
            },
        ],
        author="Product Strategy Team",
        filename="product_launch_strategy_2025.pptx",
        description="Comprehensive product launch strategy presentation",
        tags=["powerpoint", "business", "product-launch"],
    )

    print(f"✓ Presentation generated successfully!")
    print(f"  Asset ID: {result['asset_id']}")
    print(f"  Download URL: {result['download_url'][:80]}...")

    return result


async def example_image_generation():
    """Example: Generate AI images with Gemini 2.5 Flash Image."""
    print("\n=== AI Image Generation (Gemini 2.5 Flash Image) ===")

    service = FileGenerationService(
        tenant_id="demo_tenant", agent_id="agent_demo", job_id="job_image_001"
    )

    # Generate a single image
    result = await service.generate_image(
        prompt="A modern minimalist office workspace with natural lighting, indoor plants, "
        "wooden desk, ergonomic chair, laptop, and large windows overlooking a city skyline. "
        "Professional and inspiring atmosphere.",
        description="Modern office workspace concept",
        tags=["office", "workspace", "modern", "minimalist"],
        number_of_images=1,
    )

    print(f"✓ Image generated successfully!")
    print(f"  Asset ID: {result['asset_id']}")
    print(f"  Size: {result['size_bytes'] / 1024:.2f} KB")
    print(f"  Download URL: {result['download_url'][:80]}...")
    if result.get("preview_base64"):
        print(
            f"  Base64 preview available: Yes (length: {len(result['preview_base64'])})"
        )

    return result


async def example_batch_generation():
    """Example: Generate multiple files in batch."""
    print("\n=== Batch File Generation ===")

    service = FileGenerationService(
        tenant_id="demo_tenant", agent_id="agent_demo", job_id="job_batch_001"
    )

    requests = [
        {
            "file_type": "pdf",
            "template": None,
            "data": {
                "title": "Monthly Report - January 2025",
                "paragraphs": [
                    "Executive Summary: January showed strong performance across all metrics.",
                    "Key achievements: 25% revenue growth, 3 new client acquisitions, "
                    "successful product launch.",
                    "Looking ahead: Q2 pipeline is robust with $5M in opportunities.",
                ],
            },
            "kwargs": {"filename": "january_report.pdf"},
        },
        {
            "file_type": "excel",
            "template": None,
            "data": {
                "data": [
                    {
                        "Month": "January",
                        "Revenue": 250000,
                        "Expenses": 180000,
                        "Profit": 70000,
                    },
                    {
                        "Month": "February",
                        "Revenue": 280000,
                        "Expenses": 190000,
                        "Profit": 90000,
                    },
                    {
                        "Month": "March",
                        "Revenue": 320000,
                        "Expenses": 200000,
                        "Profit": 120000,
                    },
                ]
            },
            "kwargs": {"filename": "q1_summary.xlsx"},
        },
        {
            "file_type": "powerpoint",
            "template": None,
            "data": {
                "title": "Weekly Update",
                "slides": [
                    {
                        "type": "title",
                        "content": {
                            "title": "Weekly Update",
                            "subtitle": f"Week of {datetime.now().strftime('%B %d, %Y')}",
                        },
                    },
                    {
                        "type": "title_content",
                        "content": {
                            "title": "This Week's Highlights",
                            "bullet_points": [
                                "Closed 2 enterprise deals worth $500K",
                                "Launched beta program with 50 users",
                                "Completed security audit with zero findings",
                            ],
                        },
                    },
                ],
            },
            "kwargs": {"filename": "weekly_update.pptx"},
        },
    ]

    results = await service.batch_generate(requests)

    print(f"✓ Batch generation completed!")
    successful = sum(1 for r in results if r["success"])
    failed = len(results) - successful
    print(f"  Successful: {successful}/{len(results)}")
    print(f"  Failed: {failed}/{len(results)}")

    for i, result in enumerate(results):
        if result["success"]:
            asset = result["result"]
            print(f"  [{i + 1}] ✓ {asset['filename']}: {asset['asset_id']}")
        else:
            print(f"  [{i + 1}] ✗ Failed: {result['error']}")

    return results


async def example_template_usage():
    """Example: Using templates for generation."""
    print("\n=== Template-Based Generation ===")

    from .template_manager import get_template_manager

    service = FileGenerationService(
        tenant_id="demo_tenant", agent_id="agent_demo", job_id="job_template_001"
    )

    # List available templates
    pdf_templates = service.list_templates(FileType.PDF)
    print(f"Available PDF templates: {pdf_templates}")

    excel_templates = service.list_templates(FileType.EXCEL)
    print(f"Available Excel templates: {excel_templates}")

    ppt_templates = service.list_templates(FileType.POWERPOINT)
    print(f"Available PowerPoint templates: {ppt_templates}")

    # Generate using template
    if "invoice" in pdf_templates:
        result = await service.generate_file(
            file_type=FileType.PDF,
            template_name="invoice",
            data={
                "invoice_number": "INV-TEMPLATE-001",
                "invoice_date": "2025-01-15",
                "due_date": "2025-02-15",
                "from_info": {"name": "Template Corp", "email": "info@template.com"},
                "to_info": {"name": "Client Inc", "email": "ap@client.com"},
                "line_items": [
                    {
                        "description": "Service A",
                        "quantity": 1,
                        "rate": 1000,
                        "amount": 1000,
                    }
                ],
            },
            filename="template_invoice.pdf",
        )
        print(f"✓ Generated from template: {result['filename']}")

    return result


async def run_all_examples():
    """Run all example functions."""
    print("=" * 70)
    print("FILE GENERATION MODULE - EXAMPLE USAGE")
    print("=" * 70)

    try:
        # PDF Examples
        await example_pdf_invoice()
        await example_pdf_report()

        # Excel Examples
        await example_excel_data_table()
        await example_excel_financial_report()

        # PowerPoint Examples
        await example_powerpoint_business_presentation()

        # Image Examples (Note: Requires Vertex AI setup)
        # Uncomment when Vertex AI is configured
        # await example_image_generation()

        # Batch and Template Examples
        await example_batch_generation()
        await example_template_usage()

        print("\n" + "=" * 70)
        print("ALL EXAMPLES COMPLETED SUCCESSFULLY!")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Main entry point."""
    # Check environment
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        print("⚠️  Warning: GOOGLE_CLOUD_PROJECT not set")
        print("   Set with: export GOOGLE_CLOUD_PROJECT='your-project-id'")
        print()

    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("⚠️  Warning: GOOGLE_APPLICATION_CREDENTIALS not set")
        print("   Set with: export GOOGLE_APPLICATION_CREDENTIALS='/path/to/key.json'")
        print()

    # Run examples
    asyncio.run(run_all_examples())


if __name__ == "__main__":
    main()
