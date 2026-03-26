{ config, pkgs, lib, ... }:

{
  services.minio = {
    enable = true;
    dataDir = [ "/var/lib/minio/data" ];
    configDir = "/var/lib/minio/config";
    # Credentials are injected via Vault Agent into this file at runtime
    rootCredentialsFile = "/run/secrets/minio-credentials";
    listenAddress = ":9000";
    consoleAddress = ":9001";
  };

  # Create default buckets on first start
  systemd.services.minio-buckets = {
    description = "Create default MinIO buckets";
    after = [ "minio.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      export MINIO_ENDPOINT=http://localhost:9000
      ${pkgs.minio-client}/bin/mc alias set local http://localhost:9000 minioadmin minioadmin
      ${pkgs.minio-client}/bin/mc mb --ignore-existing local/etherion-artifacts
      ${pkgs.minio-client}/bin/mc mb --ignore-existing local/etherion-kb
      ${pkgs.minio-client}/bin/mc mb --ignore-existing local/etherion-media
    '';
  };

  networking.firewall.allowedTCPPorts = [ 9000 9001 ];
}
