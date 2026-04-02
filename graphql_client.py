"""
graphql_client.py
~~~~~~~~~~~~~~~~~
Async GraphQL client that wraps the `gql` library and adds lightweight
retry / error-normalisation logic used by the MCP server tools.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from gql import Client, gql
from gql.transport.exceptions import TransportQueryError, TransportServerError
from gql.transport.httpx import HTTPXAsyncTransport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_ENDPOINT = os.getenv("GRAPHQL_ENDPOINT", "http://localhost:4000/graphql")
DEFAULT_TIMEOUT = float(os.getenv("GRAPHQL_TIMEOUT", "30"))


def _auth_headers() -> dict[str, str]:
    """Build auth headers from environment variables (if set)."""
    headers: dict[str, str] = {}
    token = os.getenv("GRAPHQL_API_TOKEN")
    if token:
        scheme = os.getenv("GRAPHQL_AUTH_SCHEME", "Bearer")
        headers["Authorization"] = f"{scheme} {token}"
    return headers


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def build_transport(endpoint: str | None = None) -> HTTPXAsyncTransport:
    url = endpoint or DEFAULT_ENDPOINT
    return HTTPXAsyncTransport(
        url=url,
        headers=_auth_headers(),
        timeout=httpx.Timeout(DEFAULT_TIMEOUT),
    )


def build_client(endpoint: str | None = None) -> Client:
    transport = build_transport(endpoint)
    return Client(transport=transport, fetch_schema_from_transport=False)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class GraphQLError(Exception):
    """Raised when the GraphQL server returns an error response."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.errors = errors or []


async def execute(
    query_str: str,
    variables: dict[str, Any] | None = None,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """Execute a GraphQL operation and return the ``data`` dict.

    Parameters
    ----------
    query_str:
        Raw GraphQL document (query or mutation).
    variables:
        Optional variable dict.
    endpoint:
        Override the default endpoint URL.

    Returns
    -------
    dict
        The ``data`` field from the GraphQL response.

    Raises
    ------
    GraphQLError
        On GraphQL-level errors (``errors`` array in the response).
    httpx.HTTPError
        On transport/network failures.
    """
    client = build_client(endpoint)
    document = gql(query_str)
    try:
        async with client as session:
            result: dict[str, Any] = await session.execute(
                document, variable_values=variables or {}
            )
        return result
    except TransportQueryError as exc:
        errors = exc.errors or []
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        logger.error("GraphQL query error: %s", messages)
        raise GraphQLError(messages, errors) from exc
    except TransportServerError as exc:
        logger.error("GraphQL server error: %s", exc)
        raise GraphQLError(str(exc)) from exc
