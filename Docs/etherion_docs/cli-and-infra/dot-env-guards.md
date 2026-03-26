# Environment Variable Validation: The `.env` Guards

The `.env` validation system in Etherion exists to prevent a frustrating developer experience: you run `etherion serve`, it starts, and 30 seconds later crashes deep in some library's connection logic with an unhelpful error. Instead, we validate configuration upfront and fail fast with a clear, actionable message.

The system has three layers: file loading, required-variable checking, and the tuples that define what's required for each command.

## The Three Layers

### Layer 1: `load_env()` — Safe Loading, Never Fails

```python
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
```

This function is defensive: it returns a dict whether `.env` exists or not. If `python-dotenv` is not installed, it silently returns just `os.environ`. This is used by commands that don't strictly require `.env`, like `etherion status` and `etherion where`, which can be informative even if configuration is incomplete.

**Key behavior**: If `.env` has malformed syntax, `dotenv_values` raises an exception, but `load_env` catches and ignores it. This prevents a crash; the command continues with whatever it has. Not ideal for debugging, but safe.

### Layer 2: `require_dotenv()` — Hard Requirement, Clear Message

```python
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
```

Used by commands that absolutely require `.env`, like `etherion serve`, `etherion migrate`, `etherion worker start`, and `etherion create-tenant`. This function exits immediately if `.env` doesn't exist, with a message tailored to the situation:

- If `.env.example` exists, it suggests copying and editing it.
- If `.env.example` doesn't exist, it suggests running `etherion init` first.

**Example error**:

```
✗ .env not found: /home/saturnx/langchain-app/.env

  Run etherion init first to scaffold the project,
  then edit .env before proceeding.
```

The exit happens before any other validation, so this is the first line of defense.

### Layer 3: `check_required_vars()` — Per-Command Variable Validation

```python
def check_required_vars(env: dict, *names: str) -> None:
    """
    Exit with a clear per-variable error if any of the given env vars are
    absent or empty. Prints each missing var with a hint where to set it.
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
```

This is called by each command with a tuple of required variable names. It checks that each one exists in the env dict and is non-empty. If any are missing, it prints them all in a list and exits with status 1.

**Example error**:

```
✗ Missing required environment variable(s):

  • DATABASE_URL
  • JWT_SECRET_KEY

  Set these in .env (or export them) before retrying.
  See .env.example for reference values.
```

Note: "or export them" is important. The check reads from `os.environ` as well as `.env`, so you can override any variable by exporting it in your shell session. This is useful for CI/CD pipelines that inject secrets as environment variables instead of files.

---

## Command-Specific Requirements: The Tuples

At the top of `_env.py`, four tuples define what each command needs:

```python
REQUIRED_FOR_DB = ("DATABASE_URL",)
REQUIRED_FOR_REDIS = ("REDIS_URL",)
REQUIRED_FOR_SERVE = ("DATABASE_URL", "REDIS_URL", "JWT_SECRET_KEY", "SECRET_KEY")
REQUIRED_FOR_WORKER = ("CELERY_BROKER_URL", "DATABASE_URL")
```

These are imported and used by commands:

**`cmd_migrate.py`**:
```python
def run(revision: str = "head") -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_DB)
    # ... rest of migration logic
```

**`cmd_serve.py`**:
```python
def run(host: str = None, port: int = None, workers: int = 1, reload: bool = False) -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_SERVE)
    # ... rest of serve logic
```

**`cmd_worker.py`**:
```python
def run_worker(queues: str = "celery,worker-artifacts", concurrency: int = 4, loglevel: str = "info") -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_WORKER)
    # ... rest of worker logic

def run_beat(loglevel: str = "info") -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_WORKER)
    # ... rest of beat logic
```

The tuples are defined at the module level so they can be reused without duplication. If you add a new command or change requirements, you update the tuple and the command logic together.

---

## Why This Design Matters

### Fail Fast, Not Later

Without this system, here's what happens:

1. Developer runs `etherion serve`
2. Uvicorn starts and binds to port 8080
3. App code tries to connect to the database
4. psycopg2 raises `OperationalError: connection refused`
5. Traceback appears in the logs, developer confused about what to fix

With the guards:

1. Developer runs `etherion serve`
2. Immediately sees: "Missing required environment variable: DATABASE_URL"
3. Developer edits `.env` and retries
4. Uvicorn starts

The difference is 5 seconds vs. a confusing 30-second debugging loop.

### Clear Errors vs. Cryptic Tracebacks

A missing environment variable could manifest in many places:
- `KeyError` when code reads the variable
- `ValueError` when parsing a connection string
- `ConnectionRefusedError` when the connection fails
- `AttributeError` on a None object

Each traceback looks different, and none of them directly says "you forgot to set DATABASE_URL." The guards centralize this knowledge into a single error message.

### Testability and Documentation

The tuples in `_env.py` are both code and documentation. A new developer can read them and immediately see: "to run `etherion serve`, you need these four env vars." It's the source of truth for command requirements.

### Environment Variable Aliasing

Some variables have aliases (e.g., `REDIS_URL` vs. `ETHERION_REDIS_URL`). The checks don't know about aliases; they check for exact names. But the command implementations check aliases:

```python
# In cmd_status.py
url = env.get("ETHERION_REDIS_URL") or env.get("REDIS_URL")
```

This is intentional: the validation is simple and strict (forces a canonical name), but the runtime logic is flexible (accepts aliases). If someone sets `ETHERION_REDIS_URL` but not `REDIS_URL`, the validation still passes because we check both at runtime.

---

## Adding a New Command

To add a new command that needs environment validation:

1. Define a new tuple in `_env.py`:
   ```python
   REQUIRED_FOR_MY_NEW_COMMAND = ("DATABASE_URL", "MY_SPECIAL_VAR")
   ```

2. In your command function, call the guards:
   ```python
   def run(...):
       env = require_dotenv()
       check_required_vars(env, *REQUIRED_FOR_MY_NEW_COMMAND)
       # ... your logic
   ```

3. That's it. If a required var is missing, the command exits with a clear error.

If your command doesn't need strict validation (e.g., `etherion status` is informative even without `.env`), use `load_env()` instead of `require_dotenv()`.

---

## Real-World Example: The `.env` to Production Pipeline

Local development:

```bash
# .env in the repo (git-ignored)
DATABASE_URL=postgresql://user:pass@localhost:5432/etherion
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=my_local_secret_key_here
SECRET_KEY=another_local_secret
```

```bash
etherion serve  # Works, uses .env
```

Production (Vault-injected):

```bash
# No .env file; systemd passes env vars from Vault Agent
export DATABASE_URL="postgresql://user:vault-injected@prod.example.com:5432/etherion"
export REDIS_URL="redis://prod-redis.internal:6379/0"
export JWT_SECRET_KEY="vault-injected-secret-key"
export SECRET_KEY="vault-injected-secret"

etherion serve  # Works, reads from os.environ
```

CI/CD pipeline:

```bash
# No .env file; CI system exports secrets
export DATABASE_URL="postgresql://ci_user:$DB_PASSWORD@db.ci:5432/test_etherion"
export REDIS_URL="redis://redis.ci:6379/0"
export JWT_SECRET_KEY="$CI_JWT_SECRET"
export SECRET_KEY="$CI_SECRET"

etherion migrate  # Works, reads from env vars
etherion serve --port 9000  # Works, reads from env vars
```

The validation layer is agnostic to the source: `.env` file, shell export, or systemd environment file. The same code path works everywhere.

---

## Debugging Validation Issues

If you're having trouble with environment variables, use `etherion where` to see what's currently set:

```bash
etherion where
# Shows Configuration Summary section with all env vars from .env + os.environ
```

Check if a specific variable is set:

```bash
grep DATABASE_URL .env
# or
echo $DATABASE_URL
```

Remember that `check_required_vars` checks both `.env` and `os.environ`, so make sure you're looking in both places.
