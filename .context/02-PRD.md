# 02 — Product Requirements Document (PRD)

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-11-05 |
| Traces to | 01-BRD.md |

---

## 1. Product overview

Two products, one repository:

| Product | Form | Primary user |
|---|---|---|
| **PDPGraph** | Python service (REST + SSE), MCP server, minimal web UI | Compliance analyst, agent clients |
| **Tierline** | OpenAI-compatible inference gateway | Platform/ML engineers; PDPGraph itself |

PDPGraph never calls a model directly. **All model calls go through Tierline**, tagged with a data class.

## 2. Personas

**P1 — Dewi, Data Protection Officer at a mid-size fintech.** Needs to know which obligations apply to a new marketing campaign that uses customer phone numbers. Has legal training but limited time. Distrusts AI answers she cannot verify.

**P2 — Raka, privacy consultant.** Runs gap analyses for several clients. Wants a repeatable, explainable process he can show clients.

**P3 — Sari, platform engineer.** Runs internal LLM workloads. Wants cost control, policy enforcement, and observability without rewriting clients.

**P4 — An agent client (e.g., Claude Code or a custom agent).** Calls PDPGraph via MCP during a larger task (e.g., reviewing a database schema change for PDP impact).

## 3. User stories & acceptance criteria

### PDPGraph

**US-1 (Dewi): Ask a cited question.**
> As a DPO, I ask "Apakah kami wajib menunjuk DPO jika memproses data pribadi skala besar?" and get an answer where every claim links to the exact ayat.

Acceptance:
- Response contains a `verdict`, ≥ 1 `claim`, and each claim has ≥ 1 citation with `node_id` and character `span`.
- Clicking a citation shows the verbatim source text with the span highlighted.
- Response includes `disclaimer`.
- Indonesian questions get Indonesian answers; English questions get English answers; citations always show original Indonesian text.

**US-2 (Dewi): Abstention.**
> When I ask something the law does not address, the system says so instead of inventing an answer.

Acceptance:
- Verdict `INSUFFICIENT_EVIDENCE` with a non-empty `missing_evidence` list.
- No claim without a citation is ever returned.

**US-3 (Raka): Gap analysis.**
> I upload a processing activity (purpose, data categories, legal basis, recipients, retention, cross-border transfer) and receive a checklist of applicable obligations.

Acceptance:
- Each obligation row: `obligation_id`, `status ∈ {SATISFIED, GAP, UNKNOWN, NOT_APPLICABLE}`, rationale, citations.
- `UNKNOWN` is used when input lacks the fact needed; the row says which fact.
- Exportable as JSON and Markdown.

**US-4 (Raka): Explain reasoning.**
> I can show a client how the system reached a conclusion.

Acceptance:
- `GET /v1/trace/{id}` returns the decision-trace graph (sub-questions, retrieved nodes with scores, CRAG verdicts, claims, verification results).
- UI renders it as an interactive graph.

**US-5 (Dewi): As-of date.**
> I ask "what applied on 2024-06-01?" and get answers based only on provisions in force then.

Acceptance:
- Request accepts `as_of` date; retrieval excludes nodes whose validity interval excludes that date.
- Response echoes the `as_of` used.

**US-6 (Agent): MCP access.**
> An agent calls `pdp.query`, `pdp.gap_analysis`, `pdp.get_article`, `pdp.explain` via MCP.

Acceptance:
- MCP server passes a protocol conformance smoke test with a reference MCP client.
- Tool outputs use the same schemas as REST.

### Tierline

**US-7 (Sari): Drop-in gateway.**
> I point my OpenAI SDK `base_url` at Tierline and existing code works.

Acceptance:
- `POST /v1/chat/completions` (streaming and non-streaming) and `GET /v1/models` compatible with the OpenAI Python SDK.
- `model: "auto"` triggers routing; a concrete model name bypasses routing (still subject to policy).

**US-8 (Sari): Data policy.**
> Requests tagged `confidential` or `pii` never leave local infrastructure.

Acceptance:
- Policy test suite: every combination of data class × requested model × tier health state; zero external calls for `confidential`/`pii`.
- If no allowed tier is healthy, request fails with `503 policy_no_allowed_tier` — never falls back to an external API (hosted open-weight T2 counts as external).

**US-9 (Sari): Cost control.**
> I set a monthly budget per tenant; requests over budget are rejected or downgraded per config.

Acceptance:
- Budget states visible at `GET /admin/budgets/{tenant}`.
- Configurable behavior on exhaustion: `reject` (429) or `downgrade` (local tiers only).

**US-10 (Sari): Explain routing.**
> I can see why a request went to a given tier.

Acceptance:
- `GET /v1/route/explain/{request_id}` returns policy result, candidate tiers, router scores, load penalties, final choice, and fallbacks taken.

**US-11 (Sari): Resilience.**
> When a tier fails, requests keep succeeding.

Acceptance:
- Circuit breaker opens after configurable consecutive failures/timeouts; half-open probing.
- Fallback to the next allowed tier; recorded in trace and response header `x-tierline-fallback`.

## 4. Functional requirements

### 4.1 PDPGraph (FR-PDP)

| ID | Requirement | Traces |
|---|---|---|
| FR-PDP-01 | Ingest a regulation from a source file (PDF/HTML/TXT) into a normalized hierarchical document (Bab → Bagian → Paragraf → Pasal → Ayat → huruf/angka), including Penjelasan linked to each Pasal/ayat. | BR-01 |
| FR-PDP-02 | Assign stable, human-readable node IDs (format in 04-data-model). | BR-02 |
| FR-PDP-03 | Extract cross-references (internal and external) and create `REFERENCES` edges; unresolved references are logged, not dropped. | BR-04 |
| FR-PDP-04 | Extract definitions from Pasal 1 (and any definitional article) and create `DEFINES` edges to every paragraph using the term. | BR-04 |
| FR-PDP-05 | Extract obligations (actor, action, condition, object) from paragraphs into `Obligation` nodes, LLM-assisted with schema validation and human-review queue. | BR-06 |
| FR-PDP-06 | Store validity intervals (`valid_from`, `valid_to`) on every legal node and `SUPERSEDES` edges between versions. | BR-05 |
| FR-PDP-07 | Index paragraph-level units in BM25 (Indonesian analyzer) and dense vectors; store parent IDs for context assembly. | BR-01 |
| FR-PDP-08 | Retrieve with hybrid search (BM25 + dense), reciprocal-rank fusion, cross-encoder rerank, then graph expansion (references and definitions up to 2 hops), filtered by `as_of`. | BR-01, BR-04, BR-05 |
| FR-PDP-09 | Decompose questions into sub-questions (Plan-and-Solve) with an explicit plan object stored in the trace. | BR-07 |
| FR-PDP-10 | Gate generation with a CRAG evaluator: `CORRECT` → generate; `AMBIGUOUS` → rewrite + expand once, re-evaluate; `INCORRECT` → abstain. | BR-03 |
| FR-PDP-11 | Generate structured output only (JSON schema enforced via guided decoding). | BR-02 |
| FR-PDP-12 | Verify citations deterministically: cited `node_id` exists, is in the retrieved evidence set, valid at `as_of`, and the span's text is a substring of the node text. Failing claims are dropped. | BR-02 |
| FR-PDP-13 | Verify entailment: each surviving claim is checked against its cited spans by an NLI model (and optionally an LLM verifier); unsupported claims are dropped; verdict is recomputed from surviving claims. | BR-02, BR-03 |
| FR-PDP-14 | Persist a decision trace for every request (plan, retrievals with scores, CRAG decisions, raw generation, verification results, final output). | BR-07 |
| FR-PDP-15 | Gap analysis: map a structured processing activity to applicable obligations via graph queries + LLM applicability judgment, returning per-obligation status with citations. | BR-06 |
| FR-PDP-16 | Expose REST API + SSE streaming (05-api-spec). | BR-01 |
| FR-PDP-17 | Expose an MCP server with tools `pdp.query`, `pdp.gap_analysis`, `pdp.get_article`, `pdp.explain`. | BR-15 |
| FR-PDP-18 | Tag every model call to Tierline with `x-data-class`: `internal` for any call whose prompt contains user question text (all online Q&A stages); `public` only for offline stages over regulation text alone (obligation extraction, synthetic dataset generation); `confidential` for any call containing user-supplied company data (gap analysis). The `LLMClient` has no default data class (ADR-015). | BR-08 |
| FR-PDP-19 | Minimal web UI: question box, answer with clickable citations, source viewer, decision-trace graph, gap-analysis table. | BR-07 |
| FR-PDP-20 | Currency guard: `configs/pending_changes.yaml` lists known changes not yet modeled in the corpus (affected `unit_ids`, `effective_on`, instrument, `kind ∈ {sanction_adjustment, binding_reading}`, official source URL, `confirmed_by`). Every entry is enforced, whether `confirmed_by` is set or not. A claim that cites an affected unit when `as_of ≥ effective_on` is dropped with reason `unmodeled_change`. If that leaves no claims, the system abstains with a `missing_evidence` entry naming the change. It never answers with a superseded figure or reading. | BR-02, BR-05 |

### 4.2 Tierline (FR-GW)

| ID | Requirement | Traces |
|---|---|---|
| FR-GW-01 | OpenAI-compatible `POST /v1/chat/completions` (stream and non-stream), `GET /v1/models`. | BR-12 |
| FR-GW-02 | Tier registry from config: each tier has provider type (llamacpp, vllm, openai_compatible, frontier), `locality ∈ {local, external}`, endpoint, model, price per 1M input/output tokens, allowed data classes, rate limits, timeouts. Default tiers: T1 llamacpp/local, T2 openai_compatible/external (hosted open-weight), T3 frontier/external. | BR-09 |
| FR-GW-03 | Policy layer evaluates before routing: data class → allowed tiers; tenant allowlist; budget state. Policy is deny-by-default. | BR-08, BR-10 |
| FR-GW-04 | Data class from `x-data-class` header; missing header defaults to `internal` (never `public`). | BR-08 |
| FR-GW-05 | Semantic cache (T0): only for deterministic requests (temperature 0 or explicit `cache: true`), keyed per tenant + model class; similarity threshold plus entity/number guard; TTL; `pii` requests are never cached. | BR-09 |
| FR-GW-06 | Learned router: predicts P(tier output passes quality bar) per tier from prompt features; picks the cheapest allowed tier with P ≥ τ (τ configurable per tenant/request). | BR-09 |
| FR-GW-07 | Load-aware dispatch: local tier — scrape backend metrics (llama.cpp `/metrics` and `/slots`, or vLLM metrics when used) [VERIFY endpoints]; external tiers — track in-flight requests, observed TTFT EWMA, and provider rate-limit headers/429s. Apply a latency penalty; skip saturated or rate-limited tiers. | BR-09, BR-11 |
| FR-GW-08 | Confidence-gated cascade [STRETCH]: run lower tier, estimate confidence (mean logprob / self-consistency), escalate below threshold. | BR-09 |
| FR-GW-09 | Circuit breaker per tier (closed/open/half-open) with configurable thresholds. | BR-11 |
| FR-GW-10 | Fallback chain restricted to policy-allowed tiers; retries with jittered backoff for non-streaming requests only. | BR-11 |
| FR-GW-11 | Streaming SSE pass-through with token accounting; mid-stream failover [STRETCH]. | BR-11, BR-12 |
| FR-GW-12 | Budgets: per-tenant token and cost counters (Redis), monthly windows, `reject` or `downgrade` on exhaustion. | BR-10 |
| FR-GW-13 | Request log: one row per request with routing decision, tier, tokens, cost, latency breakdown, cache result, fallbacks (training data for the router). | BR-13 |
| FR-GW-14 | `GET /v1/route/explain/{request_id}`, `GET /metrics` (Prometheus), `GET /healthz`, `GET /readyz`. | BR-13 |
| FR-GW-15 | Response headers: `x-tierline-request-id`, `x-tierline-tier`, `x-tierline-cache`, `x-tierline-fallback`, `x-tierline-cost-usd`. | BR-13 |
| FR-GW-17 | Deterministic PII scanner on request content that can only escalate the effective data class to `pii` (patterns per 03 §6.2); escalation visible in explain/metrics; matched text never logged. | BR-08 |
| FR-GW-16 | Router training pipeline: export logs/eval outputs → features → train → evaluate → versioned artifact; gateway hot-reloads router artifact. | BR-09, BR-14 |

## 5. UX requirements (PDPGraph UI)

Minimal, functional, professional. Not a design showcase.

- Single-page app (React + Vite + TypeScript).
- Left: question input, `as_of` date picker, language auto-detect.
- Center: verdict badge, claims list; each citation is a chip (`Pasal 20 ayat (2)`) that opens the source panel.
- Right: source panel with verbatim text, highlighted span, Penjelasan toggle, and links to referenced/defining nodes.
- Tab "Reasoning": decision-trace graph (sub-questions → evidence → claims → verdict), node colors by status (verified / dropped / abstained).
- Tab "Gap analysis": upload YAML/JSON or fill a form; results table with status filters; export.
- Persistent footer: "Not legal advice" disclaimer.
- Streaming: show plan and retrieval progress as they arrive; show final claims only after verification completes (never stream unverified claims to the user).

## 6. Non-goals

- Chat history / multi-turn memory (each query is independent in MVP).
- Authentication beyond static API keys.
- Admin UI for Tierline (config files + Grafana suffice).
- Auto-updating the legal corpus from the web.

## 7. Release plan

| Release | Contents | Gate |
|---|---|---|
| v0.1 "Grounded" | PDPGraph Q&A over UU PDP with verification + abstention; eval report | EV gates for SC-1..SC-4 measured (not necessarily met) and published |
| v0.2 "Routed" | Tierline MVP; PDPGraph calls routed through it; policy suite passes | SC-6 = 0 violations (hard) |
| v0.3 "Measured" | Router trained; Pareto curve; load + chaos tests; dashboards | Reports published |
| v1.0 "Integrated" | Gap analysis, MCP server, UI, as-of queries, polished README | All BRD success criteria reported with honest results |
