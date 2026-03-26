{ config, pkgs, ... }:

{
  services.postgresql = {
    enable = true;
    package = pkgs.postgresql_16;
    extraPlugins = with pkgs.postgresql_16.pkgs; [ pgvector ];
    enableTCPIP = true;
    authentication = pkgs.lib.mkOverride 10 ''
      local all all trust
      host all all 127.0.0.1/32 md5
      host all all ::1/128 md5
    '';
    initialScript = pkgs.writeText "etherion-init.sql" ''
      CREATE EXTENSION IF NOT EXISTS vector;
      CREATE USER etherion WITH PASSWORD 'etherion' CREATEDB;
      CREATE DATABASE etherion OWNER etherion;
    '';
    settings = {
      max_connections = 200;
      shared_buffers = "256MB";
      wal_level = "replica";
      max_wal_senders = 5;
    };
  };

  networking.firewall.allowedTCPPorts = [ 5432 ];
}
