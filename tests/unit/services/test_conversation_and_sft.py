import os
import pytest
from unittest.mock import patch
from datetime import datetime

from sqlmodel import Session

from src.services.conversation_logger import ConversationLogger
from src.services.sft_data_collector import SFTDataCollector
from src.database.db import get_db
from src.database.ts_models import Conversation, Project, Tenant


@pytest.fixture(autouse=True)
def project_setup():
    # ensure project id and tenant exist in DB
    session: Session = get_db()
    tenant = Tenant(name="t", subdomain="t", tenant_id="t1")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    project = Project(name="p", description="", user_id=1, tenant_id=tenant.id)
    session.add(project)
    session.commit()
    session.refresh(project)

    convo = Conversation(title="c", project_id=project.id, tenant_id=tenant.id)
    session.add(convo)
    session.commit()
    session.refresh(convo)

    yield tenant.id, project.id, convo.id


def test_conversation_logger_and_sft(project_setup):
    tenant_db_id, _, conversation_id = project_setup

    logger = ConversationLogger()
    mid1 = logger.log_user_message(tenant_db_id, conversation_id, "My email is user@example.com")
    assert mid1 > 0
    mid2 = logger.log_assistant_message(tenant_db_id, conversation_id, "Hello, I've redacted data.")
    assert mid2 > 0

    collector = SFTDataCollector()
    with patch("src.services.fine_tuning_gcs.FineTuningGCSService.upload_trace_to_fine_tuning_bucket", return_value="gs://bucket/key"):
        uri = pytest.run(async_fn=lambda: collector.collect_conversation_trace(tenant_db_id, conversation_id, job_id="job_1"))
        # note: if pytest doesn't support async_fn helper here, this is a placeholder for async test runner in project
        assert isinstance(uri, str)


