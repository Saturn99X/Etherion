{ config, pkgs, modulesPath, ... }:

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
  networking.hostName = "etherion-dev";

  environment.systemPackages = with pkgs; [
    git vim curl wget htop
    python311 python311Packages.pip
  ];
}
