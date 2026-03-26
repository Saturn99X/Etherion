{ config, pkgs, ... }:

{
  systemd.services.etherion-beat = {
    description = "Etherion Celery Beat Scheduler";
    after = [ "network.target" "redis.service" "etherion-worker.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      ExecStart = "/opt/etherion/venv/bin/etherion worker beat";
      EnvironmentFile = "/etc/etherion/.env";
      User = "etherion";
      Group = "etherion";
      WorkingDirectory = "/opt/etherion";
      Restart = "always";
      RestartSec = "10s";
    };
  };
}
