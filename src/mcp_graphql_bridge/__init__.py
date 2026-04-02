"""
MCP GraphQL Bridge – connects GraphQL APIs with external AI platforms
via the Model Context Protocol (MCP).
"""

from .config import EndpointConfig, BridgeConfig
from .graphql_client import GraphQLClient, GraphQLResponse
from .schema_inspector import SchemaInspector, OperationInfo, FieldInfo
from .tool_generator import ToolGenerator, MCPTool
from .server import MCPServer

__all__ = [
    "EndpointConfig",
    "BridgeConfig",
    "GraphQLClient",
    "GraphQLResponse",
    "SchemaInspector",
    "OperationInfo",
    "FieldInfo",
    "ToolGenerator",
    "MCPTool",
    "MCPServer",
]
