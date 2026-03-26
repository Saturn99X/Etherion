"""
Integration tests for checklist GraphQL API.

Tests the GraphQL queries and subscriptions for checklist functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from src.services.checklist_manager import ChecklistManager, Checklist, ChecklistItem
from src.database.models import Job, JobStatus
from datetime import datetime


@pytest.fixture
def checklist_manager():
    """Create a checklist manager instance."""
    return ChecklistManager()


@pytest.fixture
def sample_job():
    """Create a sample job for testing."""
    job = Mock(spec=Job)
    job.job_id = "test_job_123"
    job.tenant_id = 1
    job.user_id = 100
    job.status = JobStatus.RUNNING
    job.created_at = datetime.utcnow()
    return job


@pytest.fixture
def sample_checklist(checklist_manager):
    """Create a sample checklist."""
    return checklist_manager.create_checklist(
        owner_id="team_123",
        owner_type="team",
        task_description="Test task with multiple steps"
    )


@pytest.mark.asyncio
async def test_get_checklists_by_job_query(sample_job, sample_checklist):
    """Test getChecklistsByJob GraphQL query."""
    # Mock the database session and query
    with patch('src.etherion_ai.graphql_schema.queries.session_scope') as mock_session:
        mock_db = Mock()
        mock_session.return_value.__enter__.return_value = mock_db
        
        # Mock job query
        mock_db.exec.return_value.first.return_value = sample_job
        
        # Mock checklist query
        from src.database.models.checklist import Checklist as ChecklistORM
        mock_checklist_orm = Mock(spec=ChecklistORM)
        mock_checklist_orm.id = sample_checklist.id
        mock_checklist_orm.owner_id = sample_checklist.owner_id
        mock_checklist_orm.owner_type = sample_checklist.owner_type
        mock_checklist_orm.job_id = sample_job.job_id
        mock_checklist_orm.tenant_id = sample_job.tenant_id
        mock_checklist_orm.created_at = datetime.utcnow()
        mock_checklist_orm.completed_at = None
        mock_checklist_orm.get_items.return_value = [
            {"id": item.id, "description": item.description, "completed": item.completed}
            for item in sample_checklist.items
        ]
        
        mock_db.exec.return_value.all.return_value = [mock_checklist_orm]
        
        # Import and test the query
        from src.etherion_ai.graphql_schema.queries import Query
        query = Query()
        
        # Mock info context
        mock_info = Mock()
        mock_info.context = {
            "request": Mock(state=Mock(auth_context={
                "current_user": Mock(tenant_id=1, id=100),
                "db_session": mock_db
            }))
        }
        
        # Execute query
        result = await query.getChecklistsByJob(mock_info, sample_job.job_id)
        
        # Verify results
        assert len(result) == 1
        assert result[0]["id"] == sample_checklist.id
        assert result[0]["owner_id"] == sample_checklist.owner_id
        assert result[0]["owner_type"] == "team"
        assert result[0]["job_id"] == sample_job.job_id
        assert "items" in result[0]
        assert "progress" in result[0]
        assert result[0]["progress"]["total"] == len(sample_checklist.items)


@pytest.mark.asyncio
async def test_get_checklists_unauthorized(sample_job):
    """Test that unauthorized users cannot access checklists."""
    with patch('src.etherion_ai.graphql_schema.queries.session_scope') as mock_session:
        mock_db = Mock()
        mock_session.return_value.__enter__.return_value = mock_db
        
        # Mock job query returning None (job not found or unauthorized)
        mock_db.exec.return_value.first.return_value = None
        
        from src.etherion_ai.graphql_schema.queries import Query
        query = Query()
        
        mock_info = Mock()
        mock_info.context = {
            "request": Mock(state=Mock(auth_context={
                "current_user": Mock(tenant_id=1, id=100),
                "db_session": mock_db
            }))
        }
        
        # Should raise exception for unauthorized access
        with pytest.raises(Exception, match="Job not found or access denied"):
            await query.getChecklistsByJob(mock_info, sample_job.job_id)


@pytest.mark.asyncio
async def test_checklist_subscription_authentication():
    """Test that checklist subscription requires authentication."""
    from src.etherion_ai.graphql_schema.subscriptions import Subscription
    subscription = Subscription()
    
    # Mock unauthenticated context
    mock_info = Mock()
    mock_info.context = {
        "request": Mock(state=Mock(auth_context={})),
        "connection_params": {}
    }
    
    # Execute subscription
    result_gen = subscription.subscribeToChecklistUpdates(mock_info, "test_job_123")
    
    # Should yield error message
    first_result = await result_gen.__anext__()
    assert first_result.status == "ERROR"
    assert "Authentication required" in first_result.error_message


@pytest.mark.asyncio
async def test_checklist_subscription_receives_events(sample_job):
    """Test that checklist subscription receives checklist events."""
    with patch('src.etherion_ai.graphql_schema.subscriptions.session_scope') as mock_session, \
         patch('src.etherion_ai.graphql_schema.subscriptions.subscribe_to_execution_trace') as mock_subscribe:
        
        mock_db = Mock()
        mock_session.return_value.__enter__.return_value = mock_db
        
        # Mock job query
        mock_db.query.return_value.filter.return_value.first.return_value = sample_job
        
        # Mock execution trace events
        async def mock_trace_generator():
            yield {
                "type": "CHECKLIST_CREATED",
                "job_id": sample_job.job_id,
                "timestamp": datetime.utcnow().isoformat(),
                "step_description": "Global checklist created",
                "checklist_id": "checklist_123",
                "owner_type": "team",
                "item_count": 3
            }
            yield {
                "type": "TOOL_START",  # Non-checklist event, should be filtered
                "job_id": sample_job.job_id,
                "timestamp": datetime.utcnow().isoformat(),
                "tool": "unified_research_tool"
            }
            yield {
                "type": "EXECUTION_MODE_SELECTED",
                "job_id": sample_job.job_id,
                "timestamp": datetime.utcnow().isoformat(),
                "step_description": "Sequential mode selected",
                "mode": "sequential"
            }
        
        mock_subscribe.return_value = mock_trace_generator()
        
        from src.etherion_ai.graphql_schema.subscriptions import Subscription
        subscription = Subscription()
        
        # Mock authenticated context
        mock_info = Mock()
        mock_info.context = {
            "request": Mock(
                state=Mock(auth_context={
                    "current_user": Mock(tenant_id=1, id=100, user_id=100)
                }),
                client=Mock(host="127.0.0.1")
            ),
            "connection_params": {}
        }
        
        # Execute subscription
        result_gen = subscription.subscribeToChecklistUpdates(mock_info, sample_job.job_id)
        
        # Collect events
        events = []
        async for event in result_gen:
            events.append(event)
            if len(events) >= 2:  # Should receive 2 checklist events (CHECKLIST_CREATED, EXECUTION_MODE_SELECTED)
                break
        
        # Verify we received only checklist-related events
        assert len(events) == 2
        assert events[0].status == "CHECKLIST_CREATED"
        assert events[1].status == "EXECUTION_MODE_SELECTED"


@pytest.mark.asyncio
async def test_checklist_progress_calculation():
    """Test that checklist progress is calculated correctly."""
    manager = ChecklistManager()
    checklist = manager.create_checklist(
        owner_id="test_owner",
        owner_type="team",
        task_description="Task with 5 items"
    )
    
    # Initially, no items completed
    progress = manager.get_progress(checklist.id)
    assert progress["total"] == 5
    assert progress["completed"] == 0
    assert progress["percentage"] == 0.0
    
    # Complete 2 items
    manager.mark_item_complete(checklist.id, checklist.items[0].id)
    manager.mark_item_complete(checklist.id, checklist.items[1].id)
    
    progress = manager.get_progress(checklist.id)
    assert progress["completed"] == 2
    assert progress["percentage"] == 40.0
    
    # Complete all items
    for item in checklist.items[2:]:
        manager.mark_item_complete(checklist.id, item.id)
    
    progress = manager.get_progress(checklist.id)
    assert progress["completed"] == 5
    assert progress["percentage"] == 100.0


@pytest.mark.asyncio
async def test_multiple_checklists_per_job():
    """Test that a job can have multiple checklists (team + specialists)."""
    manager = ChecklistManager()
    
    # Create global team checklist
    team_checklist = manager.create_checklist(
        owner_id="team_123",
        owner_type="team",
        task_description="Global team tasks"
    )
    
    # Create specialist checklists
    specialist1_checklist = manager.create_checklist(
        owner_id="specialist_1",
        owner_type="specialist",
        task_description="Specialist 1 tasks"
    )
    
    specialist2_checklist = manager.create_checklist(
        owner_id="specialist_2",
        owner_type="specialist",
        task_description="Specialist 2 tasks"
    )
    
    # Verify all checklists exist
    all_checklists = [team_checklist, specialist1_checklist, specialist2_checklist]
    assert len(all_checklists) == 3
    
    # Verify owner types
    assert team_checklist.owner_type == "team"
    assert specialist1_checklist.owner_type == "specialist"
    assert specialist2_checklist.owner_type == "specialist"
    
    # Verify each has items
    for checklist in all_checklists:
        assert len(checklist.items) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
