import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ._env import load_env

console = Console()


def run() -> None:
    env = load_env()

    if not Path(".env").exists():
        console.print(
            "[yellow]⚠ No .env found in current directory — "
            "using environment variables only.[/yellow]\n"
        )

    table = Table(
        title="Etherion Platform Status",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Service", style="bold", width=14)
    table.add_column("Status", width=8)
    table.add_column("Detail")

    _add_row(table, "PostgreSQL", _check_postgres, env)
    _add_row(table, "Redis", _check_redis, env)
    _add_row(table, "MinIO", _check_minio, env)
    _add_row(table, "API", _check_api, env)
    _add_row(table, "Worker", _check_worker, env)

    if env.get("SECRETS_BACKEND", "").lower() == "vault":
        _add_row(table, "Vault", _check_vault, env)

    console.print(table)


def _add_row(table: Table, label: str, fn, env: dict) -> None:
    t0 = time.monotonic()
    try:
        detail = fn(env)
        ms = int((time.monotonic() - t0) * 1000)
        table.add_row(label, "[green]✓[/green]", f"{detail} ({ms}ms)")
    except _MissingVar as e:
        table.add_row(label, "[yellow]?[/yellow]", str(e))
    except Exception as e:
        table.add_row(label, "[red]✗[/red]", str(e)[:120])


class _MissingVar(Exception):
    """Raised when a required env var is absent — shown differently from a real error."""


# ── checkers ──────────────────────────────────────────────────────────────────

def _check_postgres(env: dict) -> str:
    import psycopg2

    raw = env.get("DATABASE_URL") or env.get("ETHERION_DATABASE_URL")
    if not raw:
        raise _MissingVar(
            "DATABASE_URL not set — add it to .env "
            "(e.g. postgresql+psycopg2://user:pass@localhost:5432/etherion)"
        )
    url = _strip_pg_prefix(raw)
    conn = psycopg2.connect(url, connect_timeout=5)
    cur = conn.cursor()
    cur.execute("SELECT version()")
    ver = cur.fetchone()[0].split(",")[0]
    conn.close()
    return ver


def _check_redis(env: dict) -> str:
    import redis as redis_lib

    url = env.get("ETHERION_REDIS_URL") or env.get("REDIS_URL")
    if not url:
        raise _MissingVar(
            "REDIS_URL not set — add it to .env "
            "(e.g. redis://localhost:6379/0)"
        )
    r = redis_lib.from_url(url, socket_connect_timeout=5)
    info = r.info("server")
    ver = info.get("redis_version", "?")
    r.close()
    return f"Redis {ver}"


def _check_minio(env: dict) -> str:
    import urllib.request

    endpoint = env.get("MINIO_ENDPOINT")
    if not endpoint:
        raise _MissingVar(
            "MINIO_ENDPOINT not set — add it to .env "
            "(e.g. http://localhost:9000)"
        )
    if not endpoint.startswith("http"):
        endpoint = f"http://{endpoint}"
    urllib.request.urlopen(f"{endpoint}/minio/health/live", timeout=5)
    return endpoint


def _check_api(env: dict) -> str:
    import urllib.request

    raw_host = env.get("API_HOST", "localhost")
    port = env.get("API_PORT", "8080")

    if raw_host.startswith("http"):
        base = raw_host.rstrip("/")
    elif raw_host in ("0.0.0.0", "::"):
        base = f"http://localhost:{port}"
    else:
        base = f"http://{raw_host}:{port}"

    with urllib.request.urlopen(f"{base}/health", timeout=5) as r:
        return f"HTTP {r.status} at {base}"


def _check_worker(env: dict) -> str:
    import redis as redis_lib

    url = env.get("ETHERION_REDIS_URL") or env.get("REDIS_URL") or env.get("CELERY_BROKER_URL")
    if not url:
        raise _MissingVar(
            "REDIS_URL / CELERY_BROKER_URL not set — "
            "cannot check worker heartbeat"
        )
    r = redis_lib.from_url(url, socket_connect_timeout=5)
    keys = r.keys("_kombu.binding.*")
    r.close()
    if keys:
        return f"{len(keys)} queue binding(s)"
    return "no queue bindings (worker may still be starting)"


def _check_vault(env: dict) -> str:
    import json
    import urllib.request

    addr = env.get("VAULT_ADDR")
    if not addr:
        raise _MissingVar(
            "VAULT_ADDR not set — add it to .env "
            "(e.g. http://localhost:8200)"
        )
    with urllib.request.urlopen(f"{addr}/v1/sys/health", timeout=5) as r:
        data = json.loads(r.read())
    return f"initialized={data.get('initialized')} sealed={data.get('sealed')}"


# ── helpers ───────────────────────────────────────────────────────────────────

def _strip_pg_prefix(url: str) -> str:
    for prefix in ("postgresql+psycopg2://", "postgresql+asyncpg://", "postgres+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url
