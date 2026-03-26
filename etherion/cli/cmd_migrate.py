import os
import subprocess
import sys

from rich.console import Console

from ._env import require_dotenv, check_required_vars, REQUIRED_FOR_DB

console = Console()


def run(revision: str = "head") -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_DB)

    db_url = env.get("DATABASE_URL") or env.get("ETHERION_DATABASE_URL")
    console.print(f"[dim]DATABASE_URL → {db_url[:40]}…[/dim]")

    cmd = [sys.executable, "-m", "alembic", "upgrade", revision]
    console.print(f"[bold]Running:[/bold] {' '.join(cmd)}")

    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    console.print("[bold green]✓ Migration complete.[/bold green]")
