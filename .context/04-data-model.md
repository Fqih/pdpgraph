# 04 — Data Model

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-11-05 |

All schemas below are normative. Pydantic models in `packages/pdp_core/src/pdp_core/schemas/` and `packages/tierline/src/tierline/schemas/` are the code-level source of truth and must match this document; when they diverge, update both in the same PR.

---

## 1. Source registry

Every ingested document has a `Source` record (Postgres `sources` + Neo4j `:Source` node).

| Field | Type | Example |
|---|---|---|
| `source_id` | str (slug) | `uu27-2022` |
| `title` | str | `Undang-Undang Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi` |
| `instrument_type` | enum `UU, PP, PERPRES, PERMEN, PERBAN, PUTUSAN_MK, OTHER` | `UU` |
| `number` / `year` | int / int | `27` / `2022` |
| `enacted_on` | date | [VERIFY] |
| `promulgated_on` | date | [VERIFY] |
| `effective_from` | date | [VERIFY] |
| `url` | str | official URL |
| `sha256` | str | hash of raw file |
| `fetched_at` | datetime | |
| `parser_version` | str | `segment@1.3.0` |
| `overrides_total` / `overrides_unconfirmed` | int / int | `31` / `31`: entries in `data/overrides/<source_id>.yaml`, and those without `confirmed_by`. Unconfirmed overrides are applied; the v0.1 exit gate requires `overrides_unconfirmed = 0` |

## 2. Identifier scheme

Two identifiers:

- **`unit_id`** — a legal or structural unit, independent of version.
- **`node_id`** — one version of that unit: `{unit_id}@{version}`.

### 2.1 Grammar (normative)

```ebnf
node_id        = unit_id "@" version ;
version        = digit_nz { digit } ;                          (* 1, 2, ... no leading zeros *)
unit_id        = source_id "/" path [ "#pj" ] ;                (* "#pj" = Penjelasan of that unit; always BEFORE "@" *)
source_id      = alnum { alnum } { "-" alnum { alnum } } ;     (* e.g. uu27-2022, pp-x-2025 *)
path           = structure | pasal_path | def_path | obl_path | "pj-umum" ;
structure      = "bab" int [ "/bag" int [ "/par" int ] ] ;     (* BAB III -> bab3; Bagian Kesatu -> bag1; Paragraf 2 -> par2 *)
pasal_path     = "p" int [ suffix ] [ "/a" int [ suffix ] ] [ "/h" letters ] [ "/n" int ] ;
suffix         = lower ;                                        (* Pasal 20A -> p20a; ayat (1a) -> a1a *)
letters        = lower { lower } ;                              (* huruf a -> ha; huruf aa (rare) -> haa *)
def_path       = "def/" slug ;
obl_path       = "obl/" pasal_ref "-" seq2 ;                    (* pasal_ref = "p" int [suffix], e.g. obl/p20-01 *)
seq2           = digit digit ;                                  (* 01..99, per Pasal *)
slug           = lower_alnum { lower_alnum | "-" } ;            (* ASCII-folded, lowercase, kebab-case of the term *)
int            = digit_nz { digit } ;
```

Rules:
- IDs are lowercase ASCII. Inputs are never case-folded silently: uppercase or malformed IDs are **rejected** by the parser.
- Pasal numbering is global within a source, so Pasal IDs are **not** nested under Bab/Bagian; structure membership is the `PART_OF` edge.
- `/n` (angka) may follow an ayat (`p20/a2/n1`) or a huruf (`p20/a2/hb/n1`).
- `#pj` attaches to any citable unit; the general elucidation is `{source_id}/pj-umum`.
- Definition slug: NFKD ASCII fold → lowercase → non-alphanumerics to `-` → collapse/trim `-`. Collisions get `-2`, `-3` in order of appearance.
- Obligation `seq2` is assigned in order of extraction within the Pasal and is stable across re-runs (sorted by source offset).
- IDs are **never** reused; a text change creates a new version and a `SUPERSEDES` edge.
- Display labels are generated (`Pasal 20 ayat (2) huruf b UU 27/2022`), never stored as identity.
- Implemented in `common/ids.py`: `parse(str) -> NodeId | UnitId`, `format(obj) -> str`, with round-trip property tests (`parse(format(x)) == x`).

### 2.2 Examples

| Legal unit | `unit_id` | `node_id` |
|---|---|---|
| BAB III | `uu27-2022/bab3` | `uu27-2022/bab3@1` |
| BAB III Bagian Kesatu Paragraf 2 | `uu27-2022/bab3/bag1/par2` | `uu27-2022/bab3/bag1/par2@1` |
| Pasal 20 | `uu27-2022/p20` | `uu27-2022/p20@1` |
| Pasal 20A | `uu27-2022/p20a` | `uu27-2022/p20a@1` |
| Pasal 20 ayat (2) | `uu27-2022/p20/a2` | `uu27-2022/p20/a2@1` |
| Pasal 20 ayat (1a) | `uu27-2022/p20/a1a` | `uu27-2022/p20/a1a@1` |
| Pasal 20 ayat (2) huruf b | `uu27-2022/p20/a2/hb` | `uu27-2022/p20/a2/hb@1` |
| Pasal 20 ayat (2) huruf b angka 1 | `uu27-2022/p20/a2/hb/n1` | `uu27-2022/p20/a2/hb/n1@1` |
| Penjelasan of Pasal 20 ayat (2) | `uu27-2022/p20/a2#pj` | `uu27-2022/p20/a2#pj@1` |
| Penjelasan Umum | `uu27-2022/pj-umum` | `uu27-2022/pj-umum@1` |
| Definition "Data Pribadi" | `uu27-2022/def/data-pribadi` | `uu27-2022/def/data-pribadi@1` |
| First obligation in Pasal 20 | `uu27-2022/obl/p20-01` | `uu27-2022/obl/p20-01@1` |

## 3. Knowledge graph (Neo4j)

### 3.1 Node labels

| Label | Key properties | Notes |
|---|---|---|
| `:Source` | `source_id`, `title`, `instrument_type`, `number`, `year`, `enacted_on`, `promulgated_on`, `effective_from`, `url`, `body_sha256`, `canonicalization_version`, `parser_version`, `segment_version`, `refs_version`, `defs_version`, `overrides_total`, `overrides_unconfirmed` | Provenance of the loaded artifacts (`source.json`, §3.9) |
| `:Structure` | `node_id`, `unit_id`, `kind ∈ {BAB, BAGIAN, PARAGRAF}`, `number`, `heading` | Grouping only, not citable |
| `:LegalUnit` | `node_id`, `unit_id`, `kind ∈ {PASAL, AYAT, HURUF, ANGKA, PENJELASAN}`, `text`, `text_norm`, `text_sha256`, `label`, `valid_from`, `valid_to` (null = open), `version`, `order` | **Citable** units. `text`/`text_norm` are absent in a text-less graph (§3.9) |
| `:Definition` | `node_id` (`<source>/def/<slug>@1`), `term`, `term_norm`, `aliases[]`, `text`, `text_sha256` | From definitional articles. The artifacts' `node_id` is the versionless id; the graph appends `@<version>` (§2) |
| `:Obligation` | `node_id`, `actor_role`, `action`, `object`, `condition`, `deadline`, `modality ∈ {WAJIB, DILARANG, DAPAT}`, `review_status ∈ {PENDING, APPROVED, REJECTED}` | Extracted; only `APPROVED` used online |
| `:Actor` | `name ∈ {PENGENDALI, PROSESOR, SUBJEK_DATA, LEMBAGA, DPO, PIHAK_KETIGA, ...}` | Controlled vocabulary |
| `:DataCategory` | `source_id` + `code` (key), `label`, `unit_id`, `open`, `explanation`, `status ∈ {proposed, confirmed}` | Derived from Pasal 4 (§3.8): classes `SPESIFIK`, `UMUM`; members `KESEHATAN`, `BIOMETRIK`, `GENETIKA`, `CATATAN_KEJAHATAN`, `ANAK`, `KEUANGAN_PRIBADI`, `LAINNYA` (open) under `SPESIFIK`; `NAMA_LENGKAP`, `JENIS_KELAMIN`, `KEWARGANEGARAAN`, `AGAMA`, `STATUS_PERKAWINAN`, `DIKOMBINASIKAN_UNTUK_MENGIDENTIFIKASI_SESEORANG` under `UMUM`. All `proposed` until the owner confirms them. `SPESIFIK` and `UMUM` are parent nodes; members link to them with `SUBCATEGORY_OF`. `LAINNYA` is open-ended (03 §5.3: unmappable categories give `UNKNOWN`) |
| `:Sanction` | `node_id`, `type ∈ {ADMINISTRATIVE, CRIMINAL}`, `description` | |
| `:Concept` | `code` (e.g., `LEGAL_BASIS`, `CONSENT`, `BREACH_NOTIFICATION`, `CROSS_BORDER_TRANSFER`, `DPO`, `DPIA`, `RETENTION`) | Topic tags for routing gap analysis |

### 3.2 Relationships

| Relationship | From → To | Properties |
|---|---|---|
| `PART_OF` | `LegalUnit`/`Structure` → parent | `order` |
| `IN_SOURCE` | any → `Source` | |
| `REFERENCES` | `LegalUnit` → `LegalUnit` | `mention_text`, `resolution ∈ {EXACT, PARENT, EXTERNAL_UNRESOLVED}`, `start`, `end` (mention span in the source unit's text; one edge per mention and target) |
| `EXPLAINED_BY` | `LegalUnit` → `LegalUnit{kind:PENJELASAN}` | |
| `DEFINES` | `LegalUnit` → `Definition` | |
| `USES_TERM` | `LegalUnit` → `Definition` | `count`, `informal_count`, `nested_in_informal`, `ambiguous_case` (defined uses only, §3.8) |
| `SUPERSEDES` | newer `LegalUnit` → older `LegalUnit` | `effective_on`, `by_source_id` |
| `MODIFIES_READING` | `Source{instrument_type: PUTUSAN_MK}` → `LegalUnit` | `effective_on`, `holding_summary`, `operative_text_quote` (verbatim, citable quote from the ruling), `status ∈ {CONDITIONALLY_UNCONSTITUTIONAL, UNCONSTITUTIONAL, OTHER}` (§3.5, ADR-017) |
| `AMENDS` | `Source` (amending instrument) → `LegalUnit` | `effective_on`, `lampiran_ref`, `operative_text_quote` (verbatim, citable) (§3.6, ADR-019) |
| `IMPOSES` | `LegalUnit` → `Obligation` | |
| `APPLIES_TO_ACTOR` | `Obligation` → `Actor` | |
| `TRIGGERED_BY` | `Obligation` → `DataCategory` / `Concept` | `condition_text` |
| `SUBCATEGORY_OF` | `DataCategory` (member) → `DataCategory` (`SPESIFIK` / `UMUM`) | |
| `EXCEPTION_OF` | `LegalUnit` → `Obligation` / `LegalUnit` | |
| `SANCTIONED_BY` | `Obligation` → `Sanction` | |
| `ABOUT` | `LegalUnit` → `Concept` | `confidence`, `method ∈ {RULE, LLM, MANUAL}` |

### 3.3 Constraints & indexes

```cypher
CREATE CONSTRAINT legal_unit_id IF NOT EXISTS FOR (n:LegalUnit) REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT definition_id IF NOT EXISTS FOR (n:Definition) REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT obligation_id IF NOT EXISTS FOR (n:Obligation) REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT source_id IF NOT EXISTS FOR (n:Source) REQUIRE n.source_id IS UNIQUE;
CREATE INDEX legal_unit_unit IF NOT EXISTS FOR (n:LegalUnit) ON (n.unit_id);
CREATE INDEX legal_unit_validity IF NOT EXISTS FOR (n:LegalUnit) ON (n.valid_from, n.valid_to);
```

### 3.4 Canonical queries (kept in `pdp_core/graph/queries.cypher`, tested)

- `expand_references(node_ids, as_of, max_hops)` — variable-length `REFERENCES` traversal, filtered by validity at `as_of`, returning paths.
- `definitions_for(node_ids, as_of)` — `USES_TERM` targets with defining unit.
- `context_of(node_id)` — parent Pasal + sibling ayat + Penjelasan, each Penjelasan labeled `own_explanation`, `ancestor_explanation` or `descendant_explanation`.
- `version_at(unit_id, as_of)` — the single valid version (assert exactly one).
- `candidate_obligations(actor_role, data_categories[], concepts[], as_of)` — gap-analysis seed.

### 3.5 Constitutional Court rulings (ADR-017)

A Mahkamah Konstitusi ruling changes the binding reading of a unit, not its promulgated text. It is ingested as its own `Source` (`instrument_type: PUTUSAN_MK`, e.g. `putusan-mk-151-2024`) linked to each affected unit by `MODIFIES_READING`. The affected `LegalUnit` keeps its text and version: no `SUPERSEDES` edge and no new version are created.

- `as_of ≥ effective_on`: graph expansion (`expand_references`, `context_of`) returns the ruling alongside the unit, and generation must cite both the article text and the ruling's `operative_text_quote`.
- `as_of < effective_on`: the ruling is not returned.
- Citations to a ruling use a `node_id` under the ruling's own `source_id` (`putusan-mk-151-2024/…`). The minimal §2 grammar extension for ruling paths, the node representation of the operative quote for citation verification, and the ID round-trip tests are specified and implemented in M4.4.
- Holding details come from the official MK PDF only; the owner confirms the operative part before ingestion.

### 3.6 Amendments and consolidated readings (ADR-019)

The official text of a source is never overwritten. An amending instrument (e.g. UU 1/2026 Penyesuaian Pidana) is its own `Source`. It links to each affected unit by `AMENDS {effective_on, lampiran_ref, operative_text_quote}`. Instruments needed to resolve the amendment are also sources, e.g. KUHP Pasal 79 for the fine-category amounts.

- A consolidated reading may be materialized for retrieval only. It is marked `derived: true` and carries provenance to both official texts.
- Citations always point to the official original unit and to the amending provision. They never point to derived text alone; citation verification rejects a citation that only names a derived node.
- `as_of < effective_on`: the amendment and any derived reading are not returned.
- Until an amendment is modeled, the currency guard (FR-PDP-20, `configs/pending_changes.yaml`) keeps the pipeline from answering with the superseded text.
- Implementation is M4.4.

### 3.7 Reference mentions (`refs` stage, M1.3)

`data/processed/<source_id>/refs.jsonl`, one row per mention:

| Field | Meaning |
|---|---|
| `unit_id` | Unit whose text contains the mention |
| `start`, `end`, `text` | Char span in the unit text (overrides applied) and the raw text, including a "sebagaimana dimaksud dalam/pada" prefix and an "Undang-Undang ini" or instrument suffix |
| `kind` | `REFERENCE` or `DELEGATION` ("diatur dengan/dalam Peraturan Pemerintah/Presiden/…") |
| `resolution` | `EXACT` (every item resolved), `UNRESOLVED` (an internal item has no unit; logged, FR-PDP-03), `SELF` ("Undang-Undang ini" alone), `EXTERNAL_UNRESOLVED` (external instrument, and every delegation) |
| `targets` | Internal unit ids, ranges expanded to one id per unit |
| `instrument` | External or delegated instrument as written |
| `patterns` | Sampling strata (06 §2.9) |
| `unresolved` | Internal items without a unit |

A mention is one chain of items joined by lists or ranges. Relative items take missing upper levels from the previous item, else from the context unit (the explained unit for a Penjelasan). `load_graph` (M1.5) creates one `REFERENCES {mention_text, resolution: EXACT}` edge per target of a `REFERENCES`-kind mention. `SELF` and `UNRESOLVED` items create no edge. `DELEGATION` creates no edge until the delegated instrument (PP 33/2026) is ingested. `PARENT` is not produced by the v1 resolver. The committed list of unresolved, external, delegation and self mentions is `data/review/<source_id>/refs.md`.

### 3.8 Definitions, term uses and data categories (`defs` stage, M1.4)

Artifacts in `data/processed/<source_id>/`:

- `defs.jsonl`, one row per definition: `node_id` (`<source>/def/<slug>`, §2.1), `unit_id`, `term`, `term_norm`, `aliases` (from "yang selanjutnya disebut/disingkat"), and `text` (the whole definition item).
- `term_uses.jsonl`, one row per unit, definition and kind:
  - `kind`: `defined` (the term's own capitalization; becomes a `USES_TERM` edge) or `informal` (another capitalization; `confidence: low`, no edge);
  - `count` and char `spans`;
  - for defined links: `nested_spans` and `ambiguous_spans` hold the indices of the spans inside an informal match and of the spans opening a sentence. `nested_in_informal` and `ambiguous_case` are true when either list is non-empty.
  - The flags never drop a link; the owner's labels decide (06 §2.10).
- `terms.json`: the sorted terms and aliases. This is the protected-terms list for the index (M1.6).
- `data_categories.jsonl`: the candidate `:DataCategory` rows (§3.1) with `explanation` (the Penjelasan text, or null for "Cukup jelas").

Matching rules:

- Longest match first, and matches do not overlap.
- An enclitic "-nya" is part of the match.
- A defining unit never links its own term or aliases.
- Text inside reference mentions is skipped, so the "Pemerintah" in "Peraturan Pemerintah" is not a use of the defined term.
- An informal match may contain a defined one: "subjek Data Pribadi" is an informal use of Subjek Data Pribadi and a defined use of Data Pribadi.

The owner's review list is `data/review/<source_id>/definitions.md`. Its `Review:` lines are kept on regeneration and record:
- per definition: `ok`, `term_wrong` or `text_wrong`;
- per category: `confirmed`, `code_change` or `not_a_category`.

Only confirmed codes are used downstream.

### 3.9 Loading (`load_graph`, M1.5)

`python -m pdp_ingest.graph_load --source <id>` (`make load-graph SOURCE=<id>`) reads only these files:
- the stage artifacts in `data/processed/<id>/`: `source.json`, `structures.jsonl`, `units.jsonl`, `refs.jsonl`, `defs.jsonl`, `term_uses.jsonl`, `data_categories.jsonl`;
- the category verdicts in `data/review/<id>/definitions.md`.

Nothing is re-parsed.

**Write rules**
- The §3.3 constraints are created first, with `IF NOT EXISTS`.
- Every node is `MERGE`d on its key and its properties are replaced with `SET n = row`:
  - `node_id` for Structure, LegalUnit and Definition;
  - `source_id` for Source;
  - `source_id` + `code` for DataCategory.
- Edges are `MERGE`d on their endpoints; `REFERENCES` is also keyed on `start`.
- Writes go in batched write transactions (500 rows by default). A re-run gives identical nodes, edges and properties.

**Node rules**
- Every unit is version 1: `node_id = unit_id@1`, `valid_from = Source.effective_from`, no `valid_to` (open; Neo4j stores no nulls).
- `text_norm` is the text NFC-normalized, lowercased, with whitespace collapsed.
- `text_sha256` is the SHA-256 of the UTF-8 text (units and definitions).

**Edge rules**
- `PART_OF {order}`: body units point to their parent unit or structure; Bagian/Paragraf point to their parent structure. Penjelasan units have no `PART_OF`.
- `EXPLAINED_BY`: the explained unit points to its Penjelasan; `pj-umum` has no edge.
- `IN_SOURCE`: from every node to its Source.
- `REFERENCES`: one per internal target of a `REFERENCE` mention.
- `DEFINES`, `SUBCATEGORY_OF`.
- `USES_TERM`: defined uses only. A unit with only informal matches for a term has no edge; those matches stay in `term_uses.jsonl`.
- Delegations, `SELF` and external mentions create no edge.

**Category status**
- `confirmed` when the owner's verdict is `confirmed`, else `proposed`.

**Text-free structure (CI)**
- The law text is not committed ([VERIFY], redistribution undecided). `--export-structure PATH` writes every row without its text fields (`heading`; `text`, `text_norm`; `term`, `term_norm`, `aliases`; category `label`, `explanation`; `mention_text`), keeping ids, kinds, order, edges, edge properties, `text_sha256` and Source provenance (`pdp_ingest.graph_structure`, sorted-key JSON).
- `tests/fixtures/<id>/structure.json` is committed. `--from-structure PATH` loads it as a text-less graph: same nodes, edges and counts. CI runs the real-graph ID/structure tests on it; exact-text tests are `needs_corpus` (local only).
- A `snapshot` test re-runs the text stages and fails if the committed structure differs.

**Test isolation**
- Integration tests use the separate `neo4j-test` instance (compose profile `test`, `make up-test`, `127.0.0.1:7688`, tmpfs data), wiped at the start and end of each test session. They refuse the dev port 7687.

**Consistency check**
- The CLI and the integration test compare graph counts with the artifact counts per label and edge type, and fail naming every mismatch.

**Canonical query contracts (§3.4, `pdp_core/graph/queries.py`)**
- `expand_references`: returns paths of up to `max_hops` (1..5), shortest first, then in document order.
- `context_of`: returns
  - the unit's Pasal;
  - its siblings (same kind, same parent);
  - the Penjelasan units of the unit, its ancestors up to the Pasal, and its descendants (up to 3 levels), in document order, each with a `relation`: `own_explanation` (of the unit itself), `ancestor_explanation` (of a unit it is part of) or `descendant_explanation` (of a unit part of it; e.g. Pasal 20 ayat (2) has none of its own, its huruf do).
- `definitions_for`: ordered by unit, then definition id; `term` is null in a text-less graph.
- `version_at`: raises unless exactly one version is valid.
- `candidate_obligations`:
  - takes approved obligations of the actor whose units are valid at `as_of`;
  - keeps unconditional ones, and those triggered by a given confirmed category, its parent class, or a given concept;
  - returns separately the categories with no confirmed code or with an open-ended one, which give `UNKNOWN` (03 §5.3).

## 4. Search index (OpenSearch)

Every build creates a new index `legal_units_v<build>` (the next free build number) behind the alias `legal_units`. Documents (`_id` = `node_id`):
- every citable `LegalUnit` of kind `AYAT`, `HURUF`, `ANGKA`, or `PASAL` when it has no ayat;
- every substantive Penjelasan unit (text not starting "Cukup jelas") as its own document of kind `PENJELASAN`. `explains` is the unit it explains (absent for the general Penjelasan, `pj-umum`). The explained unit keeps the same text in `penjelasan_text`.

"Cukup jelas" units are not indexed. A Penjelasan document is citable as Penjelasan. A gloss ("Yang dimaksud dengan …") is never cited as the law's definition (M1.4).

For UU 27/2022 this gives 351 documents: PASAL 34, AYAT 122, HURUF 144, ANGKA 13, PENJELASAN 38.

| Field | Type | Notes |
|---|---|---|
| `node_id` | keyword | |
| `unit_id` | keyword | |
| `source_id` | keyword | |
| `kind` | keyword | |
| `label` | keyword | e.g. "Pasal 46 ayat (1)" |
| `explains` | keyword | Penjelasan documents: `unit_id` of the explained unit |
| `text` | text, `legal_plain` (standard + lowercase, no stemming); subfields `text.stem` (`legal_stem`), `text.shingle` (`legal_shingle`) | BM25 |
| `context_text` | text, `legal_plain` + `.stem` | structure headings (BAB, Bagian, Paragraf), then ancestor unit texts (lead-ins such as "… meliputi:"; for a Penjelasan, the explained unit and its ancestors), then the explained unit's label (Penjelasan only) and the unit label, joined by " / " |
| `penjelasan_text` | text, `legal_plain` + `.stem` | Penjelasan of the unit and its ancestors, without "Cukup jelas."; empty on Penjelasan documents; lower boost |
| `terms` | keyword[] | `term_norm` of the defined terms used (`USES_TERM`) |
| `concepts` | keyword[] | empty until concept tagging |
| `valid_from` / `valid_to` | date | range filter; no `valid_to` = open |
| `embedding` | knn_vector (dim from the model, HNSW, Lucene, cosine) | bge-m3 dense vector of the ancestor lead-ins + unit text |
| `embedding_model`, `embedding_revision` | keyword | per document |

**Analyzers (no stop words)**
- `legal_plain`: standard tokenizer, lowercase.
- `legal_stem`: lowercase, then `keyword_marker` `protected_terms` (ignore case), then the Indonesian stemmer.
- `legal_shingle`: lowercase 2- and 3-word shingles, no unigrams.

**Protected terms**
- The marker's keywords are the lowercase words of the source's defined terms and aliases (`terms.json`), plus the Actor vocabulary words (§3.1).
- So "pengendali", "pribadi" and "prosesor" stay whole in `text.stem` while other words stem ("kewajiban" becomes "wajib"). Without the marker the stemmer turns "pengendali" into "endali" and "pribadi" into "pribad".
- The body is committed at `tests/fixtures/uu27-2022/legal_units.index.json`. A unit test pins the code to it; a snapshot test pins its keywords to a fresh ingest and its model to `configs/models_aux.yaml`.

**One model per index**
- The mapping `_meta` holds `embedding_model`, `embedding_revision`, `embedding_dim` and `mapping_version`.
- `bulk` refuses documents of another model, revision or dim, and the stage refuses a model change mid-run.

**Builds, alias and retention (`store.publish`)**
- Every build creates a new index `legal_units_v<build>`. `create_index` refuses an existing name, and a rebuild never writes into the live index.
- After the documents are written, one `_aliases` call moves `legal_units` to the new index (atomic).
- `prune` then keeps the newest `SEARCH_INDEX_RETENTION` builds (default 2: live + previous, for rollback by swapping the alias back) and never deletes an alias target.

**Test isolation**
- Integration tests use per-test `itest-<hex>-` index and alias names on the dev OpenSearch.
- A guard on the test client refuses any create, delete, alias or bulk write outside `itest-*`; a test proves `legal_units` and `legal_units_v*` cannot be touched.
- Leftover `itest-*` indices are deleted at session start and end.

**Multi-vector cache**
- During embedding, the bge-m3 ColBERT outputs (one 1024-d vector per token, ADR-020) are written per document (Penjelasan documents included) to `data/processed/<id>/multivectors/<model>@<revision[:12]>.jsonl`, as base64 float16, keyed by `node_id` + revision.
- They are not indexed and not used; they exist for the M1.10 rerank experiment.

**Query bodies (`pdp_core.search.queries`; untuned defaults)**
- Every query is filtered by `valid_from ≤ as_of < valid_to`.
- BM25 field sets: `bm25_plain` (`text`), `bm25_stem` (`text.stem`), `multi_field` (`text`, `text.stem`, `text.shingle`, `context_text(.stem)`, `penjelasan_text(.stem)` ^0.5), all `most_fields`.
- Dense: k-NN on `embedding`.
- Hybrid: RRF (k = 60) of `multi_field` and dense.

## 5. Application schemas (Pydantic)

### 5.1 Query request/response

```python
class QueryRequest(BaseModel):
    question: str                      # 1..2000 chars
    as_of: date | None = None          # default: today (server tz Asia/Jakarta)
    language: Literal["id", "en", "auto"] = "auto"
    options: QueryOptions = QueryOptions()

class QueryOptions(BaseModel):
    max_subquestions: int = 4
    graph_max_hops: int = 2
    include_trace: bool = False
    pipeline_variant: Literal["full", "hybrid_no_graph", "dense_only", "bm25_only"] = "full"  # for ablations

class Citation(BaseModel):
    node_id: str
    label: str                         # display label
    quote: str                         # verbatim substring of node text
    span: tuple[int, int]              # char offsets into node.text
    valid_at_as_of: bool

class Claim(BaseModel):
    claim_id: str
    text: str
    citations: list[Citation]          # >= 1 after verification
    support: Literal["ENTAILED", "LLM_VERIFIED"]
    subquestion_id: str | None

Verdict = Literal[
    "OBLIGATION_APPLIES", "PROHIBITED", "PERMITTED", "NOT_APPLICABLE",
    "INFORMATIONAL", "INSUFFICIENT_EVIDENCE",
]

class QueryResponse(BaseModel):
    request_id: str
    trace_id: str
    verdict: Verdict
    summary: str                       # 1-3 sentences, derived only from surviving claims
    claims: list[Claim]
    missing_evidence: list[str]
    as_of: date
    language: Literal["id", "en"]
    dropped_claims: int                # count removed by verification
    disclaimer: str
    timings_ms: dict[str, float]
```

### 5.2 Model-facing generation schema (guided decoding)

```python
class GeneratedCitation(BaseModel):
    evidence_id: str                   # must be one of the provided evidence ids
    quote: str                         # must be verbatim from that evidence (<= 300 chars)

class GeneratedClaim(BaseModel):
    text: str
    citations: list[GeneratedCitation] # min 1
    subquestion_id: str

class GeneratedAnswer(BaseModel):
    verdict: Verdict
    claims: list[GeneratedClaim]
    missing_evidence: list[str]
```

### 5.3 CRAG evaluator output

```python
class CragJudgement(BaseModel):
    subquestion_id: str
    decision: Literal["CORRECT", "AMBIGUOUS", "INCORRECT"]
    method: Literal["THRESHOLD", "LLM"]
    max_rerank_score: float
    missing_aspect: str | None
```

### 5.4 Gap analysis

```python
class ProcessingActivity(BaseModel):
    name: str
    role: Literal["PENGENDALI", "PROSESOR", "JOINT_CONTROLLER"]
    purposes: list[str]
    data_categories: list[str]         # controlled vocabulary codes (DataCategory)
    data_subjects: list[str]           # e.g. "customers", "employees", "children"
    legal_basis: list[str] | None      # e.g. "CONSENT", "CONTRACT", "LEGAL_OBLIGATION", ...
    large_scale: bool | None
    automated_decision_making: bool | None
    recipients: list[str] = []
    processors: list[str] = []
    cross_border_transfer: bool | None
    transfer_destinations: list[str] = []
    retention: str | None
    security_measures: list[str] = []
    dpia_done: bool | None
    notes: str | None                  # free text, treated as untrusted data

class ObligationAssessment(BaseModel):
    obligation_id: str
    obligation_label: str
    status: Literal["SATISFIED", "GAP", "UNKNOWN", "NOT_APPLICABLE"]
    rationale: str
    facts_used: list[str]
    facts_missing: list[str]
    citations: list[Citation]

class GapReport(BaseModel):
    request_id: str
    activity_name: str
    as_of: date
    assessments: list[ObligationAssessment]
    summary_counts: dict[str, int]
    disclaimer: str
```

## 6. Postgres schema

```sql
-- PDPGraph
CREATE TABLE sources (
  source_id text PRIMARY KEY, title text NOT NULL, instrument_type text NOT NULL,
  number int, year int, enacted_on date, promulgated_on date, effective_from date,
  url text, sha256 text NOT NULL, fetched_at timestamptz NOT NULL, parser_version text NOT NULL
);

CREATE TABLE decision_traces (
  request_id uuid PRIMARY KEY,
  trace_id text NOT NULL,             -- OTel trace id
  kind text NOT NULL,                 -- 'query' | 'gap_analysis'
  created_at timestamptz NOT NULL DEFAULT now(),
  request jsonb NOT NULL,
  pipeline_variant text NOT NULL,
  config_hash text NOT NULL,          -- hash of prompts + thresholds + model ids
  states jsonb NOT NULL,              -- ordered list of state snapshots
  response jsonb,
  error jsonb,
  total_ms double precision
);
CREATE INDEX ix_decision_traces_created_at ON decision_traces (created_at DESC);

CREATE TABLE obligation_review_queue (
  obligation_node_id text PRIMARY KEY, candidate jsonb NOT NULL,
  status text NOT NULL DEFAULT 'PENDING', reviewer text, reviewed_at timestamptz, note text
);

-- Tierline
CREATE TABLE gw_requests (
  request_id uuid PRIMARY KEY,
  trace_id text,
  ts timestamptz NOT NULL DEFAULT now(),
  tenant text NOT NULL,
  data_class text NOT NULL,
  requested_model text,
  task_tag text,
  policy_allowed_tiers text[] NOT NULL,
  policy_reasons jsonb,
  cache_result text NOT NULL,          -- 'hit' | 'miss' | 'guard_reject' | 'ineligible'
  router_version text,
  router_scores jsonb,                 -- {tier: p}
  tau double precision,
  chosen_tier text,
  final_tier text,                     -- after fallbacks
  fallbacks jsonb,                     -- [{tier, error, ms}]
  stream boolean NOT NULL,
  prompt_tokens int, completion_tokens int, tokens_estimated boolean DEFAULT false,
  cost_usd numeric(12,6),
  ttft_ms double precision, total_ms double precision, gateway_overhead_ms double precision,
  status_code int NOT NULL,
  error_code text,
  features_ref text                    -- pointer to stored feature vector (for training)
);
CREATE INDEX ix_gw_requests_ts ON gw_requests (ts DESC);
CREATE INDEX ix_gw_requests_tenant_ts ON gw_requests (tenant, ts DESC);

-- Evals
CREATE TABLE eval_runs (
  run_id uuid PRIMARY KEY, started_at timestamptz NOT NULL, finished_at timestamptz,
  suite text NOT NULL, dataset_version text NOT NULL, config_hash text NOT NULL,
  git_sha text NOT NULL, hardware_profile text, summary jsonb
);
CREATE TABLE eval_results (
  run_id uuid REFERENCES eval_runs, item_id text NOT NULL, variant text NOT NULL,
  output jsonb NOT NULL, metrics jsonb NOT NULL, judge jsonb,
  PRIMARY KEY (run_id, item_id, variant)
);

-- 0002: manual override counts per source (M1.2 safeguard)
ALTER TABLE sources ADD COLUMN overrides_total int NOT NULL DEFAULT 0;
ALTER TABLE sources ADD COLUMN overrides_unconfirmed int NOT NULL DEFAULT 0;
```

Prompt and message content in `gw_requests` is **not stored** by default; only hashes and feature refs. For `pii`/`confidential`, features are computed and stored without raw text (SEC-05).

## 7. Valkey keys (Redis protocol)

| Key | Type | TTL |
|---|---|---|
| `budget:{tenant}:{yyyymm}:tokens` | integer counter | 40 days |
| `budget:{tenant}:{yyyymm}:cost_micro_usd` | integer counter | 40 days |
| `breaker:{tier}` | hash (`state`, `failures`, `opened_at`, `open_ms`) | none |
| `cache:{tenant}:{model_class}:{sys_hash}:{entry_id}` | hash (`response`, `entities`, `created_at`) | per config |
| `cache-idx:{tenant}:{model_class}` | vector index | — |
| `load:{tier}` | hash (scraped backend metrics) | 5 s |

## 8. Configuration files

- `configs/tierline.yaml` — tiers, prices, data-class matrix overrides (restrict-only), tenants, budgets, breaker thresholds, cache settings, router artifact path, τ defaults.
- `configs/pdpgraph.yaml` — retrieval k values, RRF k, hop budget, rerank top-m, CRAG thresholds, NLI thresholds, prompt versions, model task tags.
- `configs/pending_changes.yaml`: known legal changes not yet modeled in the corpus (FR-PDP-20). Each entry has `id`, `instrument`, `kind ∈ {sanction_adjustment, binding_reading}`, `effective_on`, `affected_unit_ids` (version-free, 04 §2.1), `source_url` (official), `summary`, and `confirmed_by` (`null` until the owner has read the primary text). Every entry is enforced regardless of `confirmed_by`. An entry is removed when the change is modeled (ADR-017 / ADR-019, M4.4). The loader and guard land in M1.14.
- Prompts live in `packages/pdp_core/prompts/*.md` with front-matter `version`; their content hash contributes to `config_hash`.

## 9. Eval dataset formats

See 06-eval-plan §2. All datasets are JSONL with a `schema_version` field and live under `evals/datasets/<name>/v<n>/`.
