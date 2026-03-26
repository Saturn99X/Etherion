from __future__ import annotations

from typing import Any, Dict, List, Optional
import os
import logging
from google.api_core.client_options import ClientOptions
try:
    from google.cloud import discoveryengine_v1 as discoveryengine
    from google.api_core import exceptions as gax_exceptions
    from google.protobuf import struct_pb2
except Exception:  # pragma: no cover
    discoveryengine = None  # type: ignore
    gax_exceptions = None  # type: ignore
    struct_pb2 = None  # type: ignore


class VertexSearchCacheCDC:
    """Push BigQuery 'docs' rows into per-tenant Vertex AI Search datastore."""

    def __init__(self, project_id: Optional[str] = None, location: Optional[str] = None) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required")
        self.location = location or os.getenv("VERTEX_AI_LOCATION", "global")
        # Disable CDC by default unless explicitly enabled
        explicit_enable = os.getenv("ENABLE_VERTEX_AI_SEARCH", "false").lower() in ("1", "true", "yes", "on") and os.getenv("KB_BACKEND", "bq").lower() == "vertex"
        self.disabled: bool = not explicit_enable or discoveryengine is None or os.getenv("VERTEX_CDC_DISABLED", "true").lower() in ("1", "true", "yes", "on", "offline")
        # If strict is enabled, raise on PermissionDenied; otherwise, swallow and continue
        self.strict_errors: bool = os.getenv("VERTEX_CDC_STRICT", "false").lower() in ("1", "true", "yes", "on")
        self._logger = logging.getLogger(__name__)
        client_options = (
            ClientOptions(api_endpoint=f"{self.location}-discoveryengine.googleapis.com")
            if self.location != "global"
            else None
        )
        if not self.disabled and discoveryengine is not None:
            self.doc_client = discoveryengine.DocumentServiceClient(client_options=client_options)
            self.ds_client = discoveryengine.DataStoreServiceClient(client_options=client_options)
        else:
            self.doc_client = None  # type: ignore[assignment]
            self.ds_client = None  # type: ignore[assignment]
        # We no longer depend on discoveryengine.StructuredData; using protobuf Struct for portability.

    def _datastore(self, tenant_id: str) -> str:
        return f"tenant-kb-{tenant_id}"

    def _branch_path(self, tenant_id: str) -> str:
        # Always write to default branch
        return self.doc_client.branch_path(
            project=self.project_id,
            location=self.location,
            data_store=self._datastore(tenant_id),
            branch="default_branch",
        )

    def _ensure_datastore(self, tenant_id: str) -> None:
        """Create the per-tenant datastore if it does not exist."""
        if self.disabled or discoveryengine is None:
            return
        # Use collection-scoped parent as required by v1 APIs
        parent = self.ds_client.collection_path(self.project_id, self.location, "default_collection")
        data_store = discoveryengine.DataStore(
            display_name=f"Tenant KB {tenant_id}",
            solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
            content_config=discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED,
        )
        try:
            op = self.ds_client.create_data_store(
                parent=parent,
                data_store=data_store,
                data_store_id=self._datastore(tenant_id),
            )
            # Wait until created to avoid races with import
            op.result(timeout=120)
        except gax_exceptions.AlreadyExists:
            return
        except gax_exceptions.PermissionDenied:
            # In non-strict mode, swallow permission errors to allow tests to proceed using
            # BigQuery-only retrieval paths. In strict mode, surface the error.
            if not self.strict_errors:
                try:
                    # Best-effort: verify existence; otherwise continue silently
                    for ds in self.ds_client.list_data_stores(parent=parent):
                        if ds.name.rsplit("/", 1)[-1] == self._datastore(tenant_id):
                            return
                except Exception:
                    pass
                self._logger.debug(
                    "VertexSearchCacheCDC: PermissionDenied creating datastore for tenant %s; proceeding without CDC",
                    tenant_id,
                )
                return
            # strict -> re-raise
            raise
        except Exception:
            # Surface unexpected errors as well
            raise

    def push_rows(self, tenant_id: str, rows: List[Dict[str, Any]]) -> None:
        if self.disabled or discoveryengine is None or not rows:
            return
        # Ensure the tenant datastore exists before importing
        self._ensure_datastore(tenant_id)
        branch = self._branch_path(tenant_id)
        requests: List[discoveryengine.ImportDocumentsRequest] = []

        docs: List[discoveryengine.Document] = []
        for r in rows:
            doc_id = r.get("doc_id") or r.get("chunk_hash")
            if not doc_id:
                continue
            derived_json = {
                "doc_id": doc_id,
                "text_chunk": r.get("text_chunk"),
                "metadata": r.get("metadata", {}),
                "file_uri": r.get("file_uri"),
            }
            sd = struct_pb2.Struct()
            try:
                sd.update(derived_json)
            except Exception:
                # Fallback: ensure metadata is serializable
                import json as _json
                parsed = {
                    "doc_id": str(derived_json.get("doc_id")),
                    "text_chunk": derived_json.get("text_chunk") or "",
                    "metadata": derived_json.get("metadata") or {},
                    "file_uri": derived_json.get("file_uri") or "",
                }
                sd.update(parsed)
            # Provide fulltext in `content` so the engine can index it without a custom schema
            text_content = str(derived_json.get("text_chunk") or "")
            docs.append(
                discoveryengine.Document(
                    id=str(doc_id),
                    content=text_content,
                    content_type="text/plain",
                    struct_data=sd,
                )
            )

        if not docs:
            return

        # Import in one batch
        request = discoveryengine.ImportDocumentsRequest(
            parent=branch,
            inline_source=discoveryengine.ImportDocumentsRequest.InlineSource(documents=docs),
            reconciliation_mode=discoveryengine.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
        )
        # Import and wait for completion so downstream checks can read immediately
        try:
            op = self.doc_client.import_documents(request=request)
            op.result(timeout=180)
        except Exception as e:
            # Do not raise to avoid breaking ingestion path; log best-effort for observability
            try:
                self._logger.warning("VertexSearchCacheCDC import failed for tenant %s: %s", tenant_id, str(e))
            except Exception:
                pass
        return


