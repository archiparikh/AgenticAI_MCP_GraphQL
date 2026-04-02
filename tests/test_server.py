"""
Tests for server.py (MCPServer)
"""

import io
import json

import pytest
import responses as resp_lib

from mcp_graphql_bridge.config import BridgeConfig, EndpointConfig
from mcp_graphql_bridge.server import MCPServer, MCPError


ENDPOINT_URL = "http://test.example.com/graphql"

# Minimal introspection payload that the server can consume
MINIMAL_SCHEMA = {
    "data": {
        "__schema": {
            "queryType": {"name": "Query"},
            "mutationType": None,
            "subscriptionType": None,
            "types": [
                {
                    "kind": "OBJECT",
                    "name": "Query",
                    "description": None,
                    "fields": [
                        {
                            "name": "hello",
                            "description": "Say hello",
                            "args": [],
                            "type": {"kind": "SCALAR", "name": "String", "ofType": None},
                            "isDeprecated": False,
                            "deprecationReason": None,
                        }
                    ],
                    "inputFields": None,
                    "interfaces": [],
                    "enumValues": None,
                    "possibleTypes": None,
                }
            ],
            "directives": [],
        }
    }
}


@pytest.fixture
def config():
    return BridgeConfig(
        endpoints=[EndpointConfig(name="default", url=ENDPOINT_URL)],
        server_name="test-server",
    )


@pytest.fixture
def server(config):
    return MCPServer(config)


def _msg(method: str, params=None, msg_id=1) -> dict:
    m = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params:
        m["params"] = params
    return m


def _notification(method: str, params=None) -> dict:
    m = {"jsonrpc": "2.0", "method": method}
    if params:
        m["params"] = params
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHandleInitialize:
    @resp_lib.activate
    def test_returns_server_info(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        response = server.handle_message(_msg("initialize", {}))
        assert response["result"]["serverInfo"]["name"] == "test-server"

    @resp_lib.activate
    def test_capabilities_include_tools(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        response = server.handle_message(_msg("initialize", {}))
        assert "tools" in response["result"]["capabilities"]

    @resp_lib.activate
    def test_protocol_version_present(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        response = server.handle_message(_msg("initialize", {}))
        assert "protocolVersion" in response["result"]


class TestHandleInitialized:
    @resp_lib.activate
    def test_initialized_notification_returns_none(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        server.handle_message(_msg("initialize", {}))
        result = server.handle_message(_notification("initialized"))
        assert result is None


class TestHandleToolsList:
    @resp_lib.activate
    def test_returns_tool_list(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(_msg("tools/list"))
        tools = response["result"]["tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0

    @resp_lib.activate
    def test_includes_utility_tools(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(_msg("tools/list"))
        names = {t["name"] for t in response["result"]["tools"]}
        assert "graphql_execute_default" in names
        assert "graphql_introspect_default" in names
        assert "graphql_list_operations_default" in names

    @resp_lib.activate
    def test_includes_hello_operation_tool(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(_msg("tools/list"))
        names = {t["name"] for t in response["result"]["tools"]}
        assert "default__query_hello" in names


class TestHandleToolsCall:
    @resp_lib.activate
    def test_execute_raw_query(self, server):
        # First call: introspection during initialize
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        # Second call: the actual query
        resp_lib.add(
            resp_lib.POST, ENDPOINT_URL, json={"data": {"hello": "world"}}, status=200
        )
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(
            _msg(
                "tools/call",
                {
                    "name": "graphql_execute_default",
                    "arguments": {"query": "{ hello }"},
                },
            )
        )
        assert "isError" not in response["result"] or not response["result"]["isError"]
        content_text = response["result"]["content"][0]["text"]
        assert "world" in content_text

    @resp_lib.activate
    def test_introspect_tool(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(
            _msg(
                "tools/call",
                {
                    "name": "graphql_introspect_default",
                    "arguments": {},
                },
            )
        )
        text = response["result"]["content"][0]["text"]
        assert "Query" in text

    @resp_lib.activate
    def test_list_operations_tool(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(
            _msg(
                "tools/call",
                {
                    "name": "graphql_list_operations_default",
                    "arguments": {},
                },
            )
        )
        text = response["result"]["content"][0]["text"]
        assert "hello" in text

    @resp_lib.activate
    def test_unknown_tool_returns_error(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(
            _msg("tools/call", {"name": "nonexistent_tool", "arguments": {}})
        )
        assert "error" in response

    @resp_lib.activate
    def test_graphql_error_in_response(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        resp_lib.add(
            resp_lib.POST,
            ENDPOINT_URL,
            json={"data": None, "errors": [{"message": "Cannot query field"}]},
            status=200,
        )
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(
            _msg(
                "tools/call",
                {
                    "name": "graphql_execute_default",
                    "arguments": {"query": "{ badField }"},
                },
            )
        )
        result = response["result"]
        assert result.get("isError") is True
        assert "Cannot query field" in result["content"][0]["text"]


class TestHandleResourcesList:
    @resp_lib.activate
    def test_returns_schema_resource(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(_msg("resources/list"))
        resources = response["result"]["resources"]
        uris = [r["uri"] for r in resources]
        assert any("default" in u for u in uris)

    @resp_lib.activate
    def test_resource_has_mime_type(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(_msg("resources/list"))
        for resource in response["result"]["resources"]:
            assert "mimeType" in resource


class TestHandleResourcesRead:
    @resp_lib.activate
    def test_reads_schema_resource(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        server.handle_message(_msg("initialize", {}))

        response = server.handle_message(
            _msg("resources/read", {"uri": "graphql://default/schema"})
        )
        contents = response["result"]["contents"]
        assert len(contents) == 1
        assert "Query" in contents[0]["text"]


class TestHandlePing:
    def test_ping_returns_empty(self, server):
        response = server.handle_message(_msg("ping"))
        assert response["result"] == {}


class TestUnknownMethod:
    def test_returns_method_not_found_error(self, server):
        response = server.handle_message(_msg("unknown/method"))
        assert "error" in response
        assert response["error"]["code"] == -32601


class TestParseError:
    def test_parse_error_on_invalid_json(self, server):
        stdin = io.StringIO("not-valid-json\n")
        stdout = io.StringIO()
        server.run(stdin=stdin, stdout=stdout)
        output = stdout.getvalue()
        response = json.loads(output.strip())
        assert response["error"]["code"] == -32700


class TestStdioRun:
    @resp_lib.activate
    def test_run_processes_messages(self, server):
        resp_lib.add(resp_lib.POST, ENDPOINT_URL, json=MINIMAL_SCHEMA, status=200)
        messages = [
            json.dumps(_msg("initialize", {})),
            json.dumps(_msg("ping")),
        ]
        stdin = io.StringIO("\n".join(messages) + "\n")
        stdout = io.StringIO()
        server.run(stdin=stdin, stdout=stdout)

        lines = [l for l in stdout.getvalue().splitlines() if l.strip()]
        assert len(lines) == 2
        init_resp = json.loads(lines[0])
        assert "result" in init_resp
        ping_resp = json.loads(lines[1])
        assert ping_resp["result"] == {}
