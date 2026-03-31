import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console

console = Console()


def run(
    host: str | None = None,
    port: int | None = None,
    workers: int = 1,
    no_api: bool = False,
    no_worker: bool = False,
) -> None:
    """Bring up the full Etherion stack: infrastructure + API + worker."""
    # 1. Infrastructure containers
    console.print("[bold]Starting infrastructure…[/bold]")
    from .cmd_bootstrap import run as bootstrap_run
    bootstrap_run(mode="docker")

    bg_pids: list[tuple[str, subprocess.Popen]] = []

    # 2. API server (background)
    if not no_api:
        from ._env import require_dotenv
        env = require_dotenv()
        resolved_host = host or env.get("API_HOST", "0.0.0.0")
        resolved_port = port or int(env.get("API_PORT", "8080"))
        console.print(f"[bold]Starting API on {resolved_host}:{resolved_port}…[/bold]")

        api_proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "src.etherion_ai.app:app",
                "--host", str(resolved_host),
                "--port", str(resolved_port),
                "--workers", str(workers),
            ],
            env={**os.environ},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        bg_pids.append(("API", api_proc))
        console.print(f"[green]✓[/green] API started (pid {api_proc.pid})")

    # 3. Celery worker (background)
    if not no_worker:
        console.print("[bold]Starting Celery worker…[/bold]")
        worker_proc = subprocess.Popen(
            [
                sys.executable, "-m", "celery",
                "-A", "src.core.celery",
                "worker",
                "--queues=celery,worker-artifacts",
                "--concurrency=4",
                "--loglevel=info",
            ],
            env={**os.environ},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        bg_pids.append(("Worker", worker_proc))
        console.print(f"[green]✓[/green] Worker started (pid {worker_proc.pid})")

    if bg_pids:
        pids_str = ", ".join(f"{name}={p.pid}" for name, p in bg_pids)
        console.print(f"\n[bold green]✓ All services running.[/bold green]  pids: {pids_str}")
        console.print("[dim]Run [bold]etherion down[/bold] to stop everything.[/dim]")
    else:
        console.print("[bold green]✓ Infrastructure running.[/bold green]")
