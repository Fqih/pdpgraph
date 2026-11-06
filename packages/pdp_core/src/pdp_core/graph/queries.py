# SPDX-License-Identifier: Apache-2.0
"""Canonical graph queries (04 §3.4) over `queries.cypher`. Read-only; `as_of` is a date."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from neo4j import Driver, RoutingControl

MAX_HOPS = 5  # upper bound of the variable-length pattern in expand_references


class VersionError(Exception):
    """A unit has no version, or more than one, valid at the requested date."""


@dataclass(frozen=True)
class DefinitionUse:
    unit: str
    definition: str
    term: str
    defined_by: str
    count: int
    nested_in_informal: bool
    ambiguous_case: bool


@dataclass(frozen=True)
class Context:
    pasal: str | None
    siblings: tuple[str, ...]  # same kind, same parent, document order
    penjelasan: tuple[str, ...]  # of the unit, its ancestors up to the Pasal, its descendants


@dataclass(frozen=True)
class Candidates:
    obligations: tuple[str, ...]
    unknown_categories: tuple[str, ...]  # no confirmed code, or open-ended: gap status UNKNOWN


def _run(driver: Driver, name: str, **params: Any) -> list[dict[str, Any]]:
    from pdp_core.graph import QUERIES

    records, _, _ = driver.execute_query(QUERIES[name], params, routing_=RoutingControl.READ)
    return [r.data() for r in records]


def expand_references(
    driver: Driver, node_ids: list[str], as_of: date, max_hops: int = 2
) -> list[tuple[str, ...]]:
    """REFERENCES paths from the given nodes, shortest first; every node valid at `as_of`."""
    if not 1 <= max_hops <= MAX_HOPS:
        raise ValueError(f"max_hops must be 1..{MAX_HOPS}")
    rows = _run(driver, "expand_references", node_ids=node_ids, as_of=as_of, max_hops=max_hops)
    return [tuple(r["path"]) for r in rows]


def definitions_for(driver: Driver, node_ids: list[str], as_of: date) -> list[DefinitionUse]:
    """USES_TERM targets of the nodes with their defining unit (valid at `as_of`)."""
    return [
        DefinitionUse(**r) for r in _run(driver, "definitions_for", node_ids=node_ids, as_of=as_of)
    ]


def context_of(driver: Driver, node_id: str) -> Context:
    rows = _run(driver, "context_of", node_id=node_id)
    if not rows:
        raise KeyError(node_id)
    r = rows[0]
    pj = sorted(r["penjelasan"], key=lambda p: p["order"])
    return Context(
        next(iter(r["pasal"]), None), tuple(r["siblings"]), tuple(p["node_id"] for p in pj)
    )


def version_at(driver: Driver, unit_id: str, as_of: date) -> str:
    """The node_id of the single version of `unit_id` valid at `as_of`."""
    found = [r["node_id"] for r in _run(driver, "version_at", unit_id=unit_id, as_of=as_of)]
    if len(found) != 1:
        raise VersionError(f"{unit_id} at {as_of}: {len(found)} valid versions {found}")
    return str(found[0])


def candidate_obligations(
    driver: Driver, actor_role: str, data_categories: list[str], concepts: list[str], as_of: date
) -> Candidates:
    """Approved obligations of the actor imposed by units valid at `as_of`: unconditional ones,
    and those triggered by a given confirmed category, its parent class, or a given concept.
    Categories without a confirmed code, or open-ended ones, are returned as unknown (03 §5.3)
    and never mapped to the nearest code."""
    codes = _run(driver, "category_codes", codes=data_categories)
    unknown = sorted({r["code"] for r in codes if not r["known"] or r["open"]})
    known = {r["code"] for r in codes if r["known"] and not r["open"]}
    parents = {r["parent"] for r in codes if r["code"] in known and r["parent"]}
    triggers = sorted(known | parents | set(concepts))
    rows = _run(driver, "candidate_obligations", actor_role=actor_role, codes=triggers, as_of=as_of)
    return Candidates(tuple(r["node_id"] for r in rows), tuple(unknown))
