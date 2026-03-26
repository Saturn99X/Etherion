import logging
from typing import Dict, Any, Optional

import os
import sys
from datetime import datetime
from src.core.redis import RedisClient, get_redis_client, publish_execution_trace
from src.services.pricing import llm_pricing
from src.services.pricing import services as svc_pricing

logger = logging.getLogger(__name__)


def _log_cost(job_id: str, event_type: str, message: str, **kwargs):
    """Log cost tracking event to stdout for observability."""
    ts = datetime.utcnow().isoformat()
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None) if kwargs else ""
    log_line = f"[COST] ts={ts} job_id={job_id} type={event_type} | {message}"
    if extra:
        log_line += f" | {extra}"
    print(log_line, file=sys.stdout, flush=True)


def _must_env_float(name: str) -> float:
    """Return float value for required env var or raise error if missing/invalid."""
    val = os.environ.get(name)
    if val is None or str(val).strip() == "":
        raise RuntimeError(f"Missing required pricing environment variable: {name}")
    try:
        return float(val)
    except Exception as e:
        raise RuntimeError(f"Invalid float for env {name}: {val}") from e


class CostTracker:
    """
    Tracks usage and computes cost at zero rates (policy: values are 0 until provided).
    Records counters per job and per tenant in Redis (tenant-prefixed via RedisClient).
    """

    def __init__(self, redis_client: Optional[RedisClient] = None):
        # Do not cache a potentially stale global client; keep an override if provided.
        self._override_redis = redis_client

    def _prefix(self, job_id: str, tenant_id: Optional[str] = None) -> str:
        """Build Redis key prefix for cost counters.

        If tenant_id provided → `cost:{tenant_id}:{job_id}` else legacy `cost:{job_id}`.
        """
        if tenant_id:
            return f"cost:{tenant_id}:{job_id}"
        return f"cost:{job_id}"

    def _prefixes(self, job_id: str, tenant_id: Optional[str] = None) -> list[str]:
        if tenant_id:
            return [f"cost:{tenant_id}:{job_id}", f"cost:{job_id}"]
        return [f"cost:{job_id}"]

    async def record_tokens(self, job_id: str, input_tokens: int = 0, output_tokens: int = 0, *, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.incr(f"{p}:tokens_in", input_tokens)
        await redis.incr(f"{p}:tokens_out", output_tokens)
        _log_cost(job_id, "TOKENS", f"Recorded token usage",
                  input_tokens=input_tokens, output_tokens=output_tokens, tenant_id=tenant_id)

    async def record_api_call(self, job_id: str, provider: str, *, tenant_id: Optional[str] = None) -> None:
        # Track provider-specific and aggregate API counts
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.incr(f"{p}:api:{provider}", 1)
        await redis.incr(f"{p}:api_total", 1)

    async def record_data_transfer(self, job_id: str, mb_in: float = 0.0, mb_out: float = 0.0, *, tenant_id: Optional[str] = None) -> None:
        # Store as integers of kilobytes to avoid float precision in counters
        kb_in = int(mb_in * 1024)
        kb_out = int(mb_out * 1024)
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.incr(f"{p}:kb_in", kb_in)
        await redis.incr(f"{p}:kb_out", kb_out)

    async def record_compute_time_ms(self, job_id: str, ms: int, *, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.incr(f"{p}:compute_ms", ms)

    # ---- LLM context & advanced metering ----
    async def set_llm_context(self, job_id: str, *, provider: str, model: str, mode: Optional[str] = None, tenant_id: Optional[str] = None) -> None:
        """Attach LLM provider/model/mode to a job for accurate pricing later."""
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.set(f"{p}:llm_provider", provider)
        await redis.set(f"{p}:llm_model", model)
        if mode:
            await redis.set(f"{p}:llm_mode", mode)
        _log_cost(job_id, "LLM_CONTEXT", f"Set LLM context",
                  provider=provider, model=model, mode=mode, tenant_id=tenant_id)

    async def record_llm_cache_tokens(self, job_id: str, tokens: int, *, tenant_id: Optional[str] = None) -> None:
        """Record number of tokens benefiting from context caching."""
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.incr(f"{p}:llm_cache_tokens", int(tokens))

    # ---- EXA usage ----
    async def record_exa_search(self, job_id: str, *, kind: str, results: Optional[int] = None, tenant_id: Optional[str] = None) -> None:
        """Record EXA search usage.
        kind: 'auto_fast' | 'neural' | 'keyword'
        results: for 'auto_fast', bucket into 1-25 vs 26-100 per pricing.
        """
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        if kind in {"auto_fast", "neural"} and results is not None:
            bucket = "1_25" if int(results) <= 25 else "26_100"
            await redis.incr(f"{p}:exa:search:{kind}:{bucket}", 1)
        elif kind in {"neural", "keyword"}:
            await redis.incr(f"{p}:exa:search:{kind}", 1)

    async def record_exa_contents(self, job_id: str, *, kind: str, pages: int, tenant_id: Optional[str] = None) -> None:
        """Record EXA contents pages: kind in {'text','highlights','summary'}"""
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.incr(f"{p}:exa:contents:{kind}_pages", int(pages))

    async def record_exa_answer(self, job_id: str, *, count: int = 1, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.incr(f"{p}:exa:answers", int(count))

    async def record_exa_research(self, job_id: str, *, agent_ops: int = 0, page_reads_standard: int = 0, page_reads_pro: int = 0, reasoning_tokens: int = 0, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        if agent_ops:
            await redis.incr(f"{p}:exa:research:agent_ops", int(agent_ops))
        if page_reads_standard:
            await redis.incr(f"{p}:exa:research:page_reads_standard", int(page_reads_standard))
        if page_reads_pro:
            await redis.incr(f"{p}:exa:research:page_reads_pro", int(page_reads_pro))
        if reasoning_tokens:
            await redis.incr(f"{p}:exa:research:reasoning_tokens", int(reasoning_tokens))

    # ---- Vertex AI Search (queries) ----
    async def record_vertex_search(self, job_id: str, *, standard_q: int = 0, enterprise_q: int = 0, advanced_q: int = 0, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        if standard_q:
            await redis.incr(f"{p}:vertex_search:standard_q", int(standard_q))
        if enterprise_q:
            await redis.incr(f"{p}:vertex_search:enterprise_q", int(enterprise_q))
        if advanced_q:
            await redis.incr(f"{p}:vertex_search:advanced_q", int(advanced_q))

    # ---- BigQuery ----
    async def record_bigquery_scan(self, job_id: str, *, bytes_scanned: int, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.incr(f"{p}:bq:bytes_scanned", int(bytes_scanned))

    async def record_bigquery_storage(self, job_id: str, *, active_gb_month: float = 0.0, long_term_gb_month: float = 0.0, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        if active_gb_month:
            await redis.incr(f"{p}:bq:active_gb_month_milli", int(float(active_gb_month) * 1000.0))
        if long_term_gb_month:
            await redis.incr(f"{p}:bq:long_term_gb_month_milli", int(float(long_term_gb_month) * 1000.0))

    async def record_bigquery_slot_hours(self, job_id: str, *, slot_hours: float, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.incr(f"{p}:bq:slot_hours_milli", int(float(slot_hours) * 1000.0))

    # ---- Compute / Network / GCS ----
    async def record_compute_resources(self, job_id: str, *, vcpu_hours: float = 0.0, ram_gb_hours: float = 0.0, gpu_hours: float = 0.0, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        if vcpu_hours:
            await redis.incr(f"{p}:compute:vcpu_hours_milli", int(float(vcpu_hours) * 1000.0))
        if ram_gb_hours:
            await redis.incr(f"{p}:compute:ram_gb_hours_milli", int(float(ram_gb_hours) * 1000.0))
        if gpu_hours:
            await redis.incr(f"{p}:compute:gpu_hours_milli", int(float(gpu_hours) * 1000.0))

    async def record_network_egress_gib(self, job_id: str, *, egress_gib: float, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        await redis.incr(f"{p}:network:egress_gib_milli", int(float(egress_gib) * 1000.0))

    async def record_gcs_usage(self, job_id: str, *, standard_gb_month: float = 0.0, nearline_gb_month: float = 0.0, coldline_gb_month: float = 0.0, archive_gb_month: float = 0.0, ops_a: int = 0, ops_b: int = 0, tenant_id: Optional[str] = None) -> None:
        redis = self._override_redis or get_redis_client()
        p = self._prefix(job_id, tenant_id)
        if standard_gb_month:
            await redis.incr(f"{p}:gcs:standard_gb_month_milli", int(float(standard_gb_month) * 1000.0))
        if nearline_gb_month:
            await redis.incr(f"{p}:gcs:nearline_gb_month_milli", int(float(nearline_gb_month) * 1000.0))
        if coldline_gb_month:
            await redis.incr(f"{p}:gcs:coldline_gb_month_milli", int(float(coldline_gb_month) * 1000.0))
        if archive_gb_month:
            await redis.incr(f"{p}:gcs:archive_gb_month_milli", int(float(archive_gb_month) * 1000.0))
        if ops_a:
            await redis.incr(f"{p}:gcs:ops_a", int(ops_a))
        if ops_b:
            await redis.incr(f"{p}:gcs:ops_b", int(ops_b))

    async def record_gcs_upload(self, job_id: str, *, bytes_uploaded: int, tenant_id: Optional[str] = None) -> None:
        mb = float(bytes_uploaded) / (1024.0 * 1024.0)
        gb = float(bytes_uploaded) / (1024.0 ** 3)
        try:
            retention_days = int(os.getenv("GCS_RETENTION_DAYS", "7") or "7")
        except Exception:
            retention_days = 7
        gb_month = gb * (max(retention_days, 1) / 30.0)
        await self.record_data_transfer(job_id, mb_out=mb, tenant_id=tenant_id)
        await self.record_gcs_usage(job_id, standard_gb_month=gb_month, ops_a=1, tenant_id=tenant_id)

    async def record_gcs_download(self, job_id: str, *, bytes_downloaded: int, tenant_id: Optional[str] = None) -> None:
        mb = float(bytes_downloaded) / (1024.0 * 1024.0)
        await self.record_data_transfer(job_id, mb_in=mb, tenant_id=tenant_id)
        await self.record_gcs_usage(job_id, ops_b=1, tenant_id=tenant_id)

    async def summarize(self, job_id: str, *, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        redis = self._override_redis or get_redis_client()
        prefixes = self._prefixes(job_id, tenant_id)

        async def _sum_int(suffix: str) -> int:
            total = 0
            for p in prefixes:
                total += int(await redis.get(f"{p}:{suffix}", 0) or 0)
            return total

        async def _first_str(suffix: str) -> Optional[str]:
            for p in prefixes:
                v = await redis.get(f"{p}:{suffix}", None)
                if v is not None and str(v).strip() != "":
                    return str(v)
            return None

        tokens_in = await _sum_int("tokens_in")
        tokens_out = await _sum_int("tokens_out")
        kb_in = await _sum_int("kb_in")
        kb_out = await _sum_int("kb_out")
        compute_ms = await _sum_int("compute_ms")
        api_total = await _sum_int("api_total")

        # Derive costs using configured rates (require environment configuration via GSM)
        price_in_tok = _must_env_float("PRICE_PER_1K_INPUT_TOKENS")
        price_out_tok = _must_env_float("PRICE_PER_1K_OUTPUT_TOKENS")
        price_api = _must_env_float("PRICE_PER_API_CALL")
        price_mb_in = _must_env_float("PRICE_PER_MB_INBOUND")
        price_mb_out = _must_env_float("PRICE_PER_MB_OUTBOUND")
        price_ms_compute = _must_env_float("PRICE_PER_MS_COMPUTE")

        # LLM-specific pricing if context is available; else fallback to generic per-1K
        llm_provider = await _first_str("llm_provider")
        llm_model = await _first_str("llm_model")
        llm_mode = await _first_str("llm_mode")
        llm_cache_tokens = await _sum_int("llm_cache_tokens")

        if llm_provider and llm_model:
            cost_tokens = llm_pricing.estimate_tokens_cost(
                provider=str(llm_provider),
                model=str(llm_model),
                input_tokens=int(tokens_in),
                output_tokens=int(tokens_out),
                mode=str(llm_mode) if llm_mode else None,
                caching_tokens=int(llm_cache_tokens),
            )
        else:
            # Tokens: generic per 1K
            cost_tokens = ((int(tokens_in) / 1000.0) * price_in_tok) + ((int(tokens_out) / 1000.0) * price_out_tok)

        # API calls: flat per call (generic)
        cost_api = int(api_total) * price_api
        # Data transfer: KB → MB
        cost_data_in = (int(kb_in) / 1024.0) * price_mb_in
        cost_data_out = (int(kb_out) / 1024.0) * price_mb_out
        cost_data = cost_data_in + cost_data_out
        # Compute: per millisecond
        cost_compute = int(compute_ms) * price_ms_compute

        # Optional service-specific costs (present only if counters exist)
        # EXA
        exa_af_1_25 = await _sum_int("exa:search:auto_fast:1_25")
        exa_af_26_100 = await _sum_int("exa:search:auto_fast:26_100")
        exa_neural_legacy = await _sum_int("exa:search:neural")
        exa_neural_1_25 = await _sum_int("exa:search:neural:1_25")
        exa_neural_26_100 = await _sum_int("exa:search:neural:26_100")
        exa_keyword = await _sum_int("exa:search:keyword")
        exa_text_pages = await _sum_int("exa:contents:text_pages")
        exa_highlights_pages = await _sum_int("exa:contents:highlights_pages")
        exa_summary_pages = await _sum_int("exa:contents:summary_pages")
        exa_answers = await _sum_int("exa:answers")
        exa_agent_ops = await _sum_int("exa:research:agent_ops")
        exa_page_reads_std = await _sum_int("exa:research:page_reads_standard")
        exa_page_reads_pro = await _sum_int("exa:research:page_reads_pro")
        exa_reasoning_tokens = await _sum_int("exa:research:reasoning_tokens")
        exa_costs = svc_pricing.estimate_exa_cost(
            search_auto_fast_1_25=int(exa_af_1_25),
            search_auto_fast_26_100=int(exa_af_26_100),
            search_neural=int(exa_neural_legacy),
            search_neural_1_25=int(exa_neural_1_25),
            search_neural_26_100=int(exa_neural_26_100),
            search_keyword=int(exa_keyword),
            contents_text_pages=int(exa_text_pages),
            contents_highlights_pages=int(exa_highlights_pages),
            contents_summary_pages=int(exa_summary_pages),
            answers=int(exa_answers),
            research_agent_ops=int(exa_agent_ops),
            research_page_reads_standard=int(exa_page_reads_std),
            research_page_reads_pro=int(exa_page_reads_pro),
            research_reasoning_tokens=int(exa_reasoning_tokens),
        )

        # Vertex AI Search
        vs_std = await _sum_int("vertex_search:standard_q")
        vs_ent = await _sum_int("vertex_search:enterprise_q")
        vs_adv = await _sum_int("vertex_search:advanced_q")
        vs_costs = svc_pricing.estimate_vertex_search_cost(
            standard_q=int(vs_std), enterprise_q=int(vs_ent), advanced_q=int(vs_adv), index_gib_month=0.0
        )

        # BigQuery
        bq_bytes = await _sum_int("bq:bytes_scanned")
        bq_active_milli = await _sum_int("bq:active_gb_month_milli")
        bq_long_milli = await _sum_int("bq:long_term_gb_month_milli")
        bq_slots_milli = await _sum_int("bq:slot_hours_milli")
        bq_active = (float(bq_active_milli) / 1000.0) if bq_active_milli else float(await _sum_int("bq:active_gb_month"))
        bq_long = (float(bq_long_milli) / 1000.0) if bq_long_milli else float(await _sum_int("bq:long_term_gb_month"))
        bq_slots = (float(bq_slots_milli) / 1000.0) if bq_slots_milli else float(await _sum_int("bq:slot_hours"))
        bq_costs = svc_pricing.estimate_bigquery_cost(
            bytes_scanned=int(bq_bytes), active_gb_month=float(bq_active), long_term_gb_month=float(bq_long), slot_hours=float(bq_slots)
        )

        # Compute/Network/GCS (infra)
        vcpu_h_milli = await _sum_int("compute:vcpu_hours_milli")
        ram_h_milli = await _sum_int("compute:ram_gb_hours_milli")
        gpu_h_milli = await _sum_int("compute:gpu_hours_milli")
        vcpu_h = (float(vcpu_h_milli) / 1000.0) if vcpu_h_milli else float(await _sum_int("compute:vcpu_hours"))
        ram_h = (float(ram_h_milli) / 1000.0) if ram_h_milli else float(await _sum_int("compute:ram_gb_hours"))
        gpu_h = (float(gpu_h_milli) / 1000.0) if gpu_h_milli else float(await _sum_int("compute:gpu_hours"))
        compute_res_costs = svc_pricing.estimate_compute_cost(vcpu_hours=float(vcpu_h), ram_gb_hours=float(ram_h), gpu_hours=float(gpu_h))

        egress_gib_milli = await _sum_int("network:egress_gib_milli")
        egress_gib = (float(egress_gib_milli) / 1000.0) if egress_gib_milli else float(await _sum_int("network:egress_gib"))
        network_costs = svc_pricing.estimate_network_cost(egress_gib=float(egress_gib))

        gcs_std_milli = await _sum_int("gcs:standard_gb_month_milli")
        gcs_near_milli = await _sum_int("gcs:nearline_gb_month_milli")
        gcs_cold_milli = await _sum_int("gcs:coldline_gb_month_milli")
        gcs_arch_milli = await _sum_int("gcs:archive_gb_month_milli")
        gcs_std = (float(gcs_std_milli) / 1000.0) if gcs_std_milli else float(await _sum_int("gcs:standard_gb_month"))
        gcs_near = (float(gcs_near_milli) / 1000.0) if gcs_near_milli else float(await _sum_int("gcs:nearline_gb_month"))
        gcs_cold = (float(gcs_cold_milli) / 1000.0) if gcs_cold_milli else float(await _sum_int("gcs:coldline_gb_month"))
        gcs_arch = (float(gcs_arch_milli) / 1000.0) if gcs_arch_milli else float(await _sum_int("gcs:archive_gb_month"))
        gcs_ops_a = await _sum_int("gcs:ops_a")
        gcs_ops_b = await _sum_int("gcs:ops_b")
        gcs_costs = svc_pricing.estimate_gcs_cost(
            standard_gb_month=float(gcs_std), nearline_gb_month=float(gcs_near), coldline_gb_month=float(gcs_cold), archive_gb_month=float(gcs_arch), ops_a=int(gcs_ops_a), ops_b=int(gcs_ops_b)
        )

        # Total
        total_cost = float(
            cost_tokens + cost_api + cost_data + cost_compute +
            exa_costs.get("total", 0.0) + vs_costs.get("total", 0.0) +
            bq_costs.get("total", 0.0) + compute_res_costs.get("total", 0.0) + network_costs.get("total", 0.0) + gcs_costs.get("total", 0.0)
        )

        # LOG: Cost summary
        _log_cost(job_id, "SUMMARY", f"Cost summary computed",
                  total_cost=f"${total_cost:.6f}",
                  tokens_in=tokens_in, tokens_out=tokens_out,
                  llm_provider=llm_provider, llm_model=llm_model,
                  tenant_id=tenant_id)

        return {
            "job_id": job_id,
            "currency": os.getenv("PRICING_CURRENCY", "USD"),
            "counters": {
                "tokens_in": int(tokens_in),
                "tokens_out": int(tokens_out),
                "kb_in": int(kb_in),
                "kb_out": int(kb_out),
                "compute_ms": int(compute_ms),
                "api_total": int(api_total),
                "llm_provider": llm_provider,
                "llm_model": llm_model,
                "llm_mode": llm_mode,
                "llm_cache_tokens": int(llm_cache_tokens),
            },
            "cost_breakdown": {
                "tokens": cost_tokens,
                "api": cost_api,
                "data_transfer": cost_data,
                "compute": cost_compute,
                "exa": exa_costs.get("total", 0.0),
                "vertex_search": vs_costs.get("total", 0.0),
                "bigquery": bq_costs.get("total", 0.0),
                "compute_resources": compute_res_costs.get("total", 0.0),
                "network_egress": network_costs.get("total", 0.0),
                "gcs_storage_ops": gcs_costs.get("total", 0.0),
            },
            "total_cost": total_cost,
        }

    async def publish_cost_event(self, job_id: str, *, tenant_id: Optional[str] = None) -> None:
        """Publish a cost update event to the existing job trace channel.

        Frontend already subscribes to `job_trace_{job_id}` via GraphQL
        subscription (see `src/core/redis.publish_execution_trace`).
        """
        try:
            summary = await self.summarize(job_id, tenant_id=tenant_id)
            _log_cost(job_id, "PUBLISH", f"Publishing cost update",
                      total_cost=f"${summary.get('total_cost', 0):.6f}", tenant_id=tenant_id)
            payload = {
                "type": "cost_update",
                "job_id": job_id,
                "currency": summary.get("currency"),
                "counters": summary.get("counters"),
                "cost_breakdown": summary.get("cost_breakdown"),
                "total_cost": summary.get("total_cost"),
            }
            await publish_execution_trace(job_id, payload)
        except Exception as e:
            logger.error(f"Failed to publish cost update for job {job_id}: {e}")


