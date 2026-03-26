"""
Google Cloud Function for intelligent data ingestion from GCS.
Triggers on file uploads and processes them with appropriate preprocessors.
"""

import functions_framework
import json
import logging
import os
import asyncio
from typing import Dict, Any, Optional
from google.cloud import storage
from google.cloud import bigquery
from google.cloud import secretmanager
from google.cloud import pubsub_v1
from google.cloud import aiplatform as vertexai
try:
    from vertexai.preview.language_models import TextEmbeddingModel
except Exception:  # pragma: no cover - safety in minimal envs
    TextEmbeddingModel = None  # type: ignore
import pandas as pd
from datetime import datetime
import hashlib

# Import preprocessors
# NOTE: Minimal inline preprocessors to avoid extra module files

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Initialize clients
storage_client = storage.Client()
secret_client = secretmanager.SecretManagerServiceClient()
publisher = pubsub_v1.PublisherClient()

# Configuration
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT')
VERTEX_LOCATION = os.getenv('VERTEX_AI_LOCATION', 'us-central1')
PUBSUB_TOPIC = os.getenv('PUBSUB_TOPIC', 'data-ingestion-complete')
BUCKET_NAME = os.getenv('INGESTION_BUCKET_NAME') or os.getenv('INGESTION_BUCKET') or 'etherion-data-ingestion'


class DataIngestionProcessor:
    """Main processor for handling data ingestion from GCS."""
    
    def __init__(self):
        pass
    
    async def process_file(self, bucket_name: str, file_name: str, tenant_id: str) -> Dict[str, Any]:
        """
        Process a file uploaded to GCS.
        
        Args:
            bucket_name: Name of the GCS bucket
            file_name: Name of the uploaded file
            tenant_id: ID of the tenant who uploaded the file
            
        Returns:
            Dict with processing results
        """
        try:
            # Get file metadata (get_blob populates metadata in one call)
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.get_blob(file_name)
            
            if blob is None:
                raise FileNotFoundError(f"File {file_name} not found in bucket {bucket_name}")
            
            # Get file info
            file_size = blob.size
            content_type = blob.content_type
            created_time = blob.time_created
            # Some storage backends or recent uploads may not have time_created available immediately.
            # Fall back to current UTC time to avoid None.isoformat() errors during manual HTTP invocations.
            try:
                created_time_iso = created_time.isoformat() if created_time else datetime.utcnow().isoformat()
            except Exception:
                created_time_iso = datetime.utcnow().isoformat()
            
            logger.info(f"Processing file: {file_name} (size: {file_size}, type: {content_type})")
            
            # Determine file type and select appropriate preprocessor
            file_extension = file_name.lower().split('.')[-1]
            
            if file_extension in ['txt', 'md', 'rst', 'docx', 'pdf']:
                # Text file processing
                result = await self._process_text_file(blob, tenant_id, file_name)
            elif file_extension in ['csv', 'xlsx', 'xls', 'json']:
                # Tabular data processing
                result = await self._process_tabular_file(blob, tenant_id, file_name)
            else:
                # Unsupported file type
                result = {
                    "success": False,
                    "error": f"Unsupported file type: {file_extension}",
                    "file_name": file_name,
                    "tenant_id": tenant_id
                }
            
            # Add metadata
            result.update({
                "file_name": file_name,
                "tenant_id": tenant_id,
                "file_size": file_size,
                "content_type": content_type,
                "created_time": created_time_iso,
                "processed_at": datetime.utcnow().isoformat()
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing file {file_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_name": file_name,
                "tenant_id": tenant_id
            }
    
    async def _process_text_file(self, blob, tenant_id: str, file_name: str) -> Dict[str, Any]:
        """Process text files using semantic chunking."""
        try:
            # Download file content
            content = blob.download_as_text()
            
            # Process with inline text preprocessor (naive paragraph split)
            await asyncio.sleep(0)
            parts = [p.strip() for p in (content or "").split("\n\n") if p.strip()]
            if not parts:
                parts = [content or ""]
            chunks = []
            for idx, p in enumerate(parts):
                chunks.append({
                    "content": p,
                    "metadata": {
                        "tenant_id": tenant_id,
                        "source_file": file_name,
                        "index": idx,
                        "strategy": "inline-paragraph-split",
                    },
                })
            
            # Store processed chunks
            chunk_metadata = []
            for i, chunk in enumerate(chunks):
                chunk_id = f"{tenant_id}_{file_name}_{i}_{hashlib.md5(chunk['content'].encode()).hexdigest()[:8]}"
                
                # Store chunk in GCS
                chunk_blob_name = f"processed/{tenant_id}/text_chunks/{chunk_id}.json"
                chunk_blob = storage_client.bucket(BUCKET_NAME).blob(chunk_blob_name)
                chunk_blob.upload_from_string(
                    json.dumps(chunk),
                    content_type='application/json'
                )
                
                chunk_metadata.append({
                    "chunk_id": chunk_id,
                    "blob_name": chunk_blob_name,
                    "size": len(chunk['content']),
                    "metadata": chunk.get('metadata', {})
                })

            # Insert chunks into BigQuery with embeddings
            try:
                bq_client = bigquery.Client(project=PROJECT_ID)
                _bq_ensure_table(bq_client, PROJECT_ID, tenant_id)
                # Compute embeddings in batch (fallback to zero vectors if vertex model not available)
                texts = [c["content"] for c in chunks]
                vectors: list[list[float]] = []
                if TextEmbeddingModel is not None:
                    try:
                        vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
                        model = TextEmbeddingModel.from_pretrained("text-embedding-005")
                        embs = model.get_embeddings(texts, task="RETRIEVAL_DOCUMENT")
                        for e in embs:
                            v = list(getattr(e, "values", []) or [])
                            vectors.append([float(x) for x in v])
                    except Exception:
                        vectors = []
                # Ensure fixed length vectors (768) if present, else empty
                if not vectors or len(vectors) != len(texts):
                    vectors = [ [] for _ in texts ]

                table_ref = f"{PROJECT_ID}.tnt_{tenant_id}.docs"
                now_iso = datetime.utcnow().isoformat()
                rows = []
                file_uri = f"gs://{blob.bucket.name}/{file_name}"
                for i, chunk in enumerate(chunks):
                    chunk_id = chunk_metadata[i]["chunk_id"]
                    vec = vectors[i] if i < len(vectors) else []
                    rows.append({
                        "doc_id": chunk_id,
                        "text_chunk": chunk["content"],
                        "vector_embedding": [float(x) for x in vec],
                        "metadata": chunk.get("metadata", {}),
                        "file_uri": file_uri,
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    })
                if rows:
                    errors = bq_client.insert_rows_json(table_ref, rows)
                    if errors:
                        logger.error(f"BigQuery insert errors for {file_name}: {errors}")
            except Exception as be:
                logger.error(f"BQ/Embedding step failed for {file_name}: {be}")
            
            return {
                "success": True,
                "file_type": "text",
                "chunks_created": len(chunks),
                "chunk_metadata": chunk_metadata,
                "total_size": len(content)
            }
            
        except Exception as e:
            logger.error(f"Error processing text file {file_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_type": "text"
            }
    
    async def _process_tabular_file(self, blob, tenant_id: str, file_name: str) -> Dict[str, Any]:
        """Process tabular files using pandas grouping."""
        try:
            # Download file content
            file_extension = file_name.lower().split('.')[-1]
            
            if file_extension == 'csv':
                content = blob.download_as_text()
                df = pd.read_csv(pd.StringIO(content))
            elif file_extension in ['xlsx', 'xls']:
                content = blob.download_as_bytes()
                df = pd.read_excel(content)
            elif file_extension == 'json':
                content = blob.download_as_text()
                df = pd.read_json(content)
            else:
                raise ValueError(f"Unsupported tabular file type: {file_extension}")
            
            # Process with inline tabular preprocessor (summary + sample)
            await asyncio.sleep(0)
            summary = {
                "rows": int(df.shape[0]),
                "cols": int(df.shape[1]),
                "columns": [str(c) for c in df.columns],
            }
            try:
                desc = df.describe(include="all").to_dict()
            except Exception:
                desc = {}
            try:
                sample = df.head(10).to_dict(orient="records")
            except Exception:
                sample = []
            processed_data = {
                "tenant_id": tenant_id,
                "source_file": file_name,
                "summary_stats": summary,
                "describe": desc,
                "sample": sample,
            }
            
            # Store processed data
            processed_blob_name = f"processed/{tenant_id}/tabular/{file_name}_processed.json"
            processed_blob = storage_client.bucket(BUCKET_NAME).blob(processed_blob_name)
            processed_blob.upload_from_string(
                json.dumps(processed_data),
                content_type='application/json'
            )
            
            return {
                "success": True,
                "file_type": "tabular",
                "rows_processed": len(df),
                "columns": list(df.columns),
                "processed_blob_name": processed_blob_name,
                "summary_stats": processed_data.get('summary_stats', {})
            }
            
        except Exception as e:
            logger.error(f"Error processing tabular file {file_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_type": "tabular"
            }
    
    async def publish_completion_event(self, result: Dict[str, Any]) -> None:
        """Publish completion event to Pub/Sub."""
        try:
            topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)
            
            message_data = {
                "event_type": "data_ingestion_complete",
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            message_bytes = json.dumps(message_data).encode('utf-8')
            future = publisher.publish(topic_path, message_bytes)
            future.result()  # Wait for publish to complete
            
            logger.info(f"Published completion event for {result.get('file_name')}")
            
        except Exception as e:
            logger.error(f"Error publishing completion event: {e}")


def _gsm_get_secret(project_id: str, secret_id: str) -> Optional[str]:
    try:
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        resp = secret_client.access_secret_version(request={"name": name})
        return resp.payload.data.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to access secret {secret_id}: {e}")
        return None


def _bq_ensure_table(client: bigquery.Client, project_id: str, tenant_id: str) -> bigquery.Table:
    dataset_id = f"tnt_{tenant_id}"
    table_id = "docs"
    ds_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    try:
        client.get_dataset(ds_ref)
    except Exception:
        ds_ref.location = "US"
        client.create_dataset(ds_ref, exists_ok=True)
    tbl_ref = f"{project_id}.{dataset_id}.{table_id}"
    try:
        return client.get_table(tbl_ref)
    except Exception:
        schema = [
            bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("text_chunk", "STRING"),
            bigquery.SchemaField("vector_embedding", "FLOAT", mode="REPEATED"),
            bigquery.SchemaField("metadata", "JSON"),
            bigquery.SchemaField("file_uri", "STRING"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
            bigquery.SchemaField("updated_at", "TIMESTAMP"),
        ]
        table = bigquery.Table(tbl_ref, schema=schema)
        return client.create_table(table)


@functions_framework.http
def pull_tenant_data(request):
    """
    HTTP puller to fetch tenant data from external silos and insert into BigQuery.

    Expected JSON body:
    {
      "tenant_id": "123",
      "provider": "slack",
      "limit": 20
    }
    """
    try:
        if request.method not in ("POST", "GET"):
            return {"error": "Method not allowed"}, 405
        payload = {}
        if request.method == "POST":
            try:
                payload = request.get_json() or {}
            except Exception:
                payload = {}
        else:
            # GET: allow query params
            payload = {k: v for k, v in request.args.items()}

        tenant_id = str(payload.get("tenant_id") or "").strip()
        provider = str(payload.get("provider") or "").strip().lower()
        limit = int(payload.get("limit") or 20)
        if not tenant_id or not provider:
            return {"error": "tenant_id and provider are required"}, 400

        if provider != "slack":
            return {"error": f"provider_not_supported:{provider}"}, 400

        # Fetch OAuth tokens from GSM using naming convention
        secret_id = f"{tenant_id}--{provider}--oauth_tokens"
        raw = _gsm_get_secret(PROJECT_ID, secret_id)
        if not raw:
            return {"error": "oauth_tokens_not_found"}, 404
        try:
            tokens = json.loads(raw)
        except Exception:
            tokens = {}
        access_token = tokens.get("access_token")
        if not access_token:
            return {"error": "missing_access_token"}, 400

        # Pull recent Slack conversations (lightweight sample: list channels)
        import requests
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get("https://slack.com/api/conversations.list", params={"limit": max(1, min(200, limit))}, headers=headers, timeout=12)
        data = resp.json() if resp.status_code < 500 else {"ok": False, "error": f"http_{resp.status_code}"}
        if not data.get("ok"):
            return {"error": "slack_api_error", "details": data}, 502
        channels = data.get("channels") or []

        # Prepare rows for BigQuery
        bq_client = bigquery.Client(project=PROJECT_ID)
        _bq_ensure_table(bq_client, PROJECT_ID, tenant_id)
        now = datetime.utcnow().isoformat()
        rows = []
        for ch in channels[:limit]:
            doc_id = f"slack:channel:{ch.get('id')}"
            text_chunk = f"Slack channel: {ch.get('name')} (members: {ch.get('num_members')})"
            metadata = {
                "provider": "slack",
                "channel_id": ch.get("id"),
                "name": ch.get("name"),
                "created": ch.get("created"),
                "is_private": ch.get("is_private"),
            }
            rows.append({
                "doc_id": doc_id,
                "text_chunk": text_chunk,
                "metadata": metadata,
                "created_at": now,
                "updated_at": now,
            })
        table_ref = f"{PROJECT_ID}.tnt_{tenant_id}.docs"
        errors = bq_client.insert_rows_json(table_ref, rows)
        if errors:
            return {"error": "bq_insert_errors", "details": errors}, 500

        return {"ok": True, "provider": provider, "tenant_id": tenant_id, "inserted": len(rows)}
    except Exception as e:
        logger.error(f"pull_tenant_data error: {e}")
        return {"error": str(e)}, 500


# Global processor instance
processor = DataIngestionProcessor()


@functions_framework.cloud_event
def process_uploaded_file(cloud_event):
    """
    Cloud Function entry point for processing uploaded files.
    
    Args:
        cloud_event: Cloud Event containing file upload information
    """
    try:
        # Parse the cloud event
        data = cloud_event.data
        
        # Extract file information
        bucket_name = data.get('bucket')
        file_name = data.get('name')
        
        if not bucket_name or not file_name:
            logger.error("Missing bucket or file name in cloud event")
            return
        
        # Extract tenant ID from file path (assuming structure: tenant_id/filename)
        path_parts = file_name.split('/')
        if len(path_parts) < 2:
            logger.error(f"Invalid file path structure: {file_name}")
            return
        
        tenant_id = path_parts[0]
        
        # Skip processing if file is already processed
        if file_name.startswith('processed/'):
            logger.info(f"Skipping already processed file: {file_name}")
            return
        
        logger.info(f"Processing file upload: {file_name} for tenant: {tenant_id}")
        
        # Process the file
        result = asyncio.run(processor.process_file(bucket_name, file_name, tenant_id))
        
        # Publish completion event
        asyncio.run(processor.publish_completion_event(result))
        
        logger.info(f"File processing completed: {result}")
        
    except Exception as e:
        logger.error(f"Error in process_uploaded_file: {e}")
        raise


@functions_framework.http
def health_check(request):
    """Health check endpoint for the Cloud Function."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "function": "data-ingestion-processor"
    }


@functions_framework.http
def manual_process(request):
    """
    Manual processing endpoint for testing and debugging.
    
    Expected JSON payload:
    {
        "bucket_name": "bucket-name",
        "file_name": "tenant_id/filename.ext",
        "tenant_id": "tenant-id"
    }
    """
    try:
        if request.method != 'POST':
            return {"error": "Method not allowed"}, 405
        
        data = request.get_json()
        if not data:
            return {"error": "No JSON data provided"}, 400
        
        bucket_name = data.get('bucket_name')
        file_name = data.get('file_name')
        tenant_id = data.get('tenant_id')
        
        if not all([bucket_name, file_name, tenant_id]):
            return {"error": "Missing required fields"}, 400
        
        # Process the file
        result = asyncio.run(processor.process_file(bucket_name, file_name, tenant_id))
        
        # Publish completion event
        asyncio.run(processor.publish_completion_event(result))
        
        return result
        
    except Exception as e:
        logger.error(f"Error in manual_process: {e}")
        return {"error": str(e)}, 500
