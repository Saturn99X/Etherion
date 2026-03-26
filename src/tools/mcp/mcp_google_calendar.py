"""
Google Calendar MCP Tool (vendor-bridged)

Operations:
- list_calendars
- get_events
- create_event
- update_event
- delete_event
"""
from __future__ import annotations

from typing import Any, Dict, Optional, List
import asyncio

from .base_mcp_tool import RateLimitConfig, RetryConfig, CircuitBreakerConfig, AuthType, ValidationError
from .google_workspace_base import GoogleWorkspaceBase
from .vendor_bridge.google_workspace_adapter import GoogleWorkspaceVendorAdapter


class MCPGoogleCalendarTool(GoogleWorkspaceBase):
    CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"

    # Scopes
    SCOPES_READ = [
        "https://www.googleapis.com/auth/calendar.readonly",
    ]
    SCOPES_WRITE = [
        "https://www.googleapis.com/auth/calendar.events",
    ]

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(
        requests_per_second=10.0,
        requests_per_minute=600.0,
        requests_per_hour=36000.0,
        burst_size=20,
    )

    DEFAULT_RETRY_CONFIG = RetryConfig(max_retries=3, initial_delay=1.0, max_delay=30.0)
    DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)

    def __init__(self):
        super().__init__(
            name="mcp_google_calendar",
            description="Google Calendar operations (list, events CRUD)",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            base_url=self.CALENDAR_BASE,
            rate_limit_config=self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )

    def _get_operation_schema(self, operation: str):
        STR = str
        INT = int
        BOOL = bool
        DICT = dict
        schemas = {
            "list_calendars": {},
            "get_events": {
                "calendar_id": {"required": False, "type": STR},  # default 'primary'
                "time_min": {"required": False, "type": STR},
                "time_max": {"required": False, "type": STR},
                "max_results": {"required": False, "type": INT},
            },
            "create_event": {
                "calendar_id": {"required": False, "type": STR},
                "event": {"required": True, "type": DICT},  # raw Google event resource
            },
            "update_event": {
                "calendar_id": {"required": False, "type": STR},
                "event_id": {"required": True, "type": STR},
                "patch": {"required": True, "type": DICT},
            },
            "delete_event": {
                "calendar_id": {"required": False, "type": STR},
                "event_id": {"required": True, "type": STR},
            },
        }
        return schemas.get((operation or "").lower())

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        return (operation in {"create_event", "update_event", "delete_event"}) or super()._is_write_operation(operation, params)

    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]):
        op = (operation or "").lower()
        adapter = GoogleWorkspaceVendorAdapter(str(tenant_id))

        if op == "list_calendars":
            cal = await adapter.get_service("calendar", "v3", self.SCOPES_READ)
            def _list():
                return cal.calendarList().list().execute()
            return await asyncio.to_thread(_list)

        if op == "get_events":
            calendar_id = params.get("calendar_id", "primary")
            cal = await adapter.get_service("calendar", "v3", self.SCOPES_READ)
            time_min = params.get("time_min")
            time_max = params.get("time_max")
            max_results = params.get("max_results")
            def _list_events():
                kwargs = {"calendarId": calendar_id}
                if time_min:
                    kwargs["timeMin"] = time_min
                if time_max:
                    kwargs["timeMax"] = time_max
                if max_results:
                    kwargs["maxResults"] = int(max_results)
                return cal.events().list(**kwargs).execute()
            return await asyncio.to_thread(_list_events)

        if op == "create_event":
            calendar_id = params.get("calendar_id", "primary")
            event = params["event"]
            cal = await adapter.get_service("calendar", "v3", self.SCOPES_WRITE)
            def _insert():
                return cal.events().insert(calendarId=calendar_id, body=event).execute()
            return await asyncio.to_thread(_insert)

        if op == "update_event":
            calendar_id = params.get("calendar_id", "primary")
            event_id = params["event_id"]
            patch = params["patch"]
            cal = await adapter.get_service("calendar", "v3", self.SCOPES_WRITE)
            def _patch():
                return cal.events().patch(calendarId=calendar_id, eventId=event_id, body=patch).execute()
            return await asyncio.to_thread(_patch)

        if op == "delete_event":
            calendar_id = params.get("calendar_id", "primary")
            event_id = params["event_id"]
            cal = await adapter.get_service("calendar", "v3", self.SCOPES_WRITE)
            def _delete():
                try:
                    cal.events().delete(calendarId=calendar_id, eventId=event_id).execute()
                    return {"deleted": True}
                except Exception as e:
                    raise
            return await asyncio.to_thread(_delete)

        raise ValidationError(f"Unsupported operation: {operation}")
