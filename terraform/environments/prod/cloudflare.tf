# Cloudflare DNS records management (gated by var.use_cloudflare)
# Requires CLOUDFLARE_API_TOKEN in environment or var.cloudflare_api_token via provider configuration.

# Note: Do not explicitly configure the provider. When Cloudflare is enabled,
# the provider will pick up credentials from environment variables (e.g., CLOUDFLARE_API_TOKEN).

// Cloudflare records are temporarily disabled to unblock plan/apply.
// TODO: Re-implement using provider v5 schema (data.cloudflare_zone with filter {} and cloudflare_record resources)
// and gate with `var.use_cloudflare` once token and zone are confirmed.
