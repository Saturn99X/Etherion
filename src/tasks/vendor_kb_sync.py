"""
Vendor KB Sync — Celery task that fetches recent data from a connected vendor
and upserts it into the tenant's knowledge base.

Triggered from two places:
  - silo_oauth_service.handle_callback()  (browser OAuth: Slack, Google, Microsoft, Shopify)
  - connectIntegration mutation           (token-based: GitHub, Notion, Jira, HubSpot, Linear)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import textwrap
from typing import Any, Dict, List, Tuple

from src.core.celery import celery_app
from src.utils.secrets_manager import TenantSecretsManager

logger = logging.getLogger(__name__)

_MAX_CHUNK = 1500  # characters per KB document chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk(text: str, size: int = _MAX_CHUNK) -> List[str]:
    wrapped = textwrap.wrap(text, size, break_long_words=False, break_on_hyphens=False)
    return wrapped if wrapped else [text[:size]]


def _doc_id(tenant_id: str, provider: str, source_id: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{provider}:{source_id}".encode()).hexdigest()[:32]


def _embed(texts: List[str]) -> List[List[float]]:
    try:
        from src.services.embedding_service import EmbeddingService
        return EmbeddingService().embed_texts(texts)
    except Exception as exc:
        logger.warning(f"[vendor_kb_sync] embedding unavailable: {exc}")
        dim = int(os.getenv("KB_EMBEDDING_DIM", "768"))
        return [[0.0] * dim for _ in texts]


async def _upsert_chunks(
    tenant_id: str,
    provider: str,
    items: List[Tuple[str, str, Dict[str, Any]]],
) -> int:
    """Embed and upsert (source_id, text, metadata) tuples into the KB."""
    if not items:
        return 0
    from src.services.kb_backend import get_kb_backend
    kb = get_kb_backend()
    texts = [t for _, t, _ in items]
    embeddings = _embed(texts)
    count = 0
    for (source_id, text, meta), emb in zip(items, embeddings):
        meta["provider"] = provider
        meta["tenant_id"] = tenant_id
        await kb.upsert(tenant_id, _doc_id(tenant_id, provider, source_id), text, emb, meta)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Per-provider fetch functions
# Each returns a list of (source_id, text_chunk, metadata) tuples.
# ---------------------------------------------------------------------------

async def _fetch_slack(tenant_id: str) -> List[Tuple[str, str, Dict]]:
    from src.tools.mcp.mcp_slack import MCPSlackTool
    tool = MCPSlackTool()
    items: List[Tuple[str, str, Dict]] = []

    r = await tool.execute(tenant_id, "get_channels", {"limit": 20})
    if not r.success or not r.data:
        return items

    for ch in (r.data.get("channels") or [])[:8]:
        ch_id = ch.get("id", "")
        ch_name = ch.get("name", ch_id)
        h = await tool.execute(tenant_id, "get_channel_history", {"channel_id": ch_id, "limit": 100})
        if not h.success or not h.data:
            continue
        for msg in (h.data.get("messages") or []):
            text = msg.get("text", "").strip()
            if len(text) < 20:
                continue
            ts = msg.get("ts", "")
            for i, chunk in enumerate(_chunk(text)):
                items.append((f"{ch_id}:{ts}:{i}", chunk, {"channel": ch_name, "ts": ts}))
    return items


async def _fetch_notion(tenant_id: str) -> List[Tuple[str, str, Dict]]:
    from src.tools.mcp.mcp_notion import MCPNotionTool
    tool = MCPNotionTool()
    items: List[Tuple[str, str, Dict]] = []

    r = await tool.execute(tenant_id, "list_databases", {})
    if not r.success or not r.data:
        return items

    for db in (r.data.get("results") or [])[:5]:
        db_id = db.get("id", "")
        title_list = db.get("title") or []
        title = title_list[0].get("plain_text", db_id) if title_list else db_id

        blocks = await tool.execute(tenant_id, "get_block_children", {"block_id": db_id, "page_size": 50})
        if not blocks.success or not blocks.data:
            continue
        for block in (blocks.data.get("results") or []):
            btype = block.get("type", "")
            content = block.get(btype) or {}
            rich = content.get("rich_text") if isinstance(content, dict) else []
            text = " ".join(r.get("plain_text", "") for r in (rich or []) if r.get("plain_text"))
            if len(text) < 10:
                continue
            bid = block.get("id", "")
            for i, chunk in enumerate(_chunk(text)):
                items.append((f"{db_id}:{bid}:{i}", chunk, {"database": title}))
    return items


async def _fetch_jira(tenant_id: str) -> List[Tuple[str, str, Dict]]:
    from src.tools.mcp.mcp_jira import MCPJiraTool
    tool = MCPJiraTool()
    items: List[Tuple[str, str, Dict]] = []

    r = await tool.execute(tenant_id, "search_jql", {
        "jql": "ORDER BY updated DESC",
        "max_results": 50,
    })
    if not r.success or not r.data:
        return items

    for issue in (r.data.get("issues") or []):
        key = issue.get("key", "")
        fields = issue.get("fields") or {}
        summary = fields.get("summary", "")
        desc = fields.get("description") or ""
        if isinstance(desc, dict):
            # Atlassian Document Format → extract plain text
            desc = " ".join(
                node_content.get("text", "")
                for node in (desc.get("content") or [])
                for node_content in (node.get("content") or [])
                if node_content.get("type") == "text"
            )
        text = f"{key}: {summary}\n{desc}".strip()
        if len(text) < 10:
            continue
        for i, chunk in enumerate(_chunk(text)):
            items.append((f"{key}:{i}", chunk, {"key": key, "summary": summary}))
    return items


async def _fetch_hubspot(tenant_id: str) -> List[Tuple[str, str, Dict]]:
    from src.tools.mcp.mcp_hubspot import MCPHubSpotTool
    tool = MCPHubSpotTool()
    items: List[Tuple[str, str, Dict]] = []

    r = await tool.execute(tenant_id, "search_contacts", {"limit": 50})
    if not r.success or not r.data:
        return items

    for contact in (r.data.get("results") or []):
        props = contact.get("properties") or {}
        name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
        email = props.get("email", "")
        company = props.get("company", "")
        cid = contact.get("id", "")
        text = f"Contact: {name} | Email: {email} | Company: {company}".strip()
        if len(text) < 10:
            continue
        items.append((cid, text, {"name": name, "email": email, "company": company}))
    return items


async def _fetch_ms365(tenant_id: str) -> List[Tuple[str, str, Dict]]:
    from src.tools.mcp.mcp_ms365 import MCPMS365Tool
    tool = MCPMS365Tool()
    items: List[Tuple[str, str, Dict]] = []

    r = await tool.execute(tenant_id, "list_messages", {"top": 50})
    if r.success and r.data:
        for msg in (r.data.get("value") or []):
            subject = msg.get("subject", "")
            preview = msg.get("bodyPreview", "")
            sender = (msg.get("from") or {}).get("emailAddress", {}).get("address", "")
            mid = msg.get("id", "")
            text = f"Email from {sender} — {subject}\n{preview}".strip()
            if len(text) < 10:
                continue
            for i, chunk in enumerate(_chunk(text)):
                items.append((f"{mid}:{i}", chunk, {"subject": subject, "sender": sender}))

    d = await tool.execute(tenant_id, "list_drive_items", {"top": 30})
    if d.success and d.data:
        for item in (d.data.get("value") or []):
            name = item.get("name", "")
            iid = item.get("id", "")
            url = item.get("webUrl", "")
            text = f"OneDrive file: {name} — {url}".strip()
            if len(text) < 10:
                continue
            items.append((iid, text, {"filename": name, "url": url}))
    return items


async def _fetch_shopify(tenant_id: str) -> List[Tuple[str, str, Dict]]:
    from src.tools.mcp.mcp_shopify import MCPShopifyTool
    tool = MCPShopifyTool()
    items: List[Tuple[str, str, Dict]] = []

    r = await tool.execute(tenant_id, "product_list_paginated", {"limit": 50})
    if r.success and r.data:
        for product in (r.data.get("products") or []):
            title = product.get("title", "")
            desc = product.get("body_html") or product.get("description") or ""
            desc = re.sub(r"<[^>]+>", " ", desc).strip()
            pid = str(product.get("id", ""))
            text = f"Product: {title}\n{desc}".strip()
            if len(text) < 5:
                continue
            for i, chunk in enumerate(_chunk(text)):
                items.append((f"{pid}:{i}", chunk, {"title": title}))
    return items


async def _fetch_github(tenant_id: str) -> List[Tuple[str, str, Dict]]:
    """GitHub via REST API (PAT stored in secrets_manager under 'credentials')."""
    import aiohttp
    tsm = TenantSecretsManager()
    creds = await tsm.get_secret(tenant_id, "github", "credentials")
    if not creds:
        return []
    token = (
        creds.get("token") or creds.get("access_token")
        if isinstance(creds, dict) else str(creds)
    )
    if not token:
        return []

    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    items: List[Tuple[str, str, Dict]] = []

    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.get("https://api.github.com/repos?per_page=20&affiliation=owner,collaborator") as resp:
            if resp.status == 200:
                for repo in (await resp.json())[:10]:
                    name = repo.get("full_name", "")
                    desc = repo.get("description") or ""
                    text = f"GitHub repo: {name}\n{desc}".strip()
                    if len(text) > 5:
                        items.append((f"repo:{name}", text, {"repo": name}))

        async with session.get("https://api.github.com/issues?filter=all&state=open&per_page=50") as resp:
            if resp.status == 200:
                for issue in await resp.json():
                    title = issue.get("title", "")
                    body = (issue.get("body") or "")[:500]
                    repo = (issue.get("repository") or {}).get("full_name", "")
                    iid = str(issue.get("number", ""))
                    text = f"Issue #{iid} in {repo}: {title}\n{body}".strip()
                    if len(text) < 10:
                        continue
                    for i, chunk in enumerate(_chunk(text)):
                        items.append((f"issue:{repo}:{iid}:{i}", chunk, {"repo": repo, "title": title}))
    return items


async def _fetch_linear(tenant_id: str) -> List[Tuple[str, str, Dict]]:
    """Linear via GraphQL API (API key stored in secrets_manager under 'credentials')."""
    import aiohttp
    tsm = TenantSecretsManager()
    creds = await tsm.get_secret(tenant_id, "linear", "credentials")
    if not creds:
        return []
    token = (
        creds.get("token") or creds.get("api_key")
        if isinstance(creds, dict) else str(creds)
    )
    if not token:
        return []

    query = """
    query {
      issues(first: 50, filter: {state: {type: {in: ["started", "unstarted"]}}}) {
        nodes { id title description team { name } }
      }
    }
    """
    items: List[Tuple[str, str, Dict]] = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.post(
            "https://api.linear.app/graphql",
            json={"query": query},
            headers={"Authorization": token, "Content-Type": "application/json"},
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                nodes = (data.get("data") or {}).get("issues", {}).get("nodes") or []
                for issue in nodes:
                    title = issue.get("title", "")
                    desc = issue.get("description") or ""
                    team = (issue.get("team") or {}).get("name", "")
                    iid = issue.get("id", "")
                    text = f"Linear issue in {team}: {title}\n{desc}".strip()
                    if len(text) < 10:
                        continue
                    for i, chunk in enumerate(_chunk(text)):
                        items.append((f"{iid}:{i}", chunk, {"team": team, "title": title}))
    return items


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_FETCHERS = {
    "slack":     _fetch_slack,
    "notion":    _fetch_notion,
    "jira":      _fetch_jira,
    "hubspot":   _fetch_hubspot,
    "microsoft": _fetch_ms365,
    "shopify":   _fetch_shopify,
    "github":    _fetch_github,
    "linear":    _fetch_linear,
}


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="tasks.vendor_kb_sync",
    ignore_result=True,
    max_retries=2,
    default_retry_delay=120,
)
def vendor_kb_sync_task(self, tenant_id: str, provider: str) -> None:
    """Fetch recent data from a vendor and upsert into the tenant's knowledge base."""
    fetcher = _FETCHERS.get(provider)
    if fetcher is None:
        logger.info(f"[vendor_kb_sync] no fetcher for provider '{provider}' — skipping")
        return

    try:
        items = asyncio.run(fetcher(tenant_id))
        count = asyncio.run(_upsert_chunks(tenant_id, provider, items))
        logger.info(f"[vendor_kb_sync] {provider} → tenant {tenant_id}: {count} chunks upserted")
    except Exception as exc:
        logger.exception(f"[vendor_kb_sync] {provider} → tenant {tenant_id} failed: {exc}")
        raise self.retry(exc=exc)
