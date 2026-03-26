{ config, pkgs, ... }:

{
  systemd.services.etherion-api = {
    description = "Etherion API (uvicorn)";
    after = [ "network.target" "postgresql.service" "redis.service" "minio.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      ExecStart = "/opt/etherion/venv/bin/etherion serve";
      EnvironmentFile = "/etc/etherion/.env";
      User = "etherion";
      Group = "etherion";
      WorkingDirectory = "/opt/etherion";
      Restart = "always";
      RestartSec = "5s";
      StandardOutput = "journal";
      StandardError = "journal";
    };
  };

  users.users.etherion = {
    isSystemUser = true;
    group = "etherion";
    home = "/opt/etherion";
  };
  users.groups.etherion = {};
}
