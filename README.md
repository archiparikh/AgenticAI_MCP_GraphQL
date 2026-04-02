# AgenticAI MCP GraphQL Bridge

MCP integrations that connect GraphQL APIs with external AI platforms and tools.

## Overview

**MCP GraphQL Bridge** implements the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server-side to expose any GraphQL API as a set of AI-callable tools. It bridges:

- **GraphQL APIs** → introspected at startup; every query and mutation becomes a named tool
- **MCP clients** (Claude Desktop, any MCP-compatible client) → via JSON-RPC 2.0 over stdio
- **OpenAI function calling** → via the included `OpenAIGraphQLAdapter`

```
┌────────────────────┐      MCP / stdio       ┌──────────────────────┐
│  AI Platform       │◄──────────────────────►│  MCP GraphQL Bridge  │
│  (Claude, GPT, …)  │                         │  server.py           │
└────────────────────┘                         └──────────┬───────────┘
                                                          │  HTTP/HTTPS
                                                          ▼
                                               ┌──────────────────────┐
                                               │  GraphQL Endpoint(s) │
                                               └──────────────────────┘
```

---

## Project Structure

```
src/mcp_graphql_bridge/
├── __init__.py          – public exports
├── config.py            – endpoint & server configuration (Pydantic models)
├── graphql_client.py    – lightweight HTTP client for GraphQL
├── schema_inspector.py  – parse introspection results into operation metadata
├── tool_generator.py    – convert schema operations → MCP tool descriptors
├── server.py            – MCP server (JSON-RPC 2.0 over stdio)
└── openai_adapter.py    – OpenAI function-calling adapter

tests/
├── test_config.py
├── test_graphql_client.py
├── test_schema_inspector.py
├── test_tool_generator.py
└── test_server.py

examples/
├── config.example.json  – sample multi-endpoint configuration
├── run_demo.py          – MCP server demo (no API key required)
└── openai_demo.py       – OpenAI adapter demo
```

---

## Installation

### Prerequisites

- Python ≥ 3.10
- `pip`

### Install dependencies

```bash
pip install -r requirements.txt
```

For development (adds pytest + responses for testing):

```bash
pip install -r requirements-dev.txt
```

Or install the package in editable mode:

```bash
pip install -e ".[dev]"
```

---

## Quick Start

### 1. Configure the server

**Option A – environment variables (single endpoint)**

```bash
export GRAPHQL_URL=https://countries.trevorblades.com/
export GRAPHQL_HEADERS='{"Authorization": "Bearer <token>"}'  # optional
export MCP_LOG_LEVEL=INFO
```

**Option B – JSON config file**

Copy `examples/config.example.json` and edit it:

```json
{
  "server_name": "my-mcp-server",
  "endpoints": [
    {
      "name": "countries",
      "url": "https://countries.trevorblades.com/",
      "headers": {},
      "timeout": 30,
      "introspection_enabled": true
    }
  ]
}
```

The `$ENV_VAR` syntax inside header values is expanded from the environment at startup.

### 2. Run the MCP server

```bash
# From environment variables:
python -m mcp_graphql_bridge.server

# From a config file:
python -m mcp_graphql_bridge.server --config my-config.json

# Or via the installed console script (after pip install):
mcp-graphql-server --config my-config.json
```

The server communicates over **stdio** (JSON-RPC 2.0 newline-delimited), the standard MCP transport.

### 3. Use with Claude Desktop

Add the server to your `claude_desktop_config.json`:
# AgenticAI_MCP_GraphQL

MCP server that connects a **GraphQL planning-workflow API** to AI assistants
(Claude Desktop, Cursor, or any MCP-compatible client).

---

## Repository layout

```
.
├── mcp_server.py       # MCP server — exposes planning tools to the AI client
├── graphql_client.py   # Async GraphQL client wrapper (gql + httpx)
├── schema.graphql      # Reference schema for the planning GraphQL API
├── requirements.txt    # Python dependencies
└── .env.example        # Example environment configuration
```

---

## Quick start

### 1 — Prerequisites

* Python 3.11+
* A running GraphQL API that implements `schema.graphql`
  (or any compatible service such as Hasura, PostGraphile, or a custom server)

### 2 — Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3 — Configure environment

Copy `.env.example` to `.env` and fill in your values:

```
GRAPHQL_ENDPOINT=http://localhost:4000/graphql
GRAPHQL_API_TOKEN=                # leave blank if no auth required
GRAPHQL_AUTH_SCHEME=Bearer        # Bearer | Token | …
GRAPHQL_TIMEOUT=30
```

### 4 — Run the MCP server

```bash
python mcp_server.py
```

The server communicates over **stdio** (MCP standard transport) and is ready
to be connected to any MCP-compatible AI client.

---

## Connecting to Claude Desktop

Add the following block to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "graphql": {
      "command": "python",
      "args": ["-m", "mcp_graphql_bridge.server"],
      "env": {
        "GRAPHQL_URL": "https://countries.trevorblades.com/"
      }
    }
  }
}
```

Claude will now have access to every GraphQL query and mutation as a callable tool.

---

## MCP Tools

The server registers tools in two categories for every configured endpoint.

### Utility tools (always present)

| Tool name | Description |
|---|---|
| `graphql_execute_<ep>` | Execute any raw GraphQL query or mutation |
| `graphql_introspect_<ep>` | Return a schema summary (SDL-like) |
| `graphql_list_operations_<ep>` | List all available queries and mutations |

### Per-operation tools (generated from schema)

Each query and mutation discovered during introspection gets its own tool, named `<endpoint>__<type>_<operationName>`, e.g.:

- `countries__query_countries`
- `countries__query_country`
- `myapi__mutation_createUser`

Arguments are derived from the operation signature and exposed as typed JSON Schema properties.

---

## OpenAI Function Calling

```python
from mcp_graphql_bridge import BridgeConfig
from mcp_graphql_bridge.openai_adapter import OpenAIGraphQLAdapter

config = BridgeConfig.from_env()  # or BridgeConfig.from_file("config.json")
adapter = OpenAIGraphQLAdapter(config)

# Pass to OpenAI
functions = adapter.get_openai_functions()

# Handle a function call returned by the model
result_text = adapter.handle_function_call(
    name=function_call.name,
    arguments_json=function_call.arguments,
)
```

---

## Using the Library Programmatically

```python
from mcp_graphql_bridge import (
    BridgeConfig, EndpointConfig,
    GraphQLClient, SchemaInspector, ToolGenerator, MCPServer,
)

# Build config
config = BridgeConfig(
    endpoints=[
        EndpointConfig(
            name="myapi",
            url="https://api.example.com/graphql",
            headers={"Authorization": "Bearer mytoken"},
        )
    ]
)

# Introspect schema and list operations
client = GraphQLClient(config.endpoints[0])
resp = client.introspect()
inspector = SchemaInspector(resp.data)
print(inspector.get_schema_sdl_summary())

# Generate MCP tools
generator = ToolGenerator()
tools = generator.generate_from_operations(inspector.get_all_operations(), "myapi")
for tool in tools:
    print(tool.name, "–", tool.description.splitlines()[0])

# Start the MCP server
server = MCPServer(config)
server.run()  # reads from stdin, writes to stdout
```

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest
```

---

## Architecture Notes

- **No GraphQL library required** – queries are sent as plain HTTP POST with JSON.
- **Pure stdio transport** – the server speaks JSON-RPC 2.0 over stdin/stdout, which is the standard MCP transport for CLI-launched servers.
- **Schema-driven tool generation** – tools are built from introspection at startup; the AI always has an up-to-date view of the API.
- **Multiple endpoints** – a single server instance can bridge several GraphQL APIs simultaneously; each gets its own namespaced set of tools.
- **OpenAI compatible** – the same tool descriptors use JSON Schema, making them directly usable as OpenAI function definitions.

    "planning-graphql": {
      "command": "python",
      "args": ["/absolute/path/to/mcp_server.py"],
      "env": {
        "GRAPHQL_ENDPOINT": "http://localhost:4000/graphql",
        "GRAPHQL_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

---

## Available tools

| Tool | Description |
|---|---|
| `list_plans` | List all plans, optionally filtered by owner |
| `get_plan` | Fetch a single plan with all its tasks |
| `create_plan` | Create a new planning workflow |
| `update_plan` | Update plan title / description / owner |
| `delete_plan` | Delete a plan and all its tasks |
| `list_tasks` | List tasks for a plan; filter by status or assignee |
| `get_task` | Fetch a single task |
| `add_task` | Add a task to a plan with priority, assignee, due date, and dependencies |
| `update_task` | Update any task field (status, priority, assignee, …) |
| `delete_task` | Delete a task |
| `execute_graphql` | Run any ad-hoc GraphQL query or mutation |

---

## GraphQL schema

See [`schema.graphql`](schema.graphql) for the full API schema.
Key types:

* **Plan** — top-level planning workflow with a title, description, owner, and list of tasks.
* **Task** — individual work item with status (`PENDING` → `IN_PROGRESS` → `DONE`),
  priority (`LOW` / `MEDIUM` / `HIGH` / `CRITICAL`), optional assignee, due date,
  and a list of dependency task UUIDs.

---

## Architecture

```
AI Client (Claude / Cursor / …)
        │  MCP protocol (stdio)
        ▼
  mcp_server.py   ←─ FastMCP tools
        │  async GraphQL operations
        ▼
  graphql_client.py  (gql + httpx)
        │  HTTP/HTTPS
        ▼
  GraphQL API  (Hasura / PostGraphile / custom)
        │
        ▼
  Database (PostgreSQL / etc.)
```
