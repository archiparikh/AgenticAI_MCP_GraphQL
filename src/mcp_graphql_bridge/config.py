"""
Configuration management for the MCP GraphQL Bridge.

Supports multiple named GraphQL endpoints with per-endpoint auth headers,
timeouts, and optional introspection caching.
"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field, model_validator


class EndpointConfig(BaseModel):
    """Configuration for a single GraphQL endpoint."""

    name: str = Field(..., description="Unique name for this endpoint")
    url: str = Field(..., description="GraphQL endpoint URL")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers sent with every request (e.g. Authorization)",
    )
    timeout: float = Field(
        default=30.0,
        ge=1.0,
        description="Request timeout in seconds",
    )
    introspection_enabled: bool = Field(
        default=True,
        description="Whether to introspect the schema on startup",
    )

    @model_validator(mode="before")
    @classmethod
    def expand_env_vars_in_headers(cls, values: Any) -> Any:
        """Expand ``$ENV_VAR`` references inside header values."""
        headers = values.get("headers", {})
        if isinstance(headers, dict):
            values["headers"] = {
                key: os.path.expandvars(value)
                for key, value in headers.items()
            }
        return values


class BridgeConfig(BaseModel):
    """Top-level configuration for the MCP GraphQL Bridge."""

    endpoints: list[EndpointConfig] = Field(
        default_factory=list,
        description="List of GraphQL endpoints to expose as MCP tools",
    )
    server_name: str = Field(
        default="mcp-graphql-bridge",
        description="MCP server name reported during capability negotiation",
    )
    server_version: str = Field(
        default="0.1.0",
        description="MCP server version",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    @classmethod
    def from_file(cls, path: str) -> "BridgeConfig":
        """Load configuration from a JSON file."""
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls.model_validate(data)

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        """
        Construct a minimal single-endpoint config from environment variables.

        Expected environment variables
        ------------------------------
        GRAPHQL_URL         GraphQL endpoint URL (required)
        GRAPHQL_HEADERS     JSON object of headers, e.g. ``{"Authorization":"Bearer tok"}``
        GRAPHQL_TIMEOUT     Request timeout in seconds (default: 30)
        MCP_SERVER_NAME     Override server name
        MCP_LOG_LEVEL       Logging level
        """
        url = os.environ.get("GRAPHQL_URL", "")
        if not url:
            return cls()

        headers_raw = os.environ.get("GRAPHQL_HEADERS", "{}")
        try:
            headers: dict[str, str] = json.loads(headers_raw)
        except json.JSONDecodeError:
            headers = {}

        endpoint = EndpointConfig(
            name="default",
            url=url,
            headers=headers,
            timeout=float(os.environ.get("GRAPHQL_TIMEOUT", "30")),
        )

        return cls(
            endpoints=[endpoint],
            server_name=os.environ.get("MCP_SERVER_NAME", "mcp-graphql-bridge"),
            log_level=os.environ.get("MCP_LOG_LEVEL", "INFO"),
        )

    def get_endpoint(self, name: str) -> EndpointConfig | None:
        """Return the named endpoint, or *None* if not found."""
        for ep in self.endpoints:
            if ep.name == name:
                return ep
        return None
