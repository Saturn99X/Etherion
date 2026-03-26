"""
Unit tests for ToolRequestQueue.
"""

import pytest
from src.services.tool_request_queue import (
    ToolRequestQueue, ToolRequest, ToolJustification, ToolRequestStatus
)


class TestToolJustification:
    """Tests for ToolJustification."""

    def test_create_justification(self):
        """Test creating a justification."""
        just = ToolJustification(
            what="unified_research_tool to search knowledge base",
            how="Query with user's question",
            why="Need to find relevant documents"
        )
        
        assert just.what == "unified_research_tool to search knowledge base"
        assert just.how == "Query with user's question"
        assert just.why == "Need to find relevant documents"

    def test_to_dict(self):
        """Test converting to dictionary."""
        just = ToolJustification(what="test", how="test", why="test")
        data = just.to_dict()
        
        assert data["what"] == "test"
        assert data["how"] == "test"
        assert data["why"] == "test"

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {"what": "test", "how": "test", "why": "test"}
        just = ToolJustification.from_dict(data)
        
        assert just.what == "test"
        assert just.how == "test"
        assert just.why == "test"


class TestToolRequest:
    """Tests for ToolRequest."""

    def test_create_request(self):
        """Test creating a tool request."""
        just = ToolJustification(what="test", how="test", why="test")
        req = ToolRequest(
            id="req_1",
            specialist_id="spec_1",
            tool_name="unified_research_tool",
            parameters={"query": "test"},
            justification=just
        )
        
        assert req.id == "req_1"
        assert req.specialist_id == "spec_1"
        assert req.tool_name == "unified_research_tool"
        assert req.status == ToolRequestStatus.PENDING
        assert req.reviewed_at is None

    def test_approve_request(self):
        """Test approving a request."""
        just = ToolJustification(what="test", how="test", why="test")
        req = ToolRequest(
            id="req_1",
            specialist_id="spec_1",
            tool_name="test_tool",
            parameters={},
            justification=just
        )
        
        req.approve(reviewed_by="orchestrator")
        assert req.status == ToolRequestStatus.APPROVED
        assert req.reviewed_by == "orchestrator"
        assert req.reviewed_at is not None

    def test_reject_request(self):
        """Test rejecting a request."""
        just = ToolJustification(what="test", how="test", why="test")
        req = ToolRequest(
            id="req_1",
            specialist_id="spec_1",
            tool_name="test_tool",
            parameters={},
            justification=just
        )
        
        req.reject(reviewed_by="orchestrator", reason="Tool not allowed")
        assert req.status == ToolRequestStatus.REJECTED
        assert req.reviewed_by == "orchestrator"
        assert req.rejection_reason == "Tool not allowed"
        assert req.reviewed_at is not None

    def test_mark_executed(self):
        """Test marking as executed."""
        just = ToolJustification(what="test", how="test", why="test")
        req = ToolRequest(
            id="req_1",
            specialist_id="spec_1",
            tool_name="test_tool",
            parameters={},
            justification=just
        )
        
        req.mark_executed(result={"output": "success"})
        assert req.status == ToolRequestStatus.EXECUTED
        assert req.execution_result == {"output": "success"}

    def test_mark_failed(self):
        """Test marking as failed."""
        just = ToolJustification(what="test", how="test", why="test")
        req = ToolRequest(
            id="req_1",
            specialist_id="spec_1",
            tool_name="test_tool",
            parameters={},
            justification=just
        )
        
        req.mark_failed(error="Tool execution failed")
        assert req.status == ToolRequestStatus.FAILED
        assert req.execution_result == {"error": "Tool execution failed"}

    def test_to_dict(self):
        """Test converting to dictionary."""
        just = ToolJustification(what="test", how="test", why="test")
        req = ToolRequest(
            id="req_1",
            specialist_id="spec_1",
            tool_name="test_tool",
            parameters={"query": "test"},
            justification=just
        )
        
        data = req.to_dict()
        assert data["id"] == "req_1"
        assert data["specialist_id"] == "spec_1"
        assert data["tool_name"] == "test_tool"
        assert data["status"] == "pending"

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "id": "req_1",
            "specialist_id": "spec_1",
            "tool_name": "test_tool",
            "parameters": {"query": "test"},
            "justification": {"what": "test", "how": "test", "why": "test"},
            "status": "pending",
            "submitted_at": "2026-03-16T19:00:00",
            "reviewed_at": None,
            "reviewed_by": None,
            "rejection_reason": None,
            "execution_result": None
        }
        
        req = ToolRequest.from_dict(data)
        assert req.id == "req_1"
        assert req.specialist_id == "spec_1"
        assert req.status == ToolRequestStatus.PENDING


class TestToolRequestQueue:
    """Tests for ToolRequestQueue."""

    def test_submit_request(self):
        """Test submitting a request."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        
        req = queue.submit_request(
            specialist_id="spec_1",
            tool_name="test_tool",
            parameters={"query": "test"},
            justification=just
        )
        
        assert req.id is not None
        assert req.specialist_id == "spec_1"
        assert len(queue.queue) == 1

    def test_get_next_pending_fifo(self):
        """Test FIFO ordering of pending requests."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        
        req1 = queue.submit_request("spec_1", "tool_1", {}, just)
        req2 = queue.submit_request("spec_2", "tool_2", {}, just)
        req3 = queue.submit_request("spec_3", "tool_3", {}, just)
        
        # Should get first request
        next_req = queue.get_next_pending()
        assert next_req.id == req1.id
        
        # Approve first, should get second
        queue.approve_request(req1.id, "orchestrator")
        next_req = queue.get_next_pending()
        assert next_req.id == req2.id

    def test_get_request(self):
        """Test getting a request by ID."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        req = queue.submit_request("spec_1", "tool_1", {}, just)
        
        found = queue.get_request(req.id)
        assert found is not None
        assert found.id == req.id
        
        not_found = queue.get_request("nonexistent")
        assert not_found is None

    def test_approve_request(self):
        """Test approving a request."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        req = queue.submit_request("spec_1", "tool_1", {}, just)
        
        result = queue.approve_request(req.id, "orchestrator")
        assert result is True
        assert req.status == ToolRequestStatus.APPROVED

    def test_reject_request(self):
        """Test rejecting a request."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        req = queue.submit_request("spec_1", "tool_1", {}, just)
        
        result = queue.reject_request(req.id, "orchestrator", "Not allowed")
        assert result is True
        assert req.status == ToolRequestStatus.REJECTED
        assert req.rejection_reason == "Not allowed"

    def test_mark_executed(self):
        """Test marking as executed."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        req = queue.submit_request("spec_1", "tool_1", {}, just)
        
        # Must approve first
        queue.approve_request(req.id, "orchestrator")
        
        result = queue.mark_executed(req.id, {"output": "success"})
        assert result is True
        assert req.status == ToolRequestStatus.EXECUTED

    def test_mark_failed(self):
        """Test marking as failed."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        req = queue.submit_request("spec_1", "tool_1", {}, just)
        
        # Must approve first
        queue.approve_request(req.id, "orchestrator")
        
        result = queue.mark_failed(req.id, "Execution error")
        assert result is True
        assert req.status == ToolRequestStatus.FAILED

    def test_get_all_requests(self):
        """Test getting all requests."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        
        req1 = queue.submit_request("spec_1", "tool_1", {}, just)
        req2 = queue.submit_request("spec_2", "tool_2", {}, just)
        
        all_reqs = queue.get_all_requests()
        assert len(all_reqs) == 2
        assert req1 in all_reqs
        assert req2 in all_reqs

    def test_get_requests_by_specialist(self):
        """Test getting requests by specialist."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        
        req1 = queue.submit_request("spec_1", "tool_1", {}, just)
        req2 = queue.submit_request("spec_1", "tool_2", {}, just)
        req3 = queue.submit_request("spec_2", "tool_3", {}, just)
        
        spec1_reqs = queue.get_requests_by_specialist("spec_1")
        assert len(spec1_reqs) == 2
        assert req1 in spec1_reqs
        assert req2 in spec1_reqs
        
        spec2_reqs = queue.get_requests_by_specialist("spec_2")
        assert len(spec2_reqs) == 1
        assert req3 in spec2_reqs

    def test_get_pending_count(self):
        """Test getting pending count."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        
        assert queue.get_pending_count() == 0
        
        req1 = queue.submit_request("spec_1", "tool_1", {}, just)
        req2 = queue.submit_request("spec_2", "tool_2", {}, just)
        assert queue.get_pending_count() == 2
        
        queue.approve_request(req1.id, "orchestrator")
        assert queue.get_pending_count() == 1

    def test_clear(self):
        """Test clearing the queue."""
        queue = ToolRequestQueue()
        just = ToolJustification(what="test", how="test", why="test")
        
        queue.submit_request("spec_1", "tool_1", {}, just)
        queue.submit_request("spec_2", "tool_2", {}, just)
        assert len(queue.queue) == 2
        
        queue.clear()
        assert len(queue.queue) == 0
