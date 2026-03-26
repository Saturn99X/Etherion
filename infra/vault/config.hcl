# Vault server configuration
# Dev mode: file storage, no TLS
# Production: replace with raft storage + TLS (see prod-node-01.nix)

storage "file" {
  path = "/var/lib/vault/data"
}

listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = 1
}

api_addr = "http://127.0.0.1:8200"
ui       = true

# Telemetry
telemetry {
  disable_hostname = true
}
