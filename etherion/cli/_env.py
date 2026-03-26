"""Shared .env loading and pre-flight validation utilities."""

import os
import sys
from pathlib import Path

from rich.console import Console

console = Console(stderr=True)

# Variables that must be non-empty for each command to work.
REQUIRED_FOR_DB = ("DATABASE_URL",)
REQUIRED_FOR_REDIS = ("REDIS_URL",)
REQUIRED_FOR_SERVE = ("DATABASE_URL", "REDIS_URL", "JWT_SECRET_KEY", "SECRET_KEY")
REQUIRED_FOR_WORKER = ("CELERY_BROKER_URL", "DATABASE_URL")


def load_env(path: str = ".env") -> dict:
    """Load .env into a dict (merged over os.environ). Never raises."""
    env = os.environ.copy()
    p = Path(path)
    if p.exists():
        try:
            from dotenv import dotenv_values
            env.update({k: v for k, v in dotenv_values(str(p)).items() if v is not None})
        except ImportError:
            pass
    return env


def require_dotenv(path: str = ".env") -> dict:
    """
    Load and return the env dict. Hard-exit if .env is absent.
    Prints a clear, actionable error pointing at the missing file.
    """
    p = Path(path).resolve()
    if not p.exists():
        console.print(f"\n[bold red]✗ .env not found:[/bold red] {p}\n")
        if Path(".env.example").exists():
            console.print(
                "  Copy the example file and fill in your values:\n"
                "  [bold]cp .env.example .env && $EDITOR .env[/bold]\n"
            )
        else:
            console.print(
                "  Run [bold]etherion init[/bold] first to scaffold the project,\n"
                "  then edit [bold].env[/bold] before proceeding.\n"
            )
        sys.exit(1)
    return load_env(path)


def check_required_vars(env: dict, *names: str) -> None:
    """
    Exit with a clear per-variable error if any of the given env vars are
    absent or empty.  Prints each missing var with a hint where to set it.
    """
    missing = [n for n in names if not env.get(n)]
    if not missing:
        return

    console.print("\n[bold red]✗ Missing required environment variable(s):[/bold red]\n")
    for name in missing:
        console.print(f"  [red]•[/red] [bold]{name}[/bold]")
    console.print(
        "\n  Set these in [bold].env[/bold] (or export them) before retrying.\n"
        "  See [bold].env.example[/bold] for reference values.\n"
    )
    sys.exit(1)
