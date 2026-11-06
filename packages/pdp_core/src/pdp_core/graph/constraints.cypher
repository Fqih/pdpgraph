// SPDX-License-Identifier: Apache-2.0
// 04-data-model §3.3, verbatim (tests/test_spec_graph_sync.py). Idempotent: IF NOT EXISTS.
CREATE CONSTRAINT legal_unit_id IF NOT EXISTS FOR (n:LegalUnit) REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT definition_id IF NOT EXISTS FOR (n:Definition) REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT obligation_id IF NOT EXISTS FOR (n:Obligation) REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT source_id IF NOT EXISTS FOR (n:Source) REQUIRE n.source_id IS UNIQUE;
CREATE INDEX legal_unit_unit IF NOT EXISTS FOR (n:LegalUnit) ON (n.unit_id);
CREATE INDEX legal_unit_validity IF NOT EXISTS FOR (n:LegalUnit) ON (n.valid_from, n.valid_to);
