import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.evaluation.eval_lib import EvalConfig, admin_ingest_bytes, finalize_admin_ingest, read_json, write_json


STATE_PATH = os.getenv("ETHERION_EVAL_STATE", "/home/saturnx/langchain-app/scripts/evaluation/state.json")


async def main() -> None:
    cfg = EvalConfig()
    state = read_json(STATE_PATH)

    tenant_id = state.get("tenant_id")
    if tenant_id is None:
        raise RuntimeError(f"Missing tenant_id in state file: {STATE_PATH}")

    tenant_id_str = str(tenant_id)

    # Bootstraps KB by forcing ingestion to call tenant dataset/table ensure + embedding writes.
    print(f"Attempting KB bootstrap for tenant {tenant_id_str}...")
    ingest = await admin_ingest_bytes(
        cfg,
        tenant_id=tenant_id_str,
        text="KB bootstrap: create dataset + docs/assets tables and verify vector schema.",
        filename="kb_bootstrap.txt",
        mime_type="text/plain",
        project_id="eval_kb_bootstrap",
        timeout_seconds=180.0,
        max_retries=3,
        retry_delay=10.0,
    )

    ingest = await finalize_admin_ingest(cfg, ingest, timeout_seconds=300.0, poll_interval_seconds=1.0, skip_on_error=True)

    verify: dict = {"dataset": None, "tables": {}, "errors": [], "fallback_used": False}

    # Verify via BigQuery API (requires creds). This is part of the evaluation.
    try:
        from google.cloud import bigquery

        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required to verify KB existence")

        client = bigquery.Client(project=project)
        dataset_id = f"tnt_{tenant_id_str}"
        
        # Try to get dataset, if not found and admin ingest failed, create it directly
        try:
            ds = client.get_dataset(f"{project}.{dataset_id}")
        except Exception as get_err:
            if "Not found" in str(get_err) and ingest.get("status_code") != 200:
                print(f"Dataset not found and admin ingest failed. Creating dataset directly...")
                from src.services.bq_schema_manager import ensure_tenant_multimodal_kb
                try:
                    ensure_tenant_multimodal_kb(client, tenant_id_str)
                    verify["fallback_used"] = True
                    ds = client.get_dataset(f"{project}.{dataset_id}")
                    print(f"Successfully created dataset via fallback")
                except Exception as create_err:
                    verify["errors"].append({"type": "FallbackCreationError", "message": str(create_err)})
                    raise get_err
            else:
                raise
        verify["dataset"] = {
            "full_id": ds.full_dataset_id,
            "location": ds.location,
        }

        def _count_rows(table: str) -> int:
            try:
                q = f"SELECT COUNT(1) AS cnt FROM `{project}.{dataset_id}.{table}`"
                res = list(client.query(q).result())
                if res:
                    return int(res[0].get("cnt") or 0)
            except Exception:
                pass
            return 0

        tables_to_check = ["multimodal_docs"]
        # Also check legacy tables if they exist.
        for table_name in tables_to_check + ["docs", "assets"]:
            try:
                t = client.get_table(f"{project}.{dataset_id}.{table_name}")
                fields = [f.name for f in (t.schema or [])]
                verify["tables"][table_name] = {
                    "num_rows": _count_rows(table_name),
                    "fields": fields,
                    "has_vector_embedding": "vector_embedding" in fields,
                }
            except Exception:
                # Legacy tables might not exist if we only init multimodal
                pass

    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        verify["errors"].append({"type": error_type, "message": error_msg})
        print(f"KB verification error ({error_type}): {error_msg}")
        
        # If this is a credentials issue, provide helpful message
        if "credentials" in error_msg.lower() or "authentication" in error_msg.lower():
            print("\nTip: Ensure GOOGLE_CLOUD_PROJECT is set and you have valid GCP credentials.")
            print("Run: gcloud auth application-default login")

    state.setdefault("kb", {})
    state["kb"]["bootstrap_ingest"] = ingest
    state["kb"]["verification"] = verify

    write_json(STATE_PATH, state)


if __name__ == "__main__":
    asyncio.run(main())
