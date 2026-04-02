"""
Tests for graphql_client.py
"""

import json

import pytest
import responses as resp_lib

from mcp_graphql_bridge.config import EndpointConfig
from mcp_graphql_bridge.graphql_client import GraphQLClient, GraphQLError, GraphQLResponse


ENDPOINT_URL = "http://test.example.com/graphql"


@pytest.fixture
def endpoint_config():
    return EndpointConfig(name="test", url=ENDPOINT_URL)


@pytest.fixture
def client(endpoint_config):
    return GraphQLClient(endpoint_config)


class TestGraphQLResponse:
    def test_has_errors_false(self):
        r = GraphQLResponse(data={"foo": 1})
        assert r.has_errors is False
        assert r.ok is True

    def test_has_errors_true(self):
        r = GraphQLResponse(errors=[{"message": "oops"}])
        assert r.has_errors is True
        assert r.ok is False

    def test_ok_false_on_bad_status(self):
        r = GraphQLResponse(data={}, http_status=500)
        assert r.ok is False

    def test_raise_for_errors_raises(self):
        r = GraphQLResponse(errors=[{"message": "bad field"}])
        with pytest.raises(GraphQLError, match="bad field"):
            r.raise_for_errors()

    def test_raise_for_errors_no_raise(self):
        r = GraphQLResponse(data={"user": {"id": "1"}})
        r.raise_for_errors()  # should not raise


class TestGraphQLClient:
    @resp_lib.activate
    def test_execute_success(self, client):
        resp_lib.add(
            resp_lib.POST,
            ENDPOINT_URL,
            json={"data": {"hello": "world"}},
            status=200,
        )
        result = client.execute("{ hello }")
        assert result.ok
        assert result.data == {"hello": "world"}

    @resp_lib.activate
    def test_execute_with_variables(self, client):
        resp_lib.add(
            resp_lib.POST,
            ENDPOINT_URL,
            json={"data": {"user": {"id": "1"}}},
            status=200,
        )
        result = client.execute(
            "query GetUser($id: ID!) { user(id: $id) { id } }",
            variables={"id": "1"},
        )
        assert result.data == {"user": {"id": "1"}}

        # Verify the request payload
        sent_body = json.loads(resp_lib.calls[0].request.body)
        assert sent_body["variables"] == {"id": "1"}

    @resp_lib.activate
    def test_execute_with_operation_name(self, client):
        resp_lib.add(
            resp_lib.POST,
            ENDPOINT_URL,
            json={"data": {}},
            status=200,
        )
        client.execute("query A { a } query B { b }", operation_name="A")
        sent_body = json.loads(resp_lib.calls[0].request.body)
        assert sent_body["operationName"] == "A"

    @resp_lib.activate
    def test_execute_with_graphql_errors(self, client):
        resp_lib.add(
            resp_lib.POST,
            ENDPOINT_URL,
            json={"data": None, "errors": [{"message": "Field not found"}]},
            status=200,
        )
        result = client.execute("{ badField }")
        assert result.has_errors
        assert result.errors[0]["message"] == "Field not found"

    @resp_lib.activate
    def test_execute_sends_auth_header(self):
        ep = EndpointConfig(
            name="auth",
            url=ENDPOINT_URL,
            headers={"Authorization": "Bearer mytoken"},
        )
        auth_client = GraphQLClient(ep)
        resp_lib.add(
            resp_lib.POST,
            ENDPOINT_URL,
            json={"data": {}},
            status=200,
        )
        auth_client.execute("{ ping }")
        request = resp_lib.calls[0].request
        assert request.headers["Authorization"] == "Bearer mytoken"

    @resp_lib.activate
    def test_execute_http_error_raises(self, client):
        resp_lib.add(
            resp_lib.POST,
            ENDPOINT_URL,
            status=500,
            body="Internal Server Error",
        )
        with pytest.raises(Exception):
            client.execute("{ ping }")

    @resp_lib.activate
    def test_introspect_sends_introspection_query(self, client):
        resp_lib.add(
            resp_lib.POST,
            ENDPOINT_URL,
            json={"data": {"__schema": {"types": [], "queryType": {"name": "Query"}}}},
            status=200,
        )
        result = client.introspect()
        assert result.ok
        sent_body = json.loads(resp_lib.calls[0].request.body)
        assert "__schema" in sent_body["query"]
        assert sent_body["operationName"] == "IntrospectionQuery"
