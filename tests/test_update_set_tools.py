"""
Tests for the update set tools.

This module contains tests for the update set tools in the ServiceNow MCP server.
"""

import unittest
from unittest.mock import MagicMock, patch

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.update_set_tools import (
    CompleteUpdateSetParams,
    CreateUpdateSetParams,
    ListUpdateSetsParams,
    SetCurrentUpdateSetParams,
    complete_update_set,
    create_update_set,
    list_update_sets,
    set_current_update_set,
)
from servicenow_mcp.utils.config import AuthConfig, AuthType, BasicAuthConfig, ServerConfig


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_config():
    auth_config = AuthConfig(
        type=AuthType.BASIC,
        basic=BasicAuthConfig(username="test_user", password="test_password"),
    )
    return ServerConfig(
        instance_url="https://test.service-now.com",
        auth=auth_config,
    )


def _make_auth_manager():
    auth_manager = MagicMock(spec=AuthManager)
    auth_manager.get_headers.return_value = {"Authorization": "Bearer test"}
    return auth_manager


# ---------------------------------------------------------------------------
# Tool function tests
# ---------------------------------------------------------------------------

class TestCreateUpdateSet(unittest.TestCase):
    """Tests for create_update_set."""

    def setUp(self):
        self.config = _make_config()
        self.auth_manager = _make_auth_manager()

    @patch("servicenow_mcp.tools.update_set_tools.requests.post")
    def test_create_update_set_success(self, mock_post):
        """A successful POST should return success=True with sys_id and name."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"sys_id": "abc123", "name": "My Update Set"}
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        params = CreateUpdateSetParams(name="My Update Set", description="A test update set")
        result = create_update_set(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        self.assertEqual(result.update_set_id, "abc123")
        self.assertEqual(result.update_set_name, "My Update Set")
        self.assertIn("successfully", result.message)

    @patch("servicenow_mcp.tools.update_set_tools.requests.post")
    def test_create_update_set_sends_correct_payload(self, mock_post):
        """The POST body should include name, state, description, and release_date."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"sys_id": "abc123", "name": "Payload Test"}
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        params = CreateUpdateSetParams(
            name="Payload Test",
            description="Desc",
            release_date="2026-06-01",
        )
        create_update_set(self.config, self.auth_manager, params)

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["name"], "Payload Test")
        self.assertEqual(kwargs["json"]["state"], "in progress")
        self.assertEqual(kwargs["json"]["description"], "Desc")
        self.assertEqual(kwargs["json"]["release_date"], "2026-06-01")

    @patch("servicenow_mcp.tools.update_set_tools.requests.post")
    def test_create_update_set_uses_correct_url(self, mock_post):
        """POST should target the sys_update_set table endpoint."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"sys_id": "x", "name": "x"}}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        create_update_set(self.config, self.auth_manager, CreateUpdateSetParams(name="x"))

        args, _ = mock_post.call_args
        self.assertEqual(
            args[0], "https://test.service-now.com/api/now/table/sys_update_set"
        )

    @patch("servicenow_mcp.tools.update_set_tools.requests.post")
    def test_create_update_set_request_exception(self, mock_post):
        """A network error should return success=False with an error message."""
        import requests as req
        mock_post.side_effect = req.RequestException("connection refused")

        result = create_update_set(
            self.config, self.auth_manager, CreateUpdateSetParams(name="Fail")
        )

        self.assertFalse(result.success)
        self.assertIn("connection refused", result.message)


# ---------------------------------------------------------------------------

class TestSetCurrentUpdateSet(unittest.TestCase):
    """Tests for set_current_update_set."""

    def setUp(self):
        self.config = _make_config()
        self.auth_manager = _make_auth_manager()

    @patch("servicenow_mcp.tools.update_set_tools.requests.post")
    def test_set_current_success(self, mock_post):
        """A successful call should return the update set id and name from the API response."""
        sys_id = "a" * 32
        mock_post.return_value = MagicMock(
            json=lambda: {
                "success": True,
                "message": "Current update set changed successfully",
                "update_set_id": sys_id,
                "update_set_name": "My Set",
            },
            raise_for_status=lambda: None,
        )

        result = set_current_update_set(
            self.config, self.auth_manager, SetCurrentUpdateSetParams(update_set_id=sys_id)
        )

        self.assertTrue(result.success)
        self.assertEqual(result.update_set_id, sys_id)
        self.assertEqual(result.update_set_name, "My Set")

    @patch("servicenow_mcp.tools.update_set_tools.requests.post")
    def test_set_current_calls_scripted_rest_endpoint(self, mock_post):
        """Should POST to the ServiceNow MCP Scripted REST API, not sys_user_preference."""
        mock_post.return_value = MagicMock(
            json=lambda: {"success": True, "message": "", "update_set_id": "x", "update_set_name": "x"},
            raise_for_status=lambda: None,
        )

        set_current_update_set(
            self.config, self.auth_manager,
            SetCurrentUpdateSetParams(update_set_id="some-id"),
        )

        url = mock_post.call_args[0][0]
        self.assertIn("x_83547_servicen_0/servicenow_mcp/update_set/current", url)
        self.assertNotIn("sys_user_preference", url)

    @patch("servicenow_mcp.tools.update_set_tools.requests.post")
    def test_set_current_passes_update_set_id_in_body(self, mock_post):
        """The update_set_id should be forwarded as-is in the request body."""
        mock_post.return_value = MagicMock(
            json=lambda: {"success": True, "message": "", "update_set_id": "x", "update_set_name": "x"},
            raise_for_status=lambda: None,
        )

        set_current_update_set(
            self.config, self.auth_manager,
            SetCurrentUpdateSetParams(update_set_id="My Update Set"),
        )

        body = mock_post.call_args[1]["json"]
        self.assertEqual(body["update_set_id"], "My Update Set")

    @patch("servicenow_mcp.tools.update_set_tools.requests.post")
    def test_set_current_not_found(self, mock_post):
        """A 404 response from the scripted API should return success=False."""
        import requests as req
        http_err = req.HTTPError(response=MagicMock(status_code=404))
        mock_post.return_value = MagicMock(
            raise_for_status=MagicMock(side_effect=http_err)
        )

        result = set_current_update_set(
            self.config, self.auth_manager,
            SetCurrentUpdateSetParams(update_set_id="Nonexistent"),
        )

        self.assertFalse(result.success)

    @patch("servicenow_mcp.tools.update_set_tools.requests.post")
    def test_set_current_network_error(self, mock_post):
        """A network error should return success=False with the error message."""
        import requests as req
        mock_post.side_effect = req.RequestException("connection refused")

        result = set_current_update_set(
            self.config, self.auth_manager,
            SetCurrentUpdateSetParams(update_set_id="some-id"),
        )

        self.assertFalse(result.success)
        self.assertIn("connection refused", result.message)


# ---------------------------------------------------------------------------

class TestCompleteUpdateSet(unittest.TestCase):
    """Tests for complete_update_set."""

    def setUp(self):
        self.config = _make_config()
        self.auth_manager = _make_auth_manager()

    @patch("servicenow_mcp.tools.update_set_tools.requests.patch")
    def test_complete_update_set_by_sys_id(self, mock_patch):
        """Should PATCH state=complete for a valid sys_id."""
        mock_patch.return_value = MagicMock(
            json=lambda: {"result": {"sys_id": "a" * 32, "name": "Done Set"}},
            raise_for_status=lambda: None,
        )

        sys_id = "a" * 32
        result = complete_update_set(
            self.config, self.auth_manager, CompleteUpdateSetParams(update_set_id=sys_id)
        )

        self.assertTrue(result.success)
        self.assertIn("complete", result.message)

        _, kwargs = mock_patch.call_args
        self.assertEqual(kwargs["json"]["state"], "complete")

    @patch("servicenow_mcp.tools.update_set_tools.requests.patch")
    def test_complete_update_set_uses_correct_url(self, mock_patch):
        """PATCH URL should include the sys_id."""
        sys_id = "c" * 32
        mock_patch.return_value = MagicMock(
            json=lambda: {"result": {"sys_id": sys_id, "name": "x"}},
            raise_for_status=lambda: None,
        )

        complete_update_set(
            self.config, self.auth_manager, CompleteUpdateSetParams(update_set_id=sys_id)
        )

        args, _ = mock_patch.call_args
        self.assertIn(sys_id, args[0])

    @patch("servicenow_mcp.tools.update_set_tools.requests.get")
    def test_complete_update_set_not_found(self, mock_get):
        """When the update set is not found by name, should return success=False."""
        mock_get.return_value = MagicMock(
            json=lambda: {"result": []}, raise_for_status=lambda: None
        )

        result = complete_update_set(
            self.config,
            self.auth_manager,
            CompleteUpdateSetParams(update_set_id="Ghost Set"),
        )

        self.assertFalse(result.success)
        self.assertIn("not found", result.message)

    @patch("servicenow_mcp.tools.update_set_tools.requests.patch")
    def test_complete_update_set_request_exception(self, mock_patch):
        """A network error should return success=False."""
        import requests as req

        sys_id = "d" * 32
        mock_patch.side_effect = req.RequestException("timeout")

        result = complete_update_set(
            self.config, self.auth_manager, CompleteUpdateSetParams(update_set_id=sys_id)
        )

        self.assertFalse(result.success)
        self.assertIn("timeout", result.message)


# ---------------------------------------------------------------------------

class TestListUpdateSets(unittest.TestCase):
    """Tests for list_update_sets."""

    def setUp(self):
        self.config = _make_config()
        self.auth_manager = _make_auth_manager()

    @patch("servicenow_mcp.tools.update_set_tools.requests.get")
    def test_list_update_sets_returns_results(self, mock_get):
        """Should return a list of update sets with expected fields."""
        mock_get.return_value = MagicMock(
            json=lambda: {
                "result": [
                    {
                        "sys_id": "1",
                        "name": "Set A",
                        "state": "in progress",
                        "description": "Desc A",
                        "release_date": "2026-06-01",
                        "sys_created_on": "2026-01-01",
                        "sys_updated_on": "2026-01-02",
                    },
                    {
                        "sys_id": "2",
                        "name": "Set B",
                        "state": "complete",
                        "description": "",
                        "release_date": "",
                        "sys_created_on": "2026-02-01",
                        "sys_updated_on": "2026-02-02",
                    },
                ]
            },
            raise_for_status=lambda: None,
        )

        result = list_update_sets(
            self.config, self.auth_manager, ListUpdateSetsParams(limit=10, offset=0)
        )

        self.assertTrue(result["success"])
        self.assertEqual(len(result["update_sets"]), 2)
        self.assertEqual(result["update_sets"][0]["sys_id"], "1")
        self.assertEqual(result["update_sets"][1]["name"], "Set B")

    @patch("servicenow_mcp.tools.update_set_tools.requests.get")
    def test_list_update_sets_state_filter(self, mock_get):
        """When state is provided, sysparm_query should include it."""
        mock_get.return_value = MagicMock(
            json=lambda: {"result": []}, raise_for_status=lambda: None
        )

        list_update_sets(
            self.config,
            self.auth_manager,
            ListUpdateSetsParams(limit=5, offset=0, state="in progress"),
        )

        _, kwargs = mock_get.call_args
        self.assertIn("sysparm_query", kwargs["params"])
        self.assertIn("in progress", kwargs["params"]["sysparm_query"])

    @patch("servicenow_mcp.tools.update_set_tools.requests.get")
    def test_list_update_sets_pagination(self, mock_get):
        """limit and offset should be forwarded to the API."""
        mock_get.return_value = MagicMock(
            json=lambda: {"result": []}, raise_for_status=lambda: None
        )

        list_update_sets(
            self.config, self.auth_manager, ListUpdateSetsParams(limit=25, offset=50)
        )

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["sysparm_limit"], 25)
        self.assertEqual(kwargs["params"]["sysparm_offset"], 50)

    @patch("servicenow_mcp.tools.update_set_tools.requests.get")
    def test_list_update_sets_empty(self, mock_get):
        """An empty result set should return success=True with an empty list."""
        mock_get.return_value = MagicMock(
            json=lambda: {"result": []}, raise_for_status=lambda: None
        )

        result = list_update_sets(
            self.config, self.auth_manager, ListUpdateSetsParams()
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["update_sets"], [])

    @patch("servicenow_mcp.tools.update_set_tools.requests.get")
    def test_list_update_sets_request_exception(self, mock_get):
        """A network error should return success=False."""
        import requests as req

        mock_get.side_effect = req.RequestException("DNS failure")

        result = list_update_sets(
            self.config, self.auth_manager, ListUpdateSetsParams()
        )

        self.assertFalse(result["success"])
        self.assertIn("DNS failure", result["message"])
        self.assertEqual(result["update_sets"], [])


# ---------------------------------------------------------------------------
# Param model tests
# ---------------------------------------------------------------------------

class TestUpdateSetParams(unittest.TestCase):
    """Tests for the update set Pydantic param models."""

    def test_create_update_set_params_required(self):
        params = CreateUpdateSetParams(name="Minimal")
        self.assertEqual(params.name, "Minimal")
        self.assertIsNone(params.description)
        self.assertIsNone(params.release_date)

    def test_create_update_set_params_full(self):
        params = CreateUpdateSetParams(
            name="Full Set",
            description="All fields",
            release_date="2026-12-31",
        )
        self.assertEqual(params.name, "Full Set")
        self.assertEqual(params.description, "All fields")
        self.assertEqual(params.release_date, "2026-12-31")

    def test_set_current_update_set_params(self):
        params = SetCurrentUpdateSetParams(update_set_id="some-id")
        self.assertEqual(params.update_set_id, "some-id")

    def test_complete_update_set_params(self):
        params = CompleteUpdateSetParams(update_set_id="some-id")
        self.assertEqual(params.update_set_id, "some-id")

    def test_list_update_sets_params_defaults(self):
        params = ListUpdateSetsParams()
        self.assertEqual(params.limit, 10)
        self.assertEqual(params.offset, 0)
        self.assertIsNone(params.state)

    def test_list_update_sets_params_custom(self):
        params = ListUpdateSetsParams(limit=50, offset=10, state="complete")
        self.assertEqual(params.limit, 50)
        self.assertEqual(params.offset, 10)
        self.assertEqual(params.state, "complete")


if __name__ == "__main__":
    unittest.main()
