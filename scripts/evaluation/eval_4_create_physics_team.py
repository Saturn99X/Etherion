import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.evaluation.eval_lib import (
    EvalConfig,
    graphql,
    read_json,
    write_json,
    delete_agent_team,
    list_agent_teams,
    admin_purge_eval_state,
)


STATE_PATH = os.getenv("ETHERION_EVAL_STATE", "/home/saturnx/langchain-app/scripts/evaluation/state.json")


async def main() -> None:
    cfg = EvalConfig()
    state = read_json(STATE_PATH)

    token = state.get("access_token")
    if not token:
        raise RuntimeError(f"Missing access_token in state file: {STATE_PATH}")

    tenant_id = state.get("tenant_id")
    if tenant_id is None:
        raise RuntimeError(f"Missing tenant_id in state file: {STATE_PATH}")
    
    print(f"Creating physics teaching team for tenant {tenant_id}...")

    try:
        purge = await admin_purge_eval_state(cfg, tenant_id=str(tenant_id), dry_run=False, timeout_seconds=120.0)
        print(f"Admin purge eval state: status={purge.get('status_code')}")
    except Exception as e:
        print(f"Admin purge eval state failed (continuing): {e}")

    try:
        # Hard reset: delete all non-system teams for this tenant (best-effort).
        resp = await list_agent_teams(cfg, token=str(token), limit=200, offset=0, timeout_seconds=60.0)
        items = (((resp.get("data") or {}).get("data") or {}).get("listAgentTeams") or [])
        if isinstance(items, list):
            for rec in items:
                if not isinstance(rec, dict):
                    continue
                if rec.get("isSystemTeam") is True:
                    continue
                tid = rec.get("id")
                if isinstance(tid, str) and tid.strip():
                    print(f"Deleting existing tenant team (best-effort): {tid} ({rec.get('name')})")
                    await delete_agent_team(cfg, team_id=str(tid), token=str(token), timeout_seconds=60.0)
    except Exception:
        pass

    email = state.get("email")
    password = state.get("password")
    if email and password:
        login_mutation = """
        mutation PasswordLogin($email: String!, $password: String!) {
          passwordLogin(email: $email, password: $password) {
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

        login_resp = await graphql(
            cfg,
            query=login_mutation,
            variables={"email": str(email), "password": str(password)},
            timeout_seconds=120.0,
        )

        body = login_resp.get("data") or {}
        errors = (body.get("errors") or []) if isinstance(body, dict) else []
        if login_resp.get("status_code") == 200 and not errors:
            login_data = ((body.get("data") or {}).get("passwordLogin") or {}) if isinstance(body, dict) else {}
            new_token = login_data.get("access_token")
            if isinstance(new_token, str) and new_token.strip():
                token = new_token
                state["access_token"] = new_token
                user_obj = login_data.get("user")
                if isinstance(user_obj, dict):
                    state["user"] = user_obj
                # Persist refreshed token and user info immediately so downstream scripts
                # (e.g., eval_5_run_questions.py) never use a stale access_token even if
                # createAgentTeam fails later in this script.
                write_json(STATE_PATH, state)

    # IMPORTANT: Do not mention tools explicitly; we want to observe IO's intuition.
    team_name = "Physics Teaching Team"
    spec = (
        "Create a physics teaching team with exactly 3 specialists: "
        "(1) an Information Theory specialist (Shannon entropy, coding, KL divergence), "
        "(2) a Thermodynamics specialist (stat mech foundations, ensembles, Boltzmann/Gibbs entropy), "
        "(3) an Entropy specialist that bridges both and focuses on intuition and worked examples. "
        "The team should be able to teach progressively from basics to advanced, create exercises, "
        "and produce structured learning artifacts when helpful."
    )

    mutation = """
    mutation CreateTeam($team_input: AgentTeamInput!) {
      createAgentTeam(team_input: $team_input) {
        id
        name
        description
        customAgentIDs
        preApprovedToolNames
      }
    }
    """

    team_input = {
        "name": team_name,
        "description": "Evaluation team for physics teaching",
        "specification": spec,
    }

    print("Sending createAgentTeam mutation...")
    resp = await graphql(
        cfg,
        query=mutation,
        variables={"team_input": team_input},
        token=token,
        timeout_seconds=120.0,
    )
    
    if resp.get("status_code") != 200:
        print(f"GraphQL request failed with status {resp.get('status_code')}")
        print(f"Response: {resp}")

    data = (resp.get("data") or {})
    if resp.get("status_code") == 200 and isinstance(data, dict) and not data.get("errors"):
        team_data = (data.get("data") or {}).get("createAgentTeam") or {}
        team_id = team_data.get("id")
        custom_agent_ids = team_data.get("customAgentIDs") or []
        pre_approved_tool_names = team_data.get("preApprovedToolNames") or []
        
        print(f"Team created successfully:")
        print(f"  Team ID: {team_id}")
        print(f"  Custom Agents: {len(custom_agent_ids)}")
        print(f"  Pre-approved Tools: {len(pre_approved_tool_names)}")

        state.setdefault("teams", {})
        state["teams"]["physics_teaching"] = {
            "request": {"name": team_name, "specification": spec},
            "response": resp,
        }

        state["team_id"] = team_id
        state["team_custom_agent_ids"] = custom_agent_ids
        state["team_preapproved_tools"] = pre_approved_tool_names

        write_json(STATE_PATH, state)

    # Validation: the evaluation expects exactly 3 specialist agents.
    ids = state.get("team_custom_agent_ids")
    if not isinstance(ids, list) or len(ids) != 3:
        raise RuntimeError(
            f"Expected createAgentTeam to create exactly 3 custom agents, got {0 if not isinstance(ids, list) else len(ids)}: {ids}"
        )


if __name__ == "__main__":
    asyncio.run(main())
