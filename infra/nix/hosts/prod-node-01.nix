{ config, pkgs, ... }:

{
  imports = [
    ../modules/postgres.nix
    ../modules/redis.nix
    ../modules/minio.nix
    ../modules/vault.nix
    ../modules/haproxy.nix
    ../modules/etherion-api.nix
    ../modules/etherion-worker.nix
    ../modules/etherion-beat.nix
  ];

  system.stateVersion = "24.11";
  networking.hostName = "etherion-prod-01";

  # Production: use TLS for Vault
  services.vault.extraConfig = pkgs.lib.mkForce ''
    listener "tcp" {
      address       = "0.0.0.0:8200"
      tls_cert_file = "/etc/vault/tls/vault.crt"
      tls_key_file  = "/etc/vault/tls/vault.key"
    }
    api_addr    = "https://vault.etherion.internal:8200"
    cluster_addr = "https://vault.etherion.internal:8201"
    storage "raft" {
      path    = "/var/lib/vault/data"
      node_id = "node-01"
    }
    ui = true
  '';

  boot.loader.grub.enable = true;
  boot.loader.grub.device = "/dev/sda";
}
