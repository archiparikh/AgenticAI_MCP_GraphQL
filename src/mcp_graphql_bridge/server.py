"""
MCP Server – JSON-RPC 2.0 over stdio.

Implements the Model Context Protocol server side:
  * Capability negotiation (``initialize`` / ``initialized``)
  * Tool listing  (``tools/list``)
  * Tool invocation (``tools/call``)
  * Resource listing (``resources/list``)
  * Resource reading (``resources/read``)

The server reads newline-delimited JSON messages from *stdin* and writes
responses to *stdout*, which is the standard MCP stdio transport.

Usage
-----
.. code-block:: bash

    export GRAPHQL_URL=https://countries.trevorblades.com/
    python -m mcp_graphql_bridge.server

Or from Python:

.. code-block:: python

    from mcp_graphql_bridge import BridgeConfig, MCPServer

    config = BridgeConfig.from_env()
    server = MCPServer(config)
    server.run()
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from .config import BridgeConfig, EndpointConfig
from .graphql_client import GraphQLClient, GraphQLError
from .schema_inspector import SchemaInspector
from .tool_generator import MCPTool, ToolGenerator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

JSONRPC_VERSION = "2.0"


def _ok(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _err(
    request_id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


def _notification(method: str, params: Any = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------


class MCPServer:
    """
    Model Context Protocol server that bridges GraphQL endpoints to AI tools.

    Parameters
    ----------
    config:
        Bridge configuration (endpoints, server metadata, …).
    """

    def __init__(self, config: BridgeConfig):
        self._config = config
        self._tools: dict[str, MCPTool] = {}
        self._clients: dict[str, GraphQLClient] = {}
        self._inspectors: dict[str, SchemaInspector] = {}
        self._generator = ToolGenerator()

        # Build clients for each configured endpoint
        for ep in config.endpoints:
            self._clients[ep.name] = GraphQLClient(ep)

    # ------------------------------------------------------------------
    # Public entry-points
    # ------------------------------------------------------------------

    def run(
        self,
        stdin: Any = None,
        stdout: Any = None,
    ) -> None:
        """
        Start the server event loop.

        Reads JSON-RPC messages line-by-line from *stdin* (defaults to
        ``sys.stdin``) and writes responses to *stdout* (defaults to
        ``sys.stdout``).
        """
        _stdin = stdin or sys.stdin
        _stdout = stdout or sys.stdout

        logging.basicConfig(
            level=getattr(logging, self._config.log_level.upper(), logging.INFO),
            stream=sys.stderr,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )
        logger.info(
            "MCP GraphQL Bridge server starting (%s endpoints)",
            len(self._config.endpoints),
        )

        for line in _stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                response = _err(None, -32700, f"Parse error: {exc}")
                self._write(response, _stdout)
                continue

            response = self._handle(message)
            if response is not None:
                self._write(response, _stdout)

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single JSON-RPC message and return the response (or *None* for notifications)."""
        return self._handle(message)

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    def _handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method: str = message.get("method", "")
        request_id = message.get("id")
        params: dict[str, Any] = message.get("params") or {}

        # Notifications have no id – no response expected
        is_notification = "id" not in message

        try:
            result = self._dispatch(method, params)
        except MCPError as exc:
            if is_notification:
                return None
            return _err(request_id, exc.code, exc.message, exc.data)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error processing %s", method)
            if is_notification:
                return None
            return _err(request_id, -32603, f"Internal error: {exc}")

        if is_notification:
            return None

        return _ok(request_id, result)

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        handlers = {
            "initialize": self._handle_initialize,
            "initialized": self._handle_initialized,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "ping": self._handle_ping,
        }

        handler = handlers.get(method)
        if handler is None:
            raise MCPError(-32601, f"Method not found: {method}")

        return handler(params)

    # ------------------------------------------------------------------
    # MCP method handlers
    # ------------------------------------------------------------------

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Respond to the MCP ``initialize`` handshake."""
        self._build_tools()
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {
                "name": self._config.server_name,
                "version": self._config.server_version,
            },
        }

    def _handle_initialized(self, params: dict[str, Any]) -> None:  # noqa: ARG002
        """Handle the ``initialized`` notification (no response needed)."""
        logger.info("Client confirmed initialization")
        return None

    def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        return {"tools": [t.to_mcp_dict() for t in self._tools.values()]}

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name: str = params.get("name", "")
        arguments: dict[str, Any] = params.get("arguments") or {}

        tool = self._tools.get(name)
        if tool is None:
            raise MCPError(-32602, f"Unknown tool: {name}")

        return self._invoke_tool(tool, arguments)

    def _handle_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        resources = []
        for ep_name in self._clients:
            resources.append(
                {
                    "uri": f"graphql://{ep_name}/schema",
                    "name": f"{ep_name} – GraphQL Schema Summary",
                    "mimeType": "text/plain",
                }
            )
        return {"resources": resources}

    def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri: str = params.get("uri", "")
        # uri format: graphql://<endpoint_name>/schema
        parts = uri.replace("graphql://", "").split("/", 1)
        ep_name = parts[0]

        inspector = self._get_inspector(ep_name)
        summary = inspector.get_schema_sdl_summary()
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/plain",
                    "text": summary,
                }
            ]
        }

    def _handle_ping(self, params: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        return {}

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    def _invoke_tool(
        self, tool: MCPTool, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Route a tool call to the appropriate handler."""
        name = tool.name

        for ep_name in self._clients:
            # Utility: execute raw GraphQL
            if name == f"graphql_execute_{ep_name}":
                return self._invoke_execute(ep_name, arguments)
            # Utility: introspect
            if name == f"graphql_introspect_{ep_name}":
                return self._invoke_introspect(ep_name)
            # Utility: list operations
            if name == f"graphql_list_operations_{ep_name}":
                return self._invoke_list_operations(ep_name)
            # Per-operation tool
            if name.startswith(f"{ep_name}__") and tool.operation is not None:
                return self._invoke_operation(ep_name, tool, arguments)

        raise MCPError(-32602, f"Cannot resolve endpoint for tool: {name}")

    def _invoke_execute(
        self, ep_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        client = self._get_client(ep_name)
        query: str = arguments.get("query", "")
        variables: dict[str, Any] | None = arguments.get("variables")
        op_name: str | None = arguments.get("operation_name")

        try:
            resp = client.execute(query, variables=variables, operation_name=op_name)
        except GraphQLError as exc:
            return self._error_content(str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._error_content(f"HTTP error: {exc}")

        if resp.has_errors:
            return self._error_content(
                "; ".join(e.get("message", str(e)) for e in resp.errors)
            )

        return self._ok_content(json.dumps(resp.data, indent=2))

    def _invoke_introspect(self, ep_name: str) -> dict[str, Any]:
        inspector = self._get_inspector(ep_name)
        summary = inspector.get_schema_sdl_summary()
        return self._ok_content(summary or "(empty schema)")

    def _invoke_list_operations(self, ep_name: str) -> dict[str, Any]:
        inspector = self._get_inspector(ep_name)
        operations = inspector.get_all_operations()
        if not operations:
            return self._ok_content("No operations found.")

        lines = [f"Available operations on '{ep_name}':", ""]
        for op in operations:
            arg_str = (
                ", ".join(
                    f"{a.name}: {a.type_name}" for a in op.args
                )
                if op.args
                else ""
            )
            sig = f"{op.operation_type} {op.name}({arg_str}): {op.return_type}"
            lines.append(f"• {sig}")
            if op.description:
                lines.append(f"  {op.description}")

        return self._ok_content("\n".join(lines))

    def _invoke_operation(
        self,
        ep_name: str,
        tool: MCPTool,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        op = tool.operation
        assert op is not None  # guaranteed by caller

        client = self._get_client(ep_name)

        # Build the query document dynamically
        query_doc = self._build_query_document(op, arguments)

        try:
            resp = client.execute(query_doc, variables=arguments)
        except GraphQLError as exc:
            return self._error_content(str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._error_content(f"HTTP error: {exc}")

        if resp.has_errors:
            return self._error_content(
                "; ".join(e.get("message", str(e)) for e in resp.errors)
            )

        return self._ok_content(json.dumps(resp.data, indent=2))

    # ------------------------------------------------------------------
    # Build / refresh tools
    # ------------------------------------------------------------------

    def _build_tools(self) -> None:
        """Introspect all endpoints and register tools."""
        self._tools = {}
        for ep_name, client in self._clients.items():
            # Register utility tools (always present, no introspection needed)
            for t in ToolGenerator.build_utility_tools(ep_name):
                self._tools[t.name] = t

            ep_config: EndpointConfig | None = self._config.get_endpoint(ep_name)
            if ep_config is None or not ep_config.introspection_enabled:
                continue

            # Try to introspect and register per-operation tools
            try:
                resp = client.introspect()
                if resp.data:
                    inspector = SchemaInspector(resp.data)
                    self._inspectors[ep_name] = inspector
                    operations = inspector.get_all_operations()
                    for tool in self._generator.generate_from_operations(
                        operations, ep_name
                    ):
                        self._tools[tool.name] = tool
                    logger.info(
                        "Registered %d operation tools for endpoint '%s'",
                        len(operations),
                        ep_name,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to introspect endpoint '%s': %s – "
                    "only utility tools will be available.",
                    ep_name,
                    exc,
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_client(self, ep_name: str) -> GraphQLClient:
        client = self._clients.get(ep_name)
        if client is None:
            raise MCPError(-32602, f"Unknown endpoint: {ep_name}")
        return client

    def _get_inspector(self, ep_name: str) -> SchemaInspector:
        inspector = self._inspectors.get(ep_name)
        if inspector is None:
            # Attempt lazy introspection
            client = self._get_client(ep_name)
            resp = client.introspect()
            if resp.data:
                inspector = SchemaInspector(resp.data)
                self._inspectors[ep_name] = inspector
            else:
                raise MCPError(-32603, f"Could not introspect endpoint: {ep_name}")
        return inspector

    @staticmethod
    def _build_query_document(op: Any, variables: dict[str, Any]) -> str:
        """
        Build a minimal GraphQL document for the given operation.

        The document uses variables for all provided arguments so that
        the GraphQL server handles type coercion correctly.
        """
        from .schema_inspector import OperationInfo  # local import

        assert isinstance(op, OperationInfo)

        # Variable declarations for the operation signature
        var_decls = [
            f"${a.name}: {a.type_name}" for a in op.args if a.name in variables
        ]
        var_sig = f"({', '.join(var_decls)})" if var_decls else ""

        # Field arguments inside the selection set
        field_args = [
            f"{a.name}: ${a.name}" for a in op.args if a.name in variables
        ]
        field_arg_str = f"({', '.join(field_args)})" if field_args else ""

        return (
            f"{op.operation_type} {op.name.capitalize()}{var_sig} {{\n"
            f"  {op.name}{field_arg_str}\n"
            f"}}"
        )

    @staticmethod
    def _ok_content(text: str) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": text}]}

    @staticmethod
    def _error_content(text: str) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": text}],
            "isError": True,
        }

    @staticmethod
    def _write(message: dict[str, Any], stream: Any) -> None:
        stream.write(json.dumps(message) + "\n")
        stream.flush()


# ---------------------------------------------------------------------------
# MCPError
# ---------------------------------------------------------------------------


class MCPError(Exception):
    """Raised to return a JSON-RPC error response."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry-point used by ``mcp-graphql-server`` console script."""
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="MCP GraphQL Bridge – serve GraphQL APIs as MCP tools"
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=os.environ.get("MCP_CONFIG"),
        help="Path to a JSON configuration file (env: MCP_CONFIG)",
    )
    args = parser.parse_args()

    if args.config:
        config = BridgeConfig.from_file(args.config)
    else:
        config = BridgeConfig.from_env()

    server = MCPServer(config)
    server.run()


if __name__ == "__main__":
    main()
