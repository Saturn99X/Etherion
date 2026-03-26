# src/utils/llm_wrapper.py (DEPRECATED)
# DEPRECATED: Prefer explicit cost tracking via src/services/pricing/* and direct LLM clients.
from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import BaseMessage
from typing import Any, List, Union
import asyncio
from src.utils.token_counter import count_tokens_and_calculate_cost


def get_llm_with_cost_tracking(llm_client: BaseLanguageModel) -> BaseLanguageModel:
    """
    Wrap an LLM client to add token counting and cost tracking.
    
    Args:
        llm_client: The LLM client to wrap
        
    Returns:
        BaseLanguageModel: The wrapped LLM client
    """
    # Store original methods
    original_invoke = llm_client.invoke
    original_ainvoke = llm_client.ainvoke
    
    def wrapped_invoke(input: Union[str, List[BaseMessage]], **kwargs) -> Any:
        # Record input text for token counting
        input_text = input if isinstance(input, str) else str(input)
        
        # Call original invoke
        result = original_invoke(input, **kwargs)
        
        # Count tokens and calculate cost
        output_text = str(result)
        cost_data = count_tokens_and_calculate_cost(llm_client, input_text, output_text)
        
        # Log cost to database (implementation would go here)
        print(f"LLM call cost: {cost_data['total_cost']} USD")
        
        return result
    
    async def wrapped_ainvoke(input: Union[str, List[BaseMessage]], **kwargs) -> Any:
        # Record input text for token counting
        input_text = input if isinstance(input, str) else str(input)
        
        # Call original ainvoke
        result = await original_ainvoke(input, **kwargs)
        
        # Count tokens and calculate cost
        output_text = str(result)
        cost_data = count_tokens_and_calculate_cost(llm_client, input_text, output_text)
        
        # Log cost to database (implementation would go here)
        print(f"Async LLM call cost: {cost_data['total_cost']} USD")
        
        return result
    
    # Monkey-patch the methods
    llm_client.invoke = wrapped_invoke
    llm_client.ainvoke = wrapped_ainvoke
    
    return llm_client