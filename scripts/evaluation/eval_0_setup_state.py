import asyncio
import os
import sys
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.evaluation.eval_lib import EvalConfig, graphql, write_json, decode_jwt_payload_no_verify

async def login():
    cfg = EvalConfig(graphql_http="http://localhost:8080/graphql")
    email = "phys@eval.com"
    password = "phys-pass-123"
    
    mutation = """
    mutation PasswordLogin($email: String!, $password: String!) {
      passwordLogin(email: $email, password: $password) {
        access_token
        user {
          user_id
          tenant_subdomain
        }
      }
    }
    """
    
    resp = await graphql(cfg, query=mutation, variables={"email": email, "password": password})
    print(resp)
    
    login_result = resp.get("data", {}).get("data", {}).get("passwordLogin", {})
    token = login_result.get("access_token")
    
    if not token:
        print("Login failed, no token returned.")
        return

    payload = decode_jwt_payload_no_verify(token)
    tenant_id = payload.get("tenant_id")
    
    state = {
        "email": email,
        "password": password,
        "access_token": token,
        "user": login_result.get("user"),
        "subdomain": login_result.get("user", {}).get("tenant_subdomain"),
        "tenant_id": tenant_id,
        "jwt_payload": payload
    }
    
    write_json("scripts/evaluation/state.json", state)
    print(f"state.json updated. tenant_id={tenant_id}")
    
    write_json("scripts/evaluation/state.json", state)
    print("state.json updated.")

if __name__ == "__main__":
    asyncio.run(login())
