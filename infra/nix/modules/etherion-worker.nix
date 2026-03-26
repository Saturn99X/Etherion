{ config, pkgs, ... }:

{
  systemd.services.etherion-worker = {
    description = "Etherion Celery Worker";
    after = [ "network.target" "redis.service" "postgresql.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      ExecStart = "/opt/etherion/venv/bin/etherion worker start";
      EnvironmentFile = "/etc/etherion/.env";
      User = "etherion";
      Group = "etherion";
      WorkingDirectory = "/opt/etherion";
      Restart = "always";
      RestartSec = "5s";
    };
  };

  systemd.services.etherion-worker-artifacts = {
    description = "Etherion Celery Worker (Artifacts Queue)";
    after = [ "network.target" "redis.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      ExecStart = "/opt/etherion/venv/bin/etherion worker start --queues=worker-artifacts --concurrency=2";
      EnvironmentFile = "/etc/etherion/.env";
      User = "etherion";
      Group = "etherion";
      WorkingDirectory = "/opt/etherion";
      Restart = "always";
      RestartSec = "5s";
    };
  };
}
