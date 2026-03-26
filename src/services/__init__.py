"""Lightweight services package initializer.

Avoid importing heavy submodules at import time to keep tests and tooling fast.
Import submodules directly where needed, e.g.:
    from src.services.bigquery_service import BigQueryService
"""

__all__: list[str] = []
