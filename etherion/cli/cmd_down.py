import os
import signal
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()


def run(force: bool = False) -> None:
    """Stop all Etherion services: API, workers, and infrastructure containers."""
    stopped = []

    # 1. Kill API (uvicorn)
    stopped += _kill_proc("uvicorn", signal.SIGTERM)

    # 2. Kill Celery workers + beat
    stopped += _kill_proc("celery", signal.SIGTERM)

    if stopped:
        console.print(f"[green]✓[/green] Stopped processes: {', '.join(stopped)}")
    else:
        console.print("[dim]No running API/worker processes found.[/dim]")

    # 3. Docker compose down
    compose_file = _find_compose()
    if compose_file:
        console.print("[bold]Stopping infrastructure containers…[/bold]")
        rc = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "down"],
            check=False,
        ).returncode
        if rc != 0:
            rc = subprocess.run(
                ["docker-compose", "-f", str(compose_file), "down"],
                check=False,
            ).returncode
        if rc == 0:
            console.print("[green]✓[/green] Containers stopped.")
        else:
            console.print("[red]✗ docker compose down failed.[/red]")
            raise SystemExit(rc)
    else:
        console.print("[yellow]No docker-compose.services.yml found — skipping containers.[/yellow]")

    console.print("[bold green]✓ All services down.[/bold green]")


def _kill_proc(name: str, sig: int) -> list[str]:
    """Kill all processes matching *name* via pgrep/pkill. Returns labels of killed procs."""
    killed = []
    try:
        pids = subprocess.check_output(
            ["pgrep", "-f", name], text=True
        ).strip().splitlines()
        if pids:
            subprocess.run(["pkill", "-f", name], check=False)
            killed.append(f"{name}(pid {','.join(pids)})")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return killed


def _find_compose() -> Path | None:
    candidates = [
        Path("docker-compose.services.yml"),
        Path("etherion/_data/infra/docker/docker-compose.services.yml"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None
