# File Generation Module

Production-ready file generation tools for the Etherion AI Platform.

## Overview

This module provides comprehensive file generation capabilities integrated with:
- **Private GCS Storage**: Multi-tenant isolated buckets (`tnt-{tenant_id}-assets`)
- **BigQuery Indexing**: Metadata and searchability with per-tenant datasets
- **Vertex AI Search**: Vector cache integration for semantic search
- **Gemini 2.5 Flash Image**: AI-powered image generation (Nano Banana)
- **Signed URLs**: Secure temporary access (5-minute expiry by default)
- **MCP Protocol**: Model Context Protocol for agent integration

## Supported File Types

### 1. PDF Documents (ReportLab)
- Professional reports with multi-page layouts
- Invoices with line items and totals
- Forms with custom fields
- Tables, images, and styled content
- Custom headers and footers

### 2. Excel Spreadsheets (openpyxl)
- Multi-sheet workbooks
- Formatted tables with styles
- Financial reports with formulas
- Charts and graphs (bar, line, pie)
- Data validation and conditional formatting

### 3. PowerPoint Presentations (python-pptx)
- Business presentations
- Report decks with data tables
- Pitch decks
- Multiple slide layouts (title, content, two-column, etc.)
- Images, tables, and bullet points

### 4. Images (Gemini 2.5 Flash Image)
- Text-to-image generation
- Image editing with prompts
- Style transfer
- Image variations
- Character consistency across multiple images

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  File Generation Service                     │
│  (Unified API for PDF, Excel, PowerPoint, Image)            │
└──────────────┬──────────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       │   Template     │
       │    Manager     │
       └───────┬────────┘
               │
    ┌──────────┴──────────────────────┐
    │                                  │
    ▼                                  ▼
┌─────────────────┐          ┌──────────────────┐
│ Base Generator  │          │   Specialized    │
│                 │          │   Generators     │
│ - GCS Storage   │◄─────────┤                  │
│ - BigQuery      │          │ - PDFGenerator   │
│ - Signed URLs   │          │ - ExcelGenerator │
│ - Base64        │          │ - PresentationGen│
└────────┬────────┘          │ - ImageGenerator │
         │                   └──────────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌──────┐  ┌──────────────┐
│ GCS  │  │  BigQuery    │
│Bucket│  │  Dataset     │
└──────┘  └───────┬──────┘
                  │
                  ▼
          ┌──────────────┐
          │ Vertex AI    │
          │   Search     │
          └──────────────┘
```

## Installation

### Dependencies

Add to `requirements.txt`:
```txt
# File generation
reportlab>=4.0.0
openpyxl>=3.1.0
python-pptx>=0.6.21
Pillow>=10.0.0

# Google Cloud
google-cloud-storage>=2.10.0
google-cloud-bigquery>=3.11.0
google-cloud-aiplatform>=1.38.0
```

Install:
```bash
pip install -r requirements.txt
```

### GCP Setup

1. **Enable APIs**:
   ```bash
   gcloud services enable storage.googleapis.com
   gcloud services enable bigquery.googleapis.com
   gcloud services enable aiplatform.googleapis.com
   ```

2. **Set Environment Variables**:
   ```bash
   export GOOGLE_CLOUD_PROJECT="your-project-id"
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
   ```

3. **Create Service Account** (if needed):
   ```bash
   gcloud iam service-accounts create etherion-file-gen \
     --display-name="Etherion File Generation Service"
   
   gcloud projects add-iam-policy-binding $PROJECT_ID \
     --member="serviceAccount:etherion-file-gen@$PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/storage.admin"
   
   gcloud projects add-iam-policy-binding $PROJECT_ID \
     --member="serviceAccount:etherion-file-gen@$PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/bigquery.admin"
   ```

## Quick Start

### Basic Usage

```python
from src.tools.file_generation import FileGenerationService, FileType

# Initialize service
service = FileGenerationService(
    tenant_id="acme_corp",
    agent_id="agent_001",
    job_id="job_12345",
    user_id="user_456"
)

# Generate a PDF invoice
invoice_result = await service.generate_invoice(
    invoice_number="INV-2025-001",
    from_info={
        "name": "Acme Corporation",
        "address": "123 Business St",
        "email": "billing@acme.com"
    },
    to_info={
        "name": "Client Corp",
        "address": "456 Client Ave",
        "email": "ap@client.com"
    },
    line_items=[
        {
            "description": "Consulting Services",
            "quantity": 10,
            "rate": 150.00,
            "amount": 1500.00
        },
        {
            "description": "Software License",
            "quantity": 1,
            "rate": 500.00,
            "amount": 500.00
        }
    ]
)

print(f"Invoice URL: {invoice_result['download_url']}")
print(f"Asset ID: {invoice_result['asset_id']}")
```

### Excel Financial Report

```python
# Generate financial report
report_result = await service.generate_financial_report(
    title="Q1 2025 Financial Report",
    period="Q1 2025",
    summary_data={
        "Total Revenue": 125000.50,
        "Total Expenses": 87500.25,
        "Net Profit": 37500.25,
        "Profit Margin": 0.30
    },
    detail_data=[
        {
            "Date": "2025-01-15",
            "Category": "Sales",
            "Amount": 50000.00,
            "Description": "Product Sales"
        },
        {
            "Date": "2025-02-20",
            "Category": "Services",
            "Amount": 75000.50,
            "Description": "Consulting Revenue"
        }
    ]
)
```

### PowerPoint Presentation

```python
# Generate business presentation
presentation_result = await service.generate_presentation(
    title="Q1 Business Review",
    slides=[
        {
            "type": "title",
            "content": {
                "title": "Q1 Business Review",
                "subtitle": "January - March 2025"
            }
        },
        {
            "type": "title_content",
            "content": {
                "title": "Key Achievements",
                "bullet_points": [
                    "30% revenue growth",
                    "Launched 3 new products",
                    "Expanded to 5 new markets",
                    "Achieved 95% customer satisfaction"
                ]
            }
        },
        {
            "type": "table",
            "content": {
                "title": "Financial Summary",
                "table_data": [
                    ["Metric", "Q1 2025", "Q4 2024", "Change"],
                    ["Revenue", "$125K", "$100K", "+25%"],
                    ["Profit", "$37.5K", "$28K", "+34%"],
                    ["Customers", "150", "120", "+25%"]
                ]
            }
        }
    ]
)
```

### AI Image Generation

```python
# Generate image with Gemini 2.5 Flash Image
image_result = await service.generate_image(
    prompt="A modern office workspace with natural lighting, plants, and minimalist design",
    description="Office workspace concept",
    tags=["office", "workspace", "modern"]
)

# Edit an existing image
edited_result = await service.image_generator.edit_image(
    base_image_bytes=original_image_bytes,
    edit_prompt="Add more plants and warmer lighting"
)

# Generate variations
variations = await service.image_generator.generate_variations(
    base_image_bytes=base_image_bytes,
    num_variations=3,
    variation_strength=0.7
)
```

## Using Templates

### List Available Templates

```python
# List templates
pdf_templates = service.list_templates(FileType.PDF)
print(f"PDF Templates: {pdf_templates}")

excel_templates = service.list_templates(FileType.EXCEL)
print(f"Excel Templates: {excel_templates}")

ppt_templates = service.list_templates(FileType.POWERPOINT)
print(f"PowerPoint Templates: {ppt_templates}")
```

### Generate with Template

```python
# Generate using a template
result = await service.generate_file(
    file_type=FileType.PDF,
    template_name="invoice",
    data={
        "invoice_number": "INV-2025-001",
        "from_info": {...},
        "to_info": {...},
        "line_items": [...]
    },
    filename="invoice_2025_001.pdf"
)
```

### Create Custom Template

```python
from src.tools.file_generation.template_manager import get_template_manager

template_manager = get_template_manager()

# Create custom invoice template
custom_template = {
    "type": "invoice",
    "page_size": "A4",
    "margins": {"top": 50, "bottom": 50, "left": 50, "right": 50},
    "header": {
        "show": True,
        "logo_path": "gs://bucket/logo.png",
        "company_name": "Acme Corp"
    },
    "footer": {
        "show": True,
        "text": "Payment terms: Net 30 days"
    },
    "theme": {
        "primary_color": "#366092",
        "secondary_color": "#4F81BD"
    }
}

# Save for specific tenant
template_manager.save_template(
    doc_type="pdf",
    template_name="custom_invoice",
    template_config=custom_template,
    tenant_id="acme_corp"
)
```

## Advanced Features

### Batch Generation

```python
# Generate multiple files in batch
requests = [
    {
        "file_type": "pdf",
        "template": "invoice",
        "data": {...},
        "kwargs": {"filename": "invoice_001.pdf"}
    },
    {
        "file_type": "excel",
        "template": "data_table",
        "data": {...},
        "kwargs": {"filename": "report_001.xlsx"}
    },
    {
        "file_type": "powerpoint",
        "template": "business_deck",
        "data": {...},
        "kwargs": {"filename": "presentation_001.pptx"}
    }
]

results = await service.batch_generate(requests)

for i, result in enumerate(results):
    if result["success"]:
        print(f"Generated {i+1}: {result['result']['download_url']}")
    else:
        print(f"Failed {i+1}: {result['error']}")
```

### Custom Storage Configuration

```python
from src.tools.file_generation import PDFGeneratorTool

# Initialize with custom project
pdf_gen = PDFGeneratorTool(
    tenant_id="custom_tenant",
    agent_id="agent_001",
    job_id="job_001",
    project_id="custom-project-id"
)

# Generate with custom expiration
result = await pdf_gen.generate_simple_document(
    title="Custom Document",
    paragraphs=["Content here..."]
)

# Get signed URL with custom expiration (60 minutes)
extended_url = pdf_gen.generate_signed_url(
    gcs_uri=result["gcs_uri"],
    expiration_minutes=60
)
```

### Direct Access to Generators

```python
# Access specific generators directly
pdf_gen = service.pdf_generator
excel_gen = service.excel_generator
ppt_gen = service.presentation_generator
img_gen = service.image_generator

# Generate with full control
pdf_result = await pdf_gen.generate_report(
    title="Custom Report",
    content=[
        {
            "type": "heading",
            "text": "Section 1",
            "level": 2
        },
        {
            "type": "paragraph",
            "text": "This is paragraph content...",
            "style": "CustomBody"
        },
        {
            "type": "table",
            "data": [
                ["Header 1", "Header 2"],
                ["Value 1", "Value 2"]
            ]
        },
        {
            "type": "spacer",
            "height": 20
        }
    ]
)
```

## Storage and Access

### Storage Architecture

All generated files are stored with the following structure:

```
gs://tnt-{tenant_id}-assets/
  └── {agent_id}/
      └── {job_id}/
          ├── invoice_001.pdf
          ├── report_001.xlsx
          └── presentation_001.pptx
```

### BigQuery Schema

Files are indexed in BigQuery with the following schema:

```sql
CREATE TABLE `tnt_{tenant_id}.assets` (
  asset_id STRING NOT NULL,
  job_id STRING NOT NULL,
  tenant_id STRING NOT NULL,
  agent_name STRING,
  agent_id STRING,
  user_id STRING,
  mime_type STRING,
  gcs_uri STRING,
  filename STRING,
  size_bytes INT64,
  text_extract STRING,
  description STRING,
  vector_embedding ARRAY<FLOAT64>,
  created_at TIMESTAMP,
  created_by STRING,
  tags ARRAY<STRING>,
  metadata JSON
)
PARTITION BY DATE(created_at)
CLUSTER BY tenant_id, agent_id;
```

### Querying Assets

```python
from google.cloud import bigquery

client = bigquery.Client()

# Query assets for a tenant
query = f"""
SELECT 
    asset_id,
    filename,
    mime_type,
    gcs_uri,
    created_at,
    description,
    tags
FROM `{project_id}.tnt_{tenant_id}.assets`
WHERE agent_id = @agent_id
  AND DATE(created_at) = CURRENT_DATE()
ORDER BY created_at DESC
LIMIT 100
"""

job_config = bigquery.QueryJobConfig(
    query_parameters=[
        bigquery.ScalarQueryParameter("agent_id", "STRING", "agent_001")
    ]
)

results = client.query(query, job_config=job_config).result()

for row in results:
    print(f"{row.filename}: {row.gcs_uri}")
```

## Security and Privacy

### Multi-Tenant Isolation

- **GCS Buckets**: Separate bucket per tenant (`tnt-{tenant_id}-assets`)
- **BigQuery Datasets**: Separate dataset per tenant (`tnt_{tenant_id}`)
- **IAM Policies**: Per-tenant access control
- **No Cross-Tenant Access**: Enforced at infrastructure level

### Signed URLs

- **Short-Lived**: Default 5-minute expiry
- **HTTPS Only**: Encrypted transport
- **No Public Access**: All buckets are private
- **Audit Trail**: All access logged in BigQuery

### Data Privacy

- **Private by Default**: No public URLs or links
- **Encrypted at Rest**: GCS encryption
- **Encrypted in Transit**: TLS 1.2+
- **Compliance Ready**: GDPR, HIPAA, SOC 2 compatible

## Testing

### Unit Tests

```python
import pytest
from src.tools.file_generation import FileGenerationService

@pytest.mark.asyncio
async def test_generate_pdf_invoice():
    service = FileGenerationService(
        tenant_id="test_tenant",
        agent_id="test_agent",
        job_id="test_job"
    )
    
    result = await service.generate_invoice(
        invoice_number="TEST-001",
        from_info={"name": "Test Corp"},
        to_info={"name": "Client"},
        line_items=[
            {"description": "Test", "quantity": 1, "rate": 100, "amount": 100}
        ]
    )
    
    assert result["asset_id"]
    assert result["download_url"]
    assert result["mime_type"] == "application/pdf"

@pytest.mark.asyncio
async def test_generate_excel_data_table():
    service = FileGenerationService(
        tenant_id="test_tenant",
        agent_id="test_agent",
        job_id="test_job"
    )
    
    result = await service.excel_generator.generate_data_table(
        data=[
            {"Name": "Alice", "Age": 30, "City": "NYC"},
            {"Name": "Bob", "Age": 25, "City": "LA"}
        ]
    )
    
    assert result["asset_id"]
    assert "xlsx" in result["filename"]
```

### Integration Tests

```bash
# Run integration tests
pytest tests/integration/test_file_generation.py -v

# Run with coverage
pytest tests/integration/test_file_generation.py --cov=src/tools/file_generation
```

## Performance

### Benchmarks

| File Type | Average Generation Time | File Size (Avg) |
|-----------|------------------------|-----------------|
| PDF (Simple) | 100-200ms | 50-100KB |
| PDF (Complex) | 300-500ms | 200-500KB |
| Excel (Table) | 150-250ms | 20-50KB |
| Excel (Complex) | 400-600ms | 100-300KB |
| PowerPoint | 200-400ms | 100-500KB |
| Image (AI) | 2-5 seconds | 500KB-2MB |

### Optimization Tips

1. **Batch Operations**: Use `batch_generate()` for multiple files
2. **Template Reuse**: Cache templates for repeated use
3. **Async Everywhere**: All operations are async
4. **Connection Pooling**: GCS/BigQuery clients are reused
5. **Lazy Loading**: Generators instantiated on first use

## Troubleshooting

### Common Issues

**Issue**: "Permission denied" when accessing GCS
```bash
# Solution: Check service account permissions
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:*"
```

**Issue**: BigQuery table not found
```python
# Solution: Ensure table exists (auto-created on first use)
service._ensure_bigquery_table_exists()
```

**Issue**: Signed URL expired
```python
# Solution: Generate new URL with longer expiration
new_url = service.pdf_generator.generate_signed_url(
    gcs_uri=result["gcs_uri"],
    expiration_minutes=60  # 1 hour
)
```

**Issue**: Gemini 2.5 Flash Image not available
```bash
# Solution: Check region and quota
gcloud ai models list --region=us-central1 | grep gemini-2.5-flash-image
```

## Monitoring and Logging

### Cloud Logging

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Logs are automatically sent to Cloud Logging
# View in console: https://console.cloud.google.com/logs
```

### Metrics

Track generation metrics:

```python
from google.cloud import monitoring_v3

client = monitoring_v3.MetricServiceClient()
project_name = f"projects/{project_id}"

# Create custom metric for file generation
# (Implementation details in monitoring docs)
```

## Contributing

See [CONTRIBUTING.md](../../../CONTRIBUTING.md) for guidelines.

## License

Copyright © 2025 Etherion AI Platform. All rights reserved.

## Support

- Documentation: https://docs.etherion.ai
- Issues: https://github.com/etherion/platform/issues
- Email: support@etherion.ai