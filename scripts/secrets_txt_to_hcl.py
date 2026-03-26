#!/usr/bin/env python3
"""
Convert secrets.txt (export KEY=VALUE) into an HCL map suitable for the Terraform Cloud
variable 'secret_seed_values' (mark as Sensitive + HCL in TFC UI).

Usage:
  python3 scripts/secrets_txt_to_hcl.py > secret_seed_values.hcl
Then copy-paste the contents of secret_seed_values.hcl into the TFC variable 'secret_seed_values'.
"""
import re
import sys
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "secrets.txt"
if not src.exists():
    print("# secrets.txt not found at repo root", file=sys.stderr)
    sys.exit(1)

pairs = {}
for line in src.read_text(encoding="utf-8", errors="ignore").splitlines():
    line = line.strip()
    if not line or line.startswith('#') or not line.startswith('export '):
        continue
    try:
        k, v = line.split('=', 1)
    except ValueError:
        continue
    k = k.split()[1]
    pairs[k] = v

# Helper to pick first present value among several keys
pick = lambda *keys: next((pairs[k] for k in keys if k in pairs), None)

# Build mapping from desired GSM secret ids to values from secrets.txt
m = {}
# Core app secrets
m["app-secret-key"] = pick("SECRET_KEY", "APP_SECRET_KEY", "JWT_SECRET_KEY")
# OAuth
m["oauth-google-client-id"] = pairs.get("OAUTH_GOOGLE_CLIENT_ID")
m["oauth-google-client-secret"] = pairs.get("OAUTH_GOOGLE_CLIENT_SECRET")
m["oauth-github-client-id"] = pairs.get("OAUTH_GITHUB_CLIENT_ID")
m["oauth-github-client-secret"] = pairs.get("OAUTH_GITHUB_CLIENT_SECRET")
m["oauth-ms-client-id"] = pairs.get("OAUTH_MS_CLIENT_ID")
m["oauth-ms-client-secret"] = pairs.get("OAUTH_MS_CLIENT_SECRET")
m["ms365-tenant-id"] = pairs.get("MS365_TENANT_ID")
# Admin
m["etherion-admin-ingest-secret"] = pairs.get("ETHERION_ADMIN_INGEST_SECRET")
# Pricing and misc referenced by Terraform/services
for k in (
    "OAUTH_STATE_SECRET",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "BQ_PRICE_SLOT_PER_HOUR",
    "PRICE_PER_1K_INPUT_TOKENS",
    "PRICE_PER_1K_OUTPUT_TOKENS",
    "PRICE_PER_API_CALL",
    "PRICE_PER_MB_INBOUND",
    "PRICE_PER_MB_OUTBOUND",
    "PRICE_PER_MS_COMPUTE",
    "PRICING_CURRENCY",
    "VS_INDEX_FREE_GIB",
    "VS_INDEX_PRICE_PER_GIB_MONTH",
    "VS_PRICE_ADVANCED_ADDON_PER_1K_Q",
    "VS_PRICE_ENTERPRISE_PER_1K_Q",
    "VS_PRICE_STANDARD_PER_1K_Q",
    # Frontend public IDs (safe, but kept in GSM by policy)
    "NEXT_PUBLIC_GOOGLE_CLIENT_ID",
    "NEXT_PUBLIC_GITHUB_CLIENT_ID",
    "NEXT_PUBLIC_MICROSOFT_CLIENT_ID",
    "NEXT_PUBLIC_MICROSOFT_TENANT_ID",
):
    if k in pairs:
        m[k] = pairs[k]

# Emit only present entries, as an HCL map body
print("{")
for k, v in m.items():
    if not v:
        continue
    v = v.replace("\\", "\\\\").replace('"', '\\"')
    print(f"  {k} = \"{v}\"")
print("}")
