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
