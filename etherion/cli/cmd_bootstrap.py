import subprocess
from ._env import load_env
import sys
import time
from pathlib import Path

from rich.console import Console

console = Console()

_POLL_INTERVAL = 2
_POLL_TIMEOUT = 90


def run(mode: str = "docker") -> None:
    from pathlib import Path
    if not Path(".env").exists():
        console.print(
            "[yellow]⚠  No .env found — using default service credentials.\n"
            "   Run [bold]etherion init[/bold] then edit .env to customise passwords.[/yellow]"
        )
    if mode == "docker":
        _docker_mode()
    elif mode == "native":
        _native_mode()
    else:
        console.print(f"[red]Unknown mode: {mode}[/red]")
        raise SystemExit(1)


def _docker_mode() -> None:
    compose_file = Path("docker-compose.services.yml")
    if not compose_file.exists():
        console.print("[red]docker-compose.services.yml not found. Run `etherion init` first.[/red]")
        raise SystemExit(1)

    console.print("[bold]Starting services via Docker Compose…[/bold]")
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d"],
        check=False,
    )
    if result.returncode != 0:
        # Fallback to legacy docker-compose
        result = subprocess.run(
            ["docker-compose", "-f", str(compose_file), "up", "-d"],
            check=False,
        )
    if result.returncode != 0:
        console.print("[red]docker compose up failed.[/red]")
        raise SystemExit(result.returncode)

    _poll_services()


def _poll_services() -> None:
    import os
    from dotenv import dotenv_values

    env = {**os.environ}
    if Path(".env").exists():
        env.update({k: v for k, v in dotenv_values(".env").items() if v})

    checks = [
        ("PostgreSQL", _check_postgres, env),
        ("Redis", _check_redis, env),
        ("MinIO", _check_minio, env),
    ]

    deadline = time.time() + _POLL_TIMEOUT
    pending = list(checks)

    with console.status("[bold]Waiting for services…[/bold]") as status:
        while pending and time.time() < deadline:
            still_pending = []
            for label, fn, e in pending:
                try:
                    fn(e)
                    console.print(f"[green]✓[/green] {label} ready")
                except Exception:
                    still_pending.append((label, fn, e))
            pending = still_pending
            if pending:
                time.sleep(_POLL_INTERVAL)

    if pending:
        labels = ", ".join(lbl for lbl, _, _ in pending)
        console.print(f"[red]Timed out waiting for: {labels}[/red]")
        raise SystemExit(1)

    console.print("[bold green]✓ All services healthy.[/bold green]")


def _check_postgres(env: dict) -> None:
    import psycopg2

    raw = env.get("DATABASE_URL", "")
    url = _strip_pg_prefix(raw) or "postgresql://etherion:etherion@localhost:5432/etherion"
    conn = psycopg2.connect(url, connect_timeout=3)
    conn.close()


def _check_redis(env: dict) -> None:
    import redis as redis_lib

    url = env.get("ETHERION_REDIS_URL") or env.get("REDIS_URL") or "redis://localhost:6379/0"
    r = redis_lib.from_url(url, socket_connect_timeout=3)
    r.ping()
    r.close()


def _check_minio(env: dict) -> None:
    import urllib.request

    endpoint = env.get("MINIO_ENDPOINT", "http://localhost:9000")
    if not endpoint.startswith("http"):
        endpoint = f"http://{endpoint}"
    urllib.request.urlopen(f"{endpoint}/minio/health/live", timeout=3)


def _native_mode() -> None:
    console.print("[yellow]native mode: assuming postgres/redis/minio are managed by systemd.[/yellow]")
    import os
    from dotenv import dotenv_values

    env = {**os.environ}
    if Path(".env").exists():
        env.update({k: v for k, v in dotenv_values(".env").items() if v})
    _poll_services()


def _strip_pg_prefix(url: str) -> str:
    for prefix in ("postgresql+psycopg2://", "postgresql+asyncpg://", "postgres+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url
