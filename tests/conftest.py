# Ensure repository root is on sys.path for imports like `src.*` and `tests.*`
import sys
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Use a shared SQLite file across sync/async engines and Celery tasks for E2E (absolute path)
DB_FILE = (ROOT / "e2e.db").resolve()
# Absolute SQLite paths require four slashes after scheme and no extra leading slash in the path part
DB_POSIX = DB_FILE.as_posix().lstrip("/")

# Reset DB on each test session run to ensure a clean slate and avoid IntegrityError on reruns
if os.getenv("E2E_DB_RESET", "1") != "0":
    try:
        os.remove(DB_FILE)
    except FileNotFoundError:
        pass
os.environ.setdefault("DATABASE_URL", f"sqlite:////{DB_POSIX}")
# Also set the async URL explicitly to preserve exact path
os.environ.setdefault("ASYNC_DATABASE_URL", f"sqlite+aiosqlite:////{DB_POSIX}")

# Silence GCP logging in tests to avoid permission errors and event loop warnings
os.environ.setdefault("DISABLE_GCP_LOGGING", "1")

# Isolate environment and reset singletons per test to avoid cross-test interference
import pytest


@pytest.fixture(autouse=True)
def _isolate_env_and_singletons(monkeypatch):
    import src.core.caching as caching_mod
    import src.core.redis as redis_mod

    # Snapshot environment
    original_env = os.environ.copy()

    # Reset singletons before test starts
    try:
        monkeypatch.setattr(caching_mod, "_cache_manager", None, raising=False)
    except Exception:
        pass
    try:
        monkeypatch.setattr(redis_mod, "_redis_client", None, raising=False)
    except Exception:
        pass

    # Conditionally disable Vertex-dependent tests if IAM not guaranteed
    # Skip only Pillar04's Discovery Engine validation unless explicitly forced
    try:
        current = os.environ.get("PYTEST_CURRENT_TEST", "")
        force_vertex = os.environ.get("FORCE_VERTEX_TESTS", "0").lower() in ("1", "true", "yes")
        if ("tests/e2e/test_pillar04_memory_e2e.py" in current) and not force_vertex:
            monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    except Exception:
        pass

    yield

    # Restore environment variables exactly
    for k in list(os.environ.keys()):
        if k not in original_env:
            monkeypatch.delenv(k, raising=False)
    for k, v in original_env.items():
        os.environ[k] = v

    # Reset singletons again to ensure no state leaks to next test
    try:
        monkeypatch.setattr(caching_mod, "_cache_manager", None, raising=False)
    except Exception:
        pass
    try:
        monkeypatch.setattr(redis_mod, "_redis_client", None, raising=False)
    except Exception:
        pass
