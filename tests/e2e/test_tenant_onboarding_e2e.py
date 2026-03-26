import os
import json
import time
import random
import string
import asyncio
import httpx
import pytest

# E2E configuration
API_GRAPHQL_URL = os.getenv("E2E_API_GRAPHQL_URL", "https://api.etherionai.com/graphql")
PRIMARY_DOMAIN = os.getenv("E2E_PRIMARY_DOMAIN", "etherionai.com")


def _rand_suffix(n: int = 5) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _fake_ip(last_octet: int | None = None) -> str:
    # RFC 5737 TEST-NET-2 range 198.51.100.0/24 (non-routable)
    if last_octet is None:
        last_octet = random.randint(10, 250)
    return f"198.51.100.{last_octet}"


@pytest.mark.asyncio
async def test_create_tenant_e2e():
    ts = int(time.time())
    sub = f"e2e-{ts}-{_rand_suffix(4)}"
    admin_email = f"e2e+{sub}@example.com"
    name = f"E2E Org {sub}"

    query = """
    mutation CreateTenant($tenant_input: TenantInput!) {
      createTenant(tenant_input: $tenant_input) {
        id
        tenantId
        subdomain
        name
        adminEmail
        createdAt
        inviteToken
      }
    }
    """

    variables = {
        "tenant_input": {
            "name": name,
            "adminEmail": admin_email,
            "password": "E2E_Test_Passw0rd!",
            "subdomain": sub,
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Satisfy CSRF guard with a dummy Authorization header; token doesn't need to be valid
        headers = {
            "Content-Type": "application/json",
            "X-Forwarded-For": _fake_ip(),
            "Authorization": "Bearer e2e-test-token",
        }
        resp = await client.post(
            API_GRAPHQL_URL,
            headers=headers,
            json={"operationName": "CreateTenant", "query": query, "variables": variables},
        )
        assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
        body = resp.json()
        # Log the body for CI visibility
        print(json.dumps(body, indent=2))
        if "errors" in body:
            msgs = "; ".join(err.get("message", "") for err in body["errors"])
            pytest.fail(f"GraphQL errors: {msgs}")
        data = body.get("data", {})
        t = (data or {}).get("createTenant")
        assert t and t.get("subdomain") == sub
        assert t.get("inviteToken") and len(t["inviteToken"]) >= 16
        # Basic cross-check of invite URL format
        invite_url = f"https://{sub}.{PRIMARY_DOMAIN}/invite/{t['inviteToken']}"
        print(f"Invite URL: {invite_url}")


@pytest.mark.asyncio
async def test_create_tenant_duplicate_subdomain_e2e():
    ts = int(time.time())
    sub = f"e2e-dupe-{ts}-{_rand_suffix(3)}"

    async def _create(subdomain: str, ip_last_octet: int):
        query = """
        mutation CreateTenant($tenant_input: TenantInput!) {
          createTenant(tenant_input: $tenant_input) {
            id
            tenantId
            subdomain
            name
            adminEmail
            createdAt
            inviteToken
          }
        }
        """
        variables = {
            "tenant_input": {
                "name": f"E2E Org {subdomain}",
                "adminEmail": f"e2e+{subdomain}@example.com",
                "password": "E2E_Test_Passw0rd!",
                "subdomain": subdomain,
            }
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Content-Type": "application/json",
                "X-Forwarded-For": _fake_ip(ip_last_octet),
                "Authorization": "Bearer e2e-test-token",
            }
            resp = await client.post(
                API_GRAPHQL_URL,
                headers=headers,
                json={"operationName": "CreateTenant", "query": query, "variables": variables},
            )
            return resp

    # First creation should succeed
    r1 = await _create(sub, 11)
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert "errors" not in b1, f"Unexpected errors: {b1}"
    assert b1.get("data", {}).get("createTenant", {}).get("subdomain") == sub

    # Second creation with a different IP must fail with 'Subdomain already taken'
    r2 = await _create(sub, 12)
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    errs = b2.get("errors") or []
    assert errs, f"Expected GraphQL error, got: {b2}"
    messages = "; ".join(e.get("message", "") for e in errs)
    assert "Subdomain already taken" in messages
