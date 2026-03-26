# The Bare-Metal Stack: NixOS, Ansible, Systemd, and Vault

Etherion's production infrastructure is deployed on bare metal (physical servers or VMs), not Kubernetes or container orchestration. This document explains why, what the stack looks like, and how the pieces fit together.

## Why Bare Metal, Not Kubernetes?

Many platforms choose Kubernetes for its declarative model, horizontal scaling, and self-healing. But Kubernetes adds complexity: you need to manage a control plane, learn YAML manifests, understand network policies, tune resource requests, and debug pod scheduling issues. It's powerful, but overkill for platforms that don't need to scale to thousands of nodes or manage multi-cloud deployments.

Etherion's design philosophy is different: keep the infrastructure simple, predictable, and auditable. Here's why we chose bare metal:

1. **Declarative OS state** via NixOS, not imperative shell scripts
2. **SSH-based provisioning** via Ansible, not API-based orchestration
3. **Process supervision** via systemd, a standard Linux init system
4. **Configuration drift prevention** via version-controlled infrastructure code
5. **Secrets injection** via HashiCorp Vault, not Kubernetes secrets

This stack is familiar to Unix/Linux operators, has decades of battle-testing, and doesn't require learning a new paradigm.

## The Stack Components

### 1. NixOS: Declarative Operating System

NixOS is a Linux distribution built on the Nix package manager, where the entire OS configuration is declarative. You write a Nix module that describes what packages are installed, what services run, what firewall rules apply, etc. When you change the module and rebuild, NixOS deterministically applies those changes.

**Example NixOS module for Etherion**:

```nix
{
  services.postgresql = {
    enable = true;
    package = pkgs.postgresql_14;
    initialScript = pkgs.writeText "init.sql" ''
      CREATE DATABASE etherion;
      CREATE USER etherion WITH PASSWORD 'secure_password';
      GRANT ALL PRIVILEGES ON DATABASE etherion TO etherion;
    '';
  };

  services.redis = {
    enable = true;
    port = 6379;
    requirePass = "redis_password";
  };

  systemd.services.etherion-api = {
    description = "Etherion API Server";
    after = [ "network.target" "postgresql.service" "redis.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      User = "etherion";
      WorkingDirectory = "/opt/etherion";
      ExecStart = "${pkgs.python39}/bin/python -m uvicorn src.etherion_ai.app:app --host 0.0.0.0 --port 8080";
      Restart = "always";
      RestartSec = 5;
    };
  };

  networking.firewall.allowedTCPPorts = [ 22 80 443 8080 ];
  security.acme.certs = {
    "etherion.example.com" = {
      email = "admin@example.com";
      dnsProvider = "route53";
    };
  };
}
```

Key benefits:

- **No config drift**: The OS always matches the Nix module. If someone SSHes in and changes `/etc/postgresql/postgresql.conf`, the next NixOS rebuild will revert it.
- **Reproducible builds**: The same Nix code produces the same OS on any machine (down to the bit).
- **Atomic upgrades**: NixOS builds the new OS configuration and then atomically switches to it. If something breaks, you can roll back to the previous generation instantly.
- **Version control**: Check in the Nix modules and version them like code. You can see the history of infrastructure changes in git.

### 2. Ansible: Fleet Provisioning and Updates

Ansible is an agentless configuration management tool: you describe desired state in YAML playbooks, and Ansible applies them via SSH to multiple machines. Unlike configuration drift, Ansible is imperative: it runs tasks in order and reports what changed.

**Etherion deployment workflow**:

1. New server boots with a minimal NixOS image
2. You run `ansible-playbook site.yml` from your laptop
3. Ansible:
   - Copies the NixOS Nix modules to the server
   - Builds and switches to the new NixOS configuration
   - Downloads the Etherion application code from git
   - Runs database migrations
   - Starts systemd services
4. In 5 minutes, the server is fully provisioned and running Etherion

**Example Ansible playbook**:

```yaml
- hosts: etherion-servers
  become: yes
  tasks:
    - name: Copy NixOS configuration
      copy:
        src: ./nix/
        dest: /etc/nixos/modules/etherion/

    - name: Rebuild NixOS
      shell: nixos-rebuild switch

    - name: Clone Etherion repository
      git:
        repo: https://github.com/mycompany/etherion.git
        dest: /opt/etherion
        version: "{{ app_version }}"

    - name: Run migrations
      shell: cd /opt/etherion && etherion migrate
      environment:
        DATABASE_URL: "{{ db_url }}"

    - name: Start API and workers
      systemd:
        name: "{{ item }}"
        state: started
        enabled: yes
      loop:
        - etherion-api
        - etherion-worker
        - etherion-beat
```

Key benefits:

- **Idempotent**: Running the playbook twice is safe; Ansible will skip tasks that are already satisfied.
- **Human-readable**: YAML syntax is clearer than shell scripts; a new operator can understand what's happening.
- **Multi-host**: Deploy to 10 servers by changing `hosts: etherion-servers` to target a group. Ansible fans out SSH connections and applies the playbook in parallel.

### 3. Systemd: Process Supervision

systemd is the Linux init system (PID 1 on most modern distributions). It manages services, handles dependencies, restarts crashed processes, and captures logs. NixOS uses systemd extensively.

**Example systemd unit for the Etherion API server**:

```ini
[Unit]
Description=Etherion API Server
After=network.target postgresql.service redis.service vault-agent.service
Wants=postgresql.service redis.service vault-agent.service

[Service]
Type=simple
User=etherion
WorkingDirectory=/opt/etherion

# Load secrets from Vault Agent (injected as env file)
EnvironmentFile=/etc/etherion/env.vault

# Start the service
ExecStart=/opt/etherion/venv/bin/python -m uvicorn src.etherion_ai.app:app --host 0.0.0.0 --port 8080

# Restart policy: if it crashes, restart after 5 seconds
Restart=always
RestartSec=5

# Process management
TimeoutStopSec=10
KillMode=mixed

[Install]
WantedBy=multi-user.target
```

Key benefits:

- **Automatic restart**: If the API process crashes, systemd restarts it after 5 seconds. No manual intervention needed.
- **Dependency management**: The `After=` directive ensures the service starts after PostgreSQL and Redis are running.
- **Logging**: systemd captures all process output and stores it in the journal. View logs with `journalctl -u etherion-api -f`.
- **Clean shutdown**: If you update the app, `systemctl restart etherion-api` gracefully stops the old process and starts the new one.

### 4. HAProxy: Load Balancing (Optional)

For multi-instance deployments, HAProxy sits in front of multiple Etherion API servers and distributes traffic. It's configured in text files and can be reloaded without restarting connections.

**Example HAProxy config**:

```
global
    log stdout local0
    maxconn 4096

defaults
    log global
    mode http
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms

frontend etherion_api
    bind *:443 ssl crt /etc/ssl/certs/etherion.pem
    default_backend api_servers

backend api_servers
    balance roundrobin
    server api1 10.0.1.10:8080 check
    server api2 10.0.1.11:8080 check
    server api3 10.0.1.12:8080 check
```

### 5. Vault: Secrets Management

HashiCorp Vault is a centralized secrets management system. Instead of storing database passwords and API keys in `.env` files scattered across servers, you store them in Vault and inject them into the environment at runtime.

**How Vault works with Etherion**:

1. Secrets are stored in Vault: `secret/etherion/prod/database_url`, `secret/etherion/prod/jwt_secret_key`, etc.
2. Each server runs Vault Agent (a local daemon that authenticates to Vault)
3. Vault Agent periodically retrieves secrets and writes them to a file: `/etc/etherion/env.vault`
4. systemd loads that file as `EnvironmentFile` before starting the API process
5. The CLI reads the secrets from the environment, same as if they were in `.env`

**Example Vault Agent config**:

```hcl
pid_file = "/var/run/vault-agent.pid"

vault {
  address = "https://vault.internal:8200"
}

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path   = "/etc/vault/role-id"
      secret_id_file_path = "/etc/vault/secret-id"
    }
  }

  sink "file" {
    config = {
      path = "/etc/vault/token"
    }
  }
}

template {
  source      = "/etc/vault/etherion.tpl"
  destination = "/etc/etherion/env.vault"
  command     = "systemctl restart etherion-api"
  perms       = "0600"
}
```

**Example template** (`etherion.tpl`):

```
DATABASE_URL={{ with secret "secret/etherion/prod/database" }}{{ .Data.data.url }}{{ end }}
REDIS_URL={{ with secret "secret/etherion/prod/redis" }}{{ .Data.data.url }}{{ end }}
JWT_SECRET_KEY={{ with secret "secret/etherion/prod/secrets" }}{{ .Data.data.jwt_key }}{{ end }}
SECRET_KEY={{ with secret "secret/etherion/prod/secrets" }}{{ .Data.data.secret_key }}{{ end }}
```

When a secret is rotated in Vault, Vault Agent updates the file and restarts the service automatically.

Key benefits:

- **Centralized secrets**: One source of truth for all credentials.
- **Audit trail**: Vault logs every secret access.
- **Rotation**: Update a secret in Vault; it's pushed to all servers automatically.
- **Least privilege**: Services authenticate with Vault using AppRole tokens that grant access only to their specific secrets.

## How They Work Together

A typical deployment flow:

1. **Infrastructure as Code**: Nix modules describe the OS (what packages, what services, what firewall rules).
2. **Provisioning**: Ansible playbooks deploy those modules to servers, clone the app code, and run migrations.
3. **Secrets**: Vault Agent injects secrets into environment files before systemd starts the services.
4. **Process Management**: systemd keeps the API and worker processes running, restarts them on crash, and manages dependencies.
5. **Logging**: All logs go to systemd journal; centralize them with a log forwarder (e.g., Promtail to Loki).
6. **Load Balancing**: HAProxy distributes requests across multiple API instances.

Example: Rolling app update

```bash
# Update the app version in Ansible inventory
ansible-inventory edit

# Run the deployment playbook
ansible-playbook deploy-app.yml

# Ansible:
#   - Pulls the new code from git on each server
#   - Runs migrations
#   - Restarts etherion-api and etherion-worker systemd units
#   - HAProxy notices the health checks still passing
#   - Traffic flows to the new version

# Old process stops after ~10 seconds
# New process starts with the new code
# No downtime
```

## Why Not Containers?

Docker and container orchestration solve different problems:

- **Containers shine when**: You have many isolated services, each with different dependencies, and you need to pack them densely on shared hardware.
- **Bare metal shines when**: You have a stable set of services (PostgreSQL, Redis, MinIO, Etherion), each with predictable resource needs, and you want to minimize operational complexity.

Etherion doesn't have 50 microservices. It has a few core services plus the application. NixOS + Ansible + systemd is less operational overhead than learning Kubernetes, and it's more predictable: no mysterious scheduling decisions, no networking plugins to debug, no container registry to manage.

That said, containers are useful for local development (hence `docker-compose.services.yml` for `etherion bootstrap --mode docker`), and they could be used in production if needed. The CLI supports both paths.

## Monitoring and Observability

With this stack, observability looks like:

- **Metrics**: Prometheus scrapes `/metrics` endpoints on the API and worker
- **Logs**: systemd journal → Promtail → Loki (or your centralized log store)
- **Traces**: API exports OpenTelemetry traces (if enabled)
- **Alerting**: Prometheus Alert Manager fires alerts on error rates, latency, or service down

Example alert rule:

```yaml
groups:
  - name: etherion
    rules:
      - alert: EtherionAPIDown
        expr: up{job="etherion-api"} == 0
        for: 1m
        annotations:
          summary: "Etherion API is down"
```

The `etherion status` command is your real-time health check; automation tools query it for synthetic monitoring.

## Summary

The bare-metal stack is purpose-built for operational simplicity:

- **NixOS** ensures the OS state is declarative and reproducible
- **Ansible** automates multi-server deployments via SSH
- **systemd** supervises processes and handles restarts
- **Vault** centralizes and rotates secrets
- **HAProxy** distributes traffic across instances

This is the production infrastructure for Etherion. It's not trendy, but it's reliable, auditable, and human-understandable.
