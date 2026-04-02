"""
mcp_server.py
~~~~~~~~~~~~~
MCP server that exposes planning-workflow tools backed by a GraphQL API.

Tools
-----
list_plans          – Query all plans (optionally filtered by owner).
get_plan            – Fetch a single plan with its tasks.
create_plan         – Create a new plan.
update_plan         – Update plan metadata.
delete_plan         – Delete a plan.
list_tasks          – List tasks for a plan (optionally filter by status/assignee).
get_task            – Fetch a single task.
add_task            – Add a new task to a plan.
update_task         – Update task fields (status, priority, assignee, …).
delete_task         – Remove a task from a plan.
execute_graphql     – Escape-hatch: run any ad-hoc GraphQL query/mutation.

Configuration (environment variables)
--------------------------------------
GRAPHQL_ENDPOINT    – URL of the GraphQL API  (default: http://localhost:4000/graphql)
GRAPHQL_API_TOKEN   – Bearer token for authentication (optional)
GRAPHQL_AUTH_SCHEME – Auth scheme to use, e.g. "Bearer" or "Token" (default: Bearer)
GRAPHQL_TIMEOUT     – Request timeout in seconds (default: 30)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import graphql_client as gql_client
from graphql_client import GraphQLError

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="planning-graphql",
    instructions=(
        "MCP server that provides planning workflow tools backed by a GraphQL API. "
        "Supports creating and managing plans, tasks, priorities, assignments, and "
        "dependencies through a set of structured tools."
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLAN_FIELDS = """
  id title description owner createdAt updatedAt
  tasks {
    id title description status priority assignee dueDate dependencies createdAt updatedAt
  }
"""

_PLAN_SUMMARY_FIELDS = "id title description owner createdAt updatedAt"

_TASK_FIELDS = (
    "id planId title description status priority assignee "
    "dueDate dependencies createdAt updatedAt"
)


def _ok(data: dict[str, Any]) -> str:
    return json.dumps(data, default=str, indent=2)


def _err(exc: Exception) -> str:
    return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Plan tools
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "List all planning workflows (plans). "
        "Optionally filter by owner. Returns id, title, description, owner, "
        "creation/update timestamps for each plan."
    )
)
async def list_plans(owner: str = "", limit: int = 50, offset: int = 0) -> str:
    """Return a JSON array of plan summaries."""
    variables: dict[str, Any] = {"limit": limit, "offset": offset}
    if owner:
        variables["owner"] = owner

    query = f"""
    query ListPlans($limit: Int, $offset: Int{", $owner: String" if owner else ""}) {{
      plans(limit: $limit, offset: $offset{", owner: $owner" if owner else ""}) {{
        {_PLAN_SUMMARY_FIELDS}
      }}
    }}
    """
    try:
        data = await gql_client.execute(query, variables)
        return _ok(data.get("plans", []))
    except (GraphQLError, Exception) as exc:
        return _err(exc)


@mcp.tool(
    description=(
        "Fetch a single plan by its UUID, including all of its tasks with their "
        "current status, priority, assignee, due date, and dependencies."
    )
)
async def get_plan(plan_id: str) -> str:
    """Return a JSON object for the requested plan."""
    query = f"""
    query GetPlan($id: UUID!) {{
      plan(id: $id) {{
        {_PLAN_FIELDS}
      }}
    }}
    """
    try:
        data = await gql_client.execute(query, {"id": plan_id})
        return _ok(data.get("plan"))
    except (GraphQLError, Exception) as exc:
        return _err(exc)


@mcp.tool(
    description=(
        "Create a new planning workflow. "
        "Supply a title (required), an optional description, and an optional owner "
        "string (user-name or team name)."
    )
)
async def create_plan(title: str, description: str = "", owner: str = "") -> str:
    """Return the newly created plan as JSON."""
    mutation = f"""
    mutation CreatePlan($input: CreatePlanInput!) {{
      createPlan(input: $input) {{
        {_PLAN_SUMMARY_FIELDS}
      }}
    }}
    """
    inp: dict[str, Any] = {"title": title}
    if description:
        inp["description"] = description
    if owner:
        inp["owner"] = owner

    try:
        data = await gql_client.execute(mutation, {"input": inp})
        return _ok(data.get("createPlan"))
    except (GraphQLError, Exception) as exc:
        return _err(exc)


@mcp.tool(
    description=(
        "Update an existing plan's title, description, or owner. "
        "Only the fields you provide will be changed."
    )
)
async def update_plan(
    plan_id: str,
    title: str = "",
    description: str = "",
    owner: str = "",
) -> str:
    """Return the updated plan as JSON."""
    mutation = f"""
    mutation UpdatePlan($id: UUID!, $input: UpdatePlanInput!) {{
      updatePlan(id: $id, input: $input) {{
        {_PLAN_SUMMARY_FIELDS}
      }}
    }}
    """
    inp: dict[str, Any] = {}
    if title:
        inp["title"] = title
    if description:
        inp["description"] = description
    if owner:
        inp["owner"] = owner

    if not inp:
        return _err(ValueError("Provide at least one field to update."))

    try:
        data = await gql_client.execute(mutation, {"id": plan_id, "input": inp})
        return _ok(data.get("updatePlan"))
    except (GraphQLError, Exception) as exc:
        return _err(exc)


@mcp.tool(
    description="Delete a plan and all its tasks permanently. Returns true on success."
)
async def delete_plan(plan_id: str) -> str:
    """Delete a plan by its UUID."""
    mutation = """
    mutation DeletePlan($id: UUID!) {
      deletePlan(id: $id)
    }
    """
    try:
        data = await gql_client.execute(mutation, {"id": plan_id})
        return _ok({"deleted": data.get("deletePlan", False)})
    except (GraphQLError, Exception) as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Task tools
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "List all tasks belonging to a plan. "
        "Optionally filter by status (PENDING, IN_PROGRESS, BLOCKED, DONE, CANCELLED) "
        "and/or by assignee username."
    )
)
async def list_tasks(
    plan_id: str,
    status: str = "",
    assignee: str = "",
) -> str:
    """Return a JSON array of tasks for a plan."""
    variables: dict[str, Any] = {"planId": plan_id}
    status_arg = ""
    assignee_arg = ""
    if status:
        variables["status"] = status.upper()
        status_arg = ", status: $status"
    if assignee:
        variables["assignee"] = assignee
        assignee_arg = ", assignee: $assignee"

    status_decl = ", $status: TaskStatus" if status else ""
    assignee_decl = ", $assignee: String" if assignee else ""

    query = f"""
    query ListTasks($planId: UUID!{status_decl}{assignee_decl}) {{
      tasks(planId: $planId{status_arg}{assignee_arg}) {{
        {_TASK_FIELDS}
      }}
    }}
    """
    try:
        data = await gql_client.execute(query, variables)
        return _ok(data.get("tasks", []))
    except (GraphQLError, Exception) as exc:
        return _err(exc)


@mcp.tool(description="Fetch a single task by its UUID.")
async def get_task(task_id: str) -> str:
    """Return the task as JSON."""
    query = f"""
    query GetTask($id: UUID!) {{
      task(id: $id) {{
        {_TASK_FIELDS}
      }}
    }}
    """
    try:
        data = await gql_client.execute(query, {"id": task_id})
        return _ok(data.get("task"))
    except (GraphQLError, Exception) as exc:
        return _err(exc)


@mcp.tool(
    description=(
        "Add a new task to a plan. "
        "Required: plan_id, title. "
        "Optional: description, priority (LOW/MEDIUM/HIGH/CRITICAL, default MEDIUM), "
        "assignee, due_date (ISO-8601), "
        "dependencies (comma-separated list of task UUIDs this task depends on)."
    )
)
async def add_task(
    plan_id: str,
    title: str,
    description: str = "",
    priority: str = "MEDIUM",
    assignee: str = "",
    due_date: str = "",
    dependencies: str = "",
) -> str:
    """Create a new task and return it as JSON."""
    mutation = f"""
    mutation AddTask($input: AddTaskInput!) {{
      addTask(input: $input) {{
        {_TASK_FIELDS}
      }}
    }}
    """
    inp: dict[str, Any] = {
        "planId": plan_id,
        "title": title,
        "priority": priority.upper(),
    }
    if description:
        inp["description"] = description
    if assignee:
        inp["assignee"] = assignee
    if due_date:
        inp["dueDate"] = due_date
    if dependencies:
        inp["dependencies"] = [d.strip() for d in dependencies.split(",") if d.strip()]

    try:
        data = await gql_client.execute(mutation, {"input": inp})
        return _ok(data.get("addTask"))
    except (GraphQLError, Exception) as exc:
        return _err(exc)


@mcp.tool(
    description=(
        "Update an existing task. Supply any combination of: "
        "title, description, status (PENDING/IN_PROGRESS/BLOCKED/DONE/CANCELLED), "
        "priority (LOW/MEDIUM/HIGH/CRITICAL), assignee, due_date (ISO-8601), "
        "dependencies (comma-separated task UUIDs). "
        "Only the fields you provide will be changed."
    )
)
async def update_task(
    task_id: str,
    title: str = "",
    description: str = "",
    status: str = "",
    priority: str = "",
    assignee: str = "",
    due_date: str = "",
    dependencies: str = "",
) -> str:
    """Update and return the modified task as JSON."""
    mutation = f"""
    mutation UpdateTask($id: UUID!, $input: UpdateTaskInput!) {{
      updateTask(id: $id, input: $input) {{
        {_TASK_FIELDS}
      }}
    }}
    """
    inp: dict[str, Any] = {}
    if title:
        inp["title"] = title
    if description:
        inp["description"] = description
    if status:
        inp["status"] = status.upper()
    if priority:
        inp["priority"] = priority.upper()
    if assignee:
        inp["assignee"] = assignee
    if due_date:
        inp["dueDate"] = due_date
    if dependencies:
        inp["dependencies"] = [d.strip() for d in dependencies.split(",") if d.strip()]

    if not inp:
        return _err(ValueError("Provide at least one field to update."))

    try:
        data = await gql_client.execute(mutation, {"id": task_id, "input": inp})
        return _ok(data.get("updateTask"))
    except (GraphQLError, Exception) as exc:
        return _err(exc)


@mcp.tool(description="Delete a task by its UUID. Returns true on success.")
async def delete_task(task_id: str) -> str:
    """Delete a task."""
    mutation = """
    mutation DeleteTask($id: UUID!) {
      deleteTask(id: $id)
    }
    """
    try:
        data = await gql_client.execute(mutation, {"id": task_id})
        return _ok({"deleted": data.get("deleteTask", False)})
    except (GraphQLError, Exception) as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Escape-hatch: generic GraphQL execution
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Execute any arbitrary GraphQL query or mutation against the configured "
        "endpoint.  Supply the raw GraphQL document as `query` and an optional "
        "JSON string of variables as `variables_json`. "
        "Use this for advanced or one-off operations not covered by the other tools."
    )
)
async def execute_graphql(query: str, variables_json: str = "") -> str:
    """Run an ad-hoc GraphQL operation and return the raw response data."""
    variables: dict[str, Any] = {}
    if variables_json:
        try:
            variables = json.loads(variables_json)
        except json.JSONDecodeError as exc:
            return _err(ValueError(f"Invalid variables_json: {exc}"))

    try:
        data = await gql_client.execute(query, variables)
        return _ok(data)
    except (GraphQLError, Exception) as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
