#!/usr/bin/env python3
"""
Integration tests for timeout scenarios in MCP tools.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
import time
from src.tools.mcp.base_mcp_tool import (
    BaseMCPTool, 
    MCPToolResult, 
    TimeoutError, 
    RateLimitError,
    InvalidCredentialsError
)


class TestMcpTool(BaseMCPTool):
    """Test MCP tool implementation for timeout testing."""
    
    def __init__(self):
        super().__init__("test_tool", "Test MCP tool for timeout testing")
    
    async def execute(self, params):
        """Execute the test tool."""
        return await self._retry_with_backoff(self._test_operation, params)
    
    async def _test_operation(self, params):
        """Test operation that can be configured to timeout."""
        if params.get('should_timeout', False):
            # Simulate a long-running operation
            await asyncio.sleep(params.get('delay', 10))
        elif params.get('should_rate_limit', False):
            raise RateLimitError("Rate limit exceeded for testing")
        elif params.get('should_credential_error', False):
            raise InvalidCredentialsError("Invalid credentials for testing")
        
        return self._create_result(True, data={"result": "success"})


class TestApiCallTimeouts:
    """Test API call timeout scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_tool = TestMcpTool()

    @pytest.mark.asyncio
    async def test_api_call_timeout_scenarios(self):
        """Test API call timeout scenarios."""
        # Test with a short timeout
        self.test_tool.connect_timeout = 1
        self.test_tool.read_timeout = 1
        
        # This should timeout
        params = {'should_timeout': True, 'delay': 5}
        
        with pytest.raises(TimeoutError):
            await self.test_tool.execute(params)

    @pytest.mark.asyncio
    async def test_timeout_configuration_validation(self):
        """Test timeout configuration validation."""
        # Test default timeouts
        assert self.test_tool.connect_timeout == 10
        assert self.test_tool.read_timeout == 30
        
        # Test custom timeouts
        custom_tool = TestMcpTool()
        custom_tool.connect_timeout = 5
        custom_tool.read_timeout = 15
        
        assert custom_tool.connect_timeout == 5
        assert custom_tool.read_timeout == 15

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self):
        """Test timeout error handling."""
        self.test_tool.connect_timeout = 1
        self.test_tool.read_timeout = 1
        self.test_tool.max_retries = 1  # Reduce retries for faster testing
        
        params = {'should_timeout': True, 'delay': 5}
        
        with pytest.raises(TimeoutError) as exc_info:
            await self.test_tool.execute(params)
        
        assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_timeout_recovery_mechanisms(self):
        """Test timeout recovery mechanisms."""
        # First call times out
        self.test_tool.connect_timeout = 1
        self.test_tool.read_timeout = 1
        
        params_timeout = {'should_timeout': True, 'delay': 5}
        
        start_time = time.time()
        with pytest.raises(TimeoutError):
            await self.test_tool.execute(params_timeout)
        timeout_duration = time.time() - start_time
        
        # Second call succeeds quickly
        self.test_tool.connect_timeout = 10
        self.test_tool.read_timeout = 10
        
        params_success = {'should_timeout': False}
        
        start_time = time.time()
        result = await self.test_tool.execute(params_success)
        success_duration = time.time() - start_time
        
        # Verify the tool can recover from timeout
        assert result.success is True
        assert result.data == {"result": "success"}
        # Success should be much faster than timeout
        assert success_duration < timeout_duration

    @pytest.mark.asyncio
    async def test_timeout_retry_logic(self):
        """Test timeout retry logic."""
        self.test_tool.connect_timeout = 1
        self.test_tool.read_timeout = 1
        self.test_tool.max_retries = 3
        
        params = {'should_timeout': True, 'delay': 5}
        
        # Track the number of attempts
        original_retry = self.test_tool._retry_with_backoff
        attempt_count = 0
        
        async def tracked_retry(func, *args, max_retries=None, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            return await original_retry(func, *args, max_retries=max_retries, **kwargs)
        
        self.test_tool._retry_with_backoff = tracked_retry
        
        with pytest.raises(TimeoutError):
            await self.test_tool.execute(params)
        
        # Should have attempted retries
        assert attempt_count == 3  # max_retries + 1

    @pytest.mark.asyncio
    async def test_timeout_fallback_mechanisms(self):
        """Test timeout fallback mechanisms."""
        self.test_tool.connect_timeout = 1
        self.test_tool.read_timeout = 1
        
        # Create a tool with fallback logic
        class FallbackTestTool(TestMcpTool):
            def __init__(self):
                super().__init__()
                self.fallback_used = False
            
            async def execute(self, params):
                try:
                    return await super().execute(params)
                except TimeoutError:
                    self.fallback_used = True
                    # Fallback implementation
                    return self._create_result(True, data={"result": "fallback_success"})
        
        fallback_tool = FallbackTestTool()
        params = {'should_timeout': True, 'delay': 5}
        
        # This should trigger the fallback
        result = await fallback_tool.execute(params)
        
        assert fallback_tool.fallback_used is True
        assert result.success is True
        assert result.data == {"result": "fallback_success"}

    @pytest.mark.asyncio
    async def test_timeout_error_reporting(self):
        """Test timeout error reporting."""
        self.test_tool.connect_timeout = 1
        self.test_tool.read_timeout = 1
        
        params = {'should_timeout': True, 'delay': 5}
        
        try:
            await self.test_tool.execute(params)
            assert False, "Should have raised TimeoutError"
        except TimeoutError as e:
            # Verify error has proper information
            assert hasattr(e, 'error_code')
            assert e.error_code == "TIMEOUT_ERROR"
            assert hasattr(e, 'timestamp')
            assert isinstance(e.timestamp, float)

    @pytest.mark.asyncio
    async def test_performance_under_timeout_conditions(self):
        """Test performance under timeout conditions."""
        # Measure normal operation time
        self.test_tool.connect_timeout = 10
        self.test_tool.read_timeout = 10
        
        params_normal = {'should_timeout': False}
        
        start_time = time.time()
        result = await self.test_tool.execute(params_normal)
        normal_duration = time.time() - start_time
        
        assert result.success is True
        assert normal_duration < 1.0  # Should be very fast

    @pytest.mark.asyncio
    async def test_timeout_impact_on_system_performance(self):
        """Test timeout impact on system performance."""
        self.test_tool.connect_timeout = 1
        self.test_tool.read_timeout = 1
        
        # Run multiple timeout operations concurrently
        async def timeout_operation():
            params = {'should_timeout': True, 'delay': 3}
            try:
                await self.test_tool.execute(params)
                return "success"
            except TimeoutError:
                return "timeout"
        
        # Create multiple concurrent operations
        tasks = [timeout_operation() for _ in range(5)]
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_duration = time.time() - start_time
        
        # All should timeout (or raise exceptions)
        timeout_count = sum(1 for result in results if result == "timeout" or isinstance(result, TimeoutError))
        assert timeout_count >= 4  # Most should timeout
        
        # Verify system can handle concurrent timeouts
        assert total_duration < 10  # Should not take too long even with timeouts

    @pytest.mark.asyncio
    async def test_timeout_recovery_performance(self):
        """Test timeout recovery performance."""
        # First cause a timeout
        self.test_tool.connect_timeout = 1
        self.test_tool.read_timeout = 1
        
        params_timeout = {'should_timeout': True, 'delay': 3}
        
        try:
            await self.test_tool.execute(params_timeout)
        except TimeoutError:
            pass  # Expected
        
        # Then perform a successful operation quickly
        self.test_tool.connect_timeout = 10
        self.test_tool.read_timeout = 10
        
        params_success = {'should_timeout': False}
        
        start_time = time.time()
        result = await self.test_tool.execute(params_success)
        recovery_duration = time.time() - start_time
        
        # Recovery should be fast
        assert result.success is True
        assert recovery_duration < 1.0

    @pytest.mark.asyncio
    async def test_timeout_scalability(self):
        """Test timeout scalability with many concurrent operations."""
        self.test_tool.connect_timeout = 1
        self.test_tool.read_timeout = 1
        
        async def maybe_timeout_operation(should_timeout):
            params = {'should_timeout': should_timeout, 'delay': 3}
            try:
                await self.test_tool.execute(params)
                return "success"
            except TimeoutError:
                return "timeout"
        
        # Mix of operations that timeout and succeed
        tasks = []
        for i in range(20):
            should_timeout = (i % 2 == 0)  # Half timeout, half succeed
            tasks.append(maybe_timeout_operation(should_timeout))
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_duration = time.time() - start_time
        
        # Verify system handles mixed load
        assert len(results) == 20
        assert total_duration < 20  # Should handle concurrent operations efficiently


if __name__ == "__main__":
    pytest.main([__file__, "-v"])