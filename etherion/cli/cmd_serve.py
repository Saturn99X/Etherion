import os

from rich.console import Console

from ._env import require_dotenv, check_required_vars, REQUIRED_FOR_SERVE

console = Console()


def run(
    host: str = None,
    port: int = None,
    workers: int = 1,
    reload: bool = False,
) -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_SERVE)

    from dotenv import load_dotenv
    load_dotenv(".env", override=False)

    resolved_host = host or env.get("API_HOST", "0.0.0.0")
    resolved_port = port or int(env.get("API_PORT", "8080"))

    console.print(f"[bold]Starting API on {resolved_host}:{resolved_port}[/bold]")

    import uvicorn
    uvicorn.run(
        "src.etherion_ai.app:app",
        host=resolved_host,
        port=resolved_port,
        workers=workers if not reload else 1,
        reload=reload,
        log_level="info",
    )
