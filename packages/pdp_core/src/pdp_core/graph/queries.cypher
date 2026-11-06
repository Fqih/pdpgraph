// SPDX-License-Identifier: Apache-2.0
// Canonical graph queries (04-data-model §3.4). One query per "// name:" header; parameters are
// documented in pdp_core/graph/queries.py. A node is valid at $as_of when
// valid_from <= $as_of and (valid_to is null or valid_to > $as_of).

// name: expand_references
MATCH p = (s:LegalUnit)-[:REFERENCES*1..5]->(:LegalUnit)
WHERE s.node_id IN $node_ids
  AND length(p) <= $max_hops
  AND all(n IN nodes(p) WHERE n.valid_from <= $as_of AND (n.valid_to IS NULL OR n.valid_to > $as_of))
RETURN [n IN nodes(p) | n.node_id] AS path
ORDER BY length(p), [n IN nodes(p) | n.order]

// name: definitions_for
MATCH (u:LegalUnit)-[r:USES_TERM]->(d:Definition)<-[:DEFINES]-(du:LegalUnit)
WHERE u.node_id IN $node_ids
  AND du.valid_from <= $as_of AND (du.valid_to IS NULL OR du.valid_to > $as_of)
RETURN u.node_id AS unit, d.node_id AS definition, d.term AS term, du.node_id AS defined_by,
       r.count AS count, r.nested_in_informal AS nested_in_informal,
       r.ambiguous_case AS ambiguous_case
ORDER BY unit, term

// name: context_of
MATCH (u:LegalUnit {node_id: $node_id})
RETURN
  COLLECT { MATCH (u)-[:PART_OF*0..3]->(p:LegalUnit {kind: 'PASAL'}) RETURN p.node_id } AS pasal,
  COLLECT {
    MATCH (u)-[:PART_OF]->()<-[:PART_OF]-(s:LegalUnit)
    WHERE s <> u AND s.kind = u.kind
    RETURN s.node_id ORDER BY s.order
  } AS siblings,
  COLLECT {
    MATCH (u)-[:PART_OF*0..3]->(x:LegalUnit)-[:EXPLAINED_BY]->(pj:LegalUnit)
    RETURN pj {.node_id, .order}
    UNION
    MATCH (x:LegalUnit)-[:PART_OF*1..3]->(u)
    MATCH (x)-[:EXPLAINED_BY]->(pj:LegalUnit)
    RETURN pj {.node_id, .order}
  } AS penjelasan

// name: version_at
MATCH (n:LegalUnit {unit_id: $unit_id})
WHERE n.valid_from <= $as_of AND (n.valid_to IS NULL OR n.valid_to > $as_of)
RETURN n.node_id AS node_id
ORDER BY node_id

// name: category_codes
UNWIND $codes AS code
OPTIONAL MATCH (c:DataCategory {code: code, status: 'confirmed'})
OPTIONAL MATCH (c)-[:SUBCATEGORY_OF]->(parent:DataCategory)
RETURN code, c IS NOT NULL AS known, coalesce(c.open, false) AS open, parent.code AS parent

// name: candidate_obligations
MATCH (lu:LegalUnit)-[:IMPOSES]->(o:Obligation {review_status: 'APPROVED'})
      -[:APPLIES_TO_ACTOR]->(:Actor {name: $actor_role})
WHERE lu.valid_from <= $as_of AND (lu.valid_to IS NULL OR lu.valid_to > $as_of)
WITH DISTINCT o, COLLECT { MATCH (o)-[:TRIGGERED_BY]->(t) RETURN t.code } AS triggers
WHERE size(triggers) = 0 OR any(t IN triggers WHERE t IN $codes)
RETURN o.node_id AS node_id
ORDER BY node_id
