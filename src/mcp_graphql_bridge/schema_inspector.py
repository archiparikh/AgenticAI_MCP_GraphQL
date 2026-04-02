"""
GraphQL schema inspector.

Parses the raw introspection payload and extracts structured information
about types, queries, mutations, and field arguments that is used by the
:mod:`tool_generator` to create MCP tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FieldInfo:
    """Metadata for a single field or argument."""

    name: str
    description: str
    type_name: str
    is_required: bool = False
    default_value: Any = None


@dataclass
class OperationInfo:
    """Metadata for a top-level GraphQL operation (query or mutation)."""

    name: str
    description: str
    operation_type: str  # "query" | "mutation"
    args: list[FieldInfo] = field(default_factory=list)
    return_type: str = ""

    @property
    def tool_name(self) -> str:
        """Return an MCP-safe tool name derived from the operation."""
        return f"{self.operation_type}_{self.name}"


# ---------------------------------------------------------------------------
# Inspector
# ---------------------------------------------------------------------------


class SchemaInspector:
    """
    Extracts operation metadata from a GraphQL introspection result.

    Parameters
    ----------
    introspection_data:
        The ``data.__schema`` portion of a raw introspection response, or the
        full ``data`` dict (either form is accepted).
    """

    def __init__(self, introspection_data: dict[str, Any]):
        if "__schema" in introspection_data:
            self._schema = introspection_data["__schema"]
        elif "data" in introspection_data and "__schema" in introspection_data["data"]:
            self._schema = introspection_data["data"]["__schema"]
        else:
            self._schema = introspection_data

        # Build a map from type name → type definition for quick lookups
        self._types: dict[str, dict[str, Any]] = {
            t["name"]: t for t in self._schema.get("types", []) if t.get("name")
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_queries(self) -> list[OperationInfo]:
        """Return metadata for all top-level query fields."""
        query_type_name = self._root_type_name("queryType")
        return self._extract_operations(query_type_name, "query")

    def get_mutations(self) -> list[OperationInfo]:
        """Return metadata for all top-level mutation fields."""
        mutation_type_name = self._root_type_name("mutationType")
        return self._extract_operations(mutation_type_name, "mutation")

    def get_all_operations(self) -> list[OperationInfo]:
        """Return queries and mutations combined."""
        return self.get_queries() + self.get_mutations()

    def get_type_names(self) -> list[str]:
        """Return user-defined (non-builtin) type names."""
        return [
            name
            for name in self._types
            if not name.startswith("__")
        ]

    def get_schema_sdl_summary(self) -> str:
        """Return a human-readable summary of the schema (not full SDL)."""
        lines: list[str] = []
        queries = self.get_queries()
        mutations = self.get_mutations()

        if queries:
            lines.append("type Query {")
            for op in queries:
                arg_str = self._format_args(op.args)
                lines.append(f"  {op.name}{arg_str}: {op.return_type}")
            lines.append("}")

        if mutations:
            lines.append("")
            lines.append("type Mutation {")
            for op in mutations:
                arg_str = self._format_args(op.args)
                lines.append(f"  {op.name}{arg_str}: {op.return_type}")
            lines.append("}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _root_type_name(self, kind: str) -> str:
        """Return the name of the root query/mutation/subscription type."""
        root = self._schema.get(kind)
        if root and isinstance(root, dict):
            return root.get("name", "")
        return ""

    def _extract_operations(
        self, type_name: str, operation_type: str
    ) -> list[OperationInfo]:
        """Extract :class:`OperationInfo` objects from a root type."""
        if not type_name or type_name not in self._types:
            return []

        type_def = self._types[type_name]
        operations: list[OperationInfo] = []

        for field_def in type_def.get("fields") or []:
            args = [
                self._parse_field_info(a) for a in (field_def.get("args") or [])
            ]
            operations.append(
                OperationInfo(
                    name=field_def["name"],
                    description=field_def.get("description") or "",
                    operation_type=operation_type,
                    args=args,
                    return_type=self._unwrap_type(field_def.get("type") or {}),
                )
            )

        return operations

    @staticmethod
    def _parse_field_info(arg_def: dict[str, Any]) -> FieldInfo:
        """Convert a raw argument definition to a :class:`FieldInfo`."""
        type_ref = arg_def.get("type") or {}
        type_name = SchemaInspector._unwrap_type(type_ref)
        is_required = type_ref.get("kind") == "NON_NULL"

        return FieldInfo(
            name=arg_def["name"],
            description=arg_def.get("description") or "",
            type_name=type_name,
            is_required=is_required,
            default_value=arg_def.get("defaultValue"),
        )

    @staticmethod
    def _unwrap_type(type_ref: dict[str, Any]) -> str:
        """Recursively unwrap a GraphQL type reference to a plain name string."""
        if not type_ref:
            return "Unknown"
        kind = type_ref.get("kind", "")
        name = type_ref.get("name")
        if name:
            if kind == "NON_NULL":
                return f"{name}!"
            return name
        inner = type_ref.get("ofType") or {}
        inner_name = SchemaInspector._unwrap_type(inner)
        if kind == "NON_NULL":
            return f"{inner_name}!"
        if kind == "LIST":
            return f"[{inner_name}]"
        return inner_name

    @staticmethod
    def _format_args(args: list[FieldInfo]) -> str:
        if not args:
            return ""
        parts = [
            f"{a.name}: {a.type_name}" for a in args
        ]
        return f"({', '.join(parts)})"
