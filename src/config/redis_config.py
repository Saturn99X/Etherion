from dataclasses import dataclass, field
import os


@dataclass
class RedisConfig:
    url: str = "redis://localhost:6379/0"
    max_connections: int = 20
    ssl_cert_reqs: str = "required"
    cluster_enabled: bool = False
    cluster_nodes: list = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "RedisConfig":
        url = os.getenv("ETHERION_REDIS_URL") or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
        cluster_nodes_raw = os.getenv("REDIS_CLUSTER_NODES", "")
        return cls(
            url=url,
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20")),
            ssl_cert_reqs=os.getenv("REDIS_SSL_CERT_REQS", "required"),
            cluster_enabled=os.getenv("REDIS_CLUSTER_ENABLED", "").lower() in ("1", "true", "yes"),
            cluster_nodes=[n.strip() for n in cluster_nodes_raw.split(",") if n.strip()],
        )
