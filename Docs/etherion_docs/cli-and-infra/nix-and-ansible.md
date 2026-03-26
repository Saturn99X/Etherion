# Deployment: NixOS Modules and Ansible Playbooks

This document walks through how Etherion is deployed to production using NixOS modules and Ansible playbooks. It's a practical guide: here's what the files look like, what they do, and how to extend them.

## File Structure

After running `etherion init --mode nix`, your project has:

```
your-etherion-deployment/
├── .env.example                  # Reference env vars
├── alembic.ini                   # Database migration config
├── alembic/versions/             # Migration files
├── nix/
│   ├── flake.nix                 # Nix flake (dependency management)
│   ├── configuration.nix         # Top-level NixOS config
│   ├── services/
│   │   ├── etherion-api.nix      # API server systemd unit
│   │   ├── etherion-worker.nix   # Celery worker systemd unit
│   │   └── etherion-beat.nix     # Celery beat systemd unit
│   ├── roles/
│   │   ├── postgres.nix          # PostgreSQL setup
│   │   ├── redis.nix             # Redis setup
│   │   ├── minio.nix             # MinIO object storage setup
│   │   └── vault-agent.nix       # Vault Agent setup
│   └── vault/
│       └── etherion.tpl          # Template for env file rendering
└── ansible/
    ├── inventory.yml             # Host groups (prod, staging, dev)
    ├── site.yml                  # Main provisioning playbook
    ├── deploy-app.yml            # App update and restart playbook
    ├── migrate.yml               # Database migration playbook
    ├── group_vars/
    │   ├── all.yml               # Variables applied to all hosts
    │   ├── etherion-prod.yml     # Production-specific variables
    │   └── etherion-staging.yml  # Staging-specific variables
    └── roles/
        ├── bootstrap/            # Initial server setup
        ├── nix-build/            # Build and apply NixOS config
        ├── app-deploy/           # Deploy app code
        └── migrations/           # Run migrations
```

## NixOS Modules

### `configuration.nix`: The Main Configuration

This file imports all other Nix modules and defines system-wide settings.

```nix
{ config, pkgs, lib, ... }:
{
  imports = [
    ./roles/postgres.nix
    ./roles/redis.nix
    ./roles/minio.nix
    ./roles/vault-agent.nix
    ./services/etherion-api.nix
    ./services/etherion-worker.nix
    ./services/etherion-beat.nix
  ];

  # System-wide settings
  networking.hostName = "etherion-prod-01";
  networking.firewall.allowedTCPPorts = [ 22 80 443 8080 9000 ];

  # User for running Etherion services
  users.users.etherion = {
    isSystemUser = true;
    group = "etherion";
    home = "/var/lib/etherion";
    createHome = true;
  };
  users.groups.etherion = { };

  # Timezone
  time.timeZone = "UTC";

  # Packages available globally
  environment.systemPackages = with pkgs; [
    git
    python39
    postgresql_14
    redis
  ];

  # journald configuration (log retention)
  services.journald.extraConfig = ''
    SystemMaxUse=1G
    MaxRetentionSec=30d
  '';
}
```

Key sections:

- **Imports**: Pull in specialized modules (database, worker, etc.)
- **Networking**: Firewall rules and hostname
- **Users**: Create the `etherion` user that runs services
- **Packages**: Global tools and runtime dependencies
- **Logging**: Configure systemd journal retention

### `roles/postgres.nix`: PostgreSQL Service

```nix
{ config, pkgs, ... }:
{
  services.postgresql = {
    enable = true;
    package = pkgs.postgresql_14;
    port = 5432;

    # Initial database setup
    initialScript = pkgs.writeText "init.sql" ''
      CREATE DATABASE etherion;
      CREATE USER etherion WITH PASSWORD 'PLACEHOLDER_DB_PASSWORD';
      GRANT ALL PRIVILEGES ON DATABASE etherion TO etherion;
      GRANT ALL ON SCHEMA public TO etherion;
    '';

    # PostgreSQL tuning for production
    settings = {
      max_connections = 200;
      shared_buffers = "256MB";
      effective_cache_size = "1GB";
      work_mem = "4MB";
      random_page_cost = 1.1;  # SSD-optimized
      log_min_duration_statement = 1000;  # Log queries slower than 1 second
    };
  };

  # Backup systemd service (daily backups)
  systemd.services.postgres-backup = {
    description = "PostgreSQL Daily Backup";
    after = [ "postgresql.service" ];
    startAt = "03:00";  # 3 AM daily
    serviceConfig = {
      User = "postgres";
      ExecStart = "${pkgs.postgresql_14}/bin/pg_dump etherion > /var/backups/etherion-$(date +%Y%m%d).sql";
      Type = "oneshot";
    };
  };
}
```

Key features:

- **Initial database creation**: The `initialScript` runs once on first boot to create the database and user
- **Tuning**: Production PostgreSQL settings for performance
- **Logging**: Queries slower than 1 second are logged for analysis
- **Backups**: Systemd timer triggers daily backups

**In production**, you'd extract the password from Vault:

```nix
initialScript = pkgs.writeText "init.sql" ''
  CREATE DATABASE etherion;
  CREATE USER etherion WITH PASSWORD '${config.etherion.db.password}';
  ...
''
```

And pass `config.etherion.db.password` from Ansible (see `ansible/group_vars/` below).

### `services/etherion-api.nix`: API Server Systemd Unit

```nix
{ config, pkgs, lib, ... }:
{
  systemd.services.etherion-api = {
    description = "Etherion AI API Server";
    documentation = [ "https://docs.etherion.dev" ];
    after = [
      "network-online.target"
      "postgresql.service"
      "redis.service"
      "vault-agent.service"
    ];
    wants = [ "network-online.target" ];
    wantedBy = [ "multi-user.target" ];

    # Service configuration
    serviceConfig = {
      Type = "notify";  # Supports systemd readiness notification
      User = "etherion";
      Group = "etherion";
      WorkingDirectory = "/opt/etherion";

      # Load secrets from Vault Agent
      EnvironmentFile = "/run/etherion/env.vault";

      # Start command
      ExecStart = "${pkgs.python39}/bin/python -m uvicorn src.etherion_ai.app:app --host 0.0.0.0 --port 8080";

      # Restart policy
      Restart = "always";
      RestartSec = 5;
      StartLimitInterval = 30;
      StartLimitBurst = 10;

      # Security
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectHome = true;
      ProtectSystem = "strict";
      ReadWritePaths = [ "/var/lib/etherion" "/run/etherion" ];

      # Process management
      KillMode = "mixed";
      KillSignal = "SIGTERM";
      TimeoutStopSec = 10;
    };

    # Pre-start checks
    preStart = ''
      # Wait for database
      ${pkgs.postgresql_14}/bin/pg_isready -h localhost -U etherion -d etherion || exit 1

      # Wait for Redis
      ${pkgs.redis}/bin/redis-cli -u "$REDIS_URL" ping >/dev/null 2>&1 || exit 1
    '';

    # Post-start check (healthcheck)
    postStart = ''
      sleep 2
      ${pkgs.curl}/bin/curl -f http://localhost:8080/health || systemctl stop etherion-api
    '';
  };

  # User and directories
  users.users.etherion.home = "/var/lib/etherion";
  systemd.tmpfiles.rules = [
    "d /run/etherion 0700 etherion etherion - -"
    "d /var/lib/etherion 0700 etherion etherion - -"
  ];
}
```

Key features:

- **Dependencies**: `after` ensures PostgreSQL and Redis are running before the API starts
- **Environment files**: `EnvironmentFile` loads secrets injected by Vault Agent
- **Security**: `PrivateTmp`, `ProtectHome`, `ProtectSystem` isolate the process
- **Restart policy**: Restarts up to 10 times within 30 seconds; if it keeps failing, stays stopped
- **Pre-start checks**: Validates that the database and Redis are reachable before starting
- **Post-start check**: Pings the `/health` endpoint; if it fails, stops the service

### `services/etherion-worker.nix` and `etherion-beat.nix`

Similar structure to the API unit, but:

```nix
systemd.services.etherion-worker = {
  description = "Etherion Celery Worker";
  after = [ "network-online.target" "redis.service" "postgresql.service" ];
  wantedBy = [ "multi-user.target" ];

  serviceConfig = {
    User = "etherion";
    WorkingDirectory = "/opt/etherion";
    EnvironmentFile = "/run/etherion/env.vault";
    ExecStart = "${pkgs.python39}/bin/python -m celery -A src.core.celery.celery_app worker --loglevel=info --concurrency=4 -Q celery,worker-artifacts";
    Restart = "always";
    RestartSec = 5;
  };
};

systemd.services.etherion-beat = {
  description = "Etherion Celery Beat Scheduler";
  after = [ "network-online.target" "redis.service" "postgresql.service" ];
  wantedBy = [ "multi-user.target" ];

  serviceConfig = {
    User = "etherion";
    WorkingDirectory = "/opt/etherion";
    EnvironmentFile = "/run/etherion/env.vault";
    ExecStart = "${pkgs.python39}/bin/python -m celery -A src.core.celery.celery_app beat --loglevel=info";
    Restart = "always";
    RestartSec = 5;
  };
};
```

## Vault Agent: Injecting Secrets at Runtime

Vault Agent runs on the host and periodically fetches secrets from Vault, rendering them into environment files that systemd units read before starting services.

### `roles/vault-agent.nix`: Setup

```nix
{ config, pkgs, ... }:
{
  systemd.services.vault-agent = {
    description = "Vault Agent";
    after = [ "network-online.target" ];
    wantedBy = [ "multi-user.target" ];

    serviceConfig = {
      Type = "notify";
      ExecStart = "${pkgs.vault}/bin/vault agent -config /etc/vault/agent.hcl";
      Restart = "always";
      RestartSec = 10;
      User = "root";  # Vault Agent needs root to write /run/etherion
    };
  };

  # Copy Vault Agent config (populated by Ansible)
  environment.etc."vault/agent.hcl".text = builtins.readFile ./vault-agent.hcl;
  environment.etc."vault/etherion.tpl".text = builtins.readFile ./vault/etherion.tpl;
}
```

### Vault Agent Config (populated by Ansible)

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
      path = "/var/run/vault-token"
      mode = 0600
    }
  }
}

template {
  source      = "/etc/vault/etherion.tpl"
  destination = "/run/etherion/env.vault"
  command     = "systemctl restart etherion-api etherion-worker etherion-beat"
  perms       = "0600"
  owner       = "root"
  group       = "root"
}

cache {
  use_auto_auth_token = true
}
```

### Vault Template

```
# /etc/vault/etherion.tpl
DATABASE_URL={{ with secret "secret/etherion/database" }}{{ .Data.data.url }}{{ end }}
REDIS_URL={{ with secret "secret/etherion/redis" }}{{ .Data.data.url }}{{ end }}
JWT_SECRET_KEY={{ with secret "secret/etherion/secrets" }}{{ .Data.data.jwt_key }}{{ end }}
SECRET_KEY={{ with secret "secret/etherion/secrets" }}{{ .Data.data.secret_key }}{{ end }}
MINIO_ROOT_USER={{ with secret "secret/etherion/minio" }}{{ .Data.data.root_user }}{{ end }}
MINIO_ROOT_PASSWORD={{ with secret "secret/etherion/minio" }}{{ .Data.data.root_password }}{{ end }}
```

When Vault Agent starts, it:
1. Authenticates to Vault using AppRole credentials (stored on the server)
2. Fetches secrets from Vault
3. Renders the template into `/run/etherion/env.vault`
4. Systemd units load that file before starting services

If a secret is rotated in Vault, Vault Agent detects the change and restarts the services automatically.

## Ansible Playbooks

### `inventory.yml`: Host Definition

```yaml
all:
  children:
    etherion-prod:
      hosts:
        prod-01:
          ansible_host: 10.0.1.10
          ansible_user: root
        prod-02:
          ansible_host: 10.0.1.11
          ansible_user: root
      vars:
        environment: production
        vault_addr: "https://vault.internal:8200"
        vault_role_id: "{{ lookup('file', '.vault/prod-role-id') }}"

    etherion-staging:
      hosts:
        staging-01:
          ansible_host: 10.1.1.10
          ansible_user: root
      vars:
        environment: staging
        vault_addr: "https://vault.internal:8200"
```

### `site.yml`: Full Server Provisioning

```yaml
---
- name: Bootstrap Etherion servers
  hosts: all
  become: yes
  roles:
    - bootstrap  # SSH hardening, packages, firewall
    - nix-build  # Deploy NixOS config and rebuild
    - app-deploy # Clone app repo, run migrations
  vars:
    nix_flake_repo: "https://github.com/mycompany/etherion.git"
    nix_flake_ref: "main"
```

### `bootstrap/main.yml` (Role)

```yaml
---
- name: Update system packages
  apt:
    update_cache: yes

- name: Install NixOS (from minimal image)
  shell: |
    curl -L https://nixos.org/nix/install | sh

- name: Create app directory
  file:
    path: /opt/etherion
    state: directory
    mode: "0755"

- name: Configure firewall
  firewalld:
    port: "{{ item }}"
    permanent: yes
    state: enabled
  loop:
    - "22/tcp"
    - "80/tcp"
    - "443/tcp"
    - "8080/tcp"
    - "9000/tcp"  # MinIO
```

### `deploy-app.yml`: Update Deployment

```yaml
---
- name: Deploy Etherion app updates
  hosts: etherion-prod
  become: yes
  tasks:
    - name: Pull latest code
      git:
        repo: "{{ nix_flake_repo }}"
        dest: /opt/etherion
        version: "{{ app_version | default('main') }}"
        update: yes

    - name: Run migrations
      shell: cd /opt/etherion && etherion migrate
      environment:
        DATABASE_URL: "{{ vault_db_url }}"

    - name: Restart services
      systemd:
        name: "{{ item }}"
        state: restarted
        daemon_reload: yes
      loop:
        - etherion-api
        - etherion-worker
        - etherion-beat

    - name: Wait for API to be healthy
      uri:
        url: "http://localhost:8080/health"
        method: GET
        status_code: 200
      retries: 30
      delay: 1
      register: result
      until: result.status == 200
```

Running an update:

```bash
# Update to a specific version
ansible-playbook deploy-app.yml -e "app_version=v1.2.3"

# Or to the latest main branch
ansible-playbook deploy-app.yml
```

### `migrate.yml`: Database Migrations

```yaml
---
- name: Run database migrations
  hosts: etherion-prod
  become: yes
  tasks:
    - name: Run Alembic migrations
      shell: cd /opt/etherion && etherion migrate head
      environment:
        DATABASE_URL: "{{ vault_db_url }}"
      register: migrate_result

    - name: Show migration result
      debug:
        msg: "{{ migrate_result.stdout }}"
```

## Deployment Workflow in Practice

### Initial deployment to a new server

```bash
# 1. Create an Ubuntu or NixOS instance on your infrastructure

# 2. Provision with Ansible
ansible-playbook site.yml -i inventory.yml -l etherion-prod

# Ansible:
#   - Installs Nix
#   - Copies NixOS config to the server
#   - Builds and switches to the new config
#   - Creates PostgreSQL, Redis, MinIO services
#   - Sets up Vault Agent for secrets injection
#   - Clones the Etherion app
#   - Runs migrations
#   - Starts etherion-api, etherion-worker, etherion-beat

# 3. Verify
ansible -i inventory.yml -m shell -a "systemctl status etherion-api" etherion-prod
```

### Rolling app update

```bash
# 1. Push changes to the app repo
git push origin main

# 2. Deploy to prod
ansible-playbook deploy-app.yml -i inventory.yml -l etherion-prod

# 3. Ansible pulls the new code, runs migrations, restarts services
# 4. HAProxy keeps routing traffic during the restart (no downtime)
```

### Scaling horizontally

```bash
# 1. Add new servers to inventory.yml
etherion-prod:
  hosts:
    prod-03:
      ansible_host: 10.0.1.12
      ansible_user: root

# 2. Provision the new server
ansible-playbook site.yml -i inventory.yml -l etherion-prod

# 3. HAProxy automatically routes traffic to the new instance
```

## Troubleshooting

Check Vault Agent:

```bash
systemctl status vault-agent
journalctl -u vault-agent -f
```

Check service logs:

```bash
journalctl -u etherion-api -f
journalctl -u etherion-worker -f
```

Validate NixOS config syntax:

```bash
nix flake check
```

Run Ansible in check mode (dry-run):

```bash
ansible-playbook deploy-app.yml --check
```

## Summary

The deployment system is:

- **Declarative** (NixOS modules describe desired state)
- **Idempotent** (Ansible playbooks are safe to run repeatedly)
- **Auditable** (all configs are in version control)
- **Automated** (Vault Agent handles secrets rotation)

This is production-grade infrastructure that scales from 1 server to many, with minimal operational overhead.
