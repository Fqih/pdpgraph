# 05 — API Specification

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-11-05 |

Conventions for all HTTP APIs:
- JSON, UTF-8. Timestamps ISO 8601 with offset. Dates `YYYY-MM-DD`.
- Auth: `Authorization: Bearer <api_key>`. Keys map to a tenant in config.
- Every response carries `x-request-id`; clients may send one (UUID) for idempotent tracing.
- W3C `traceparent` is accepted and propagated.
- Admin endpoints live under `/admin/...` (unversioned, admin key only) in both services.
- Errors (PDPGraph and models-aux) use one envelope; Tierline uses the OpenAI-compatible shape in §3.1:

```json
{"error": {"code": "string_snake_case", "message": "human readable", "request_id": "uuid", "details": {}}}
```

The OpenAPI document is generated from code (`/openapi.json`) and must match this spec; a CI test diffs the generated schema against a committed snapshot.

---

## 1. PDPGraph API (`pdp_api`, default port 8080)

### 1.1 `POST /v1/query`

Ask a question. Body: `QueryRequest` (04-data-model §5.1). Returns `QueryResponse`.

Query param `stream=true` switches to Server-Sent Events:

| Event | Data | When |
|---|---|---|
| `plan` | `{subquestions:[{id,text,intent}]}` | After Plan |
| `retrieval` | `{subquestion_id, evidence:[{node_id,label,score,source:"bm25|dense|graph",hops}]}` | After Rerank, per sub-question |
| `crag` | `CragJudgement` | After CragGate |
| `verifying` | `{generated_claims:int}` | After Generate (claims themselves are NOT streamed) |
| `result` | `QueryResponse` | Final |
| `error` | error envelope | On failure |

Example request:

```json
{"question": "Kapan Pengendali wajib memberitahukan kegagalan pelindungan data pribadi?", "as_of": "2026-11-05"}
```

Example response (abridged; content illustrative only):

```json
{
  "request_id": "6f1c…",
  "verdict": "OBLIGATION_APPLIES",
  "summary": "…",
  "claims": [{
    "claim_id": "c1",
    "text": "…",
    "citations": [{"node_id": "uu27-2022/p46/a1@1", "label": "Pasal 46 ayat (1) UU 27/2022", "quote": "…", "span": [0, 142], "valid_at_as_of": true}],
    "support": "ENTAILED"
  }],
  "missing_evidence": [],
  "dropped_claims": 1,
  "disclaimer": "Bukan nasihat hukum / Not legal advice."
}
```

Errors: `400 invalid_request`, `422 validation_error`, `503 model_unavailable` (no allowed tier healthy), `504 pipeline_timeout`.

### 1.2 `POST /v1/gap-analysis`

Body: `{ "activity": ProcessingActivity, "as_of": date | null }` (also accepts `Content-Type: application/yaml`). Returns `GapReport`. Supports `stream=true` with events `candidates`, `assessment` (one per obligation, **after** verification), `result`.

All model calls in this endpoint are sent to Tierline with `x-data-class: confidential`.

### 1.3 `GET /v1/articles/{node_id}`

Returns the legal unit: text, label, validity, parent, children, Penjelasan, outgoing references, incoming references, defined/used terms. `node_id` may be a `unit_id` plus query `as_of` to resolve the version.

### 1.4 `GET /v1/trace/{request_id}`

Returns the persisted decision trace (04-data-model §6) plus a graph projection for the UI:

```json
{"request_id": "…", "nodes": [{"id": "…", "type": "subquestion|evidence|claim|verdict|dropped", "label": "…", "data": {}}],
 "edges": [{"source": "…", "target": "…", "type": "retrieved|expanded_from|cites|supports|dropped_by"}]}
```

### 1.5 `POST /admin/ingest` (admin key only)

Triggers ingestion for a registered source: `{ "source_id": "uu27-2022", "stages": ["all"] | [...] }`. Returns job ID; progress at `GET /admin/ingest/{job_id}`. (The CLI `pdpgraph ingest` is the primary path; this endpoint is a convenience.)

### 1.6 `GET /admin/review-queue` / `POST /admin/review-queue/{obligation_node_id}`

List pending extracted obligations; approve/reject with note.

### 1.7 Health

`GET /healthz` (process alive), `GET /readyz` (Neo4j, OpenSearch, Postgres, Tierline, models-aux reachable).

---

## 2. PDPGraph MCP server (`pdp_mcp`)

Transports: stdio and streamable HTTP (port 8090). Tool inputs/outputs reuse the REST schemas.

| Tool | Input | Output | Notes |
|---|---|---|---|
| `pdp.query` | `{question, as_of?, language?}` | `QueryResponse` | |
| `pdp.gap_analysis` | `{activity, as_of?}` | `GapReport` | Marks data `confidential` |
| `pdp.get_article` | `{node_id}` or `{unit_id, as_of?}` | article object | |
| `pdp.explain` | `{request_id}` | trace graph | |

Resource template: `pdp://article/{node_id}` → article text (markdown).

Tool descriptions must state: outputs are not legal advice; citations are verifiable via `pdp.get_article`.

---

## 3. Tierline gateway (`tierline`, default port 4000)

### 3.1 `POST /v1/chat/completions`

OpenAI-compatible. Supported request fields: `model`, `messages`, `temperature`, `top_p`, `max_tokens` / `max_completion_tokens`, `stream`, `stream_options`, `stop`, `response_format` (`json_object`, `json_schema`), `seed`, `logprobs`, `top_logprobs`, `n` (=1 only in MVP). Tool calling pass-through is [STRETCH].

`model`:
- `"auto"` → routed.
- `"tier:T1"` … `"tier:T3"` → pinned tier (policy still applies).
- A concrete model name from `/v1/models` → pinned to that model's tier (policy still applies).

Request headers (Tierline extensions):

| Header | Values | Default |
|---|---|---|
| `x-data-class` | `public`, `internal`, `confidential`, `pii` | `internal` |
| `x-tierline-tenant` | tenant id (must match API key's tenant or be allowed by it) | key's tenant |
| `x-tierline-task` | free tag, e.g. `pdp.plan`, `pdp.generate`, `pdp.crag`, `pdp.extract` | none |
| `x-tierline-quality` | τ in [0,1] | tenant default |
| `x-tierline-priority` | `normal`, `high` | `normal` |
| `x-tierline-cache` | `default`, `bypass`, `force` | `default` |

Response headers:

| Header | Meaning |
|---|---|
| `x-tierline-request-id` | UUID |
| `x-tierline-tier` | tier that produced the response |
| `x-tierline-model` | backend model id |
| `x-tierline-cache` | `hit`, `miss`, `guard_reject`, `ineligible` |
| `x-tierline-fallback` | comma list of tiers tried before final, empty if none |
| `x-tierline-cost-usd` | decimal string |
| `x-tierline-router-version` | router artifact version or `static` |

Streaming: standard OpenAI SSE chunks; final chunk includes `usage` if `stream_options.include_usage` is true. A trailing SSE comment `: tierline {"tier":…,"cost_usd":…}` is emitted before `[DONE]` (comments are ignored by standard clients).

Errors use the **OpenAI error shape** so SDKs parse them natively, with Tierline fields added:

```json
{"error": {"message": "…", "type": "policy_error|budget_error|upstream_error|invalid_request_error|authentication_error", "param": null, "code": "policy_no_allowed_tier", "request_id": "uuid"}}
```

Error codes:

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `invalid_data_class` | Unknown `x-data-class` |
| 401 | `unauthorized` | Bad API key |
| 403 | `policy_model_forbidden` | Pinned model/tier not allowed for this data class/tenant |
| 429 | `budget_exhausted` | Budget mode `reject` |
| 503 | `policy_no_allowed_tier` | No healthy tier allowed by policy |
| 502 | `upstream_error` | All allowed tiers failed |
| 504 | `upstream_timeout` | All allowed tiers timed out |

### 3.2 `GET /v1/models`

Lists `auto`, `tier:*`, and backend models with `tier`, `allowed_data_classes`, `price_per_mtok_in/out`.

### 3.3 `GET /v1/route/explain/{request_id}`

```json
{"request_id": "…", "data_class": "public", "policy": {"allowed_tiers": ["T0","T1","T2","T3"], "reasons": []},
 "cache": {"eligible": true, "result": "miss", "best_similarity": 0.91},
 "router": {"version": "r-2026-12-01", "tau": 0.8, "scores": {"T1": 0.41, "T2": 0.86, "T3": 0.95}},
 "load": {"T1": {"slots_busy": 2, "slots_total": 2, "queued": 3}, "T2": {"in_flight": 4, "ttft_ewma_ms": 380, "rate_limited": false}},
 "breakers": {"T1": "closed", "T2": "closed", "T3": "closed"},
 "decision": {"chosen": "T2", "skipped": [{"tier": "T1", "reason": "score<tau"}]},
 "attempts": [{"tier": "T2", "status": "ok", "ttft_ms": 402.1, "total_ms": 2210.0}]}
```

Retention: explain records for 7 days [TUNE].

### 3.4 Admin & ops

- `GET /admin/budgets/{tenant}` → current month usage vs limits.
- `POST /admin/router/reload` → hot-reload router artifact (also on SIGHUP).
- `GET /admin/breakers` → breaker states.
- `GET /metrics` → Prometheus (metric names in 07-NFR §4).
- `GET /healthz`, `GET /readyz` (Redis + Postgres reachable; ≥ 1 tier healthy per data class).

---

## 4. models-aux service (internal, port 8070)

Not exposed publicly; no routing.

| Endpoint | Body | Returns |
|---|---|---|
| `POST /embed` | `{inputs: [str], kind: "query"|"passage", multi_vector?: bool}` | `{model, revision, dim, vectors, multi_vectors?}`; `multi_vectors` (one L2-normalized vector per token after CLS, padding dropped; bge-m3 ColBERT head converted to safetensors, ADR-020) only when `multi_vector: true` |
| `POST /rerank` | `{query, passages: [str]}` | `{model, scores}` |
| `POST /nli` | `{pairs: [{premise, hypothesis}]}` | `{model, results: [{entailment, neutral, contradiction}]}` |

Batching: server-side dynamic batching with max batch and max wait [TUNE].
