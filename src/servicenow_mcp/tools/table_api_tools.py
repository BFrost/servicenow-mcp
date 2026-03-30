"""
Generic Table API tools for the ServiceNow MCP server.

Provides read, create, and update access to any ServiceNow table without
requiring a purpose-built tool for each one.
"""

import logging
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel, Field

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import ServerConfig

logger = logging.getLogger(__name__)


# ── Param models ───────────────────────────────────────────────────────────────

class GetRecordParams(BaseModel):
    """Parameters for fetching a single record by sys_id."""

    table: str = Field(..., description="ServiceNow table name (e.g. 'incident', 'sys_user')")
    sys_id: str = Field(..., description="sys_id of the record to retrieve")
    fields: Optional[List[str]] = Field(
        None, description="Specific fields to return. Returns all fields when omitted."
    )
    display_value: bool = Field(
        False,
        description="Return display values instead of raw values for reference fields",
    )


class QueryRecordsParams(BaseModel):
    """Parameters for querying multiple records from a table."""

    table: str = Field(..., description="ServiceNow table name (e.g. 'incident', 'sys_user')")
    query: Optional[str] = Field(
        None,
        description="Encoded query string (e.g. 'active=true^state=1'). Returns all records when omitted.",
    )
    fields: Optional[List[str]] = Field(
        None, description="Specific fields to return. Returns all fields when omitted."
    )
    limit: int = Field(10, description="Maximum number of records to return (max 1000)")
    offset: int = Field(0, description="Offset for pagination")
    display_value: bool = Field(
        False,
        description="Return display values instead of raw values for reference fields",
    )
    order_by: Optional[str] = Field(
        None, description="Field to order results by (prefix with ^ for ascending, ^DESC for descending)"
    )


class CreateRecordParams(BaseModel):
    """Parameters for creating a new record in a table."""

    table: str = Field(..., description="ServiceNow table name (e.g. 'incident', 'sys_user')")
    fields: Dict[str, Any] = Field(
        ..., description="Field name/value pairs for the new record"
    )


class UpdateRecordParams(BaseModel):
    """Parameters for updating an existing record."""

    table: str = Field(..., description="ServiceNow table name (e.g. 'incident', 'sys_user')")
    sys_id: str = Field(..., description="sys_id of the record to update")
    fields: Dict[str, Any] = Field(
        ..., description="Field name/value pairs to update on the record"
    )


# ── Tool functions ─────────────────────────────────────────────────────────────

def get_record(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetRecordParams,
) -> dict:
    """
    Retrieve a single record from any ServiceNow table by sys_id.

    Returns the full record or a subset of fields if specified.
    """
    url = f"{config.api_url}/table/{params.table}/{params.sys_id}"
    query_params: Dict[str, Any] = {
        "sysparm_display_value": "true" if params.display_value else "false",
        "sysparm_exclude_reference_link": "true",
    }
    if params.fields:
        query_params["sysparm_fields"] = ",".join(params.fields)

    try:
        response = requests.get(
            url,
            params=query_params,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {"success": True, "record": result}
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return {
                "success": False,
                "message": f"Record not found: {params.table}/{params.sys_id}",
            }
        logger.error("Failed to get record %s/%s: %s", params.table, params.sys_id, e)
        return {"success": False, "message": str(e)}
    except requests.RequestException as e:
        logger.error("Failed to get record %s/%s: %s", params.table, params.sys_id, e)
        return {"success": False, "message": str(e)}


def query_records(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: QueryRecordsParams,
) -> dict:
    """
    Query records from any ServiceNow table using an encoded query string.

    Supports filtering, field selection, pagination, and ordering.
    """
    url = f"{config.api_url}/table/{params.table}"
    query_params: Dict[str, Any] = {
        "sysparm_limit": min(params.limit, 1000),
        "sysparm_offset": params.offset,
        "sysparm_display_value": "true" if params.display_value else "false",
        "sysparm_exclude_reference_link": "true",
    }
    if params.query:
        query_params["sysparm_query"] = params.query
    if params.fields:
        query_params["sysparm_fields"] = ",".join(params.fields)
    if params.order_by:
        existing = query_params.get("sysparm_query", "")
        order_clause = f"ORDERBY{params.order_by}"
        query_params["sysparm_query"] = f"{existing}^{order_clause}" if existing else order_clause

    try:
        response = requests.get(
            url,
            params=query_params,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        records = response.json().get("result", [])
        return {
            "success": True,
            "count": len(records),
            "records": records,
        }
    except requests.RequestException as e:
        logger.error("Failed to query %s: %s", params.table, e)
        return {"success": False, "message": str(e), "records": []}


def create_record(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateRecordParams,
) -> dict:
    """
    Create a new record in any ServiceNow table.

    Returns the created record including its sys_id.
    """
    url = f"{config.api_url}/table/{params.table}"

    try:
        response = requests.post(
            url,
            json=params.fields,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Record created in {params.table}",
            "sys_id": result.get("sys_id"),
            "record": result,
        }
    except requests.RequestException as e:
        logger.error("Failed to create record in %s: %s", params.table, e)
        return {"success": False, "message": str(e)}


def update_record(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateRecordParams,
) -> dict:
    """
    Update an existing record in any ServiceNow table using PATCH.

    Only the fields provided are changed; all other fields are left untouched.
    """
    url = f"{config.api_url}/table/{params.table}/{params.sys_id}"

    try:
        response = requests.patch(
            url,
            json=params.fields,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Record updated in {params.table}",
            "sys_id": params.sys_id,
            "record": result,
        }
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return {
                "success": False,
                "message": f"Record not found: {params.table}/{params.sys_id}",
            }
        logger.error("Failed to update record %s/%s: %s", params.table, params.sys_id, e)
        return {"success": False, "message": str(e)}
    except requests.RequestException as e:
        logger.error("Failed to update record %s/%s: %s", params.table, params.sys_id, e)
        return {"success": False, "message": str(e)}
