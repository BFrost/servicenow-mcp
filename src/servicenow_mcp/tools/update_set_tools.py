"""
Update Set tools for the ServiceNow MCP server.

This module provides tools for managing Update Sets in ServiceNow.
"""

import logging
from typing import Optional

import requests
from pydantic import BaseModel, Field

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import ServerConfig

logger = logging.getLogger(__name__)


# ── Param models ───────────────────────────────────────────────────────────────

class CreateUpdateSetParams(BaseModel):
    """Parameters for creating an update set."""

    name: str = Field(..., description="Name of the update set")
    description: Optional[str] = Field(None, description="Description of the update set")
    release_date: Optional[str] = Field(None, description="Target release date (YYYY-MM-DD)")


class SetCurrentUpdateSetParams(BaseModel):
    """Parameters for setting the current update set."""

    update_set_id: str = Field(..., description="Update set sys_id or name")


class CompleteUpdateSetParams(BaseModel):
    """Parameters for completing (closing) an update set."""

    update_set_id: str = Field(..., description="Update set sys_id or name")


class ListUpdateSetsParams(BaseModel):
    """Parameters for listing update sets."""

    limit: int = Field(10, description="Maximum number of results to return")
    offset: int = Field(0, description="Offset for pagination")
    state: Optional[str] = Field(
        None, description="Filter by state: 'in progress', 'complete', or 'ignore'"
    )


# ── Response model ─────────────────────────────────────────────────────────────

class UpdateSetResponse(BaseModel):
    """Response from update set operations."""

    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Message describing the result")
    update_set_id: Optional[str] = Field(None, description="sys_id of the affected update set")
    update_set_name: Optional[str] = Field(None, description="Name of the affected update set")


# ── Tool functions ─────────────────────────────────────────────────────────────

def create_update_set(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateUpdateSetParams,
) -> UpdateSetResponse:
    """
    Create a new Update Set in ServiceNow.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Parameters for creating the update set.

    Returns:
        Response with the created update set details.
    """
    api_url = f"{config.api_url}/table/sys_update_set"

    data: dict = {"name": params.name, "state": "in progress"}
    if params.description:
        data["description"] = params.description
    if params.release_date:
        data["release_date"] = params.release_date

    try:
        response = requests.post(
            api_url,
            json=data,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return UpdateSetResponse(
            success=True,
            message="Update set created successfully",
            update_set_id=result.get("sys_id"),
            update_set_name=result.get("name"),
        )
    except requests.RequestException as e:
        logger.error(f"Failed to create update set: {e}")
        return UpdateSetResponse(
            success=False,
            message=f"Failed to create update set: {str(e)}",
        )


def set_current_update_set(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: SetCurrentUpdateSetParams,
) -> UpdateSetResponse:
    """
    Set the current update set for the authenticated user's session.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Parameters containing the update set to activate.

    Returns:
        Response indicating success or failure.
    """
    update_set_id = _resolve_update_set_id(config, auth_manager, params.update_set_id)
    if not update_set_id:
        return UpdateSetResponse(
            success=False,
            message=f"Update set not found: {params.update_set_id}",
        )

    try:
        # Store the current update set preference for the authenticated user
        pref_url = f"{config.api_url}/table/sys_user_preference"
        data = {
            "name": "sys_update_set",
            "value": update_set_id,
            "user": "",  # empty string targets the current user
        }
        response = requests.post(
            pref_url,
            json=data,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()

        # Fetch the update set name for a helpful response message
        rec = requests.get(
            f"{config.api_url}/table/sys_update_set/{update_set_id}",
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        rec.raise_for_status()
        name = rec.json().get("result", {}).get("name")

        return UpdateSetResponse(
            success=True,
            message="Current update set changed successfully",
            update_set_id=update_set_id,
            update_set_name=name,
        )
    except requests.RequestException as e:
        logger.error(f"Failed to set current update set: {e}")
        return UpdateSetResponse(
            success=False,
            message=f"Failed to set current update set: {str(e)}",
        )


def complete_update_set(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CompleteUpdateSetParams,
) -> UpdateSetResponse:
    """
    Mark an Update Set as complete.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Parameters containing the update set to complete.

    Returns:
        Response indicating success or failure.
    """
    update_set_id = _resolve_update_set_id(config, auth_manager, params.update_set_id)
    if not update_set_id:
        return UpdateSetResponse(
            success=False,
            message=f"Update set not found: {params.update_set_id}",
        )

    api_url = f"{config.api_url}/table/sys_update_set/{update_set_id}"
    try:
        response = requests.patch(
            api_url,
            json={"state": "complete"},
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return UpdateSetResponse(
            success=True,
            message="Update set marked as complete",
            update_set_id=result.get("sys_id"),
            update_set_name=result.get("name"),
        )
    except requests.RequestException as e:
        logger.error(f"Failed to complete update set: {e}")
        return UpdateSetResponse(
            success=False,
            message=f"Failed to complete update set: {str(e)}",
        )


def list_update_sets(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListUpdateSetsParams,
) -> dict:
    """
    List Update Sets from ServiceNow.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Parameters for listing update sets.

    Returns:
        Dictionary with list of update sets.
    """
    api_url = f"{config.api_url}/table/sys_update_set"
    query_params: dict = {
        "sysparm_limit": params.limit,
        "sysparm_offset": params.offset,
        "sysparm_display_value": "true",
        "sysparm_exclude_reference_link": "true",
    }
    if params.state:
        query_params["sysparm_query"] = f"state={params.state}"

    try:
        response = requests.get(
            api_url,
            params=query_params,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        results = response.json().get("result", [])
        update_sets = [
            {
                "sys_id": r.get("sys_id"),
                "name": r.get("name"),
                "state": r.get("state"),
                "description": r.get("description"),
                "release_date": r.get("release_date"),
                "created_on": r.get("sys_created_on"),
                "updated_on": r.get("sys_updated_on"),
            }
            for r in results
        ]
        return {
            "success": True,
            "message": f"Found {len(update_sets)} update sets",
            "update_sets": update_sets,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to list update sets: {e}")
        return {
            "success": False,
            "message": f"Failed to list update sets: {str(e)}",
            "update_sets": [],
        }


# ── Internal helpers ───────────────────────────────────────────────────────────

def _resolve_update_set_id(
    config: ServerConfig,
    auth_manager: AuthManager,
    update_set_id: str,
) -> Optional[str]:
    """Return a sys_id, resolving from name if the input doesn't look like one."""
    if len(update_set_id) == 32 and all(c in "0123456789abcdef" for c in update_set_id):
        return update_set_id
    try:
        response = requests.get(
            f"{config.api_url}/table/sys_update_set",
            params={"sysparm_query": f"name={update_set_id}", "sysparm_limit": 1},
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        results = response.json().get("result", [])
        return results[0].get("sys_id") if results else None
    except requests.RequestException:
        return None
