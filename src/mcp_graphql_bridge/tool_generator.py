"""
MCP Tool Generator.

Converts :class:`~mcp_graphql_bridge.schema_inspector.OperationInfo` objects
into :class:`MCPTool` descriptors that the MCP server publishes and that AI
platforms (Anthropic, OpenAI, etc.) can invoke.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schema_inspector import FieldInfo, OperationInfo


# ---------------------------------------------------------------------------
# MCP tool descriptor
# ---------------------------------------------------------------------------


@dataclass
class MCPTool:
    """
    Represents a single MCP tool entry returned by ``tools/list``.

    The ``input_schema`` follows JSON Schema draft-07 so it is also compatible
    with OpenAI function-calling format.
    """

    name: str
    description: str
    input_schema: dict[str, Any]

    # Back-reference to the underlying operation for execution
    operation: OperationInfo | None = field(default=None, repr=False)

    def to_mcp_dict(self) -> dict[str, Any]:
        """Serialise to the JSON shape expected by the MCP ``tools/list`` response."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    def to_openai_function(self) -> dict[str, Any]:
        """Serialise to the OpenAI *function* schema format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

# Mapping from common GraphQL scalar names to JSON Schema types
_SCALAR_TYPE_MAP: dict[str, str] = {
    "String": "string",
    "Int": "integer",
    "Float": "number",
    "Boolean": "boolean",
    "ID": "string",
}


class ToolGenerator:
    """
    Generates :class:`MCPTool` objects from :class:`OperationInfo` objects.

    In addition to per-operation tools, it also generates three utility tools
    that are always present:

    * ``graphql_execute``  – execute any raw GraphQL query or mutation.
    * ``graphql_introspect`` – return the schema summary.
    * ``graphql_list_operations`` – list all available operations.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_from_operations(
        self, operations: list[OperationInfo], endpoint_name: str = "default"
    ) -> list[MCPTool]:
        """Generate one :class:`MCPTool` per operation."""
        tools: list[MCPTool] = []
        for op in operations:
            tool = self._operation_to_tool(op, endpoint_name)
            tools.append(tool)
        return tools

    @staticmethod
    def build_utility_tools(endpoint_name: str = "default") -> list[MCPTool]:
        """Return the three built-in utility tools for an endpoint."""
        return [
            MCPTool(
                name=f"graphql_execute_{endpoint_name}",
                description=(
                    f"Execute any GraphQL query or mutation against the '{endpoint_name}' "
                    "endpoint. Use this when no specific operation tool is available."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The GraphQL query or mutation document",
                        },
                        "variables": {
                            "type": "object",
                            "description": "Optional variables for the operation",
                        },
                        "operation_name": {
                            "type": "string",
                            "description": "Optional operation name when the document contains multiple operations",
                        },
                    },
                    "required": ["query"],
                },
            ),
            MCPTool(
                name=f"graphql_introspect_{endpoint_name}",
                description=(
                    f"Return a human-readable summary of the GraphQL schema "
                    f"exposed by the '{endpoint_name}' endpoint."
                ),
                input_schema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name=f"graphql_list_operations_{endpoint_name}",
                description=(
                    f"List all available GraphQL queries and mutations on the "
                    f"'{endpoint_name}' endpoint, with their argument signatures."
                ),
                input_schema={"type": "object", "properties": {}},
            ),
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _operation_to_tool(
        self, op: OperationInfo, endpoint_name: str
    ) -> MCPTool:
        """Convert a single :class:`OperationInfo` into an :class:`MCPTool`."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for arg in op.args:
            json_prop = self._field_to_json_schema(arg)
            properties[arg.name] = json_prop
            if arg.is_required:
                required.append(arg.name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required

        operation_word = op.operation_type.capitalize()
        desc_lines = [
            f"{operation_word}: {op.name}",
        ]
        if op.description:
            desc_lines.append(op.description)
        desc_lines.append(f"Returns: {op.return_type}")

        return MCPTool(
            name=f"{endpoint_name}__{op.tool_name}",
            description="\n".join(desc_lines),
            input_schema=schema,
            operation=op,
        )

    @staticmethod
    def _field_to_json_schema(field_info: FieldInfo) -> dict[str, Any]:
        """Convert a GraphQL field/arg to a JSON Schema property definition."""
        # Strip non-null marker
        raw_type = field_info.type_name.rstrip("!")

        # Strip list markers to get the inner scalar name
        inner = raw_type.strip("[]")
        json_type = _SCALAR_TYPE_MAP.get(inner, "string")

        is_list = raw_type.startswith("[")

        prop: dict[str, Any]
        if is_list:
            prop = {"type": "array", "items": {"type": json_type}}
        else:
            prop = {"type": json_type}

        if field_info.description:
            prop["description"] = field_info.description

        if field_info.default_value is not None:
            prop["default"] = field_info.default_value

        return prop
