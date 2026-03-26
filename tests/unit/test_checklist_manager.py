"""
Unit tests for ChecklistManager.
"""

import pytest
import json
from src.services.checklist_manager import ChecklistManager, Checklist, ChecklistItem


class TestChecklistItem:
    """Tests for ChecklistItem."""

    def test_create_item(self):
        """Test creating a checklist item."""
        item = ChecklistItem(id="item_1", description="Test task")
        assert item.id == "item_1"
        assert item.description == "Test task"
        assert item.completed is False
        assert item.validated_by is None
        assert item.validation_note is None
        assert item.created_at is not None
        assert item.completed_at is None

    def test_mark_complete(self):
        """Test marking an item complete."""
        item = ChecklistItem(id="item_1", description="Test task")
        item.mark_complete(validated_by="agent_1", validation_note="Looks good")
        
        assert item.completed is True
        assert item.validated_by == "agent_1"
        assert item.validation_note == "Looks good"
        assert item.completed_at is not None

    def test_to_dict(self):
        """Test converting item to dictionary."""
        item = ChecklistItem(id="item_1", description="Test task")
        data = item.to_dict()
        
        assert data["id"] == "item_1"
        assert data["description"] == "Test task"
        assert data["completed"] is False


class TestChecklist:
    """Tests for Checklist."""

    def test_create_checklist(self):
        """Test creating a checklist."""
        checklist = Checklist(id="cl_1", owner_id="team_1", owner_type="team")
        
        assert checklist.id == "cl_1"
        assert checklist.owner_id == "team_1"
        assert checklist.owner_type == "team"
        assert len(checklist.items) == 0
        assert checklist.completed_at is None

    def test_add_item(self):
        """Test adding items to checklist."""
        checklist = Checklist(id="cl_1", owner_id="team_1", owner_type="team")
        
        item1 = checklist.add_item("Task 1")
        item2 = checklist.add_item("Task 2")
        
        assert len(checklist.items) == 2
        assert item1.description == "Task 1"
        assert item2.description == "Task 2"

    def test_remove_item(self):
        """Test removing items from checklist."""
        checklist = Checklist(id="cl_1", owner_id="team_1", owner_type="team")
        item = checklist.add_item("Task 1")
        
        assert len(checklist.items) == 1
        result = checklist.remove_item(item.id)
        assert result is True
        assert len(checklist.items) == 0

    def test_get_item(self):
        """Test getting an item by ID."""
        checklist = Checklist(id="cl_1", owner_id="team_1", owner_type="team")
        item = checklist.add_item("Task 1")
        
        found = checklist.get_item(item.id)
        assert found is not None
        assert found.id == item.id
        
        not_found = checklist.get_item("nonexistent")
        assert not_found is None

    def test_mark_item_complete(self):
        """Test marking an item complete."""
        checklist = Checklist(id="cl_1", owner_id="team_1", owner_type="team")
        item = checklist.add_item("Task 1")
        
        result = checklist.mark_item_complete(item.id, validated_by="agent_1")
        assert result is True
        assert item.completed is True
        assert item.validated_by == "agent_1"

    def test_is_complete(self):
        """Test checking if checklist is complete."""
        checklist = Checklist(id="cl_1", owner_id="team_1", owner_type="team")
        
        # Empty checklist is not complete
        assert checklist.is_complete() is False
        
        # Add items
        item1 = checklist.add_item("Task 1")
        item2 = checklist.add_item("Task 2")
        assert checklist.is_complete() is False
        
        # Complete one item
        checklist.mark_item_complete(item1.id)
        assert checklist.is_complete() is False
        
        # Complete all items
        checklist.mark_item_complete(item2.id)
        assert checklist.is_complete() is True
        assert checklist.completed_at is not None

    def test_get_progress(self):
        """Test getting completion progress."""
        checklist = Checklist(id="cl_1", owner_id="team_1", owner_type="team")
        
        # Empty checklist
        progress = checklist.get_progress()
        assert progress["total"] == 0
        assert progress["completed"] == 0
        assert progress["percentage"] == 0
        
        # Add items
        item1 = checklist.add_item("Task 1")
        item2 = checklist.add_item("Task 2")
        
        progress = checklist.get_progress()
        assert progress["total"] == 2
        assert progress["completed"] == 0
        assert progress["percentage"] == 0
        
        # Complete one item
        checklist.mark_item_complete(item1.id)
        progress = checklist.get_progress()
        assert progress["total"] == 2
        assert progress["completed"] == 1
        assert progress["percentage"] == 50

    def test_to_dict(self):
        """Test converting checklist to dictionary."""
        checklist = Checklist(id="cl_1", owner_id="team_1", owner_type="team")
        checklist.add_item("Task 1")
        
        data = checklist.to_dict()
        assert data["id"] == "cl_1"
        assert data["owner_id"] == "team_1"
        assert data["owner_type"] == "team"
        assert len(data["items"]) == 1
        assert "progress" in data

    def test_from_dict(self):
        """Test creating checklist from dictionary."""
        data = {
            "id": "cl_1",
            "owner_id": "team_1",
            "owner_type": "team",
            "items": [
                {"id": "item_1", "description": "Task 1", "completed": False, 
                 "validated_by": None, "validation_note": None, 
                 "created_at": "2026-03-16T19:00:00", "completed_at": None}
            ],
            "created_at": "2026-03-16T19:00:00",
            "completed_at": None
        }
        
        checklist = Checklist.from_dict(data)
        assert checklist.id == "cl_1"
        assert checklist.owner_id == "team_1"
        assert len(checklist.items) == 1
        assert checklist.items[0].description == "Task 1"


class TestChecklistManager:
    """Tests for ChecklistManager."""

    def test_create_checklist(self):
        """Test creating a checklist."""
        manager = ChecklistManager()
        checklist = manager.create_checklist(owner_id="team_1", owner_type="team")
        
        assert checklist.id is not None
        assert checklist.owner_id == "team_1"
        assert checklist.owner_type == "team"
        assert checklist.id in manager.checklists

    def test_create_checklist_with_task_description(self):
        """Test creating a checklist with task description."""
        manager = ChecklistManager()
        task_desc = """
        1. Research the topic
        2. Write the code
        3. Test the implementation
        """
        
        checklist = manager.create_checklist(
            owner_id="team_1", 
            owner_type="team",
            task_description=task_desc
        )
        
        assert len(checklist.items) == 3
        assert "Research" in checklist.items[0].description
        assert "Write" in checklist.items[1].description
        assert "Test" in checklist.items[2].description

    def test_get_checklist(self):
        """Test getting a checklist by ID."""
        manager = ChecklistManager()
        checklist = manager.create_checklist(owner_id="team_1", owner_type="team")
        
        found = manager.get_checklist(checklist.id)
        assert found is not None
        assert found.id == checklist.id
        
        not_found = manager.get_checklist("nonexistent")
        assert not_found is None

    def test_get_checklists_by_owner(self):
        """Test getting checklists by owner."""
        manager = ChecklistManager()
        cl1 = manager.create_checklist(owner_id="team_1", owner_type="team")
        cl2 = manager.create_checklist(owner_id="team_1", owner_type="team")
        cl3 = manager.create_checklist(owner_id="team_2", owner_type="team")
        
        team1_checklists = manager.get_checklists_by_owner("team_1")
        assert len(team1_checklists) == 2
        assert cl1 in team1_checklists
        assert cl2 in team1_checklists
        
        team2_checklists = manager.get_checklists_by_owner("team_2")
        assert len(team2_checklists) == 1
        assert cl3 in team2_checklists

    def test_delete_checklist(self):
        """Test deleting a checklist."""
        manager = ChecklistManager()
        checklist = manager.create_checklist(owner_id="team_1", owner_type="team")
        
        assert checklist.id in manager.checklists
        result = manager.delete_checklist(checklist.id)
        assert result is True
        assert checklist.id not in manager.checklists

    def test_serialize_deserialize(self):
        """Test serializing and deserializing checklists."""
        manager = ChecklistManager()
        checklist = manager.create_checklist(owner_id="team_1", owner_type="team")
        checklist.add_item("Task 1")
        checklist.add_item("Task 2")
        
        # Serialize
        json_str = manager.serialize_checklist(checklist.id)
        assert json_str is not None
        
        # Clear and deserialize
        manager.clear()
        assert len(manager.checklists) == 0
        
        restored = manager.deserialize_checklist(json_str)
        assert restored is not None
        assert restored.id == checklist.id
        assert len(restored.items) == 2

    def test_get_all_checklists(self):
        """Test getting all checklists."""
        manager = ChecklistManager()
        cl1 = manager.create_checklist(owner_id="team_1", owner_type="team")
        cl2 = manager.create_checklist(owner_id="team_2", owner_type="team")
        
        all_checklists = manager.get_all_checklists()
        assert len(all_checklists) == 2
        assert cl1 in all_checklists
        assert cl2 in all_checklists

    def test_clear(self):
        """Test clearing all checklists."""
        manager = ChecklistManager()
        manager.create_checklist(owner_id="team_1", owner_type="team")
        manager.create_checklist(owner_id="team_2", owner_type="team")
        
        assert len(manager.checklists) == 2
        manager.clear()
        assert len(manager.checklists) == 0
