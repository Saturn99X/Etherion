import os
import subprocess
import sys

from rich.console import Console

from ._env import require_dotenv, check_required_vars, REQUIRED_FOR_WORKER

console = Console()


def run_worker(
    queues: str = "celery,worker-artifacts",
    concurrency: int = 4,
    loglevel: str = "info",
) -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_WORKER)
    from dotenv import load_dotenv
    load_dotenv(".env", override=False)
    console.print(f"[bold]Starting Celery worker (queues={queues})[/bold]")
    cmd = [
        sys.executable, "-m", "celery",
        "-A", "src.core.celery.celery_app",
        "worker",
        f"--loglevel={loglevel}",
        f"--concurrency={concurrency}",
        "-Q", queues,
        "--pool=threads",
    ]
    sys.exit(subprocess.call(cmd))


def run_beat(loglevel: str = "info") -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_WORKER)
    from dotenv import load_dotenv
    load_dotenv(".env", override=False)
    console.print("[bold]Starting Celery beat scheduler[/bold]")
    cmd = [
        sys.executable, "-m", "celery",
        "-A", "src.core.celery.celery_app",
        "beat",
        f"--loglevel={loglevel}",
    ]
    sys.exit(subprocess.call(cmd))
