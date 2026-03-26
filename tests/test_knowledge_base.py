# tests/test_knowledge_base.py
import pytest
from unittest.mock import patch, MagicMock
from src.database.models import ToneProfile, ProjectKBFile
from src.tools.vertex_ai_provisioning import provision_knowledge_base
from src.tools.file_ingestion import ingest_file_to_knowledge_base
from src.tools.unified_research_tool import unified_research_tool
from src.tools.feedback_ingestion import format_feedback_document


class TestKnowledgeBase:
    """Test cases for the knowledge base functionality."""

    def test_tone_profile_model_exists(self):
        """Test that the ToneProfile model exists and has the correct fields."""
        # This test just verifies that the model can be imported and has expected fields
        assert hasattr(ToneProfile, "name")
        assert hasattr(ToneProfile, "profile_text")
        assert hasattr(ToneProfile, "description")
        assert hasattr(ToneProfile, "is_default")
        assert hasattr(ToneProfile, "created_at")
        assert hasattr(ToneProfile, "updated_at")

    def test_project_kb_file_model_exists(self):
        """Test that the ProjectKBFile model exists and has the correct fields."""
        # This test just verifies that the model can be imported and has expected fields
        assert hasattr(ProjectKBFile, "file_name")
        assert hasattr(ProjectKBFile, "file_uri")
        assert hasattr(ProjectKBFile, "file_size")
        assert hasattr(ProjectKBFile, "mime_type")
        assert hasattr(ProjectKBFile, "status")
        assert hasattr(ProjectKBFile, "error_message")

    def test_provision_knowledge_base(self):
        """Test the knowledge base provisioning function."""
        # Test personal tier
        data_store_id = provision_knowledge_base("personal", "test_tenant_123")
        assert data_store_id == "personal-kb-test_tenant_123"
        
        # Test project tier
        data_store_id = provision_knowledge_base("project", "test_tenant_123", 1)
        assert data_store_id == "project-kb-test_tenant_123-1"
        
        # Test invalid tier
        try:
            provision_knowledge_base("invalid", "test_tenant_123")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
        
        # Test project tier without project_id
        try:
            provision_knowledge_base("project", "test_tenant_123")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_format_feedback_document(self):
        """Test the feedback document formatting function."""
        # Create a mock feedback input
        class MockFeedbackInput:
            def __init__(self):
                self.goal = "Test goal"
                self.finalOutput = "Test output"
                self.feedbackScore = 5
                self.feedbackComment = "Test comment"
        
        feedback_input = MockFeedbackInput()
        document = format_feedback_document(feedback_input)
        
        # Verify the document contains the expected sections
        assert "[GOAL]" in document
        assert "[FINAL_OUTPUT]" in document
        assert "[SCORE]" in document
        assert "[COMMENT]" in document
        assert feedback_input.goal in document
        assert feedback_input.finalOutput in document
        assert str(feedback_input.feedbackScore) in document
        assert feedback_input.feedbackComment in document

    @patch('src.tools.unified_research_tool.redis_client')
    def test_unified_research_tool(self, mock_redis):
        """Test the unified research tool."""
        # Mock Redis responses
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        
        results = unified_research_tool("test query", "test_tenant_123", "1")
        
        # Verify the results structure
        assert "project_results" in results
        assert "personal_results" in results
        assert "platform_results" in results
        
        # Verify each tier returns results
        assert len(results["project_results"]) > 0
        assert len(results["personal_results"]) > 0
        assert len(results["platform_results"]) > 0