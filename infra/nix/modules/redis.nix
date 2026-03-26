{ config, pkgs, ... }:

{
  services.redis.servers.etherion = {
    enable = true;
    port = 6379;
    bind = "127.0.0.1 ::1";
    save = [ ];  # disable AOF for pure cache use
    maxmemory = "512mb";
    maxmemoryPolicy = "allkeys-lru";
  };

  networking.firewall.allowedTCPPorts = [ 6379 ];
}
