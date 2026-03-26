# Policy for the Etherion application (read-only access to its secrets)
path "secret/data/etherion/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/etherion/*" {
  capabilities = ["read", "list"]
}
