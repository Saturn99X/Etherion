import typer

app = typer.Typer(
    name="etherion",
    help="Etherion AI Orchestration Platform",
    no_args_is_help=True,
)


@app.command()
def init(
    mode: str = typer.Option("all", "--mode", "-m", help="docker | ansible | nix | all"),
    target: str = typer.Option(".", "--target", "-t", help="Target directory"),
):
    """Scaffold .env, alembic.ini, and infra configs in the current directory."""
    from .cmd_init import run
    run(mode=mode, target=target)


@app.command()
def bootstrap(
    mode: str = typer.Option("docker", "--mode", "-m", help="docker | native"),
):
    """Start local infrastructure services."""
    from .cmd_bootstrap import run
    run(mode=mode)


@app.command()
def migrate(
    revision: str = typer.Argument("head", help="Alembic revision target"),
):
    """Run Alembic database migrations."""
    from .cmd_migrate import run
    run(revision=revision)


@app.command()
def serve(
    host: str = typer.Option(None, "--host", help="Bind host (overrides .env API_HOST)"),
    port: int = typer.Option(None, "--port", help="Bind port (overrides .env API_PORT)"),
    workers: int = typer.Option(1, "--workers", "-w"),
    reload: bool = typer.Option(False, "--reload"),
):
    """Start the Etherion API server (uvicorn)."""
    from .cmd_serve import run
    run(host=host, port=port, workers=workers, reload=reload)


worker_app = typer.Typer(help="Manage Celery workers.")
app.add_typer(worker_app, name="worker")


@worker_app.command("start")
def worker_start(
    queues: str = typer.Option("celery,worker-artifacts", "--queues", "-Q"),
    concurrency: int = typer.Option(4, "--concurrency", "-c"),
    loglevel: str = typer.Option("info", "--loglevel", "-l"),
):
    """Start a Celery worker."""
    from .cmd_worker import run_worker
    run_worker(queues=queues, concurrency=concurrency, loglevel=loglevel)


@worker_app.command("beat")
def worker_beat(
    loglevel: str = typer.Option("info", "--loglevel", "-l"),
):
    """Start the Celery beat scheduler."""
    from .cmd_worker import run_beat
    run_beat(loglevel=loglevel)


@app.command()
def status():
    """Show health status of all platform services."""
    from .cmd_status import run
    run()


@app.command("create-tenant")
def create_tenant(
    name: str = typer.Option(..., "--name", "-n", help="Tenant display name"),
    email: str = typer.Option(..., "--email", "-e", help="Admin user email"),
    password: str = typer.Option(..., "--password", "-p", help="Admin user password"),
    subdomain: str = typer.Option(None, "--subdomain", help="Tenant subdomain (auto-derived if omitted)"),
):
    """Create a new tenant and admin user."""
    from .cmd_tenant import run
    run(name=name, email=email, password=password, subdomain=subdomain)



@app.command()
def up(
    host: str = typer.Option(None, "--host", help="API bind host"),
    port: int = typer.Option(None, "--port", help="API bind port"),
    workers: int = typer.Option(1, "--workers", "-w"),
    no_api: bool = typer.Option(False, "--no-api", help="Skip starting the API server"),
    no_worker: bool = typer.Option(False, "--no-worker", help="Skip starting the Celery worker"),
):
    """Bring up the full stack: infrastructure containers + API + worker."""
    from .cmd_up import run
    run(host=host, port=port, workers=workers, no_api=no_api, no_worker=no_worker)


@app.command()
def down(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Stop all services: API, workers, and infrastructure containers."""
    if not force:
        typer.confirm("Stop all Etherion services?", abort=True)
    from .cmd_down import run
    run(force=force)


@app.command()
def where():
    """Show all files, processes, containers, and connections on this machine."""
    from .cmd_where import run
    run()


@app.command()
def version():
    """Show the installed etherion version."""
    from etherion import __version__
    typer.echo(f"etherion {__version__}")


if __name__ == "__main__":
    app()
