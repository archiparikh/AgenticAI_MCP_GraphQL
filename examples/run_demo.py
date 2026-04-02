#!/usr/bin/env python3
"""
Demo: run the MCP server against a public GraphQL API and exercise it
with a few synthesised JSON-RPC messages.

Usage
-----
    cd examples
    python run_demo.py

No API keys or external services required (uses a mock by default).
Set GRAPHQL_URL to point at a live endpoint if you want a real request.
"""

from __future__ import annotations

import io
import json
import os
import sys

# Allow running this script directly from the examples/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp_graphql_bridge.config import BridgeConfig, EndpointConfig
from mcp_graphql_bridge.server import MCPServer

# ---------------------------------------------------------------------------
# Build config
# ---------------------------------------------------------------------------

GRAPHQL_URL = os.environ.get("GRAPHQL_URL", "")

if GRAPHQL_URL:
    config = BridgeConfig.from_env()
else:
    # Use a minimal in-memory mock schema – no network calls needed
    print("[demo] GRAPHQL_URL not set, using mock schema.\n")
    config = BridgeConfig(
        endpoints=[
            EndpointConfig(
                name="demo",
                url="http://localhost:0/graphql",  # unused in mock mode
                introspection_enabled=False,       # skip real introspection
            )
        ]
    )


def demo_jsonrpc(server: MCPServer, messages: list[dict]) -> None:
    """Send a list of JSON-RPC messages through the server and print responses."""
    for msg in messages:
        response = server.handle_message(msg)
        if response is not None:
            print(f"→ {msg['method']}")
            print(json.dumps(response.get("result") or response.get("error"), indent=2))
            print()


# ---------------------------------------------------------------------------
# Run demo
# ---------------------------------------------------------------------------

server = MCPServer(config)

print("=" * 60)
print("  MCP GraphQL Bridge – Demo")
print("=" * 60)
print()

# Simulate the MCP handshake and a few tool calls
messages = [
    # 1. Initialize
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    # 2. List tools
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    # 3. List resources
    {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}},
    # 4. Ping
    {"jsonrpc": "2.0", "id": 4, "method": "ping", "params": {}},
]

demo_jsonrpc(server, messages)

print("Demo complete.")
