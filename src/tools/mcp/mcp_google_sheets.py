"""
Google Sheets MCP Tool (vendor-bridged)
- list_spreadsheets (Drive list filter for spreadsheets)
- get_spreadsheet_info
- read_sheet_values
- modify_sheet_values (write/update/clear)
- create_sheet (add sheet to spreadsheet)
- create_spreadsheet
"""
from __future__ import annotations

from typing import Any, Dict
import asyncio

from .base_mcp_tool import RateLimitConfig, RetryConfig, CircuitBreakerConfig, AuthType, ValidationError
from .google_workspace_base import GoogleWorkspaceBase
from .vendor_bridge.google_workspace_adapter import GoogleWorkspaceVendorAdapter, MissingGoogleAuthorization


class MCPGoogleSheetsTool(GoogleWorkspaceBase):
    SHEETS_BASE = "https://sheets.googleapis.com/v4"

    SCOPES_READ = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ]
    SCOPES_WRITE = [
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(requests_per_second=10.0, burst_size=20)
    DEFAULT_RETRY_CONFIG = RetryConfig(max_retries=3, initial_delay=1.0, max_delay=30.0)
    DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)

    def __init__(self):
        super().__init__(
            name="mcp_google_sheets",
            description="Google Sheets operations (read, write, create)",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            base_url=self.SHEETS_BASE,
            rate_limit_config=self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=30.0,
        )

    def _get_operation_schema(self, operation: str):
        STR = str
        DICT = dict
        schemas = {
            "list_spreadsheets": {
                "max_results": {"required": False, "type": int},
            },
            "get_spreadsheet_info": {
                "spreadsheet_id": {"required": True, "type": STR},
            },
            "read_sheet_values": {
                "spreadsheet_id": {"required": True, "type": STR},
                "range_name": {"required": True, "type": STR},
            },
            "modify_sheet_values": {
                "spreadsheet_id": {"required": True, "type": STR},
                "range_name": {"required": True, "type": STR},
                "values": {"required": False, "type": list},  # 2D array
                "value_input_option": {"required": False, "type": STR},
                "clear_values": {"required": False, "type": bool},
            },
            "create_sheet": {
                "spreadsheet_id": {"required": True, "type": STR},
                "sheet_name": {"required": True, "type": STR},
            },
            "create_spreadsheet": {
                "title": {"required": True, "type": STR},
            },
        }
        return schemas.get((operation or "").lower())

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        return (
            operation in {"modify_sheet_values", "create_sheet", "create_spreadsheet"}
        ) or super()._is_write_operation(operation, params)

    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]):
        op = (operation or "").lower()
        adapter = GoogleWorkspaceVendorAdapter(str(tenant_id))

        # list_spreadsheets (Drive API)
        if op == "list_spreadsheets":
            max_results = int(params.get("max_results", 25))
            drive = await adapter.get_drive(["https://www.googleapis.com/auth/drive.readonly"])  # Drive read scope
            def _list():
                return (
                    drive.files()
                    .list(
                        q="mimeType='application/vnd.google-apps.spreadsheet'",
                        pageSize=max_results,
                        fields="files(id,name,modifiedTime,webViewLink)",
                        orderBy="modifiedTime desc",
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )
            files_response = await asyncio.to_thread(_list)
            files = files_response.get("files", [])
            return {
                "count": len(files),
                "files": files,
            }

        # get_spreadsheet_info
        if op == "get_spreadsheet_info":
            sid = params["spreadsheet_id"]
            sheets = await adapter.get_sheets(["https://www.googleapis.com/auth/spreadsheets.readonly"])
            def _get():
                return sheets.spreadsheets().get(spreadsheetId=sid).execute()
            spreadsheet = await asyncio.to_thread(_get)
            return spreadsheet

        # read_sheet_values
        if op == "read_sheet_values":
            sid = params["spreadsheet_id"]
            range_name = params["range_name"]
            sheets = await adapter.get_sheets(["https://www.googleapis.com/auth/spreadsheets.readonly"])
            def _get():
                return (
                    sheets.spreadsheets()
                    .values()
                    .get(spreadsheetId=sid, range=range_name)
                    .execute()
                )
            res = await asyncio.to_thread(_get)
            return res

        # modify_sheet_values (write/update/clear)
        if op == "modify_sheet_values":
            sid = params["spreadsheet_id"]
            range_name = params["range_name"]
            clear_values = bool(params.get("clear_values", False))
            value_input_option = params.get("value_input_option", "USER_ENTERED")
            sheets = await adapter.get_sheets(["https://www.googleapis.com/auth/spreadsheets"])

            if clear_values:
                def _clear():
                    return (
                        sheets.spreadsheets()
                        .values()
                        .clear(spreadsheetId=sid, range=range_name, body={})
                        .execute()
                    )
                return await asyncio.to_thread(_clear)
            else:
                values = params.get("values") or []
                def _upd():
                    return (
                        sheets.spreadsheets()
                        .values()
                        .update(
                            spreadsheetId=sid,
                            range=range_name,
                            valueInputOption=value_input_option,
                            body={"values": values},
                        )
                        .execute()
                    )
                return await asyncio.to_thread(_upd)

        # create_sheet (add new sheet/tab)
        if op == "create_sheet":
            sid = params["spreadsheet_id"]
            sheet_name = params["sheet_name"]
            sheets = await adapter.get_sheets(["https://www.googleapis.com/auth/spreadsheets"])
            def _batch():
                return (
                    sheets.spreadsheets()
                    .batchUpdate(
                        spreadsheetId=sid,
                        body={
                            "requests": [
                                {"addSheet": {"properties": {"title": sheet_name}}}
                            ]
                        },
                    )
                    .execute()
                )
            response = await asyncio.to_thread(_batch)
            return response

        # create_spreadsheet
        if op == "create_spreadsheet":
            title = params["title"]
            sheets = await adapter.get_sheets(["https://www.googleapis.com/auth/spreadsheets"])
            def _create():
                return sheets.spreadsheets().create(body={"properties": {"title": title}}).execute()
            return await asyncio.to_thread(_create)

        raise ValidationError(f"Unsupported operation: {operation}")
