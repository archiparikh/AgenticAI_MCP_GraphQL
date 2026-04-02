"""
Tests for schema_inspector.py
"""

import pytest

from mcp_graphql_bridge.schema_inspector import FieldInfo, OperationInfo, SchemaInspector


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_INTROSPECTION = {
    "__schema": {
        "queryType": {"name": "Query"},
        "mutationType": {"name": "Mutation"},
        "subscriptionType": None,
        "types": [
            {
                "kind": "OBJECT",
                "name": "Query",
                "description": "Root query type",
                "fields": [
                    {
                        "name": "user",
                        "description": "Fetch a user by ID",
                        "args": [
                            {
                                "name": "id",
                                "description": "User ID",
                                "type": {"kind": "NON_NULL", "name": "ID", "ofType": None},
                                "defaultValue": None,
                            }
                        ],
                        "type": {"kind": "OBJECT", "name": "User", "ofType": None},
                        "isDeprecated": False,
                        "deprecationReason": None,
                    },
                    {
                        "name": "users",
                        "description": "List all users",
                        "args": [],
                        "type": {
                            "kind": "LIST",
                            "name": None,
                            "ofType": {"kind": "OBJECT", "name": "User", "ofType": None},
                        },
                        "isDeprecated": False,
                        "deprecationReason": None,
                    },
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "Mutation",
                "description": "Root mutation type",
                "fields": [
                    {
                        "name": "createUser",
                        "description": "Create a new user",
                        "args": [
                            {
                                "name": "name",
                                "description": "User name",
                                "type": {
                                    "kind": "NON_NULL",
                                    "name": "String",
                                    "ofType": None,
                                },
                                "defaultValue": None,
                            },
                            {
                                "name": "email",
                                "description": "User email",
                                "type": {"kind": "SCALAR", "name": "String", "ofType": None},
                                "defaultValue": None,
                            },
                        ],
                        "type": {"kind": "OBJECT", "name": "User", "ofType": None},
                        "isDeprecated": False,
                        "deprecationReason": None,
                    }
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "User",
                "description": "A user object",
                "fields": [
                    {
                        "name": "id",
                        "description": None,
                        "args": [],
                        "type": {"kind": "SCALAR", "name": "ID", "ofType": None},
                        "isDeprecated": False,
                        "deprecationReason": None,
                    }
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
        ],
        "directives": [],
    }
}


@pytest.fixture
def inspector():
    return SchemaInspector(MINIMAL_INTROSPECTION)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSchemaInspectorConstruction:
    def test_accepts_schema_key(self):
        """SchemaInspector accepts a dict with a top-level __schema key."""
        inspector = SchemaInspector(MINIMAL_INTROSPECTION)
        assert inspector is not None

    def test_accepts_data_schema_key(self):
        """SchemaInspector accepts a dict with data.__schema."""
        inspector = SchemaInspector({"data": MINIMAL_INTROSPECTION})
        assert inspector is not None

    def test_accepts_raw_schema(self):
        """SchemaInspector accepts the raw __schema dict."""
        inspector = SchemaInspector(MINIMAL_INTROSPECTION["__schema"])
        assert inspector is not None


class TestGetQueries:
    def test_returns_query_operations(self, inspector):
        queries = inspector.get_queries()
        names = [q.name for q in queries]
        assert "user" in names
        assert "users" in names

    def test_operation_type_is_query(self, inspector):
        for q in inspector.get_queries():
            assert q.operation_type == "query"

    def test_user_query_has_id_arg(self, inspector):
        user_query = next(q for q in inspector.get_queries() if q.name == "user")
        arg_names = [a.name for a in user_query.args]
        assert "id" in arg_names

    def test_id_arg_is_required(self, inspector):
        user_query = next(q for q in inspector.get_queries() if q.name == "user")
        id_arg = next(a for a in user_query.args if a.name == "id")
        assert id_arg.is_required

    def test_return_type(self, inspector):
        user_query = next(q for q in inspector.get_queries() if q.name == "user")
        assert user_query.return_type == "User"

    def test_no_queries_when_type_missing(self):
        schema_no_query = {
            "__schema": {
                "queryType": None,
                "mutationType": None,
                "subscriptionType": None,
                "types": [],
                "directives": [],
            }
        }
        inspector = SchemaInspector(schema_no_query)
        assert inspector.get_queries() == []


class TestGetMutations:
    def test_returns_mutation_operations(self, inspector):
        mutations = inspector.get_mutations()
        names = [m.name for m in mutations]
        assert "createUser" in names

    def test_operation_type_is_mutation(self, inspector):
        for m in inspector.get_mutations():
            assert m.operation_type == "mutation"

    def test_create_user_args(self, inspector):
        create = next(m for m in inspector.get_mutations() if m.name == "createUser")
        arg_names = [a.name for a in create.args]
        assert "name" in arg_names
        assert "email" in arg_names

    def test_name_arg_is_required(self, inspector):
        create = next(m for m in inspector.get_mutations() if m.name == "createUser")
        name_arg = next(a for a in create.args if a.name == "name")
        assert name_arg.is_required

    def test_email_arg_not_required(self, inspector):
        create = next(m for m in inspector.get_mutations() if m.name == "createUser")
        email_arg = next(a for a in create.args if a.name == "email")
        assert not email_arg.is_required


class TestGetAllOperations:
    def test_combines_queries_and_mutations(self, inspector):
        ops = inspector.get_all_operations()
        op_types = {o.operation_type for o in ops}
        assert "query" in op_types
        assert "mutation" in op_types

    def test_count(self, inspector):
        queries = inspector.get_queries()
        mutations = inspector.get_mutations()
        all_ops = inspector.get_all_operations()
        assert len(all_ops) == len(queries) + len(mutations)


class TestGetTypeNames:
    def test_returns_user_defined_types(self, inspector):
        names = inspector.get_type_names()
        assert "User" in names
        assert "Query" in names

    def test_excludes_introspection_types(self, inspector):
        names = inspector.get_type_names()
        for name in names:
            assert not name.startswith("__")


class TestOperationInfo:
    def test_tool_name_query(self):
        op = OperationInfo(name="user", description="", operation_type="query")
        assert op.tool_name == "query_user"

    def test_tool_name_mutation(self):
        op = OperationInfo(name="createUser", description="", operation_type="mutation")
        assert op.tool_name == "mutation_createUser"


class TestSchemaSdlSummary:
    def test_contains_query_type(self, inspector):
        summary = inspector.get_schema_sdl_summary()
        assert "type Query" in summary

    def test_contains_mutation_type(self, inspector):
        summary = inspector.get_schema_sdl_summary()
        assert "type Mutation" in summary

    def test_contains_field_names(self, inspector):
        summary = inspector.get_schema_sdl_summary()
        assert "user" in summary
        assert "createUser" in summary


class TestUnwrapType:
    def test_scalar_non_null(self):
        ref = {"kind": "NON_NULL", "name": "String", "ofType": None}
        assert SchemaInspector._unwrap_type(ref) == "String!"

    def test_list(self):
        ref = {
            "kind": "LIST",
            "name": None,
            "ofType": {"kind": "SCALAR", "name": "String", "ofType": None},
        }
        assert SchemaInspector._unwrap_type(ref) == "[String]"

    def test_nested_non_null_list(self):
        ref = {
            "kind": "NON_NULL",
            "name": None,
            "ofType": {
                "kind": "LIST",
                "name": None,
                "ofType": {"kind": "SCALAR", "name": "Int", "ofType": None},
            },
        }
        # NON_NULL wrapping a LIST of Int → [Int]!
        assert SchemaInspector._unwrap_type(ref) == "[Int]!"

    def test_empty_ref(self):
        assert SchemaInspector._unwrap_type({}) == "Unknown"
