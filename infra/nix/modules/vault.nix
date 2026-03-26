{ config, pkgs, ... }:

{
  services.vault = {
    enable = true;
    package = pkgs.vault;
    storageBackend = "file";
    storagePath = "/var/lib/vault/data";
    extraConfig = ''
      listener "tcp" {
        address     = "127.0.0.1:8200"
        tls_disable = 1
      }
      api_addr = "http://127.0.0.1:8200"
      ui = true
    '';
  };

  networking.firewall.allowedTCPPorts = [ 8200 ];
}
