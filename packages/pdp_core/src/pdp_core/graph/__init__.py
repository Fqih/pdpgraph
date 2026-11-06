# SPDX-License-Identifier: Apache-2.0
"""Neo4j graph access (04 §3, M1.5): constraints, canonical queries, driver settings."""

import re
from importlib.resources import files

from pdp_core.graph.queries import (
    Candidates,
    Context,
    DefinitionUse,
    VersionError,
    candidate_obligations,
    context_of,
    definitions_for,
    expand_references,
    version_at,
)
from pdp_core.graph.settings import Neo4jSettings, connect


def _statements(name: str) -> tuple[str, ...]:
    text = files(__package__).joinpath(name).read_text(encoding="utf-8")
    body = re.sub(r"//[^\n]*", "", text)
    return tuple(s.strip() for s in body.split(";") if s.strip())


def _queries(name: str) -> dict[str, str]:
    text = files(__package__).joinpath(name).read_text(encoding="utf-8")
    parts = re.split(r"^// name: (\w+)\n", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


CONSTRAINTS = _statements("constraints.cypher")
QUERIES = _queries("queries.cypher")

__all__ = [
    "CONSTRAINTS",
    "QUERIES",
    "Candidates",
    "Context",
    "DefinitionUse",
    "Neo4jSettings",
    "VersionError",
    "candidate_obligations",
    "connect",
    "context_of",
    "definitions_for",
    "expand_references",
    "version_at",
]
