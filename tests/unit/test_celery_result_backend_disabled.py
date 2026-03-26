import importlib
import os


def test_celery_does_not_require_result_backend_by_default(monkeypatch):
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")

    mod = importlib.import_module("src.core.celery")
    importlib.reload(mod)

    assert mod.CELERY_RESULT_BACKEND == "cache+memory://"
    assert mod.CELERY_BACKEND_FOR_APP == "cache+memory://"


def test_get_task_status_safe_without_result_backend(monkeypatch):
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

    mod = importlib.import_module("src.core.celery")
    importlib.reload(mod)

    assert mod.CELERY_RESULT_BACKEND is None
    assert mod.CELERY_BACKEND_FOR_APP == "disabled://"

    status = mod.get_task_status("abc")
    assert status["task_id"] == "abc"
    assert status["status"] == "UNKNOWN"
    assert status["ready"] is False


def test_prod_style_result_backend_is_disabled_even_if_set(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "rediss://localhost:6379/1")
    monkeypatch.delenv("CELERY_FORCE_RESULT_BACKEND", raising=False)

    mod = importlib.import_module("src.core.celery")
    importlib.reload(mod)

    assert mod.CELERY_RESULT_BACKEND is None
    assert mod.CELERY_BACKEND_FOR_APP == "disabled://"


def test_prod_style_result_backend_can_be_forced(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "rediss://localhost:6379/0")
    monkeypatch.setenv("CELERY_FORCE_RESULT_BACKEND", "true")

    mod = importlib.import_module("src.core.celery")
    importlib.reload(mod)

    assert mod.CELERY_RESULT_BACKEND == "rediss://localhost:6379/0"
    assert mod.CELERY_BACKEND_FOR_APP == "rediss://localhost:6379/0"
