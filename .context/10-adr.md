# 10 — Architecture Decision Records

Format: Context → Decision → Consequences → Alternatives rejected. Status: `Accepted`, `Superseded by ADR-xxx`, `Proposed`. Append new ADRs at the end; never delete — supersede.

---

## ADR-001 — Two layered systems in one monorepo
**Status:** Accepted · 2026-11-05
**Context:** PDPGraph needs policy-enforced, cost-aware model access; Tierline needs a realistic, demanding client to evaluate against.
**Decision:** Build both in one `uv` workspace. PDPGraph calls models only via Tierline (after Phase 2).
**Consequences:** One coherent story (application + infra); shared telemetry/config; router training data comes from real pipeline stages. Risk: larger scope — mitigated by phase gates.
**Rejected:** Two separate repos (weaker integration story); a single combined service (blurs the gateway's reusability).

## ADR-002 — Python for gateway (MVP), Go rewrite deferred
**Status:** Accepted · 2026-11-05
**Context:** Go/Rust signal infra depth and lower overhead; Python lets the router, features, and schemas share code with training.
**Decision:** Python 3.12 + FastAPI + uvloop + httpx for Tierline MVP. Measure gateway overhead (NFR-02). If p99 overhead misses the target, profile first; a Go hot-path rewrite is a stretch item with a before/after benchmark.
**Consequences:** Faster delivery; overhead must be proven by measurement rather than assumed.
**Rejected:** Go from day one (slower delivery, duplicated schemas); using an existing proxy such as LiteLLM as the core (hides the engineering this project is meant to demonstrate — may be used as a *baseline* for comparison).

## ADR-003 — Neo4j as the knowledge graph
**Status:** Accepted · 2026-11-05
**Context:** Need variable-length traversals (references, definitions), temporal filtering, and inspectable graph structure.
**Decision:** Neo4j 5 Community with Cypher queries kept in versioned files and tested.
**Consequences:** Extra service; great tooling for visual inspection; well-known to reviewers.
**Rejected:** Postgres recursive CTEs (workable, less expressive for paths); in-memory NetworkX (no persistence/query language); RDF triple store (heavier modeling overhead for this scope).

## ADR-004 — OpenSearch for hybrid retrieval
**Status:** Accepted · 2026-11-05
**Context:** BM25 with a proper Indonesian analyzer matters for legal references and terms; dense retrieval needed for paraphrases.
**Decision:** OpenSearch 2.x with `indonesian` analyzer + k-NN vectors in the same index; fusion (RRF) done in application code for transparency and ablations.
**Consequences:** One search service; fusion logic testable; JVM memory footprint.
**Rejected:** Qdrant + separate BM25 library (two systems, no Indonesian analyzer); pgvector + Postgres FTS (no built-in Indonesian stemming config) [VERIFY if this changes].

## ADR-005 — vLLM for local serving, llama.cpp for laptop tier
**Status:** Superseded by ADR-013 · 2026-11-05
**Context:** Need continuous batching, OpenAI-compatible API, guided JSON decoding, Prometheus metrics.
**Decision:** vLLM for T1/T2 on GPU servers; llama.cpp server as an optional T1 on consumer hardware (ROCm/CPU).
**Consequences:** Gateway must abstain from vendor-specific features beyond the OpenAI-compatible surface (adapter handles differences).
**Rejected:** TGI / SGLang (viable; vLLM chosen for familiarity and metrics) — may be compared later.

## ADR-006 — Semantic cache storage
**Status:** Proposed · decide in M3.7
**Options:** (a) Redis Stack vector search; (b) in-process HNSW (hnswlib) per tenant with Redis persistence.
**Decision criteria:** p99 lookup latency, operational simplicity, licensing of the Redis distribution used.

## ADR-007 — Router as per-tier classifiers over simple features
**Status:** Accepted · 2026-11-05
**Context:** Need an interpretable, cheap (< 2 ms) router that can be retrained from logged data.
**Decision:** Per-tier binary classifiers (logistic regression baseline, small MLP if it clearly beats it) predicting P(pass) from embedding + structural features; decision rule = cheapest tier with P ≥ τ.
**Consequences:** Needs labeled data (every prompt × every tier, judged); τ yields a Pareto curve.
**Rejected:** LLM-as-router (adds latency/cost); pure heuristics (kept only as baseline).

## ADR-008 — OpenTelemetry-first observability, Phoenix for dev
**Status:** Accepted · 2026-11-05
**Decision:** Instrument with OTel SDK only; export through a Collector to Phoenix (dev) and optionally Langfuse. No vendor SDK calls in application code.
**Consequences:** Vendor-neutral; can switch backends by collector config.

## ADR-009 — Custom eval harness, libraries as metric providers
**Status:** Accepted · 2026-11-05
**Context:** Need ablation variants, replay cassettes, legal-specific metrics (citation P/R on unit IDs, risk–coverage), and reports.
**Decision:** Custom harness; use Ragas/DeepEval metrics only where they fit and report which were used.
**Rejected:** Running a framework's default suite only (generic metrics don't capture unit-level citation correctness).

## ADR-010 — Custom state machine instead of an agent framework
**Status:** Accepted · 2026-11-05
**Context:** Pipeline is a bounded cyclic graph (one rewrite loop) with strict verification; must be replayable and fully traced.
**Decision:** Explicit state machine with typed context, transition table, per-state spans, persisted trace.
**Consequences:** More code than a framework, full control and easy testing; demonstrates orchestration fundamentals.
**Rejected:** LangGraph / LlamaIndex workflows (viable; less transparent for this project's goals).

## ADR-011 — Structured output via guided decoding + verification, not prompting alone
**Status:** Accepted · 2026-11-05
**Decision:** Every LLM call that feeds logic uses JSON-schema constrained decoding (llama.cpp JSON schema/grammar) or provider structured output (T2/T3, where supported; otherwise validate + 1 retry), followed by Pydantic validation; citations are verified deterministically regardless.
**Consequences:** Small models become usable for structured stages; schema errors become rare and measurable.

## ADR-012 — Local models priced by amortized machine cost
**Status:** Accepted · 2026-11-05
**Context:** Treating local inference as free makes cost comparisons misleading.
**Decision:** Config assigns local tiers a per-token price derived from documented assumptions (machine hourly cost ÷ measured tokens/hour at reference load on `cpu-local`). Assumptions printed in every cost report.

## ADR-013 — No owned GPU: CPU-local small model + hosted open-weight + frontier
**Status:** Accepted · 2026-11-05 · supersedes ADR-005
**Context:** The developer has no GPU (no laptop GPU, no other machine available for this project). The design must still demonstrate routing, policy enforcement, load awareness, and resilience — honestly.
**Decision:**
- T1 = small quantized instruct model (~1.5–4B, GGUF) on **llama.cpp, CPU**, `locality: local`. It is the only generation tier allowed for `confidential`/`pii`.
- T2 = hosted open-weight model via an OpenAI-compatible provider, `locality: external`.
- T3 = frontier API, `locality: external`.
- Embedding, rerank, and NLI run on CPU in `models-aux` (small corpus makes this viable).
- Gateway performance and chaos are measured against a **mock upstream that replays latency profiles recorded from the real tiers**, plus small-scale real-tier runs.
- A vLLM engine benchmark on a free cloud-notebook GPU is optional [STRETCH], public data only, reported as a separate hardware profile.
**Consequences:**
- The policy story becomes sharper: sensitive workloads pay a measurable quality/latency cost to stay local, and the eval shows exactly how much (`full_small_only` vs `full_open_weight` vs `full_frontier_only`).
- Real API prices make the cost–quality Pareto curve more realistic than amortized-GPU estimates.
- Interactive latency targets are relaxed (NFR-01); gap analysis is treated as a batch-style job.
- Running costs are API spend → caching and spend caps are mandatory (C-3, NFR-12).
- Load-aware dispatch focuses on T1 slot saturation and external rate limits instead of KV-cache metrics.
**Rejected:** Treating cloud notebooks as an always-on tier (sessions expire, external machine — would violate locality for sensitive data); sending `confidential` data to a "zero-retention" hosted provider (relies on a contract, not on enforceable locality — may be offered later as an explicit, opt-in data class with its own ADR).

## ADR-014 — Valkey 8 instead of Redis
**Status:** Accepted · 2026-11-05
**Context:** Redis 7.4+ moved to source-available licences; Redis 7.2 was the last BSD release. Only standard commands (counters, hashes, TTL, pub/sub) are needed.
**Decision:** Use Valkey 8 (BSD, Redis-protocol compatible) with the standard `redis` Python client. "Redis" in these documents refers to this service.
**Consequences:** Semantic cache vector search must not depend on Redis Stack modules → ADR-006 leans to option (b), in-process HNSW with Valkey persistence.

## ADR-015 — User text is `internal` by default, with deterministic PII escalation
**Status:** Accepted · 2026-11-05
**Context:** The first design tagged Q&A calls `public`, but the prompt contains free-text user input; a user pasting personal data would send it to external tiers.
**Decision:**
- Any call whose prompt contains user-supplied text is at least `internal`. Only offline stages over regulation text alone are `public`.
- Tierline runs a deterministic PII scanner that can only **raise** the data class to `pii` (→ T1 local only).
- External tiers for `internal` require a per-tenant opt-in; the demo tenant opts in, so public-regulation Q&A still benefits from T2/T3.
**Consequences:** Stricter by default; a false-positive PII hit makes a query slower (CPU T1), which is measured (escalation rate on the golden set). Scanner false negatives are a known limitation, documented in the README.
**Rejected:** Keeping `public` (unsafe); LLM-based PII detection in the hot path (slow, non-deterministic).

## ADR-017 — Constitutional Court rulings modify the reading, not the text
**Status:** Accepted · 2026-11-05 (ADR-016 is reserved for the 9router upstream, M0.7; within-tier fallback alternates move to ADR-018)
**Context:** Putusan MK 151/PUU-XXII/2024 (delivered 2025-07-30) held the word "dan" in UU 27/2022 Pasal 53 ayat (1) huruf b conditionally unconstitutional unless read as "dan/atau". The promulgated text is unchanged; only its binding reading changed. The schema had no way to represent this: `OTHER` loses the semantics and a new text version would misstate the statute.
**Decision:**
- `Source.instrument_type` gains `PUTUSAN_MK`; each ruling is its own source.
- New relationship `(:Source {instrument_type: PUTUSAN_MK})-[:MODIFIES_READING {effective_on, holding_summary, operative_text_quote, status}]->(:LegalUnit)`; `operative_text_quote` is verbatim and citable; `status ∈ {CONDITIONALLY_UNCONSTITUTIONAL, UNCONSTITUTIONAL, OTHER}`.
- `as_of ≥ effective_on`: expansion returns the ruling with the unit and the answer cites both; before that date the ruling is not returned.
- Ruling citations use node IDs under the ruling's `source_id`; the grammar extension is minimal and lands with tests in M4.4.
**Consequences:** Temporal answers stay faithful to both the statute text and the binding reading. Implementation (ingestion, expansion, `as_of` tests) is M4.4. Holding details are taken from the official MK PDF and confirmed by the owner before ingestion. A golden-set temporal item will cover it.
**Rejected:** `instrument_type: OTHER` (loses semantics); a new text version of Pasal 53(1)(b) via `SUPERSEDES` (the text did not change).
