# HAProxy Configuration

Routes traffic to:
- **Port 80**: Etherion API (round-robin across API nodes)
- **Port 5000**: PostgreSQL primary (via Patroni health check on :8008)
- **Port 5001**: PostgreSQL read-only replicas
- **Port 8404**: HAProxy stats page

Patroni exposes a REST API on port 8008:
- `GET /primary` → 200 only on primary
- `GET /replica` → 200 only on replicas
- `GET /health` → 200 on any healthy node
