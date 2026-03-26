import asyncio
import base64
import os
from pathlib import Path
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.evaluation.eval_lib import (
    EvalConfig,
    admin_ingest_bytes,
    admin_object_fetch_ingest,
    finalize_admin_ingest,
    read_json,
    write_json,
)


STATE_PATH = os.getenv("ETHERION_EVAL_STATE", "/home/saturnx/langchain-app/scripts/evaluation/state.json")
PDF_PATH = os.getenv("ETHERION_EVAL_PDF", "/home/saturnx/langchain-app/entropy.pdf")


async def main() -> None:
    cfg = EvalConfig()
    state = read_json(STATE_PATH)

    tenant_id = state.get("tenant_id")
    if tenant_id is None:
        raise RuntimeError(f"Missing tenant_id in state file: {STATE_PATH}")
    tenant_id_str = str(tenant_id)

    pdf_bytes = Path(PDF_PATH).read_bytes()
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_b64 = b64
    pdf_filename = Path(PDF_PATH).name

    try:
        from pypdf import PdfReader
        import io

        pdf_pages = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        pdf_pages = None

    project_id = "physics_entropy_eval"

    t0 = time.time()

    post_timeout_env = os.getenv("ETHERION_EVAL_INGEST_POST_TIMEOUT_SECONDS", "20")
    try:
        ingest_post_timeout_seconds = float(post_timeout_env)
    except Exception:
        ingest_post_timeout_seconds = 20.0

    wait_seconds_env = os.getenv("ETHERION_EVAL_INGEST_WAIT_SECONDS", "300")
    try:
        ingest_wait_seconds = float(wait_seconds_env)
    except Exception:
        ingest_wait_seconds = 55.0

    # Upload PDF via admin ingest with retry logic
    print(f"Uploading {pdf_filename} ({len(pdf_bytes)} bytes)...")
    ingest = await admin_ingest_bytes(
        cfg,
        tenant_id=tenant_id_str,
        base64_content=pdf_b64,
        filename=pdf_filename,
        mime_type="application/pdf",
        project_id=project_id,
        timeout_seconds=ingest_post_timeout_seconds,
        max_retries=3,
        retry_delay=10.0,
    )

    print(f"Initial ingest response: status_code={ingest.get('status_code')} data_keys={list((ingest.get('data') or {}).keys()) if isinstance(ingest.get('data'), dict) else type(ingest.get('data')).__name__}")
    ingest = await finalize_admin_ingest(
        cfg,
        ingest,
        timeout_seconds=ingest_wait_seconds,
        poll_interval_seconds=2.0,
        skip_on_error=False,
    )
    
    if ingest.get("status_code") not in {200, 202}:
        print(f"Warning: PDF ingestion returned status {ingest.get('status_code')}")
        print(f"Response: {ingest.get('data')}")

    dt = time.time() - t0
    print(f"Eval3 ingest step finished in {dt:.1f}s")
    print(f"Eval3 ingest status_code={ingest.get('status_code')}")
    
    data = ingest.get("data", {})
    print(f"Eval3 ingest data keys={list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
    
    # Multimodal pipeline result format
    if 'doc_ids' in data:
        print(f"Multimodal ingestion: {len(data.get('doc_ids', []))} docs, {len(data.get('image_ids', []))} images")
        print(f"  Chapters: {data.get('chapter_count', 0)}, Parts: {data.get('part_count', 0)}, Tokens: {data.get('total_tokens', 0)}")
        if data.get('errors'):
            print(f"  Errors: {data.get('errors')}")
    # Legacy pipeline result format
    elif 'chunks_inserted' in data:
        print(f"Legacy ingestion: {data.get('chunks_inserted', 0)} chunks inserted")

    # If ingestion isn't completed within ingest_wait_seconds, stop here.
    # This keeps the eval command deterministic (<~60s) instead of hanging silently.
    if ingest.get("status_code") != 200:
        state.setdefault("pdf_ingestion", {})
        state["pdf_ingestion"]["entropy_pdf"] = {
            "pdf_path": PDF_PATH,
            "project_id": project_id,
            "ingest": ingest,
            "search": {"errors": [{"source": "eval3", "type": "IngestNotCompleted", "message": "Ingestion not completed within time budget"}]},
        }
        write_json(STATE_PATH, state)
        print("Eval3 exiting early (ingestion not completed within time budget).")
        return

    search_results = {"errors": []}

    # KB semantic search + LIKE search (best-effort; may require BQ creds)
    try:
        from src.services.bq_vector_search import BQVectorSearchService

        print("Running KB vector search...")
        vec = BQVectorSearchService()
        rows = vec.search(
            tenant_id=tenant_id_str,
            query="entropy pdf shannon thermodynamics",
            top_k=5,
            project_id_filter=project_id,
            job_id=None,
        )
        search_results["kb_vector"] = {"count": len(rows), "top": rows[:3]}
        print(f"KB vector search: {len(rows)} results")
    except Exception as e:
        error_msg = str(e)
        print(f"KB vector search error ({type(e).__name__}): {error_msg}")
        search_results.setdefault("errors", []).append(
            {"source": "kb_vector", "type": type(e).__name__, "message": error_msg}
        )
        if "Not found" in error_msg:
            print("Tip: Ensure docs table exists and has vector_embedding column")

    try:
        from src.services.kb_query_service import KBQueryService

        print("Running KB LIKE search...")
        kbq = KBQueryService()
        rows = kbq.search(
            tenant_id=tenant_id_str,
            query="entropy",
            project_id=project_id,
            limit=10,
            job_id=None,
        )
        search_results["kb_like"] = {"count": len(rows), "top": rows[:3]}
        print(f"KB LIKE search: {len(rows)} results")
    except Exception as e:
        error_msg = str(e)
        print(f"KB LIKE search error ({type(e).__name__}): {error_msg}")
        search_results.setdefault("errors", []).append(
            {"source": "kb_like", "type": type(e).__name__, "message": error_msg}
        )

    if os.getenv("KB_OBJECT_TABLES_ENABLED", "false").lower() == "true":
        try:
            from src.services.bq_media_object_embeddings_backfill import BQMediaObjectEmbeddingsBackfillService
            from src.services.bq_media_object_search import BQMediaObjectSearchService

            ingested_gcs_uri = None
            try:
                ingested_gcs_uri = (ingest.get("data") or {}).get("gcs_uri")
            except Exception:
                ingested_gcs_uri = None
            if not ingested_gcs_uri:
                raise RuntimeError("Eval3 missing gcs_uri in admin ingest response; cannot backfill object embeddings")

            backfill = BQMediaObjectEmbeddingsBackfillService()
            backfill.backfill(tenant_id=tenant_id_str, gcs_uri=str(ingested_gcs_uri))

            obj = BQMediaObjectSearchService()
            obj_rows = obj.search(
                tenant_id=tenant_id_str,
                query="entropy pdf shannon thermodynamics",
                top_k=5,
                job_id=None,
            )
            search_results["object_kb"] = {"count": len(obj_rows), "top": obj_rows[:3]}

            if obj_rows and isinstance(obj_rows[0], dict) and obj_rows[0].get("gcs_uri"):
                gcs_uri = str(obj_rows[0].get("gcs_uri"))
                fetch_ingest = await admin_object_fetch_ingest(
                    cfg,
                    tenant_id=tenant_id_str,
                    gcs_uri=gcs_uri,
                    project_id=project_id,
                    max_size_bytes=10 * 1024 * 1024,
                    timeout_seconds=900.0,
                )
                search_results["object_fetch_ingest"] = fetch_ingest
        except Exception as e:
            search_results.setdefault("errors", []).append(
                {"source": "object_kb", "type": type(e).__name__, "message": str(e)}
            )

    state.setdefault("pdf_ingestion", {})
    state["pdf_ingestion"]["entropy_pdf"] = {
        "pdf_path": PDF_PATH,
        "project_id": project_id,
        "ingest": ingest,
        "search": search_results,
    }

    write_json(STATE_PATH, state)


if __name__ == "__main__":
    asyncio.run(main())
