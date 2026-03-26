# File Generation Quick Start Guide

Get started with the Etherion AI Platform file generation module in 5 minutes.

## Prerequisites

- Python 3.9+
- Google Cloud Project with billing enabled
- Service account with Storage Admin and BigQuery Admin roles

## Installation

1. **Install dependencies**:
```bash
pip install reportlab openpyxl python-pptx Pillow google-cloud-storage google-cloud-bigquery google-cloud-aiplatform
```

2. **Set environment variables**:
```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

3. **Enable required APIs**:
```bash
gcloud services enable storage.googleapis.com bigquery.googleapis.com aiplatform.googleapis.com
```

## Basic Usage

### 1. Generate a PDF Invoice (30 seconds)

```python
import asyncio
from src.tools.file_generation import FileGenerationService

async def create_invoice():
    # Initialize service
    service = FileGenerationService(
        tenant_id="my_company",
        agent_id="agent_001",
        job_id="job_12345"
    )
    
    # Generate invoice
    result = await service.generate_invoice(
        invoice_number="INV-2025-001",
        from_info={
            "name": "Your Company Inc.",
            "address": "123 Business St",
            "email": "billing@yourcompany.com"
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
            }
        ]
    )
    
    print(f"Invoice created!")
    print(f"Download URL: {result['download_url']}")
    return result

# Run it
asyncio.run(create_invoice())
```

**Output**:
```
Invoice created!
Download URL: https://storage.googleapis.com/tnt-my_company-assets/...
```

### 2. Generate an Excel Report (30 seconds)

```python
async def create_excel_report():
    service = FileGenerationService(
        tenant_id="my_company",
        agent_id="agent_001",
        job_id="job_67890"
    )
    
    # Sample data
    sales_data = [
        {"Product": "Widget A", "Sales": 1000, "Revenue": 25000},
        {"Product": "Widget B", "Sales": 750, "Revenue": 18750},
        {"Product": "Widget C", "Sales": 1250, "Revenue": 31250}
    ]
    
    # Generate Excel file
    result = await service.excel_generator.generate_data_table(
        data=sales_data,
        filename="sales_report.xlsx"
    )
    
    print(f"Excel report created: {result['download_url']}")
    return result

asyncio.run(create_excel_report())
```

### 3. Generate a PowerPoint Presentation (1 minute)

```python
async def create_presentation():
    service = FileGenerationService(
        tenant_id="my_company",
        agent_id="agent_001",
        job_id="job_ppt_001"
    )
    
    result = await service.generate_presentation(
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
                        "Expanded to 5 new markets"
                    ]
                }
            }
        ],
        filename="q1_review.pptx"
    )
    
    print(f"Presentation created: {result['download_url']}")
    return result

asyncio.run(create_presentation())
```

### 4. Generate AI Images (2 minutes)

```python
async def create_ai_image():
    service = FileGenerationService(
        tenant_id="my_company",
        agent_id="agent_001",
        job_id="job_img_001"
    )
    
    result = await service.generate_image(
        prompt="A modern office workspace with natural lighting and plants",
        description="Office concept art"
    )
    
    print(f"Image created: {result['download_url']}")
    return result

asyncio.run(create_ai_image())
```

## Common Patterns

### Pattern 1: Batch Generation

Generate multiple files at once:

```python
async def batch_files():
    service = FileGenerationService(
        tenant_id="my_company",
        agent_id="agent_001",
        job_id="job_batch_001"
    )
    
    requests = [
        {
            "file_type": "pdf",
            "data": {"title": "Report 1", "paragraphs": ["Content..."]},
            "kwargs": {"filename": "report1.pdf"}
        },
        {
            "file_type": "excel",
            "data": {"data": [{"A": 1, "B": 2}]},
            "kwargs": {"filename": "data.xlsx"}
        }
    ]
    
    results = await service.batch_generate(requests)
    print(f"Generated {len(results)} files")
    return results

asyncio.run(batch_files())
```

### Pattern 2: Using Templates

```python
async def use_template():
    service = FileGenerationService(
        tenant_id="my_company",
        agent_id="agent_001",
        job_id="job_template_001"
    )
    
    # List available templates
    templates = service.list_templates(FileType.PDF)
    print(f"Available templates: {templates}")
    
    # Use a template
    result = await service.generate_file(
        file_type=FileType.PDF,
        template_name="invoice",
        data={
            "invoice_number": "INV-001",
            # ... other invoice data
        }
    )
    
    return result

asyncio.run(use_template())
```

### Pattern 3: Custom Expiration URLs

```python
async def custom_url_expiration():
    service = FileGenerationService(
        tenant_id="my_company",
        agent_id="agent_001",
        job_id="job_001"
    )
    
    # Generate file
    result = await service.generate_invoice(...)
    
    # Create URL with 1-hour expiration
    long_url = service.pdf_generator.generate_signed_url(
        gcs_uri=result['gcs_uri'],
        expiration_minutes=60
    )
    
    print(f"URL valid for 1 hour: {long_url}")
    return long_url
```

## Project Structure

After setup, your files will be organized as:

```
GCS Buckets:
  tnt-my_company-assets/
    agent_001/
      job_12345/
        invoice_001.pdf
        report_001.xlsx

BigQuery:
  project.tnt_my_company.assets
    - All file metadata
    - Searchable, queryable
```

## Troubleshooting

### Issue: "Permission denied"
**Solution**: Check service account has Storage Admin and BigQuery Admin roles:
```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:YOUR_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"
```

### Issue: "Bucket already exists"
**Solution**: This is normal - the module reuses existing buckets. No action needed.

### Issue: "Model not found" (images)
**Solution**: Ensure Vertex AI is enabled and you have quota:
```bash
gcloud ai models list --region=us-central1
```

### Issue: "URL expired"
**Solution**: Generate a new signed URL:
```python
new_url = service.pdf_generator.generate_signed_url(
    gcs_uri=result['gcs_uri'],
    expiration_minutes=60
)
```

## Next Steps

1. **Read the full documentation**: See `README.md` for complete API reference
2. **Run examples**: Execute `python -m src.tools.file_generation.examples`
3. **Customize templates**: Modify JSON templates in `templates/` directory
4. **Integrate with agents**: Connect to MCP protocol for AI agent usage
5. **Add to pipeline**: Integrate with BigQuery and Vertex AI Search

## Performance Tips

- Use batch operations for multiple files
- Cache template manager instance
- Reuse service instances across requests
- Enable connection pooling for GCS/BigQuery

## Security Reminders

- ✅ All buckets are private by default
- ✅ Signed URLs expire (5 min default)
- ✅ Per-tenant isolation enforced
- ✅ No cross-tenant data access
- ✅ Audit trail in BigQuery

## Support

- **Documentation**: `README.md`
- **Examples**: `examples.py`
- **Issues**: GitHub Issues
- **Email**: support@etherion.ai

---

**You're ready to go!** Start generating files with production-ready tools.