import os
from enum import Enum


class ExecutionMode(str, Enum):
    LOCAL = "local"
    DOCKER = "docker"
    BARE_METAL = "bare_metal"
    CLOUD_RUN = "cloud_run"


def detect() -> ExecutionMode:
    explicit = os.getenv("EXECUTION_MODE", "").lower()
    if explicit:
        try:
            return ExecutionMode(explicit)
        except ValueError:
            pass

    # Heuristics
    if os.path.exists("/.dockerenv"):
        return ExecutionMode.DOCKER
    if os.path.exists("/run/systemd/system") and not os.path.exists("/.dockerenv"):
        if os.getenv("GOOGLE_CLOUD_PROJECT"):
            return ExecutionMode.CLOUD_RUN
        return ExecutionMode.BARE_METAL
    return ExecutionMode.LOCAL
