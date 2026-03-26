import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.evaluation.eval_lib import (
    EvalConfig,
    get_archived_trace_summary,
    graphql,
    read_json,
    subscribe_execution_trace,
    write_json,
    ensure_dir,
)


STATE_PATH = os.getenv("ETHERION_EVAL_STATE", "/home/saturnx/langchain-app/scripts/evaluation/state.json")
OUT_DIR = os.getenv("ETHERION_EVAL_OUT_DIR", "/home/saturnx/langchain-app/scripts/evaluation/out")


QUESTIONS: List[str] = [
    "Explain entropy in thermodynamics with a concrete everyday analogy.",
    "Define Shannon entropy and explain what it measures. Give a simple example with a biased coin.",
    "Carefully relate thermodynamic entropy (Boltzmann/Gibbs) to information entropy. Where does the analogy break?",
    "Derive (at a teaching level) why entropy is extensive for weakly interacting subsystems and mention assumptions.",
    "Given probabilities p=[0.1,0.2,0.3,0.4], compute Shannon entropy in bits and interpret the result.",
    "Create a CSV table of Shannon entropy H(p) (bits) for a Bernoulli(p) source for p in [0.01,0.05,0.1,...,0.95,0.99]. Then generate a chart of H(p) vs p (label axes, title).",
    "Create an Excel file that contains: (a) the same entropy table, (b) a second table comparing H(p) in bits vs nats, and (c) a short text block explaining how to convert between them. Also produce a chart image summarizing both curves."
]


async def execute_goal(cfg: EvalConfig, *, token: str, goal_input: Dict[str, Any]) -> Dict[str, Any]:
    mutation = """
    mutation ExecuteGoal($goalInput: GoalInput!) {
      executeGoal(goalInput: $goalInput) { success job_id status message }
    }
    """
    try:
        resp = await graphql(
            cfg,
            query=mutation,
            variables={"goalInput": goal_input},
            token=token,
            timeout_seconds=180.0,
        )
    except Exception as e:
        print(f"Error executing goal: {e}")
        return {"error": str(e), "status": "failed"}
    return resp


async def main() -> None:
    cfg = EvalConfig()
    state = read_json(STATE_PATH)

    token = state.get("access_token")
    if not token:
        raise RuntimeError(f"Missing access_token in state file: {STATE_PATH}")

    user = state.get("user") or {}
    user_id = (user.get("user_id") if isinstance(user, dict) else None) or state.get("jwt_payload", {}).get("sub")
    if not user_id:
        raise RuntimeError("Missing user_id in state.")

    team_id = state.get("team_id")
    if not team_id:
        raise RuntimeError(f"Missing team_id in state file: {STATE_PATH}")

    print(f"Running evaluation questions for team {team_id}...")

    thread_id: Optional[str] = state.get("thread_id")

    run_tag = os.getenv("ETHERION_EVAL_RUN_TAG") or "physics_team_questions"
    run_dir = str(Path(OUT_DIR) / run_tag)
    ensure_dir(run_dir)

    results: List[Dict[str, Any]] = []

    for idx, q in enumerate(QUESTIONS, start=1):
        print(f"\n{'='*60}")
        print(f"Question {idx}/{len(QUESTIONS)}")
        print(f"{'='*60}")
        print(f"Goal: {q}")
        print()

        goal_input: Dict[str, Any] = {
            "goal": q,
            "context": "Physics teaching evaluation run. Answer clearly and progressively; show steps when mathematical.",
            "userId": str(user_id),
            "agentTeamId": str(team_id),
        }
        if thread_id:
            goal_input["threadId"] = thread_id

        exec_resp = await execute_goal(cfg, token=token, goal_input=goal_input)

        if "error" in exec_resp:
            results.append({
                "question": q,
                "error": exec_resp["error"],
                "status": "failed",
            })
            continue

        job_id = None
        try:
            data = exec_resp.get("data", {})
            job_id = (((data.get("data") or {}).get("executeGoal") or {}).get("job_id"))
        except Exception:
            job_id = None

        if not job_id:
            results.append({
                "question": q,
                "error": "No job ID returned",
                "status": "failed",
            })
            continue

        step: Dict[str, Any] = {
            "index": idx,
            "question": q,
            "goal_input": goal_input,
            "execute_goal_response": exec_resp,
            "job_id": job_id,
        }

        if "errors" in data:
            errors = data['errors']
            print(f"GraphQL errors: {errors}")
            results.append({
                "question": q,
                "graphql_errors": errors,
                "status": "failed",
            })
            continue

        trace_path = str(Path(run_dir) / f"q{idx:02d}_{job_id}_trace.jsonl")

        extracted: Dict[str, Any] = {}

        def _on_evt(evt: Dict[str, Any]) -> None:
            nonlocal thread_id
            ad = evt.get("additional_data")
            if isinstance(ad, dict) and ad.get("thread_id") and not thread_id:
                thread_id = str(ad.get("thread_id"))

        try:
            await subscribe_execution_trace(
                cfg,
                job_id=job_id,
                token=token,
                out_jsonl_path=trace_path,
                on_event=_on_evt,
                recv_timeout_seconds=3600.0,
            )
            print(f"Trace subscription completed")
        except Exception as e:
            print(f"Trace subscription error: {e}")
            # Continue even if trace fails - we can still get summary

        # Persist thread_id in state once we discover it (usually from THREAD_CREATED event)
        if thread_id and not state.get("thread_id"):
            state["thread_id"] = thread_id
            write_json(STATE_PATH, state)

        archived = await get_archived_trace_summary(cfg, job_id=job_id, token=token)

        step["trace"] = {
            "jsonl_path": trace_path,
            "extracted": extracted,
        }
        step["archived_trace_summary"] = archived

        results.append(step)

    state.setdefault("question_runs", {})
    state["question_runs"][run_tag] = {
        "team_id": team_id,
        "thread_id": thread_id,
        "results": results,
    }

    write_json(STATE_PATH, state)


if __name__ == "__main__":
    asyncio.run(main())
