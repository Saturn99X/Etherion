{ config, pkgs, ... }:

{
  services.haproxy = {
    enable = true;
    config = builtins.readFile ../../../haproxy/haproxy.cfg;
  };

  networking.firewall.allowedTCPPorts = [ 5000 8404 ];
}
