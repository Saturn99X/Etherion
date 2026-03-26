# Migration Guide: Integrating File Generation Module

This guide helps you migrate existing code to use the new file generation module or integrate it into your current Etherion AI Platform setup.

## Overview

The file generation module provides a clean, unified API for generating PDFs, Excel files, PowerPoint presentations, and AI images. It replaces deprecated or scattered file generation tools with a production-ready, multi-tenant solution.

---

## Quick Migration Checklist

- [ ] Install new dependencies
- [ ] Update imports
- [ ] Replace old file generation calls
- [ ] Update storage references
- [ ] Test multi-tenant isolation
- [ ] Verify BigQuery indexing
- [ ] Update documentation

---

## 1. Dependencies Migration

### Before
```txt
# Old requirements (if any)
pdfkit
xlsxwriter
reportlab<4.0
```

### After
```txt
# New requirements
reportlab>=4.0.0
openpyxl>=3.1.0
python-pptx>=0.6.21
Pillow>=10.0.0
google-cloud-storage>=2.10.0
google-cloud-bigquery>=3.11.0
google-cloud-aiplatform>=1.38.0
```

### Installation
```bash
pip install reportlab openpyxl python-pptx Pillow \
    google-cloud-storage google-cloud-bigquery google-cloud-aiplatform
```

---

## 2. Import Migration

### Before
```python
from src.tools.save_to_gcs_tool import SaveToGCSTool
from src.tools.save_to_document_tool import SaveToDocumentTool
# Or custom implementations
```

### After
```python
from src.tools.file_generation import FileGenerationService, FileType
```

---

## 3. Code Migration Examples

### Example 1: Simple PDF Generation

#### Before (Custom Implementation)
```python
from reportlab.pdfgen import canvas
from google.cloud import storage

def generate_pdf(content, filename):
    # Create PDF manually
    c = canvas.Canvas(filename)
    c.drawString(100, 750, content)
    c.save()
    
    # Upload to GCS manually
    client = storage.Client()
    bucket = client.bucket("my-bucket")
    blob = bucket.blob(filename)
    blob.upload_from_filename(filename)
    
    return f"gs://my-bucket/{filename}"
```

#### After (File Generation Module)
```python
from src.tools.file_generation import FileGenerationService

async def generate_pdf(content, filename):
    service = FileGenerationService(
        tenant_id="my_tenant",
        agent_id="my_agent",
        job_id="my_job"
    )
    
    result = await service.pdf_generator.generate_simple_document(
        title="Document",
        paragraphs=[content],
        filename=filename
    )
    
    return result  # Contains gcs_uri, download_url, asset_id, etc.
```

### Example 2: Excel Data Export

#### Before
```python
import xlsxwriter

def export_to_excel(data, filename):
    workbook = xlsxwriter.Workbook(filename)
    worksheet = workbook.add_worksheet()
    
    # Write data manually
    for row_idx, row in enumerate(data):
        for col_idx, value in enumerate(row):
            worksheet.write(row_idx, col_idx, value)
    
    workbook.close()
    # Manual upload to GCS...
```

#### After
```python
from src.tools.file_generation import FileGenerationService

async def export_to_excel(data, filename):
    service = FileGenerationService(
        tenant_id="my_tenant",
        agent_id="my_agent",
        job_id="my_job"
    )
    
    result = await service.excel_generator.generate_data_table(
        data=data,
        filename=filename
    )
    
    return result
```

### Example 3: Invoice Generation

#### Before (Multiple Steps)
```python
def generate_invoice(invoice_data):
    # Step 1: Generate PDF manually
    pdf = create_invoice_pdf(invoice_data)
    
    # Step 2: Upload to GCS
    gcs_uri = upload_to_gcs(pdf, "invoices")
    
    # Step 3: Index in database (if any)
    db.save_invoice_record(gcs_uri, invoice_data)
    
    # Step 4: Generate public URL
    url = get_public_url(gcs_uri)
    
    return url
```

#### After (Single Call)
```python
async def generate_invoice(invoice_data):
    service = FileGenerationService(
        tenant_id=invoice_data["tenant_id"],
        agent_id="billing_agent",
        job_id=invoice_data["job_id"]
    )
    
    result = await service.generate_invoice(
        invoice_number=invoice_data["number"],
        from_info=invoice_data["from"],
        to_info=invoice_data["to"],
        line_items=invoice_data["items"]
    )
    
    # Returns: asset_id, gcs_uri, download_url, preview_base64
    return result
```

---

## 4. Storage Migration

### Before: Manual GCS Management
```python
from google.cloud import storage

def upload_file(file_bytes, bucket_name, filename):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(filename)
    blob.upload_from_string(file_bytes)
    return f"gs://{bucket_name}/{filename}"
```

### After: Automatic Multi-Tenant Storage
```python
# Storage is handled automatically by FileGenerationService
# Files are organized by tenant, agent, and job:
# gs://tnt-{tenant_id}-assets/{agent_id}/{job_id}/{filename}

service = FileGenerationService(
    tenant_id="acme_corp",  # Automatically creates tnt-acme_corp-assets bucket
    agent_id="agent_001",
    job_id="job_12345"
)

# All generated files are automatically stored and indexed
result = await service.generate_file(...)
print(result["gcs_uri"])  # gs://tnt-acme_corp-assets/agent_001/job_12345/file.pdf
```

---

## 5. BigQuery Integration

### New Feature: Automatic Indexing

All generated files are automatically indexed in BigQuery:

```python
# No manual indexing needed - automatic on generation
result = await service.generate_invoice(...)

# Query your files later
from google.cloud import bigquery

client = bigquery.Client()
query = f"""
SELECT 
    asset_id,
    filename,
    gcs_uri,
    created_at,
    tags
FROM `project.tnt_{tenant_id}.assets`
WHERE agent_id = @agent_id
  AND DATE(created_at) = CURRENT_DATE()
ORDER BY created_at DESC
"""

results = client.query(query, 
    query_parameters=[
        bigquery.ScalarQueryParameter("agent_id", "STRING", "agent_001")
    ]
).result()

for row in results:
    print(f"{row.filename}: {row.gcs_uri}")
```

---

## 6. Signed URLs vs Public URLs

### Before: Public URLs or Manual Signing
```python
# Option 1: Public bucket (insecure)
url = f"https://storage.googleapis.com/{bucket}/{filename}"

# Option 2: Manual signing
from google.cloud import storage
bucket = storage.Client().bucket(bucket_name)
blob = bucket.blob(filename)
url = blob.generate_signed_url(expiration=timedelta(hours=1))
```

### After: Automatic Signed URLs
```python
# Automatic 5-minute signed URL
result = await service.generate_invoice(...)
print(result["download_url"])  # Signed, expires in 5 min

# Custom expiration
longer_url = service.pdf_generator.generate_signed_url(
    gcs_uri=result["gcs_uri"],
    expiration_minutes=60  # 1 hour
)
```

---

## 7. Template System Migration

### Before: Hard-coded Templates
```python
def generate_invoice(data):
    # Hard-coded layout
    pdf = canvas.Canvas(filename)
    pdf.drawString(100, 750, "INVOICE")
    pdf.drawString(100, 700, f"Number: {data['number']}")
    # ... more hard-coded positioning
    pdf.save()
```

### After: JSON Templates
```python
# Create reusable template
from src.tools.file_generation.template_manager import get_template_manager

template_manager = get_template_manager()

invoice_template = {
    "type": "invoice",
    "page_size": "LETTER",
    "header": {"show": True, "logo_path": "gs://bucket/logo.png"},
    "footer": {"text": "Payment terms: Net 30 days"},
    "theme": {"primary_color": "#366092"}
}

template_manager.save_template(
    doc_type="pdf",
    template_name="company_invoice",
    template_config=invoice_template,
    tenant_id="acme_corp"
)

# Use template
result = await service.generate_file(
    file_type=FileType.PDF,
    template_name="company_invoice",
    data=invoice_data
)
```

---

## 8. Batch Operations Migration

### Before: Sequential Generation
```python
results = []
for item in items:
    pdf = generate_pdf(item)
    results.append(pdf)
```

### After: Batch Generation
```python
requests = [
    {
        "file_type": "pdf",
        "data": {"title": item["title"], "paragraphs": item["content"]},
        "kwargs": {"filename": f"{item['id']}.pdf"}
    }
    for item in items
]

results = await service.batch_generate(requests)
```

---

## 9. Error Handling Migration

### Before
```python
try:
    pdf = generate_pdf(data)
except Exception as e:
    print(f"Error: {e}")
    return None
```

### After (with 131 Framework compatibility)
```python
import logging

logger = logging.getLogger(__name__)

try:
    result = await service.generate_invoice(data)
    logger.info(f"Generated invoice: {result['asset_id']}")
    return result
except Exception as e:
    logger.error(f"Invoice generation failed", exc_info=True, extra={
        "tenant_id": service.tenant_id,
        "job_id": service.job_id,
        "error_code": "FILE_GEN_001"
    })
    raise
```

---

## 10. Multi-Tenant Migration

### Before: Single Bucket
```python
# All tenants share one bucket
BUCKET_NAME = "company-files"

def save_file(filename):
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)  # No isolation
    blob.upload_from_filename(filename)
```

### After: Per-Tenant Isolation
```python
# Each tenant gets own bucket: tnt-{tenant_id}-assets
service_tenant_a = FileGenerationService(
    tenant_id="tenant_a",  # Uses tnt-tenant_a-assets
    agent_id="agent_001",
    job_id="job_001"
)

service_tenant_b = FileGenerationService(
    tenant_id="tenant_b",  # Uses tnt-tenant_b-assets
    agent_id="agent_001",
    job_id="job_002"
)

# Complete isolation at infrastructure level
result_a = await service_tenant_a.generate_invoice(...)
result_b = await service_tenant_b.generate_invoice(...)

# tenant_a cannot access tenant_b's files (enforced by IAM)
```

---

## 11. Testing Migration

### Before: Manual Testing
```python
def test_pdf_generation():
    pdf = generate_pdf("Test content", "test.pdf")
    assert os.path.exists("test.pdf")
```

### After: Async Testing
```python
import pytest

@pytest.mark.asyncio
async def test_pdf_generation():
    service = FileGenerationService(
        tenant_id="test_tenant",
        agent_id="test_agent",
        job_id="test_job"
    )
    
    result = await service.pdf_generator.generate_simple_document(
        title="Test Document",
        paragraphs=["Test content"]
    )
    
    assert result["asset_id"]
    assert result["download_url"]
    assert result["mime_type"] == "application/pdf"
```

---

## 12. Configuration Migration

### Before: Environment Variables
```bash
export GCS_BUCKET="my-bucket"
export PDF_TEMPLATE_DIR="/app/templates"
```

### After: Service Configuration
```python
# Environment variables (required)
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"

# Configuration is handled by the service
service = FileGenerationService(
    tenant_id="my_tenant",
    agent_id="my_agent",
    job_id="my_job",
    project_id="custom-project-id"  # Optional override
)
```

---

## 13. Monitoring and Logging

### New: Automatic Logging
```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# All operations are automatically logged
service = FileGenerationService(...)
result = await service.generate_invoice(...)

# Logs include:
# - INFO: Initialization
# - INFO: File generation started
# - INFO: Saved to GCS
# - INFO: Indexed in BigQuery
# - INFO: Generation completed
```

### Query Logs in BigQuery
```sql
SELECT 
    asset_id,
    filename,
    agent_id,
    created_at,
    size_bytes,
    tags,
    metadata
FROM `project.tnt_my_tenant.assets`
WHERE DATE(created_at) >= CURRENT_DATE() - 7
ORDER BY created_at DESC;
```

---

## 14. Performance Considerations

### Optimization Tips

1. **Reuse Service Instances**
```python
# Bad: Creating new service for each request
for request in requests:
    service = FileGenerationService(...)  # Slow
    await service.generate_file(...)

# Good: Reuse service instance
service = FileGenerationService(...)
for request in requests:
    await service.generate_file(...)
```

2. **Use Batch Operations**
```python
# Bad: Sequential generation
for item in items:
    await service.generate_file(...)

# Good: Batch generation
requests = [{"file_type": ..., "data": item} for item in items]
results = await service.batch_generate(requests)
```

3. **Cache Template Manager**
```python
# Good: Singleton pattern
from src.tools.file_generation.template_manager import get_template_manager

template_manager = get_template_manager()  # Cached
```

---

## 15. Common Migration Patterns

### Pattern 1: Replace SaveToGCSTool
```python
# Before
from src.tools.save_to_gcs_tool import SaveToGCSTool

tool = SaveToGCSTool()
result = tool.save_file(file_bytes, "bucket", "filename")

# After
service = FileGenerationService(...)
result = await service.pdf_generator.save_asset(
    file_bytes=pdf_bytes,
    filename="filename.pdf",
    mime_type="application/pdf"
)
```

### Pattern 2: Replace Custom PDF Generation
```python
# Before: Custom PDF code
def create_report(data):
    # 50+ lines of ReportLab code
    ...
    return pdf_bytes

# After: Use built-in generator
async def create_report(data):
    result = await service.pdf_generator.generate_report(
        title=data["title"],
        content=data["content"]
    )
    return result
```

### Pattern 3: Replace Excel Exports
```python
# Before: Manual Excel generation
import xlsxwriter

def export_data(data):
    # Manual cell writing, formatting, etc.
    ...

# After: Automatic formatting
async def export_data(data):
    result = await service.excel_generator.generate_data_table(
        data=data,
        filename="export.xlsx"
    )
    return result
```

---

## 16. Rollback Plan

If you need to rollback:

1. **Keep old code** until migration is validated
2. **Feature flags** to switch between old and new
3. **Parallel run** both systems initially
4. **Gradual migration** by tenant or feature

```python
# Feature flag example
USE_NEW_FILE_GENERATION = os.getenv("USE_NEW_FILE_GEN", "false") == "true"

if USE_NEW_FILE_GENERATION:
    result = await new_generate_invoice(data)
else:
    result = old_generate_invoice(data)
```

---

## 17. Support and Resources

- **Documentation**: `README.md`
- **Examples**: `examples.py`
- **Quick Start**: `QUICKSTART.md`
- **This Guide**: `MIGRATION_GUIDE.md`
- **Issues**: GitHub Issues
- **Email**: support@etherion.ai

---

## 18. Migration Timeline

### Week 1: Preparation
- [ ] Install dependencies
- [ ] Set up GCP resources
- [ ] Review documentation
- [ ] Identify files to migrate

### Week 2: Development
- [ ] Migrate critical paths
- [ ] Update imports
- [ ] Add tests
- [ ] Parallel run with old code

### Week 3: Testing
- [ ] Integration testing
- [ ] Performance testing
- [ ] Security review
- [ ] User acceptance testing

### Week 4: Deployment
- [ ] Deploy to DEV
- [ ] Deploy to Staging
- [ ] Deploy to Production
- [ ] Monitor and optimize

---

**Migration Complete!** You're now using the production-ready file generation module with multi-tenant isolation, automatic indexing, and secure storage.