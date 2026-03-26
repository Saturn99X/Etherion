"""
Unit tests for ExecutionModeController.
"""

import pytest
from src.services.execution_mode import (
    ExecutionModeController, ExecutionMode, ModeDecision
)


class TestExecutionMode:
    """Tests for ExecutionMode enum."""

    def test_execution_modes(self):
        """Test execution mode values."""
        assert ExecutionMode.SEQUENTIAL == "sequential"
        assert ExecutionMode.PARALLEL == "parallel"


class TestModeDecision:
    """Tests for ModeDecision."""

    def test_create_decision(self):
        """Test creating a mode decision."""
        decision = ModeDecision(
            mode=ExecutionMode.SEQUENTIAL,
            reason="Test reason",
            confidence=0.8,
            override_allowed=True
        )
        
        assert decision.mode == ExecutionMode.SEQUENTIAL
        assert decision.reason == "Test reason"
        assert decision.confidence == 0.8
        assert decision.override_allowed is True


class TestExecutionModeController:
    """Tests for ExecutionModeController."""

    def test_select_mode_single_specialist(self):
        """Test mode selection with single specialist."""
        controller = ExecutionModeController()
        
        decision = controller.select_mode(
            task_description="Simple task",
            specialist_count=1,
            tool_count=5
        )
        
        assert decision.mode == ExecutionMode.SEQUENTIAL
        assert "Single specialist" in decision.reason
        assert decision.confidence == 1.0
        assert decision.override_allowed is False

    def test_select_mode_high_complexity(self):
        """Test mode selection with high complexity task."""
        controller = ExecutionModeController()
        
        # Create a complex task description
        complex_task = """
        This is a complex task that requires careful coordination and integration.
        Step 1: Analyze the requirements
        Step 2: Design the architecture
        Step 3: Implement the solution
        Step 4: Test and validate
        Step 5: Deploy and monitor
        The implementation depends on prerequisite systems and must be done sequentially.
        """
        
        decision = controller.select_mode(
            task_description=complex_task,
            specialist_count=3,
            tool_count=5
        )
        
        assert decision.mode == ExecutionMode.SEQUENTIAL
        assert "complexity" in decision.reason.lower()
        assert decision.override_allowed is True

    def test_select_mode_many_specialists(self):
        """Test mode selection with many specialists."""
        controller = ExecutionModeController()
        
        decision = controller.select_mode(
            task_description="Simple task",
            specialist_count=5,
            tool_count=10
        )
        
        assert decision.mode == ExecutionMode.PARALLEL
        assert "Multiple specialists" in decision.reason
        assert decision.override_allowed is True

    def test_select_mode_simple_task(self):
        """Test mode selection with simple task."""
        controller = ExecutionModeController()
        
        decision = controller.select_mode(
            task_description="Write a simple function",
            specialist_count=2,
            tool_count=3
        )
        
        assert decision.mode == ExecutionMode.PARALLEL
        assert "Simple task" in decision.reason

    def test_select_mode_with_override(self):
        """Test mode selection with override."""
        controller = ExecutionModeController()
        
        decision = controller.select_mode(
            task_description="Any task",
            specialist_count=5,
            tool_count=10,
            override=ExecutionMode.SEQUENTIAL
        )
        
        assert decision.mode == ExecutionMode.SEQUENTIAL
        assert "overridden" in decision.reason.lower()
        assert decision.confidence == 1.0
        assert decision.override_allowed is False

    def test_analyze_complexity_simple(self):
        """Test complexity analysis for simple task."""
        controller = ExecutionModeController()
        
        score = controller._analyze_complexity("Write a function")
        assert score < 0.3

    def test_analyze_complexity_medium(self):
        """Test complexity analysis for medium task."""
        controller = ExecutionModeController()
        
        task = "Integrate the authentication system with the database. Step 1: Configure. Step 2: Test."
        score = controller._analyze_complexity(task)
        assert 0.3 <= score <= 0.7

    def test_analyze_complexity_high(self):
        """Test complexity analysis for complex task."""
        controller = ExecutionModeController()
        
        task = """
        This is a sophisticated and intricate task that requires careful coordination.
        Step 1: Analyze prerequisites
        Step 2: Design architecture
        Step 3: Implement phase 1
        Step 4: Integrate with existing systems
        Step 5: Synchronize data flows
        Step 6: Test sequentially
        Each step depends on the previous one.
        """
        score = controller._analyze_complexity(task)
        assert score > 0.7

    def test_set_and_get_mode(self):
        """Test setting and getting mode."""
        controller = ExecutionModeController()
        
        assert controller.get_mode() is None
        
        controller.set_mode(ExecutionMode.SEQUENTIAL)
        assert controller.get_mode() == ExecutionMode.SEQUENTIAL
        
        controller.set_mode(ExecutionMode.PARALLEL)
        assert controller.get_mode() == ExecutionMode.PARALLEL

    def test_can_transition(self):
        """Test mode transition rules."""
        controller = ExecutionModeController()
        
        # Currently no mid-execution transitions allowed
        assert controller.can_transition(
            ExecutionMode.SEQUENTIAL,
            ExecutionMode.PARALLEL
        ) is False
        
        assert controller.can_transition(
            ExecutionMode.PARALLEL,
            ExecutionMode.SEQUENTIAL
        ) is False

    def test_get_mode_rules_sequential(self):
        """Test getting rules for sequential mode."""
        controller = ExecutionModeController()
        
        rules = controller.get_mode_rules(ExecutionMode.SEQUENTIAL)
        
        assert rules["concurrent_specialists"] == 1
        assert rules["tool_approval"] == "immediate"
        assert rules["specialist_order"] == "sequential"
        assert rules["wait_for_completion"] is True

    def test_get_mode_rules_parallel(self):
        """Test getting rules for parallel mode."""
        controller = ExecutionModeController()
        
        rules = controller.get_mode_rules(ExecutionMode.PARALLEL)
        
        assert rules["concurrent_specialists"] == "all"
        assert rules["tool_approval"] == "queued"
        assert rules["specialist_order"] == "concurrent"
        assert rules["wait_for_completion"] is False

    def test_decision_history(self):
        """Test recording decision history."""
        controller = ExecutionModeController()
        
        assert len(controller.get_decision_history()) == 0
        
        controller.select_mode("Task 1", 2, 5)
        assert len(controller.get_decision_history()) == 1
        
        controller.select_mode("Task 2", 5, 10)
        assert len(controller.get_decision_history()) == 2
        
        history = controller.get_decision_history()
        assert "Task 1" in history[0]["task_preview"]
        assert "Task 2" in history[1]["task_preview"]

    def test_clear_history(self):
        """Test clearing decision history."""
        controller = ExecutionModeController()
        
        controller.select_mode("Task 1", 2, 5)
        controller.select_mode("Task 2", 5, 10)
        assert len(controller.get_decision_history()) == 2
        assert controller.get_mode() is not None
        
        controller.clear_history()
        assert len(controller.get_decision_history()) == 0
        assert controller.get_mode() is None

    def test_mode_decision_recorded_on_select(self):
        """Test that mode is set when decision is made."""
        controller = ExecutionModeController()
        
        assert controller.get_mode() is None
        
        decision = controller.select_mode("Task", 3, 5)
        assert controller.get_mode() == decision.mode
