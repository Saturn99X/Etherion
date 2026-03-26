import os
from fastapi import FastAPI
from google.cloud import bigquery
from googleapiclient.discovery import build

app = FastAPI(title="Spend Guard", version="1.0")

PROJECT_ID = os.getenv("PROJECT_ID")
BILLING_ACCOUNT_ID = os.getenv("BILLING_ACCOUNT_ID")
BQ_DATASET = os.getenv("BQ_DATASET", "billing_export")
THRESHOLD_USD = float(os.getenv("THRESHOLD_USD", "100"))
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "24"))
SECURITY_POLICY_ID = os.getenv("SECURITY_POLICY_ID", "")  # projects/{project}/global/securityPolicies/{name}


def _export_table_id(client: bigquery.Client) -> str | None:
    dataset_ref = bigquery.DatasetReference(PROJECT_ID, BQ_DATASET)
    try:
        tables = list(client.list_tables(dataset_ref))
    except Exception:
        return None
    candidates = [t.table_id for t in tables if t.table_id.startswith("gcp_billing_export_v1_")]
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1]


def _query_spend_usd(hours: int) -> float | None:
    client = bigquery.Client(project=PROJECT_ID)
    table_id = _export_table_id(client)
    if not table_id:
        return None
    query = f"""
    SELECT COALESCE(SUM(cost), 0) AS spend_usd
    FROM `{PROJECT_ID}.{BQ_DATASET}.{table_id}`
    WHERE export_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
    """
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("hours", "INT64", hours)]
        ),
    )
    result = list(job.result(limit=1))
    if not result:
        return 0.0
    row = result[0]
    return float(row["spend_usd"] or 0.0)


def _policy_name_from_id(sec_id: str) -> str:
    # expects: projects/{project}/global/securityPolicies/{name}
    return (sec_id or "").split("/")[-1]


def _ensure_kill_switch(enable: bool) -> dict:
    if not SECURITY_POLICY_ID:
        return {"changed": False, "reason": "SECURITY_POLICY_ID not set"}
    name = _policy_name_from_id(SECURITY_POLICY_ID)
    compute = build("compute", "v1", cache_discovery=False)
    priority = 10
    project = PROJECT_ID

    def rule_exists() -> bool:
        try:
            compute.securityPolicies().getRule(
                project=project, securityPolicy=name, priority=priority
            ).execute()
            return True
        except Exception:
            return False

    exists = rule_exists()
    if enable and not exists:
        body = {
            "priority": priority,
            "action": "deny(403)",
            "match": {
                "versionedExpr": "SRC_IPS_V1",
                "config": {"srcIpRanges": ["*"]},
            },
            "description": "Spend guard kill-switch",
        }
        op = (
            compute.securityPolicies()
            .addRule(project=project, securityPolicy=name, body=body)
            .execute()
        )
        return {"changed": True, "op": op}

    if not enable and exists:
        op = (
            compute.securityPolicies()
            .deleteRule(project=project, securityPolicy=name, priority=priority)
            .execute()
        )
        return {"changed": True, "op": op}

    return {"changed": False}


@app.post("/")
def check_spend():
    spend = _query_spend_usd(LOOKBACK_HOURS)
    if spend is None:
        return {
            "status": "waiting_for_export",
            "message": "No Cloud Billing export table found yet",
            "dataset": BQ_DATASET,
        }

    enable = spend > THRESHOLD_USD
    res = _ensure_kill_switch(enable)
    return {
        "project": PROJECT_ID,
        "billing_account": BILLING_ACCOUNT_ID,
        "lookback_hours": LOOKBACK_HOURS,
        "threshold_usd": THRESHOLD_USD,
        "spend_usd_last_window": spend,
        "kill_switch_should_enable": enable,
        "result": res,
    }


@app.get("/health")
def health():
    return {"status": "ok"}
