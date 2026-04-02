#!/usr/bin/env python3
"""
Demo: use the OpenAI adapter to expose GraphQL operations as OpenAI functions.

This script does NOT call the OpenAI API – it just shows the function
definitions that would be sent to the API, and demonstrates how a function
call would be handled.

Usage
-----
    cd examples
    python openai_demo.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp_graphql_bridge.config import BridgeConfig, EndpointConfig
from mcp_graphql_bridge.openai_adapter import OpenAIGraphQLAdapter

# Build a config without introspection so no network calls are made
config = BridgeConfig(
    endpoints=[
        EndpointConfig(
            name="demo",
            url="http://localhost:0/graphql",
            introspection_enabled=False,
        )
    ]
)

adapter = OpenAIGraphQLAdapter(config)
functions = adapter.get_openai_functions()

print("=" * 60)
print("  OpenAI Function Definitions")
print("=" * 60)
print(json.dumps(functions, indent=2))
print()
print(f"Total functions available: {len(functions)}")
