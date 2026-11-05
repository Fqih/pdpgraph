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
| `:Source` | `source_id`, `title`, `instrument_type`, `year`, `effective_from` | |
| `:Structure` | `node_id`, `unit_id`, `kind ∈ {BAB, BAGIAN, PARAGRAF}`, `number`, `heading` | Grouping only, not citable |
| `:LegalUnit` | `node_id`, `unit_id`, `kind ∈ {PASAL, AYAT, HURUF, ANGKA, PENJELASAN}`, `text`, `text_norm`, `label`, `valid_from`, `valid_to` (null = open), `version`, `order` | **Citable** units |
| `:Definition` | `node_id`, `term`, `term_norm`, `aliases[]`, `text` | From definitional articles |
| `:Obligation` | `node_id`, `actor_role`, `action`, `object`, `condition`, `deadline`, `modality ∈ {WAJIB, DILARANG, DAPAT}`, `review_status ∈ {PENDING, APPROVED, REJECTED}` | Extracted; only `APPROVED` used online |
| `:Actor` | `name ∈ {PENGENDALI, PROSESOR, SUBJEK_DATA, LEMBAGA, DPO, PIHAK_KETIGA, ...}` | Controlled vocabulary |
| `:DataCategory` | `code ∈ {UMUM, SPESIFIK, KESEHATAN, BIOMETRIK, GENETIKA, CATATAN_KEJAHATAN, ANAK, KEUANGAN_PRIBADI, ...}` | [VERIFY list against Pasal 4] |
| `:Sanction` | `node_id`, `type ∈ {ADMINISTRATIVE, CRIMINAL}`, `description` | |
| `:Concept` | `code` (e.g., `LEGAL_BASIS`, `CONSENT`, `BREACH_NOTIFICATION`, `CROSS_BORDER_TRANSFER`, `DPO`, `DPIA`, `RETENTION`) | Topic tags for routing gap analysis |

### 3.2 Relationships

| Relationship | From → To | Properties |
|---|---|---|
| `PART_OF` | `LegalUnit`/`Structure` → parent | `order` |
| `IN_SOURCE` | any → `Source` | |
| `REFERENCES` | `LegalUnit` → `LegalUnit` | `mention_text`, `resolution ∈ {EXACT, PARENT, EXTERNAL_UNRESOLVED}` |
| `EXPLAINED_BY` | `LegalUnit` → `LegalUnit{kind:PENJELASAN}` | |
| `DEFINES` | `LegalUnit` → `Definition` | |
| `USES_TERM` | `LegalUnit` → `Definition` | `count` |
| `SUPERSEDES` | newer `LegalUnit` → older `LegalUnit` | `effective_on`, `by_source_id` |
| `MODIFIES_READING` | `Source{instrument_type: PUTUSAN_MK}` → `LegalUnit` | `effective_on`, `holding_summary`, `operative_text_quote` (verbatim, citable quote from the ruling), `status ∈ {CONDITIONALLY_UNCONSTITUTIONAL, UNCONSTITUTIONAL, OTHER}` (§3.5, ADR-017) |
| `AMENDS` | `Source` (amending instrument) → `LegalUnit` | `effective_on`, `lampiran_ref`, `operative_text_quote` (verbatim, citable) (§3.6, ADR-019) |
| `IMPOSES` | `LegalUnit` → `Obligation` | |
| `APPLIES_TO_ACTOR` | `Obligation` → `Actor` | |
| `TRIGGERED_BY` | `Obligation` → `DataCategory` / `Concept` | `condition_text` |
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
- `context_of(node_id)` — parent Pasal + sibling ayat + Penjelasan.
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

## 4. Search index (OpenSearch)

Index `legal_units_v{n}` (aliased as `legal_units`), one document per citable `LegalUnit` of kind `PASAL` (only when it has no ayat), `AYAT`, `HURUF`, `ANGKA`.

| Field | Type | Notes |
|---|---|---|
| `node_id` | keyword | |
| `unit_id` | keyword | |
| `source_id` | keyword | |
| `kind` | keyword | |
| `label` | keyword | |
| `text` | text, analyzer `indonesian` (+ `standard` subfield) | BM25 |
| `context_text` | text | parent Pasal heading + Bab heading for BM25 boost |
| `penjelasan_text` | text | lower boost |
| `terms` | keyword[] | defined terms used |
| `concepts` | keyword[] | |
| `valid_from` / `valid_to` | date | range filter |
| `embedding` | knn_vector (dim per model, HNSW, cosine) | dense |
| `embedding_model` | keyword | guard against mixing models |

Reindexing creates a new versioned index and swaps the alias atomically.

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
