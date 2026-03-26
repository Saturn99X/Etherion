import importlib


def _route_for_task(task_name: str):
    celery_mod = importlib.import_module("src.core.celery")
    app = getattr(celery_mod, "celery_app")
    router = app.amqp.router
    route = router.route({}, task_name, args=(), kwargs={})
    # route may contain kombu Queue object or raw name
    queue = route.get("queue")
    if hasattr(queue, "name"):
        queue = queue.name
    return queue


def test_admin_ingest_routes_to_worker_artifacts():
    assert _route_for_task("core.admin_ingest_gcs_uri") == "worker-artifacts"


def test_goal_orchestrator_routes_to_worker_agents():
    assert _route_for_task("goal_orchestrator.execute_goal") == "worker-agents"


def test_reconciliation_routes_to_worker_artifacts():
    assert _route_for_task("src.services.pricing.reconciliation.run_reconciliation") == "worker-artifacts"


def test_default_routes_to_worker_agents():
    # Non-explicit tasks should default to worker-agents
    assert _route_for_task("some.unknown.task") == "worker-agents"
