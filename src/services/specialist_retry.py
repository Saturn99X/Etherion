"""
Retry wrapper for specialist invocations to improve reliability.

This module provides retry logic with exponential backoff for specialist
invocations that return empty outputs or fail.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Callable
from functools import wraps

logger = logging.getLogger(__name__)


class SpecialistRetryConfig:
    """Configuration for specialist retry behavior."""
    
    MAX_RETRIES = 3
    INITIAL_DELAY = 1.0  # seconds
    MAX_DELAY = 10.0  # seconds
    BACKOFF_FACTOR = 2.0
    MIN_OUTPUT_LENGTH = 10  # characters


async def retry_specialist_invocation(
    specialist_func: Callable,
    *args,
    max_retries: int = SpecialistRetryConfig.MAX_RETRIES,
    min_output_length: int = SpecialistRetryConfig.MIN_OUTPUT_LENGTH,
    **kwargs
) -> Dict[str, Any]:
    """
    Retry specialist invocation with exponential backoff.
    
    Args:
        specialist_func: Async function to invoke specialist
        max_retries: Maximum number of retry attempts (default: 3)
        min_output_length: Minimum acceptable output length in characters (default: 10)
        *args, **kwargs: Arguments to pass to specialist_func
    
    Returns:
        Dict with specialist response
        
    Raises:
        Exception: If all retry attempts fail with errors
    
    Example:
        async def execute_specialist():
            return await executor.execute(instruction="...")
        
        result = await retry_specialist_invocation(
            execute_specialist,
            max_retries=3,
            min_output_length=10
        )
    """
    delay = SpecialistRetryConfig.INITIAL_DELAY
    last_error = None
    last_result = None
    
    for attempt in range(max_retries + 1):
        try:
            # Invoke specialist
            result = await specialist_func(*args, **kwargs)
            last_result = result
            
            # Extract output text for validation
            output = result.get('output', '') if isinstance(result, dict) else result
            
            # DEBUG: Log what we're validating
            logger.debug(
                f"Retry attempt {attempt + 1}/{max_retries + 1}: "
                f"output type={type(output).__name__}, "
                f"raw_length={len(str(output)) if output else 0}"
            )
            
            if isinstance(output, str):
                output_text = output
            elif isinstance(output, dict):
                output_text = output.get('text', str(output))
                logger.debug(f"Extracted text from dict: length={len(output_text)}")
            elif isinstance(output, list):
                # Handle list-of-parts format (common with Gemini/LangChain)
                output_text = ''.join(
                    part.get('text', '') if isinstance(part, dict) else str(part)
                    for part in output
                )
                logger.debug(f"Extracted text from list: length={len(output_text)}")
            else:
                output_text = str(output)
                logger.debug(f"Converted to string: length={len(output_text)}")
            
            # Validate output length
            output_length = len(output_text.strip())
            logger.debug(f"Final output length after strip: {output_length} chars")
            if output_length >= min_output_length:
                if attempt > 0:
                    logger.info(
                        f"Specialist invocation successful on attempt {attempt + 1}/{max_retries + 1} "
                        f"(output length: {output_length} chars)"
                    )
                return result
            
            # Output too short - retry if attempts remain
            logger.warning(
                f"Specialist returned short output ({output_length} chars, minimum {min_output_length}) "
                f"on attempt {attempt + 1}/{max_retries + 1}"
            )
            
            if attempt < max_retries:
                logger.info(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)
                delay = min(delay * SpecialistRetryConfig.BACKOFF_FACTOR, 
                           SpecialistRetryConfig.MAX_DELAY)
            else:
                logger.error(
                    f"Specialist failed after {max_retries + 1} attempts - "
                    f"returning last result with short output"
                )
                return result
        
        except Exception as e:
            last_error = e
            logger.error(
                f"Specialist invocation failed on attempt {attempt + 1}/{max_retries + 1}: {e}",
                exc_info=True
            )
            
            if attempt < max_retries:
                logger.info(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)
                delay = min(delay * SpecialistRetryConfig.BACKOFF_FACTOR,
                           SpecialistRetryConfig.MAX_DELAY)
            else:
                logger.error(
                    f"Specialist failed after {max_retries + 1} attempts with errors"
                )
                # If we have a last result (even with short output), return it
                if last_result is not None:
                    logger.warning("Returning last result despite errors")
                    return last_result
                # Otherwise raise the last error
                raise
    
    # Should not reach here, but handle gracefully
    if last_error:
        raise last_error
    
    if last_result is not None:
        return last_result
    
    return {"output": "", "success": False, "error": "Max retries exceeded"}


def with_retry(max_retries: int = 3, min_output_length: int = 10):
    """
    Decorator to add retry logic to specialist invocation functions.
    
    Args:
        max_retries: Maximum number of retry attempts
        min_output_length: Minimum acceptable output length
    
    Usage:
        @with_retry(max_retries=3, min_output_length=10)
        async def invoke_specialist(...):
            ...
    
    Example:
        @with_retry(max_retries=5, min_output_length=20)
        async def execute_critical_specialist(instruction: str):
            executor = get_executor()
            return await executor.execute(instruction=instruction)
        
        result = await execute_critical_specialist("Analyze this data...")
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_specialist_invocation(
                func,
                *args,
                max_retries=max_retries,
                min_output_length=min_output_length,
                **kwargs
            )
        return wrapper
    return decorator
