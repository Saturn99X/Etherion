"""
`etherion where` — show everything created/running on this machine.

Answers the question: "what did etherion put on my system and where?"
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from ._env import load_env

console = Console()


def run() -> None:
    env = load_env()

    console.print()
    _section_files(env)
    _section_processes()
    _section_docker(env)
    _section_connections(env)
    _section_how_to_stop()
    console.print()


# ── 1. Files & directories created on this machine ────────────────────────────

def _section_files(env: dict) -> None:
    cwd = Path(".").resolve()
    home = Path.home()

    rows = [
        ("Project .env",           cwd / ".env",                           "Main configuration — edit this to change secrets/URLs"),
        (".env.example",           cwd / ".env.example",                   "Reference template (safe to share)"),
        ("docker-compose file",    cwd / "docker-compose.services.yml",    "Service definitions for postgres/redis/minio"),
        ("Alembic config",         cwd / "alembic.ini",                    "Database migration settings"),
        ("Alembic migrations",     cwd / "alembic" / "versions",           "Migration history (applied to DB)"),
        ("TUI config",             home / ".config" / "etherion" / "tui.json", "Saved server URL & login token"),
    ]

    t = Table(title="Files & Directories", box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    t.add_column("Item", style="bold", min_width=22)
    t.add_column("Path")
    t.add_column("Note", style="dim")

    for label, path, note in rows:
        exists = path.exists()
        status = "[green]✓[/green]" if exists else "[dim]—[/dim]"
        t.add_row(f"{status} {label}", str(path), note)

    console.print(t)


# ── 2. Running processes ───────────────────────────────────────────────────────

def _section_processes() -> None:
    targets = [
        ("API server (uvicorn)", ["uvicorn", "etherion serve"]),
        ("Celery worker",        ["celery worker", "celery -A src"]),
        ("Celery beat",          ["celery beat"]),
    ]

    t = Table(title="Running Processes", box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    t.add_column("Process", style="bold", min_width=22)
    t.add_column("PID(s)")
    t.add_column("How to stop", style="dim")

    for label, patterns in targets:
        pids = _find_pids(patterns)
        if pids:
            t.add_row(
                f"[green]✓[/green] {label}",
                ", ".join(pids),
                f"kill {' '.join(pids)}",
            )
        else:
            t.add_row(f"[dim]—[/dim] {label}", "not running", "")

    console.print(t)


def _find_pids(patterns: list[str]) -> list[str]:
    """Return PIDs of processes matching any of the given command-line patterns."""
    import platform
    pids = []
    own_pid = str(os.getpid())
    try:
        if platform.system() == "Windows":
            # tasklist /FO CSV /NH gives: "name.exe","pid","session","#","mem"
            out = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH"],
                text=True, stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                parts = [p.strip('"') for p in line.split(",")]
                if len(parts) < 2:
                    continue
                name, pid = parts[0], parts[1]
                if any(p.lower() in name.lower() for p in patterns) and pid != own_pid:
                    pids.append(pid)
        else:
            out = subprocess.check_output(
                ["ps", "aux"], text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if any(p in line for p in patterns):
                    parts = line.split()
                    pid = parts[1] if len(parts) > 1 else ""
                    if pid and pid != own_pid:
                        pids.append(pid)
    except Exception:
        pass
    return pids


# ── 3. Docker containers ───────────────────────────────────────────────────────

def _section_docker(env: dict) -> None:
    if not _docker_available():
        console.print(
            "[dim]Docker: not available — skipping container list.[/dim]\n"
        )
        return

    try:
        raw = subprocess.check_output(
            ["docker", "ps", "-a",
             "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
            text=True, stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        console.print(f"[dim]Docker: could not query containers ({e})[/dim]\n")
        return

    lines = [l for l in raw.strip().splitlines() if l]
    if not lines:
        console.print("[dim]Docker: no containers found.[/dim]\n")
        return

    t = Table(title="Docker Containers", box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    t.add_column("Name", style="bold", min_width=22)
    t.add_column("Status")
    t.add_column("Ports", style="dim")

    for line in lines:
        parts = line.split("\t")
        name   = parts[0] if len(parts) > 0 else "?"
        status = parts[1] if len(parts) > 1 else "?"
        ports  = parts[2] if len(parts) > 2 else ""
        color  = "green" if "Up" in status else "red"
        t.add_row(name, f"[{color}]{status}[/{color}]", ports)

    console.print(t)

    # Show where docker stores its data
    compose = Path("docker-compose.services.yml")
    if compose.exists():
        try:
            raw_vol = subprocess.check_output(
                ["docker", "volume", "ls", "--format", "{{.Name}}"],
                text=True, stderr=subprocess.DEVNULL,
            )
            vols = [v for v in raw_vol.strip().splitlines() if v]
            if vols:
                console.print(
                    f"[dim]Docker volumes (data lives here): "
                    f"{', '.join(vols[:8])}[/dim]"
                )
                console.print(
                    "[dim]  Inspect: docker volume inspect <name> | grep Mountpoint[/dim]\n"
                )
        except Exception:
            pass


def _docker_available() -> bool:
    try:
        subprocess.check_output(
            ["docker", "info"], stderr=subprocess.DEVNULL, timeout=3
        )
        return True
    except Exception:
        return False


# ── 4. Connection details from .env ───────────────────────────────────────────

def _section_connections(env: dict) -> None:
    items = [
        ("DATABASE_URL",     env.get("DATABASE_URL") or env.get("ETHERION_DATABASE_URL"), "PostgreSQL"),
        ("REDIS_URL",        env.get("REDIS_URL") or env.get("ETHERION_REDIS_URL"),       "Redis"),
        ("MINIO_ENDPOINT",   env.get("MINIO_ENDPOINT"),                                   "MinIO object storage"),
        ("API_HOST:PORT",    f"{env.get('API_HOST','0.0.0.0')}:{env.get('API_PORT','8080')}", "Etherion API"),
        ("LLM_PROVIDER",     env.get("LLM_PROVIDER"),                                     "Active LLM backend"),
        ("SECRETS_BACKEND",  env.get("SECRETS_BACKEND","env"),                            "Secrets storage"),
        ("KB_VECTOR_BACKEND",env.get("KB_VECTOR_BACKEND","pgvector"),                     "Knowledge-base backend"),
    ]

    # Also show TUI saved config if present
    tui_cfg = Path.home() / ".config" / "etherion" / "tui.json"
    if tui_cfg.exists():
        try:
            data = json.loads(tui_cfg.read_text())
            items.append(("TUI → server",   data.get("api_url","?"),   "Last URL used in the TUI"))
            items.append(("TUI → logged in",data.get("email","—"),     "Last logged-in user"))
        except Exception:
            pass

    t = Table(title="Configuration Summary", box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    t.add_column("Key", style="bold", min_width=22)
    t.add_column("Value")
    t.add_column("Note", style="dim")

    for key, val, note in items:
        display = str(val) if val else "[dim]not set[/dim]"
        t.add_row(key, display, note)

    console.print(t)


# ── 5. How to stop everything ─────────────────────────────────────────────────

def _section_how_to_stop() -> None:
    import platform
    on_windows = platform.system() == "Windows"
    tui_cfg = "%APPDATA%\\etherion\\tui.json" if on_windows else "~/.config/etherion/tui.json"
    if on_windows:
        lines = [
            ("Stop API server",      "taskkill /F /IM python.exe  (or kill by PID above)"),
            ("Stop Celery worker",   "taskkill /F /IM python.exe  (or kill by PID above)"),
            ("Stop Docker services", "docker compose -f docker-compose.services.yml down"),
            ("Remove Docker data",   "docker compose -f docker-compose.services.yml down -v  ← destroys DB!"),
            ("Delete TUI config",    f"del {tui_cfg}"),
        ]
    else:
        lines = [
            ("Stop API server",      "kill $(pgrep -f 'uvicorn\\|etherion serve')"),
            ("Stop Celery worker",   "kill $(pgrep -f 'celery worker')"),
            ("Stop Docker services", "docker compose -f docker-compose.services.yml down"),
            ("Remove Docker data",   "docker compose -f docker-compose.services.yml down -v  ← destroys DB!"),
            ("Delete TUI config",    f"rm {tui_cfg}"),
        ]

    t = Table(title="How to Stop / Clean Up", box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    t.add_column("Action", style="bold", min_width=22)
    t.add_column("Command", style="green")

    for action, cmd in lines:
        t.add_row(action, cmd)

    console.print(t)
