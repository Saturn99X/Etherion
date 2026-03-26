import asyncio
import base64
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
import websockets


DEFAULT_GRAPHQL_HTTP = os.getenv("ETHERION_GRAPHQL_HTTP", "https://api.etherionai.com/graphql")
DEFAULT_GRAPHQL_WS = os.getenv("ETHERION_GRAPHQL_WS", "wss://api.etherionai.com/graphql")
DEFAULT_ADMIN_INGEST_URL = os.getenv(
    "ETHERION_ADMIN_INGEST_URL", "https://api.etherionai.com/webhook/admin/ingest-bytes"
)
DEFAULT_ADMIN_INGEST_STATUS_URL = os.getenv(
    "ETHERION_ADMIN_INGEST_STATUS_URL", "https://api.etherionai.com/webhook/admin/ingest-status"
)
DEFAULT_ADMIN_OBJECT_FETCH_INGEST_URL = os.getenv(
    "ETHERION_ADMIN_OBJECT_FETCH_INGEST_URL",
    "https://api.etherionai.com/webhook/admin/object-kb/fetch-ingest",
)
DEFAULT_ADMIN_PURGE_EVAL_STATE_URL = os.getenv(
    "ETHERION_ADMIN_PURGE_EVAL_STATE_URL",
    "https://api.etherionai.com/webhook/admin/purge-eval-state",
)
DEFAULT_ADMIN_INGEST_SECRET = os.getenv("ETHERION_ADMIN_INGEST_SECRET", "NUSv7BjKJzDvayEOvwjIv7tsb5VPFsD0")


@dataclass(frozen=True)
class EvalConfig:
    graphql_http: str = DEFAULT_GRAPHQL_HTTP
    graphql_ws: str = DEFAULT_GRAPHQL_WS
    admin_ingest_url: str = DEFAULT_ADMIN_INGEST_URL
    admin_ingest_status_url: str = DEFAULT_ADMIN_INGEST_STATUS_URL
    admin_object_fetch_ingest_url: str = DEFAULT_ADMIN_OBJECT_FETCH_INGEST_URL
    admin_purge_eval_state_url: str = DEFAULT_ADMIN_PURGE_EVAL_STATE_URL
    admin_ingest_secret: str = DEFAULT_ADMIN_INGEST_SECRET


def _now_tag() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def read_json(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str, obj: Any) -> None:
    p = Path(path)
    ensure_dir(str(p.parent))
    p.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def decode_jwt_payload_no_verify(token: str) -> Dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(payload.encode("utf-8"))
        return json.loads(raw)
    except Exception:
        return {}


async def graphql(
    cfg: EvalConfig,
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
    operation_name: Optional[str] = None,
    timeout_seconds: float = 60.0,
) -> Dict[str, Any]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    op_name = operation_name
    if not op_name:
        try:
            match = re.search(r"\b(mutation|query|subscription)\s+([_A-Za-z][_0-9A-Za-z]*)", query)
            if match:
                op_name = match.group(2)
        except Exception:
            op_name = None

    payload: Dict[str, Any] = {"query": query, "variables": variables or {}}
    if op_name:
        payload["operationName"] = op_name

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.post(
            cfg.graphql_http,
            json=payload,
            headers=headers,
        )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"raw": resp.text}
        return {"status_code": resp.status_code, "data": data}


async def delete_agent_team(cfg: EvalConfig, *, team_id: str, token: str, timeout_seconds: float = 60.0) -> Dict[str, Any]:
    mutation = """
    mutation DeleteTeam($id: String!) {
      deleteAgentTeam(agent_team_id: $id)
    }
    """
    return await graphql(
        cfg,
        query=mutation,
        variables={"id": str(team_id)},
        token=token,
        timeout_seconds=timeout_seconds,
    )


async def list_agent_teams(cfg: EvalConfig, *, token: str, limit: int = 200, offset: int = 0, timeout_seconds: float = 60.0) -> Dict[str, Any]:
    query = """
    query ListTeams($limit: Int!, $offset: Int!) {
      listAgentTeams(limit: $limit, offset: $offset) {
        id
        name
        isActive
        isSystemTeam
      }
    }
    """
    return await graphql(
        cfg,
        query=query,
        variables={"limit": int(limit), "offset": int(offset)},
        token=token,
        timeout_seconds=timeout_seconds,
    )


async def admin_ingest_bytes(
    cfg: EvalConfig,
    tenant_id: str,
    *,
    text: Optional[str] = None,
    base64_content: Optional[str] = None,
    filename: str,
    mime_type: str,
    project_id: Optional[str] = None,
    timeout_seconds: float = 180.0,
    max_retries: int = 3,
    retry_delay: float = 5.0,
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Secret": cfg.admin_ingest_secret,
    }
    payload: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "filename": filename,
        "mime_type": mime_type,
    }
    if project_id:
        payload["project_id"] = project_id
    if base64_content is not None:
        payload["base64_content"] = base64_content
    elif text is not None:
        payload["text"] = text
    else:
        raise ValueError("admin_ingest_bytes requires text or base64_content")

    last_error = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(cfg.admin_ingest_url, json=payload, headers=headers)
                try:
                    body = resp.json()
                except Exception:
                    body = {"raw": resp.text}

                try:
                    if resp.status_code >= 500 and isinstance(body, dict):
                        if body.get("job_id") and str(body.get("status") or "").upper() == "QUEUED" and body.get("tenant_id"):
                            return {"status_code": 202, "data": body}
                except Exception:
                    pass
                
                # If 500 error with Celery/Redis issue, retry
                if resp.status_code == 500 and isinstance(body, dict):
                    detail = body.get("detail", "")
                    if "Celery" in detail or "redis" in detail.lower():
                        last_error = {"status_code": resp.status_code, "data": body, "attempt": attempt + 1}
                        if attempt < max_retries - 1:
                            print(f"Celery/Redis error on attempt {attempt + 1}, retrying in {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                            continue
                
                return {"status_code": resp.status_code, "data": body}
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            last_error = {"status_code": 0, "data": {"error": str(e)}, "attempt": attempt + 1}
            if attempt < max_retries - 1:
                print(f"Connection error on attempt {attempt + 1}: {e}, retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                continue
            break
    
    return last_error or {"status_code": 500, "data": {"error": "All retries failed"}}


async def admin_ingest_status(
    cfg: EvalConfig,
    *,
    job_id: str,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Secret": cfg.admin_ingest_secret,
    }
    url = cfg.admin_ingest_status_url.rstrip("/") + f"/{job_id}"
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.get(url, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return {"status_code": resp.status_code, "data": body}


async def finalize_admin_ingest(
    cfg: EvalConfig,
    ingest: Dict[str, Any],
    *,
    timeout_seconds: float = 900.0,
    poll_interval_seconds: float = 2.0,
    skip_on_error: bool = False,
) -> Dict[str, Any]:
    status_code = ingest.get("status_code")
    data = ingest.get("data") or {}
    
    # If initial request failed and skip_on_error is True, return immediately
    if skip_on_error and status_code not in {200, 202}:
        print(f"Skipping finalization due to initial error (status={status_code})")
        return ingest
    
    if status_code != 202:
        return ingest
    
    job_id = None
    if isinstance(data, dict):
        job_id = data.get("job_id")
    if not job_id:
        return ingest

    deadline = time.time() + float(timeout_seconds)
    last: Dict[str, Any] = {"status_code": 200, "data": {"job_id": str(job_id), "status": "PENDING"}}

    print(f"Polling ingest status: job_id={job_id} timeout_s={timeout_seconds} interval_s={poll_interval_seconds}")
    
    while time.time() < deadline:
        try:
            last = await admin_ingest_status(cfg, job_id=str(job_id), timeout_seconds=30.0)
            payload = last.get("data")
            st = None
            if isinstance(payload, dict):
                st = (payload.get("status") or payload.get("state") or "").upper()

                stage = payload.get("stage")
                elapsed_s = payload.get("elapsed_s")
                updated_at = payload.get("updated_at")
                print(
                    f"Ingest poll: status={st or 'UNKNOWN'} stage={stage or '-'} elapsed_s={elapsed_s or '-'} updated_at={updated_at or '-'}"
                )
            if st in {"COMPLETED", "FAILED", "CANCELLED"}:
                break
        except Exception as e:
            print(f"Error polling status: {e}")
            if skip_on_error:
                return {"status_code": 500, "data": {"error": str(e), "job_id": job_id}}
        
        await asyncio.sleep(float(poll_interval_seconds))

    payload = last.get("data")
    st = (payload.get("status") if isinstance(payload, dict) else None) or None
    if isinstance(st, str) and st.upper() == "FAILED":
        return {"status_code": 500, "data": payload}
    if isinstance(st, str) and st.upper() == "COMPLETED":
        return {"status_code": 200, "data": payload}
    print("Ingest poll deadline reached; returning last known status payload")
    return {"status_code": 504, "data": payload}


async def admin_object_fetch_ingest(
    cfg: EvalConfig,
    tenant_id: str,
    *,
    gcs_uri: str,
    project_id: Optional[str] = None,
    max_size_bytes: Optional[int] = None,
    timeout_seconds: float = 900.0,
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Secret": cfg.admin_ingest_secret,
    }
    payload: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "gcs_uri": gcs_uri,
    }
    if project_id:
        payload["project_id"] = project_id
    if max_size_bytes is not None:
        payload["max_size_bytes"] = int(max_size_bytes)

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.post(cfg.admin_object_fetch_ingest_url, json=payload, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return {"status_code": resp.status_code, "data": body}


async def admin_purge_eval_state(
    cfg: EvalConfig,
    tenant_id: str,
    *,
    dry_run: bool = False,
    timeout_seconds: float = 120.0,
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Secret": cfg.admin_ingest_secret,
    }
    payload: Dict[str, Any] = {
        "tenant_id": str(tenant_id),
        "dry_run": bool(dry_run),
    }
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.post(cfg.admin_purge_eval_state_url, json=payload, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return {"status_code": resp.status_code, "data": body}


def _is_terminal_status(status: Optional[str]) -> bool:
    if not status:
        return False
    return status.upper() in {"END", "COMPLETED", "FAILED", "CANCELLED"}


async def subscribe_execution_trace(
    cfg: EvalConfig,
    *,
    job_id: str,
    token: str,
    out_jsonl_path: str,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    recv_timeout_seconds: float = 3600.0,
) -> Dict[str, Any]:
    ensure_dir(str(Path(out_jsonl_path).parent))

    terminal_status: Optional[str] = None
    extracted: Dict[str, Any] = {
        "job_id": job_id,
        "thread_id": None,
        "saw_dual_search": False,
        "saw_web": False,
        "saw_vector": False,
        "saw_kb": False,
        "saw_tool_use": False,
        "terminal_status": None,
    }

    subscription_query = """
    subscription OnExecutionTrace($job_id: String!) {
      subscribeToExecutionTrace(job_id: $job_id) {
        job_id
        status
        timestamp
        message
        error_message
        additional_data
      }
    }
    """

    async with websockets.connect(
        cfg.graphql_ws,
        additional_headers={"Authorization": f"Bearer {token}"},
        subprotocols=["graphql-ws"],
        max_queue=2048,
    ) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "connection_init",
                    "payload": {"headers": {"Authorization": f"Bearer {token}"}},
                }
            )
        )

        # Wait for ack
        while True:
            raw = await websocket.recv()
            msg = json.loads(raw)
            if msg.get("type") == "connection_ack":
                break

        await websocket.send(
            json.dumps(
                {
                    "id": "1",
                    "type": "start",
                    "payload": {"query": subscription_query, "variables": {"job_id": job_id}},
                }
            )
        )

        with open(out_jsonl_path, "w", encoding="utf-8") as f:
            while True:
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=recv_timeout_seconds)
                except asyncio.TimeoutError:
                    terminal_status = terminal_status or "TIMEOUT"
                    break

                msg = json.loads(raw)
                if msg.get("type") != "data":
                    continue

                update = (((msg.get("payload") or {}).get("data") or {}).get("subscribeToExecutionTrace"))
                if not isinstance(update, dict):
                    continue

                f.write(json.dumps(update, ensure_ascii=False) + "\n")
                f.flush()

                try:
                    if on_event:
                        on_event(update)
                except Exception:
                    pass

                evt = update.get("additional_data")
                evt_type = None
                details_obj: Any = None
                if isinstance(evt, dict):
                    evt_type = evt.get("type")
                    details_obj = evt.get("details")
                    if evt.get("thread_id") and not extracted.get("thread_id"):
                        extracted["thread_id"] = evt.get("thread_id")

                status = update.get("status")

                if evt_type == "DUAL_SEARCH":
                    extracted["saw_dual_search"] = True
                    try:
                        counts = (evt or {}).get("counts") or {}
                        if isinstance(counts, dict):
                            extracted["saw_web"] = bool(counts.get("web"))
                            extracted["saw_vector"] = bool(counts.get("vertex") or counts.get("bq_vector") or counts.get("vector"))
                            extracted["saw_kb"] = bool(counts.get("project") or counts.get("personal"))
                    except Exception:
                        pass

                # Heuristic tool-use detection: many events include tool_name or tool_calls
                if isinstance(evt, dict) and (evt.get("tool_name") or evt.get("tool_calls") or evt.get("tool") or evt.get("operation")):
                    extracted["saw_tool_use"] = True

                # Some events embed JSON in details
                if extracted.get("thread_id") is None and isinstance(details_obj, str) and "thr_" in details_obj:
                    try:
                        maybe = json.loads(details_obj)
                        if isinstance(maybe, dict) and maybe.get("thread_id"):
                            extracted["thread_id"] = maybe.get("thread_id")
                    except Exception:
                        pass

                if _is_terminal_status(evt_type) or _is_terminal_status(status):
                    terminal_status = (evt_type or status or "").upper()
                    break

    extracted["terminal_status"] = terminal_status
    return extracted


async def get_archived_trace_summary(cfg: EvalConfig, *, job_id: str, token: str) -> Dict[str, Any]:
    query = """
    query GetArchived($job_id: String!) {
      getArchivedTraceSummary(job_id: $job_id)
    }
    """
    resp = await graphql(cfg, query=query, variables={"job_id": job_id}, token=token, timeout_seconds=60.0)
    return resp


def make_unique_email(prefix: str = "eval") -> str:
    suf = uuid.uuid4().hex[:10]
    return f"{prefix}-{suf}@etherionai.com"


def make_unique_subdomain() -> str:
    # Must satisfy DNSManager rules: 3-12 chars, lowercase letters/hyphens, start/end letter.
    # Use 't' + 6 letters => 7 chars.
    letters = "abcdefghijklmnopqrstuvwxyz"
    suf = uuid.uuid4().hex[:8]
    # Map hex to letters deterministically
    mapped = "".join([letters[int(c, 16) % 26] for c in suf[:6]])
    return f"t{mapped}"
