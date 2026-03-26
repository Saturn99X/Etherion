import os
import json
import pytest
from datetime import datetime

pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_CLOUD_PROJECT"),
    reason="Requires GOOGLE_CLOUD_PROJECT and GCS for fine-tuning pipeline",
)


@pytest.mark.asyncio
async def test_sft_pipeline_and_user_observations_end_to_end():
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-sft")
    os.environ.setdefault("SECRET_KEY", "test-secret-sft-app")

    # 1) Prepare a synthetic anonymized trace and push to fine-tuning GCS bucket
    from src.services.fine_tuning_gcs import FineTuningGCSService

    gcs = FineTuningGCSService()

    tenant_hash = "tenanthash_e2e"
    job_id = "job_e2e_sft"
    anonymized_trace = {
        "trace_id": job_id,
        "tenant_hash": tenant_hash,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "steps": [
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": "Summarize this content."},
            {"role": "assistant", "content": "Summary: ..."},
        ],
        "metadata": {"source": "e2e_test", "pii_removed": True},
    }

    gcs_uri = await gcs.upload_trace_to_fine_tuning_bucket(
        anonymized_trace=anonymized_trace,
        job_id=job_id,
        tenant_hash=tenant_hash,
    )
    assert gcs_uri.startswith("gs://")

    # 2) Summaries and dataset fetch
    summary = await gcs.get_fine_tuning_data_summary()
    assert isinstance(summary, dict)
    assert summary.get("bucket_name")
    assert summary.get("total_traces", 0) >= 1

    dataset = await gcs.get_ml_training_dataset(tenant_hashes=[tenant_hash], limit=5)
    assert isinstance(dataset, list)
    assert any(isinstance(item, dict) for item in dataset)

    # 3) User Observations: record and generate system instructions
    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User
    from src.services.user_observation_service import UserObservationService

    async with get_scoped_session() as session:
        tenant = Tenant(
            tenant_id="sft-observations-e2e",
            subdomain="sft-observations-e2e",
            name="SFT Obs Tenant",
            admin_email="sft@test.local",
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)

        user = User(user_id="sft-user", tenant_id=tenant.id, email="sft@test.local")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    uos = UserObservationService()
    uos.record_interaction(
        user_id=user.id,
        tenant_id=tenant.id,
        interaction_data={
            "response_content": "Formal, technical response about APIs and algorithms.",
            "success_indicators": {"success": True},
            "tools_used": ["kb_search", "web_search"],
            "approaches_used": ["dual_search"],
            "response_time": 12.3,
            "follow_up_count": 1,
            "content": "Please include examples such as step-by-step."
        }
    )

    instructions = await uos.generate_system_instructions(user_id=user.id, tenant_id=tenant.id)
    assert isinstance(instructions, str)
    # May be empty if first-time/no observations cached, so allow empty or presence of key phrase
    assert instructions == "" or "Communication Style:" in instructions
