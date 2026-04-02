"""
Tests for tool_generator.py
"""

import pytest

from mcp_graphql_bridge.schema_inspector import FieldInfo, OperationInfo
from mcp_graphql_bridge.tool_generator import MCPTool, ToolGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_operations():
    return [
        OperationInfo(
            name="user",
            description="Fetch user by ID",
            operation_type="query",
            args=[
                FieldInfo(
                    name="id",
                    description="User ID",
                    type_name="ID!",
                    is_required=True,
                )
            ],
            return_type="User",
        ),
        OperationInfo(
            name="createUser",
            description="Create a new user",
            operation_type="mutation",
            args=[
                FieldInfo(
                    name="name",
                    description="Full name",
                    type_name="String!",
                    is_required=True,
                ),
                FieldInfo(
                    name="age",
                    description="Age in years",
                    type_name="Int",
                    is_required=False,
                    default_value=None,
                ),
            ],
            return_type="User",
        ),
    ]


@pytest.fixture
def generator():
    return ToolGenerator()


# ---------------------------------------------------------------------------
# MCPTool tests
# ---------------------------------------------------------------------------

class TestMCPTool:
    def test_to_mcp_dict(self):
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )
        d = tool.to_mcp_dict()
        assert d["name"] == "test_tool"
        assert d["description"] == "A test tool"
        assert "inputSchema" in d

    def test_to_openai_function(self):
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )
        f = tool.to_openai_function()
        assert f["name"] == "test_tool"
        assert "parameters" in f
        assert f["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# ToolGenerator tests
# ---------------------------------------------------------------------------

class TestToolGeneratorFromOperations:
    def test_generates_one_tool_per_operation(self, generator, sample_operations):
        tools = generator.generate_from_operations(sample_operations, "ep")
        assert len(tools) == 2

    def test_tool_names_include_endpoint_and_operation(self, generator, sample_operations):
        tools = generator.generate_from_operations(sample_operations, "myep")
        names = {t.name for t in tools}
        assert "myep__query_user" in names
        assert "myep__mutation_createUser" in names

    def test_required_arg_in_schema(self, generator, sample_operations):
        tools = generator.generate_from_operations(sample_operations, "ep")
        user_tool = next(t for t in tools if "query_user" in t.name)
        schema = user_tool.input_schema
        assert "id" in schema["properties"]
        assert "id" in schema.get("required", [])

    def test_optional_arg_not_in_required(self, generator, sample_operations):
        tools = generator.generate_from_operations(sample_operations, "ep")
        create_tool = next(t for t in tools if "createUser" in t.name)
        schema = create_tool.input_schema
        assert "age" in schema["properties"]
        required = schema.get("required", [])
        assert "age" not in required

    def test_string_scalar_maps_to_string(self, generator, sample_operations):
        tools = generator.generate_from_operations(sample_operations, "ep")
        create_tool = next(t for t in tools if "createUser" in t.name)
        assert create_tool.input_schema["properties"]["name"]["type"] == "string"

    def test_int_scalar_maps_to_integer(self, generator, sample_operations):
        tools = generator.generate_from_operations(sample_operations, "ep")
        create_tool = next(t for t in tools if "createUser" in t.name)
        assert create_tool.input_schema["properties"]["age"]["type"] == "integer"

    def test_operation_back_ref_stored(self, generator, sample_operations):
        tools = generator.generate_from_operations(sample_operations, "ep")
        for t in tools:
            assert t.operation is not None

    def test_description_contains_operation_type(self, generator, sample_operations):
        tools = generator.generate_from_operations(sample_operations, "ep")
        user_tool = next(t for t in tools if "query_user" in t.name)
        assert "Query" in user_tool.description

    def test_empty_operations_returns_empty_list(self, generator):
        tools = generator.generate_from_operations([], "ep")
        assert tools == []


class TestUtilityTools:
    def test_builds_three_utility_tools(self):
        tools = ToolGenerator.build_utility_tools("ep")
        assert len(tools) == 3

    def test_execute_tool_present(self):
        tools = ToolGenerator.build_utility_tools("ep")
        names = {t.name for t in tools}
        assert "graphql_execute_ep" in names

    def test_introspect_tool_present(self):
        tools = ToolGenerator.build_utility_tools("ep")
        names = {t.name for t in tools}
        assert "graphql_introspect_ep" in names

    def test_list_operations_tool_present(self):
        tools = ToolGenerator.build_utility_tools("ep")
        names = {t.name for t in tools}
        assert "graphql_list_operations_ep" in names

    def test_execute_tool_requires_query(self):
        tools = ToolGenerator.build_utility_tools("ep")
        exec_tool = next(t for t in tools if t.name == "graphql_execute_ep")
        assert "query" in exec_tool.input_schema.get("required", [])

    def test_introspect_tool_no_required_args(self):
        tools = ToolGenerator.build_utility_tools("ep")
        introspect_tool = next(t for t in tools if t.name == "graphql_introspect_ep")
        assert introspect_tool.input_schema.get("required", []) == []


class TestListTypeMapping:
    def test_list_type_becomes_array(self):
        op = OperationInfo(
            name="tags",
            description="",
            operation_type="query",
            args=[
                FieldInfo(
                    name="ids",
                    description="",
                    type_name="[ID]",
                    is_required=False,
                )
            ],
            return_type="[String]",
        )
        generator = ToolGenerator()
        tools = generator.generate_from_operations([op], "ep")
        assert tools[0].input_schema["properties"]["ids"]["type"] == "array"
