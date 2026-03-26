{
  description = "Etherion bare-metal platform";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python311
            python311Packages.pip
            go_1_22
            ansible
            vault
            minio-client
            postgresql_16
            redis
            haproxy
            nginx
            frr
          ];
          shellHook = ''
            echo "Etherion dev shell ready"
            export VAULT_ADDR="http://localhost:8200"
          '';
        };
      }
    ) // {
      nixosModules = {
        etherion = { imports = [ ./modules/etherion-api.nix ./modules/etherion-worker.nix ./modules/etherion-beat.nix ]; };
        postgres = import ./modules/postgres.nix;
        redis = import ./modules/redis.nix;
        minio = import ./modules/minio.nix;
        vault = import ./modules/vault.nix;
        haproxy = import ./modules/haproxy.nix;
      };
    };
}
