# tests/test_orchestrator_enhancements.py
import pytest
from decimal import Decimal
from src.utils.token_counter import count_tokens_and_calculate_cost, MODEL_PRICING
from src.utils.tool_discovery import get_available_tools_and_agents
from src.utils.credit_manager import check_tenant_credits, deduct_credits_for_execution, add_credits_to_tenant


class TestOrchestratorEnhancements:
    """Test cases for the orchestrator enhancements."""

    def test_token_counter_exists(self):
        """Test that the token counter utility exists."""
        # This test just verifies that the module can be imported
        assert hasattr(count_tokens_and_calculate_cost, "__call__")
        assert isinstance(MODEL_PRICING, dict)

    def test_tool_discovery_exists(self):
        """Test that the tool discovery utility exists."""
        # This test just verifies that the module can be imported
        assert hasattr(get_available_tools_and_agents, "__call__")

    def test_credit_manager_exists(self):
        """Test that the credit manager utility exists."""
        # This test just verifies that the module can be imported
        assert hasattr(check_tenant_credits, "__call__")
        assert hasattr(deduct_credits_for_execution, "__call__")
        assert hasattr(add_credits_to_tenant, "__call__")

    def test_token_counting_with_known_model(self):
        """Test token counting with a known model."""
        # Create a mock LLM client
        class MockLLMClient:
            def __init__(self):
                self.model_name = "gemini-2.5-pro"
            
            def get_num_tokens(self, text):
                return len(text.split())
        
        llm_client = MockLLMClient()
        input_text = "This is a test input with seven words"
        output_text = "This is a test output with six words"
        
        result = count_tokens_and_calculate_cost(llm_client, input_text, output_text)
        
        # Verify the structure of the result
        assert "input_tokens" in result
        assert "output_tokens" in result
        assert "input_cost" in result
        assert "output_cost" in result
        assert "total_cost" in result
        assert "model_name" in result
        
        # Verify the values (accounting for the fact that split() counts words, not tokens)
        assert result["input_tokens"] == 8  # "This is a test input with seven words" has 8 words
        assert result["output_tokens"] == 8  # "This is a test output with six words" has 8 words
        assert result["model_name"] == "gemini-2.5-pro"
        assert isinstance(result["total_cost"], Decimal)

    def test_token_counting_with_unknown_model(self):
        """Test token counting with an unknown model."""
        # Create a mock LLM client with unknown model
        class MockLLMClient:
            def __init__(self):
                self.model_name = "unknown-model"
            
            def get_num_tokens(self, text):
                return len(text.split())
        
        llm_client = MockLLMClient()
        input_text = "This is a test input"
        output_text = "This is a test output"
        
        result = count_tokens_and_calculate_cost(llm_client, input_text, output_text)
        
        # Verify that costs are zero for unknown model
        assert result["input_cost"] == Decimal("0")
        assert result["output_cost"] == Decimal("0")
        assert result["total_cost"] == Decimal("0")

    def test_tool_discovery_returns_string(self):
        """Test that tool discovery returns a string."""
        result = get_available_tools_and_agents()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_model_pricing_structure(self):
        """Test that MODEL_PRICING has the correct structure."""
        assert "gemini-2.5-pro" in MODEL_PRICING
        assert "gemini-2.5-flash" in MODEL_PRICING
        
        for model_name, pricing in MODEL_PRICING.items():
            assert "input" in pricing
            assert "output" in pricing
            assert isinstance(pricing["input"], Decimal)
            assert isinstance(pricing["output"], Decimal)