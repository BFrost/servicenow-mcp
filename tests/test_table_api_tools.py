"""
Tests for the generic Table API tools.
"""

import unittest
from unittest.mock import MagicMock, patch

import requests as req

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.table_api_tools import (
    CreateRecordParams,
    GetRecordParams,
    QueryRecordsParams,
    UpdateRecordParams,
    create_record,
    get_record,
    query_records,
    update_record,
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


def _ok_response(result):
    mock = MagicMock()
    mock.json.return_value = {"result": result}
    mock.raise_for_status.return_value = None
    return mock


# ---------------------------------------------------------------------------
# get_record tests
# ---------------------------------------------------------------------------

class TestGetRecord(unittest.TestCase):

    def setUp(self):
        self.config = _make_config()
        self.auth = _make_auth_manager()

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_success_returns_record(self, mock_get):
        record = {"sys_id": "abc123", "short_description": "Test"}
        mock_get.return_value = _ok_response(record)

        result = get_record(self.config, self.auth, GetRecordParams(table="incident", sys_id="abc123"))

        self.assertTrue(result["success"])
        self.assertEqual(result["record"]["sys_id"], "abc123")

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_url_includes_table_and_sys_id(self, mock_get):
        mock_get.return_value = _ok_response({})

        get_record(self.config, self.auth, GetRecordParams(table="incident", sys_id="abc123"))

        url = mock_get.call_args[0][0]
        self.assertEqual(url, "https://test.service-now.com/api/now/table/incident/abc123")

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_fields_param_joined_as_csv(self, mock_get):
        mock_get.return_value = _ok_response({})

        get_record(
            self.config, self.auth,
            GetRecordParams(table="incident", sys_id="x", fields=["sys_id", "state", "number"]),
        )

        params = mock_get.call_args[1]["params"]
        self.assertEqual(params["sysparm_fields"], "sys_id,state,number")

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_display_value_true(self, mock_get):
        mock_get.return_value = _ok_response({})

        get_record(self.config, self.auth, GetRecordParams(table="incident", sys_id="x", display_value=True))

        params = mock_get.call_args[1]["params"]
        self.assertEqual(params["sysparm_display_value"], "true")

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_404_returns_not_found_message(self, mock_get):
        http_err = req.HTTPError(response=MagicMock(status_code=404))
        mock_get.return_value = MagicMock(raise_for_status=MagicMock(side_effect=http_err))

        result = get_record(self.config, self.auth, GetRecordParams(table="incident", sys_id="missing"))

        self.assertFalse(result["success"])
        self.assertIn("not found", result["message"].lower())

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_network_error_returns_failure(self, mock_get):
        mock_get.side_effect = req.RequestException("connection refused")

        result = get_record(self.config, self.auth, GetRecordParams(table="incident", sys_id="x"))

        self.assertFalse(result["success"])
        self.assertIn("connection refused", result["message"])


# ---------------------------------------------------------------------------
# query_records tests
# ---------------------------------------------------------------------------

class TestQueryRecords(unittest.TestCase):

    def setUp(self):
        self.config = _make_config()
        self.auth = _make_auth_manager()

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_success_returns_records_and_count(self, mock_get):
        records = [{"sys_id": "1"}, {"sys_id": "2"}]
        mock_get.return_value = _ok_response(records)

        result = query_records(self.config, self.auth, QueryRecordsParams(table="incident"))

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["records"]), 2)

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_url_targets_correct_table(self, mock_get):
        mock_get.return_value = _ok_response([])

        query_records(self.config, self.auth, QueryRecordsParams(table="sys_user"))

        url = mock_get.call_args[0][0]
        self.assertEqual(url, "https://test.service-now.com/api/now/table/sys_user")

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_query_string_forwarded(self, mock_get):
        mock_get.return_value = _ok_response([])

        query_records(
            self.config, self.auth,
            QueryRecordsParams(table="incident", query="active=true^priority=1"),
        )

        params = mock_get.call_args[1]["params"]
        self.assertEqual(params["sysparm_query"], "active=true^priority=1")

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_limit_capped_at_1000(self, mock_get):
        mock_get.return_value = _ok_response([])

        query_records(self.config, self.auth, QueryRecordsParams(table="incident", limit=5000))

        params = mock_get.call_args[1]["params"]
        self.assertEqual(params["sysparm_limit"], 1000)

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_pagination_params_forwarded(self, mock_get):
        mock_get.return_value = _ok_response([])

        query_records(self.config, self.auth, QueryRecordsParams(table="incident", limit=25, offset=50))

        params = mock_get.call_args[1]["params"]
        self.assertEqual(params["sysparm_limit"], 25)
        self.assertEqual(params["sysparm_offset"], 50)

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_fields_param_joined_as_csv(self, mock_get):
        mock_get.return_value = _ok_response([])

        query_records(
            self.config, self.auth,
            QueryRecordsParams(table="incident", fields=["number", "state"]),
        )

        params = mock_get.call_args[1]["params"]
        self.assertEqual(params["sysparm_fields"], "number,state")

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_order_by_appended_to_query(self, mock_get):
        mock_get.return_value = _ok_response([])

        query_records(
            self.config, self.auth,
            QueryRecordsParams(table="incident", query="active=true", order_by="sys_created_on"),
        )

        params = mock_get.call_args[1]["params"]
        self.assertIn("ORDERBYsys_created_on", params["sysparm_query"])

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_order_by_without_query(self, mock_get):
        mock_get.return_value = _ok_response([])

        query_records(
            self.config, self.auth,
            QueryRecordsParams(table="incident", order_by="number"),
        )

        params = mock_get.call_args[1]["params"]
        self.assertIn("ORDERBYnumber", params["sysparm_query"])

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_empty_result_returns_success(self, mock_get):
        mock_get.return_value = _ok_response([])

        result = query_records(self.config, self.auth, QueryRecordsParams(table="incident"))

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["records"], [])

    @patch("servicenow_mcp.tools.table_api_tools.requests.get")
    def test_network_error_returns_failure(self, mock_get):
        mock_get.side_effect = req.RequestException("timeout")

        result = query_records(self.config, self.auth, QueryRecordsParams(table="incident"))

        self.assertFalse(result["success"])
        self.assertIn("timeout", result["message"])
        self.assertEqual(result["records"], [])


# ---------------------------------------------------------------------------
# create_record tests
# ---------------------------------------------------------------------------

class TestCreateRecord(unittest.TestCase):

    def setUp(self):
        self.config = _make_config()
        self.auth = _make_auth_manager()

    @patch("servicenow_mcp.tools.table_api_tools.requests.post")
    def test_success_returns_sys_id_and_record(self, mock_post):
        created = {"sys_id": "new123", "name": "Test"}
        mock_post.return_value = _ok_response(created)

        result = create_record(
            self.config, self.auth,
            CreateRecordParams(table="sys_user_preference", fields={"name": "test", "value": "1"}),
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "new123")
        self.assertEqual(result["record"]["name"], "Test")

    @patch("servicenow_mcp.tools.table_api_tools.requests.post")
    def test_url_targets_correct_table(self, mock_post):
        mock_post.return_value = _ok_response({"sys_id": "x"})

        create_record(
            self.config, self.auth,
            CreateRecordParams(table="incident", fields={"short_description": "Test"}),
        )

        url = mock_post.call_args[0][0]
        self.assertEqual(url, "https://test.service-now.com/api/now/table/incident")

    @patch("servicenow_mcp.tools.table_api_tools.requests.post")
    def test_fields_sent_as_json_body(self, mock_post):
        mock_post.return_value = _ok_response({"sys_id": "x"})

        fields = {"short_description": "Disk full", "priority": "1"}
        create_record(self.config, self.auth, CreateRecordParams(table="incident", fields=fields))

        body = mock_post.call_args[1]["json"]
        self.assertEqual(body["short_description"], "Disk full")
        self.assertEqual(body["priority"], "1")

    @patch("servicenow_mcp.tools.table_api_tools.requests.post")
    def test_message_includes_table_name(self, mock_post):
        mock_post.return_value = _ok_response({"sys_id": "x"})

        result = create_record(
            self.config, self.auth,
            CreateRecordParams(table="my_table", fields={"field": "value"}),
        )

        self.assertIn("my_table", result["message"])

    @patch("servicenow_mcp.tools.table_api_tools.requests.post")
    def test_network_error_returns_failure(self, mock_post):
        mock_post.side_effect = req.RequestException("DNS failure")

        result = create_record(
            self.config, self.auth,
            CreateRecordParams(table="incident", fields={"short_description": "x"}),
        )

        self.assertFalse(result["success"])
        self.assertIn("DNS failure", result["message"])


# ---------------------------------------------------------------------------
# update_record tests
# ---------------------------------------------------------------------------

class TestUpdateRecord(unittest.TestCase):

    def setUp(self):
        self.config = _make_config()
        self.auth = _make_auth_manager()

    @patch("servicenow_mcp.tools.table_api_tools.requests.patch")
    def test_success_returns_sys_id_and_record(self, mock_patch):
        updated = {"sys_id": "upd123", "state": "2"}
        mock_patch.return_value = _ok_response(updated)

        result = update_record(
            self.config, self.auth,
            UpdateRecordParams(table="incident", sys_id="upd123", fields={"state": "2"}),
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "upd123")
        self.assertEqual(result["record"]["state"], "2")

    @patch("servicenow_mcp.tools.table_api_tools.requests.patch")
    def test_url_includes_table_and_sys_id(self, mock_patch):
        mock_patch.return_value = _ok_response({})

        update_record(
            self.config, self.auth,
            UpdateRecordParams(table="incident", sys_id="abc999", fields={"state": "6"}),
        )

        url = mock_patch.call_args[0][0]
        self.assertEqual(url, "https://test.service-now.com/api/now/table/incident/abc999")

    @patch("servicenow_mcp.tools.table_api_tools.requests.patch")
    def test_only_provided_fields_sent(self, mock_patch):
        mock_patch.return_value = _ok_response({})

        update_record(
            self.config, self.auth,
            UpdateRecordParams(table="incident", sys_id="x", fields={"priority": "2"}),
        )

        body = mock_patch.call_args[1]["json"]
        self.assertEqual(body, {"priority": "2"})

    @patch("servicenow_mcp.tools.table_api_tools.requests.patch")
    def test_404_returns_not_found_message(self, mock_patch):
        http_err = req.HTTPError(response=MagicMock(status_code=404))
        mock_patch.return_value = MagicMock(raise_for_status=MagicMock(side_effect=http_err))

        result = update_record(
            self.config, self.auth,
            UpdateRecordParams(table="incident", sys_id="ghost", fields={"state": "1"}),
        )

        self.assertFalse(result["success"])
        self.assertIn("not found", result["message"].lower())

    @patch("servicenow_mcp.tools.table_api_tools.requests.patch")
    def test_network_error_returns_failure(self, mock_patch):
        mock_patch.side_effect = req.RequestException("timeout")

        result = update_record(
            self.config, self.auth,
            UpdateRecordParams(table="incident", sys_id="x", fields={"state": "1"}),
        )

        self.assertFalse(result["success"])
        self.assertIn("timeout", result["message"])


# ---------------------------------------------------------------------------
# Param model tests
# ---------------------------------------------------------------------------

class TestTableApiParams(unittest.TestCase):

    def test_get_record_params_defaults(self):
        p = GetRecordParams(table="incident", sys_id="abc")
        self.assertIsNone(p.fields)
        self.assertFalse(p.display_value)

    def test_query_records_params_defaults(self):
        p = QueryRecordsParams(table="incident")
        self.assertEqual(p.limit, 10)
        self.assertEqual(p.offset, 0)
        self.assertFalse(p.display_value)
        self.assertIsNone(p.query)
        self.assertIsNone(p.fields)
        self.assertIsNone(p.order_by)

    def test_create_record_params(self):
        p = CreateRecordParams(table="incident", fields={"short_description": "Test"})
        self.assertEqual(p.table, "incident")
        self.assertEqual(p.fields["short_description"], "Test")

    def test_update_record_params(self):
        p = UpdateRecordParams(table="incident", sys_id="abc", fields={"state": "6"})
        self.assertEqual(p.sys_id, "abc")
        self.assertEqual(p.fields["state"], "6")


if __name__ == "__main__":
    unittest.main()
