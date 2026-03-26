import asyncio
import os
from pathlib import Path
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.evaluation.eval_lib import EvalConfig, decode_jwt_payload_no_verify, make_unique_email, make_unique_subdomain, write_json


STATE_PATH = os.getenv("ETHERION_EVAL_STATE", "/home/saturnx/langchain-app/scripts/evaluation/state.json")
OUT_DIR = os.getenv("ETHERION_EVAL_OUT_DIR", "/home/saturnx/langchain-app/scripts/evaluation/out")


async def main() -> None:
    cfg = EvalConfig()

    email = os.getenv("ETHERION_EVAL_EMAIL") or make_unique_email("eval")
    password = os.getenv("ETHERION_EVAL_PASSWORD") or "TestPass123!"
    subdomain = os.getenv("ETHERION_EVAL_SUBDOMAIN") or make_unique_subdomain()
    invite_token = os.getenv("ETHERION_INVITE_TOKEN")
    name = os.getenv("ETHERION_EVAL_NAME") or "Eval User"

    mutation = """
    mutation PasswordSignup($email: String!, $password: String!, $name: String, $invite_token: String, $subdomain: String) {
      passwordSignup(email: $email, password: $password, name: $name, invite_token: $invite_token, subdomain: $subdomain) {
        access_token
        token_type
        user {
          user_id
          email
          name
          provider
          tenant_subdomain
        }
      }
    }
    """

    variables = {
        "email": email,
        "password": password,
        "name": name,
        "invite_token": invite_token,
        "subdomain": subdomain,
    }

    from scripts.evaluation.eval_lib import graphql

    resp = await graphql(cfg, query=mutation, variables=variables, token=None, timeout_seconds=60.0)

    state = {
        "email": email,
        "password": password,
        "requested_subdomain": subdomain,
        "invite_token_used": bool(invite_token),
        "graphql_http": cfg.graphql_http,
        "graphql_ws": cfg.graphql_ws,
        "admin_ingest_url": cfg.admin_ingest_url,
        "admin_ingest_secret": cfg.admin_ingest_secret,
        "signup_response": resp,
    }

    data = (resp.get("data") or {})
    if resp.get("status_code") == 200 and isinstance(data, dict) and not data.get("errors"):
        auth = ((data.get("data") or {}).get("passwordSignup"))
        if isinstance(auth, dict) and auth.get("access_token"):
            token = auth.get("access_token")
            payload = decode_jwt_payload_no_verify(token)
            state.update(
                {
                    "access_token": token,
                    "user": auth.get("user"),
                    "jwt_payload": payload,
                    "tenant_id": payload.get("tenant_id"),
                }
            )

    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    write_json(STATE_PATH, state)


if __name__ == "__main__":
    asyncio.run(main())
