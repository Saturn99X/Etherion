# Etherion Bare-Metal Infrastructure

Replaces Terraform/GCP. Full sovereign stack.

## Layers

| Layer | Component | Role |
|-------|-----------|------|
| 0 | Matchbox (PXE) | Boot NixOS from network onto bare metal |
| 1 | NixOS | Declarative OS (zero config drift) |
| 2 | Ansible | Fleet management via SSH push |
| 3A | PostgreSQL 16 + pgvector + Patroni | Sovereign vector DB + HA |
| 3B | Redis Cluster | Celery broker + cache |
| 3C | MinIO | S3-compatible object storage |
| 4 | Systemd | Process manager (no Docker) |
| 5A | HAProxy | Local load balancer (Patroni VIP + app) |
| 5B | Nginx | Reverse proxy + TLS termination |
| 5C | FRRouting | BGP for global routing |
| 6 | HashiCorp Vault | Secrets injected into RAM |

## Quick Start (Local Dev)

```bash
nix develop infra/nix#default    # enter dev shell
ansible-playbook infra/ansible/playbooks/site.yml --check  # dry run
```
