import shutil
import sys
from importlib.resources import files
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def run(mode: str = "all", target: str = ".") -> None:
    dest = Path(target).resolve()
    data_root = files("etherion") / "_data"

    # .env.example
    _copy_asset(data_root / "env" / ".env.example", dest / ".env.example")

    # alembic.ini.template → alembic.ini (only if not present)
    alembic_ini = dest / "alembic.ini"
    if not alembic_ini.exists():
        _copy_asset(data_root / "alembic" / "alembic.ini.template", alembic_ini)
    else:
        console.print("[yellow]alembic.ini already exists — skipping[/yellow]")

    # alembic/env.py + versions/ — required for `etherion migrate` to work
    (dest / "alembic" / "versions").mkdir(parents=True, exist_ok=True)
    _copy_asset(data_root / "alembic" / "env.py", dest / "alembic" / "env.py")
    src_versions = Path(str(data_root / "alembic" / "versions"))
    if src_versions.exists():
        for f in src_versions.glob("*.py"):
            _copy_asset(data_root / "alembic" / "versions" / f.name,
                        dest / "alembic" / "versions" / f.name)

    if mode in ("docker", "all"):
        _copy_asset(
            data_root / "infra" / "docker" / "docker-compose.services.yml",
            dest / "docker-compose.services.yml",
        )

    if mode in ("ansible", "all"):
        src_ansible = Path(str(data_root / "ansible"))
        if src_ansible.exists():
            shutil.copytree(str(src_ansible), str(dest / "ansible"), dirs_exist_ok=True)
            console.print("[green]✓[/green] ansible/")

    if mode in ("nix", "all"):
        src_nix = Path(str(data_root / "nix"))
        if src_nix.exists():
            shutil.copytree(str(src_nix), str(dest / "nix"), dirs_exist_ok=True)
            console.print("[green]✓[/green] nix/")

    console.print("\n[bold green]✓ Etherion project initialized.[/bold green]")
    console.print("Edit [bold].env[/bold] then run [bold]etherion bootstrap[/bold].")


def _copy_asset(src, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        src_path = Path(str(src))
        if src_path.exists():
            shutil.copy2(str(src_path), str(dest))
            console.print(f"[green]✓[/green] {dest.name}")
        else:
            console.print(f"[yellow]![/yellow] Asset not found: {src}")
    except Exception as e:
        console.print(f"[red]✗[/red] {dest.name}: {e}", file=sys.stderr)
