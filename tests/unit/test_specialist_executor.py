"""
Unit tests for Specialist Executor Wrapper (Step 2.7).

Tests that the SpecialistExecutor correctly:
- Wraps existing agent execution
- Maintains checklist state
- Submits tool requests
- Self-validates subtasks
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_specialist_executor_wraps_execution():
    """Test that specialist executor wraps underlying agent execution."""
    from src.services.specialist_executor import SpecialistExecutor
    from src.services.checklist_manager import ChecklistManager
    from src.services.tool_request_queue import ToolRequestQueue
    
    # Create mocks
    checklist_manager = ChecklistManager()
    tool_request_queue = ToolRequestQueue()
    
    # Mock underlying executor
    underlying_executor = Mock()
    underlying_executor.execute = AsyncMock(return_value={"output": "Task completed successfully"})
    
    # Create specialist executor
    executor = SpecialistExecutor(
        specialist_id="spec_001",
        specialist_name="Test Specialist",
        checklist_manager=checklist_manager,
        tool_request_queue=tool_request_queue,
        underlying_executor=underlying_executor
    )
    
    # Execute
    result = await executor.execute("Complete the task")
    
    # Verify
    assert result.success is True
    assert result.output == "Task completed successfully"
    assert underlying_executor.execute.called


@pytest.mark.asyncio
async def test_specialist_executor_maintains_checklist_state():
    """Test that specialist executor maintains checklist state."""
    from src.services.specialist_executor import SpecialistExecutor
    from src.services.checklist_manager import ChecklistManager
    from src.services.tool_request_queue import ToolRequestQueue
    
    # Create checklist
    checklist_manager = ChecklistManager()
    checklist = checklist_manager.create_checklist(
        owner_id="spec_001",
        owner_type="specialist",
        task_description="Test task with multiple steps"
    )
    
    tool_request_queue = ToolRequestQueue()
    underlying_executor = Mock()
    underlying_executor.execute = AsyncMock(return_value={"output": "Done"})
    
    # Create executor and set checklist
    executor = SpecialistExecutor(
        specialist_id="spec_001",
        specialist_name="Test Specialist",
        checklist_manager=checklist_manager,
        tool_request_queue=tool_request_queue,
        underlying_executor=underlying_executor
    )
    executor.set_checklist(checklist)
    
    # Execute
    result = await executor.execute("Do work")
    
    # Verify checklist progress is tracked
    assert "checklist_progress" in result.__dict__
    assert result.checklist_progress["total_items"] > 0


@pytest.mark.asyncio
async def test_specialist_executor_submits_tool_requests():
    """Test that specialist executor submits tool requests instead of direct execution."""
    from src.services.specialist_executor import SpecialistExecutor
    from src.services.checklist_manager import ChecklistManager
    from src.services.tool_request_queue import ToolRequestQueue
    
    checklist_manager = ChecklistManager()
    tool_request_queue = ToolRequestQueue()
    underlying_executor = Mock()
    underlying_executor.execute = AsyncMock(return_value={"output": "Done"})
    
    executor = SpecialistExecutor(
        specialist_id="spec_001",
        specialist_name="Test Specialist",
        checklist_manager=checklist_manager,
        tool_request_queue=tool_request_queue,
        underlying_executor=underlying_executor
    )
    
    # Submit tool request
    request_id = executor.submit_tool_request(
        tool_name="test_tool",
        parameters={"param1": "value1"},
        what="Execute test_tool to validate functionality",
        how="Using test_tool with param1=value1",
        why="Required to complete the test task"
    )
    
    # Verify request was submitted
    assert request_id is not None
    assert request_id.startswith("req_")
    
    # Verify request is in queue
    request = tool_request_queue.get_request(request_id)
    assert request is not None
    assert request.tool_name == "test_tool"
    assert request.specialist_id == "spec_001"


@pytest.mark.asyncio
async def test_specialist_executor_validates_subtasks():
    """Test that specialist executor can self-validate subtasks."""
    from src.services.specialist_executor import SpecialistExecutor
    from src.services.checklist_manager import ChecklistManager
    from src.services.tool_request_queue import ToolRequestQueue
    
    # Create checklist with items
    checklist_manager = ChecklistManager()
    checklist = checklist_manager.create_checklist(
        owner_id="spec_001",
        owner_type="specialist",
        task_description="Task with validation"
    )
    
    tool_request_queue = ToolRequestQueue()
    underlying_executor = Mock()
    underlying_executor.execute = AsyncMock(return_value={"output": "Done"})
    
    executor = SpecialistExecutor(
        specialist_id="spec_001",
        specialist_name="Test Specialist",
        checklist_manager=checklist_manager,
        tool_request_queue=tool_request_queue,
        underlying_executor=underlying_executor
    )
    executor.set_checklist(checklist)
    
    # Get first item
    item_id = checklist.items[0].id
    
    # Validate subtask
    success = executor.validate_subtask(item_id, "Task completed successfully")
    
    # Verify
    assert success is True
    
    # Check item is marked complete
    updated_checklist = checklist_manager.get_checklist(checklist.id)
    item = next(i for i in updated_checklist.items if i.id == item_id)
    assert item.completed is True
    assert item.validated_by == "spec_001"


@pytest.mark.asyncio
async def test_specialist_executor_handles_errors():
    """Test that specialist executor handles execution errors gracefully."""
    from src.services.specialist_executor import SpecialistExecutor
    from src.services.checklist_manager import ChecklistManager
    from src.services.tool_request_queue import ToolRequestQueue
    
    checklist_manager = ChecklistManager()
    tool_request_queue = ToolRequestQueue()
    
    # Mock executor that raises error
    underlying_executor = Mock()
    underlying_executor.execute = AsyncMock(side_effect=Exception("Execution failed"))
    
    executor = SpecialistExecutor(
        specialist_id="spec_001",
        specialist_name="Test Specialist",
        checklist_manager=checklist_manager,
        tool_request_queue=tool_request_queue,
        underlying_executor=underlying_executor
    )
    
    # Execute
    result = await executor.execute("Do work")
    
    # Verify error handling
    assert result.success is False
    assert result.error == "Execution failed"
    assert result.output == ""


@pytest.mark.asyncio
async def test_specialist_executor_get_checklist_status():
    """Test that specialist executor can report checklist status."""
    from src.services.specialist_executor import SpecialistExecutor
    from src.services.checklist_manager import ChecklistManager
    from src.services.tool_request_queue import ToolRequestQueue
    
    checklist_manager = ChecklistManager()
    checklist = checklist_manager.create_checklist(
        owner_id="spec_001",
        owner_type="specialist",
        task_description="Status test task"
    )
    
    tool_request_queue = ToolRequestQueue()
    underlying_executor = Mock()
    
    executor = SpecialistExecutor(
        specialist_id="spec_001",
        specialist_name="Test Specialist",
        checklist_manager=checklist_manager,
        tool_request_queue=tool_request_queue,
        underlying_executor=underlying_executor
    )
    executor.set_checklist(checklist)
    
    # Get status
    status = executor.get_checklist_status()
    
    # Verify
    assert "checklist_id" in status
    assert status["owner_id"] == "spec_001"
    assert status["total_items"] > 0
    assert "items" in status
    assert len(status["items"]) == status["total_items"]
