"""
Lightweight GraphQL HTTP client.

Sends queries and mutations over HTTP/HTTPS using the ``requests`` library.
No external GraphQL library required – just plain HTTP POST with JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests

from .config import EndpointConfig


@dataclass
class GraphQLResponse:
    """Parsed response from a GraphQL endpoint."""

    data: dict[str, Any] | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    extensions: dict[str, Any] | None = None
    http_status: int = 200

    @property
    def has_errors(self) -> bool:
        """Return *True* when the response contains GraphQL errors."""
        return bool(self.errors)

    @property
    def ok(self) -> bool:
        """Return *True* when there are no errors and the HTTP status is 2xx."""
        return self.http_status < 300 and not self.has_errors

    def raise_for_errors(self) -> None:
        """Raise :class:`GraphQLError` if the response contains errors."""
        if self.has_errors:
            messages = "; ".join(
                e.get("message", str(e)) for e in self.errors
            )
            raise GraphQLError(f"GraphQL errors: {messages}", errors=self.errors)


class GraphQLError(Exception):
    """Raised when a GraphQL response contains errors."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.errors = errors or []


class GraphQLClient:
    """HTTP client that executes GraphQL operations against a single endpoint."""

    INTROSPECTION_QUERY = """
    query IntrospectionQuery {
      __schema {
        queryType { name }
        mutationType { name }
        subscriptionType { name }
        types {
          ...FullType
        }
        directives {
          name
          description
          locations
          args {
            ...InputValue
          }
        }
      }
    }

    fragment FullType on __Type {
      kind
      name
      description
      fields(includeDeprecated: true) {
        name
        description
        args {
          ...InputValue
        }
        type {
          ...TypeRef
        }
        isDeprecated
        deprecationReason
      }
      inputFields {
        ...InputValue
      }
      interfaces {
        ...TypeRef
      }
      enumValues(includeDeprecated: true) {
        name
        description
        isDeprecated
        deprecationReason
      }
      possibleTypes {
        ...TypeRef
      }
    }

    fragment InputValue on __InputValue {
      name
      description
      type {
        ...TypeRef
      }
      defaultValue
    }

    fragment TypeRef on __Type {
      kind
      name
      ofType {
        kind
        name
        ofType {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
                ofType {
                  kind
                  name
                  ofType {
                    kind
                    name
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    def __init__(self, config: EndpointConfig, session: requests.Session | None = None):
        self._config = config
        self._session = session or requests.Session()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL query or mutation and return a :class:`GraphQLResponse`."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self._config.headers,
        }

        response = self._session.post(
            self._config.url,
            json=payload,
            headers=headers,
            timeout=self._config.timeout,
        )

        return self._parse_response(response)

    def introspect(self) -> GraphQLResponse:
        """Execute a full introspection query and return the raw response."""
        return self.execute(self.INTROSPECTION_QUERY, operation_name="IntrospectionQuery")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(http_response: requests.Response) -> GraphQLResponse:
        """Parse an HTTP response into a :class:`GraphQLResponse`."""
        http_response.raise_for_status()

        body: dict[str, Any] = http_response.json()
        return GraphQLResponse(
            data=body.get("data"),
            errors=body.get("errors") or [],
            extensions=body.get("extensions"),
            http_status=http_response.status_code,
        )
