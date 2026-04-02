"""
OpenAI Function-Calling Adapter.

Bridges the MCP tool registry with OpenAI's function-calling API so that a
ChatGPT / GPT-4 conversation can invoke GraphQL operations seamlessly.

Usage
-----
.. code-block:: python

    from mcp_graphql_bridge import BridgeConfig
    from mcp_graphql_bridge.openai_adapter import OpenAIGraphQLAdapter

    config = BridgeConfig.from_env()
    adapter = OpenAIGraphQLAdapter(config)

    # Get the list of functions to pass to the OpenAI API
    functions = adapter.get_openai_functions()

    # After the model returns a function_call …
    result = adapter.handle_function_call(
        name=response.choices[0].message.function_call.name,
        arguments_json=response.choices[0].message.function_call.arguments,
    )

The adapter does NOT import the ``openai`` package itself – callers are
responsible for installing and using it. This keeps the package dependency
footprint minimal.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import BridgeConfig, EndpointConfig
from .graphql_client import GraphQLClient, GraphQLError
from .schema_inspector import SchemaInspector
from .tool_generator import MCPTool, ToolGenerator

logger = logging.getLogger(__name__)


class OpenAIGraphQLAdapter:
    """
    Adapter that exposes GraphQL operations as OpenAI function-calling tools.

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

        for ep in config.endpoints:
            self._clients[ep.name] = GraphQLClient(ep)

        self._build_tools()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_openai_functions(self) -> list[dict[str, Any]]:
        """Return the list of function definitions for the OpenAI API."""
        return [t.to_openai_function() for t in self._tools.values()]

    def handle_function_call(
        self, name: str, arguments_json: str
    ) -> str:
        """
        Execute the function called by the model and return the result as a string.

        Parameters
        ----------
        name:
            The function name from ``message.function_call.name``.
        arguments_json:
            The JSON-encoded arguments from ``message.function_call.arguments``.

        Returns
        -------
        str
            A human-readable string result suitable for inclusion in the
            ``function`` role message.
        """
        try:
            arguments: dict[str, Any] = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError as exc:
            return f"Error: could not parse arguments JSON – {exc}"

        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown function '{name}'"

        return self._invoke(tool, arguments)

    # ------------------------------------------------------------------
    # Tool building
    # ------------------------------------------------------------------

    def _build_tools(self) -> None:
        self._tools = {}
        for ep_name, client in self._clients.items():
            for t in ToolGenerator.build_utility_tools(ep_name):
                self._tools[t.name] = t

            ep_config: EndpointConfig | None = self._config.get_endpoint(ep_name)
            if ep_config is None or not ep_config.introspection_enabled:
                continue

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
                    "Failed to introspect endpoint '%s': %s", ep_name, exc
                )

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------

    def _invoke(self, tool: MCPTool, arguments: dict[str, Any]) -> str:
        name = tool.name

        for ep_name in self._clients:
            if name == f"graphql_execute_{ep_name}":
                return self._execute_raw(ep_name, arguments)
            if name == f"graphql_introspect_{ep_name}":
                return self._introspect(ep_name)
            if name == f"graphql_list_operations_{ep_name}":
                return self._list_operations(ep_name)
            if name.startswith(f"{ep_name}__") and tool.operation is not None:
                return self._execute_operation(ep_name, tool, arguments)

        return f"Error: cannot resolve endpoint for function '{name}'"

    def _execute_raw(self, ep_name: str, arguments: dict[str, Any]) -> str:
        client = self._clients[ep_name]
        query: str = arguments.get("query", "")
        variables: dict[str, Any] | None = arguments.get("variables")
        op_name: str | None = arguments.get("operation_name")
        try:
            resp = client.execute(query, variables=variables, operation_name=op_name)
        except (GraphQLError, Exception) as exc:
            return f"Error: {exc}"

        if resp.has_errors:
            return "Errors: " + "; ".join(
                e.get("message", str(e)) for e in resp.errors
            )
        return json.dumps(resp.data, indent=2)

    def _introspect(self, ep_name: str) -> str:
        inspector = self._inspectors.get(ep_name)
        if inspector is None:
            return f"Schema not available for endpoint '{ep_name}'"
        return inspector.get_schema_sdl_summary()

    def _list_operations(self, ep_name: str) -> str:
        inspector = self._inspectors.get(ep_name)
        if inspector is None:
            return f"Schema not available for endpoint '{ep_name}'"
        ops = inspector.get_all_operations()
        if not ops:
            return "No operations found."
        lines = [f"Operations on '{ep_name}':"]
        for op in ops:
            arg_str = ", ".join(f"{a.name}: {a.type_name}" for a in op.args)
            lines.append(f"  {op.operation_type} {op.name}({arg_str}): {op.return_type}")
        return "\n".join(lines)

    def _execute_operation(
        self, ep_name: str, tool: MCPTool, arguments: dict[str, Any]
    ) -> str:
        from .server import MCPServer  # local to avoid circular import

        op = tool.operation
        assert op is not None

        client = self._clients[ep_name]
        query_doc = MCPServer._build_query_document(op, arguments)

        try:
            resp = client.execute(query_doc, variables=arguments)
        except (GraphQLError, Exception) as exc:
            return f"Error: {exc}"

        if resp.has_errors:
            return "Errors: " + "; ".join(
                e.get("message", str(e)) for e in resp.errors
            )
        return json.dumps(resp.data, indent=2)
