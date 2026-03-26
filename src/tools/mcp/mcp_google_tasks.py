"""
Google Tasks MCP Tool (vendor-bridged)
- list_task_lists, get_task_list, create_task_list, update_task_list, delete_task_list
- list_tasks, get_task, create_task, update_task, delete_task, move_task
"""
from __future__ import annotations

from typing import Any, Dict
import asyncio

from .base_mcp_tool import RateLimitConfig, RetryConfig, CircuitBreakerConfig, AuthType, ValidationError
from .google_workspace_base import GoogleWorkspaceBase
from .vendor_bridge.google_workspace_adapter import GoogleWorkspaceVendorAdapter


class MCPGoogleTasksTool(GoogleWorkspaceBase):
    TASKS_BASE = "https://tasks.googleapis.com/tasks/v1"

    SCOPES_READ = [
        "https://www.googleapis.com/auth/tasks.readonly",
    ]
    SCOPES_WRITE = [
        "https://www.googleapis.com/auth/tasks",
    ]

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(requests_per_second=10.0, burst_size=20)
    DEFAULT_RETRY_CONFIG = RetryConfig(max_retries=3, initial_delay=1.0, max_delay=30.0)
    DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)

    def __init__(self):
        super().__init__(
            name="mcp_google_tasks",
            description="Google Tasks operations (CRUD)",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            base_url=self.TASKS_BASE,
            rate_limit_config=self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )

    def _get_operation_schema(self, operation: str):
        STR = str
        schemas = {
            # Task lists
            "list_task_lists": {
                "max_results": {"required": False, "type": int},
                "page_token": {"required": False, "type": STR},
            },
            "get_task_list": {
                "task_list_id": {"required": True, "type": STR},
            },
            "create_task_list": {
                "title": {"required": True, "type": STR},
            },
            "update_task_list": {
                "task_list_id": {"required": True, "type": STR},
                "title": {"required": True, "type": STR},
            },
            "delete_task_list": {
                "task_list_id": {"required": True, "type": STR},
            },
            # Tasks
            "list_tasks": {
                "task_list_id": {"required": True, "type": STR},
                "max_results": {"required": False, "type": int},
                "page_token": {"required": False, "type": STR},
                "show_completed": {"required": False, "type": bool},
                "show_deleted": {"required": False, "type": bool},
                "show_hidden": {"required": False, "type": bool},
                "show_assigned": {"required": False, "type": bool},
                "completed_max": {"required": False, "type": STR},
                "completed_min": {"required": False, "type": STR},
                "due_max": {"required": False, "type": STR},
                "due_min": {"required": False, "type": STR},
                "updated_min": {"required": False, "type": STR},
            },
            "get_task": {
                "task_list_id": {"required": True, "type": STR},
                "task_id": {"required": True, "type": STR},
            },
            "create_task": {
                "task_list_id": {"required": True, "type": STR},
                "title": {"required": True, "type": STR},
                "notes": {"required": False, "type": STR},
                "due": {"required": False, "type": STR},
                "parent": {"required": False, "type": STR},
                "previous": {"required": False, "type": STR},
            },
            "update_task": {
                "task_list_id": {"required": True, "type": STR},
                "task_id": {"required": True, "type": STR},
                "title": {"required": False, "type": STR},
                "notes": {"required": False, "type": STR},
                "status": {"required": False, "type": STR},
                "due": {"required": False, "type": STR},
            },
            "delete_task": {
                "task_list_id": {"required": True, "type": STR},
                "task_id": {"required": True, "type": STR},
            },
            "move_task": {
                "task_list_id": {"required": True, "type": STR},
                "task_id": {"required": True, "type": STR},
                "parent": {"required": False, "type": STR},
                "previous": {"required": False, "type": STR},
                "destination_task_list": {"required": False, "type": STR},
            },
        }
        return schemas.get((operation or "").lower())

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        return (
            operation in {
                "create_task_list", "update_task_list", "delete_task_list",
                "create_task", "update_task", "delete_task", "move_task"
            }
        ) or super()._is_write_operation(operation, params)

    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]):
        op = (operation or "").lower()
        adapter = GoogleWorkspaceVendorAdapter(str(tenant_id))

        # Task lists
        if op == "list_task_lists":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks.readonly"])
            max_results = int(params.get("max_results", 1000))
            page_token = params.get("page_token")
            def _list():
                kwargs: Dict[str, Any] = {"maxResults": max_results}
                if page_token:
                    kwargs["pageToken"] = page_token
                return tasks.tasklists().list(**kwargs).execute()
            return await asyncio.to_thread(_list)

        if op == "get_task_list":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks.readonly"])
            task_list_id = params["task_list_id"]
            def _get():
                return tasks.tasklists().get(tasklist=task_list_id).execute()
            return await asyncio.to_thread(_get)

        if op == "create_task_list":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks"])
            title = params["title"]
            def _create():
                return tasks.tasklists().insert(body={"title": title}).execute()
            return await asyncio.to_thread(_create)

        if op == "update_task_list":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks"])
            task_list_id = params["task_list_id"]
            title = params["title"]
            def _update():
                return tasks.tasklists().update(tasklist=task_list_id, body={"id": task_list_id, "title": title}).execute()
            return await asyncio.to_thread(_update)

        if op == "delete_task_list":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks"])
            task_list_id = params["task_list_id"]
            def _delete():
                tasks.tasklists().delete(tasklist=task_list_id).execute()
                return {"deleted": True}
            return await asyncio.to_thread(_delete)

        # Tasks
        if op == "list_tasks":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks.readonly"])
            task_list_id = params["task_list_id"]
            def _list():
                kwargs: Dict[str, Any] = {"tasklist": task_list_id}
                for k in ("max_results", "page_token", "show_completed", "show_deleted", "show_hidden", "show_assigned", "completed_max", "completed_min", "due_max", "due_min", "updated_min"):
                    v = params.get(k)
                    if v is None:
                        continue
                    # map names to API
                    key_map = {
                        "max_results": "maxResults", "page_token": "pageToken",
                        "show_completed": "showCompleted", "show_deleted": "showDeleted", "show_hidden": "showHidden", "show_assigned": "showAssigned",
                        "completed_max": "completedMax", "completed_min": "completedMin",
                        "due_max": "dueMax", "due_min": "dueMin", "updated_min": "updatedMin",
                    }
                    kwargs[key_map[k]] = v if k != "max_results" else int(v)
                return tasks.tasks().list(**kwargs).execute()
            return await asyncio.to_thread(_list)

        if op == "get_task":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks.readonly"])
            task_list_id = params["task_list_id"]
            task_id = params["task_id"]
            def _get():
                return tasks.tasks().get(tasklist=task_list_id, task=task_id).execute()
            return await asyncio.to_thread(_get)

        if op == "create_task":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks"])
            task_list_id = params["task_list_id"]
            body: Dict[str, Any] = {"title": params["title"]}
            if params.get("notes"):
                body["notes"] = params["notes"]
            if params.get("due"):
                body["due"] = params["due"]
            parent = params.get("parent")
            previous = params.get("previous")
            def _insert():
                kwargs: Dict[str, Any] = {"tasklist": task_list_id, "body": body}
                if parent:
                    kwargs["parent"] = parent
                if previous:
                    kwargs["previous"] = previous
                return tasks.tasks().insert(**kwargs).execute()
            return await asyncio.to_thread(_insert)

        if op == "update_task":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks"])
            task_list_id = params["task_list_id"]
            task_id = params["task_id"]
            body: Dict[str, Any] = {k: v for k, v in {
                "title": params.get("title"),
                "notes": params.get("notes"),
                "status": params.get("status"),
                "due": params.get("due"),
            }.items() if v is not None}
            def _update():
                return tasks.tasks().update(tasklist=task_list_id, task=task_id, body=body).execute()
            return await asyncio.to_thread(_update)

        if op == "delete_task":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks"])
            task_list_id = params["task_list_id"]
            task_id = params["task_id"]
            def _delete():
                tasks.tasks().delete(tasklist=task_list_id, task=task_id).execute()
                return {"deleted": True}
            return await asyncio.to_thread(_delete)

        if op == "move_task":
            tasks = await adapter.get_tasks(["https://www.googleapis.com/auth/tasks"])
            task_list_id = params["task_list_id"]
            task_id = params["task_id"]
            parent = params.get("parent")
            previous = params.get("previous")
            destination = params.get("destination_task_list")
            if destination and destination != task_list_id:
                # Move across lists: get task, insert into destination, then delete
                def _move_cross():
                    t = tasks.tasks().get(tasklist=task_list_id, task=task_id).execute()
                    body = {k: t.get(k) for k in ("title", "notes", "due", "status") if t.get(k) is not None}
                    kwargs: Dict[str, Any] = {"tasklist": destination, "body": body}
                    if parent:
                        kwargs["parent"] = parent
                    if previous:
                        kwargs["previous"] = previous
                    created = tasks.tasks().insert(**kwargs).execute()
                    tasks.tasks().delete(tasklist=task_list_id, task=task_id).execute()
                    return {"moved": True, "new_task_id": created.get("id")}
                return await asyncio.to_thread(_move_cross)
            else:
                def _move():
                    kwargs: Dict[str, Any] = {"tasklist": task_list_id, "task": task_id}
                    if parent:
                        kwargs["parent"] = parent
                    if previous:
                        kwargs["previous"] = previous
                    return tasks.tasks().move(**kwargs).execute()
                return await asyncio.to_thread(_move)

        raise ValidationError(f"Unsupported operation: {operation}")
