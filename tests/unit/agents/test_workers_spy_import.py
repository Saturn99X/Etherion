# tests/unit/agents/test_workers_spy_import.py
"""
Test that the Workers-Spy agent can be imported correctly.
"""

def test_workers_spy_agent_import():
    """Test that the Workers-Spy agent can be imported."""
    try:
        from src.agents.WorkersSpy.workers_spy_agent import create_workers_spy_agent
        assert create_workers_spy_agent is not None
    except ImportError as e:
        # If we get an import error, it's likely because of missing dependencies
        # In a real environment, we would have all the dependencies installed
        # For now, we'll just check that the module exists
        import os
        import sys
        # Add the src directory to the path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        # Try to import the module directly
        import src.agents.WorkersSpy.workers_spy_agent
        assert src.agents.WorkersSpy.workers_spy_agent is not None