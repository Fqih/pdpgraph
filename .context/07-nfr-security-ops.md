# 07 — Non-Functional Requirements, Security & Operations

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-11-05 |

---

## 1. Non-functional requirements

All values are **[TARGET]** for the reference hardware profile `cpu-local` (CPU-only, 16 GB RAM, external APIs for T2/T3) unless stated; measured results go to reports, not here.

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Latency | PDPGraph `/v1/query` (`public`, routed) p50 ≤ 10 s, p95 ≤ 25 s end-to-end (full pipeline, warm). First SSE event (`plan`) ≤ 3 s p95. Gap analysis (`confidential`, T1 CPU) is a batch-style job: report per-obligation latency; no interactive target. |
| NFR-02 | Latency | Tierline gateway overhead p99 ≤ 15 ms at 128 concurrent streams (mock upstream). |
| NFR-03 | Throughput | Gateway sustains ≥ 500 req/s against mock upstream on a 4-vCPU container without errors. |
| NFR-04 | Availability | With one tier down, ≥ 99% of requests eligible for another tier succeed. |
| NFR-05 | Correctness | Policy violations = 0 (hard). |
| NFR-06 | Determinism | Same request + same config hash + temperature 0 → same verification outcome (replay tests). |
| NFR-07 | Reproducibility | Every report reproducible from repo + dataset version + config + model IDs. |
| NFR-08 | Portability | Full stack runs on one CPU-only machine via Compose; no GPU required anywhere in the default path. |
| NFR-09 | Observability | 100% of requests traced (sampling configurable; default 100% in dev, 20% in load tests with tail-sampling of errors/slow). |
| NFR-10 | Maintainability | Type-checked (mypy strict on `pdp_core`, `tierline`, `common`), ≥ 80% line coverage on deterministic modules (ids, segment, refs, policy, breaker, cache guard, verification). |
| NFR-11 | Resource | Ingestion of UU 27/2022 completes in ≤ 10 min (excluding obligation LLM extraction). |
| NFR-12 | Cost | Eval runs log total API spend; a single full eval run costs ≤ a configured cap (abort when exceeded). |
| NFR-13 | Localization | Indonesian and English questions supported; source text always shown in original Indonesian. |

## 2. Threat model

Assets: company processing-activity data (confidential/PII), API keys, frontier-API budget, integrity of answers (users may rely on citations).

| ID | Threat | Vector | Control |
|---|---|---|---|
| T-1 | Sensitive data exfiltration to external API | Caller omits/mislabels data class; router/fallback bug | SEC-01, SEC-02, SEC-03, policy suite (06 §6.4) |
| T-2 | Prompt injection changes behavior | Text in question, `ProcessingActivity.notes`, ingested documents | SEC-06, SEC-07, SEC-08 |
| T-3 | Fabricated or manipulated citations | Model invents node IDs or quotes | FR-PDP-12 deterministic verification |
| T-4 | Cache poisoning / cross-tenant leakage | Shared cache keys | SEC-04 |
| T-5 | Budget exhaustion / DoS | Flood of requests, huge prompts | SEC-09, SEC-10 |
| T-6 | Secret leakage | Keys in repo, logs, traces | SEC-11, SEC-12 |
| T-7 | Supply chain | Malicious model weights / packages | SEC-13 |
| T-8 | Corpus tampering | Altered source file | SEC-14 |

## 3. Security controls

| ID | Control |
|---|---|
| SEC-01 | Data-class policy is deny-by-default and enforced inside Tierline (03-architecture §6.2). Missing header → `internal`; PDPGraph always sets the header explicitly. |
| SEC-02 | Every adapter with `locality: external` (T2, T3) has a second, independent guard: it refuses (raises) any request whose context data class is `confidential`/`pii`, even if the policy layer had a bug (defense in depth). |
| SEC-03 | Fallback chains are computed only from `allowed_tiers`; a test asserts the chain is a subset of the policy decision. |
| SEC-04 | Cache keys include tenant; `pii` never cached; cache entries store data class and are only served to requests with an equal-or-stricter class. |
| SEC-05 | Prompt/response content is not persisted in `gw_requests`; OTel span attributes never include message content for `confidential`/`pii` (content capture enabled only for `public` in dev, behind a flag). |
| SEC-06 | All untrusted text (question, notes, retrieved passages) is placed in clearly delimited data blocks in prompts; system prompts instruct models to treat them as data. This is a mitigation, not a guarantee — hence SEC-07/08. |
| SEC-07 | Output structure enforced by guided JSON decoding + Pydantic validation; citations restricted to provided evidence IDs (verified deterministically). |
| SEC-08 | Models have no tools with side effects in the online pipeline; injection can at worst corrupt an answer, which verification and the adversarial/injection suites measure. |
| SEC-09 | Request size limits: question ≤ 2,000 chars; activity JSON ≤ 64 KB; gateway `max_tokens` clamp per tenant; per-key rate limit (token bucket in Redis). |
| SEC-10 | Budgets with hard caps; eval harness has its own spend cap. |
| SEC-11 | Secrets only via environment variables / `.env` (git-ignored); `.env.example` committed; `gitleaks` in pre-commit and CI. |
| SEC-12 | Structured logging with a redaction filter (API keys, `Authorization`, emails, phone numbers, NIK-like 16-digit numbers). |
| SEC-13 | Pin model revisions (commit hashes) and package lockfile; prefer safetensors; `pip-audit`/`uv` audit in CI. |
| SEC-14 | Source files verified by SHA-256 against the registry before ingestion. |
| SEC-15 | Containers run as non-root; only `pdp_api`, `ui`, and `tierline` ports are published on all interfaces. Store ports (Neo4j, OpenSearch, Postgres, Valkey) are published **only on `127.0.0.1`** for host-side dev and tests; everything else is on a private Compose network. OpenSearch security plugin may be disabled in dev only. |
| SEC-16 | PII scanner (FR-GW-17) escalates data class on detection; covered by a test set of synthetic Indonesian PII strings and near-misses; scanner output is never logged with the matched text. |

## 4. Observability specification

### 4.1 Tracing (OpenTelemetry)

- SDK in all Python services; `common/telemetry.py` provides `setup_tracing(service_name)` and decorators.
- No custom span decorator: code uses OTel's `tracer.start_as_current_span(name)` directly as decorator or context manager (sync and async); a per-state span helper, if needed, lands in M1.8.
- Propagation: W3C `traceparent` from UI → pdp_api → tierline → backends (forwarded as a header to backends; backend-side spans are out of scope).
- Exporter: OTLP → OTel Collector → Phoenix (dev); Langfuse optional via collector exporter.
- Follow OpenTelemetry GenAI semantic conventions for model-call spans where available [VERIFY current attribute names].

Span names and key attributes:

| Span | Attributes |
|---|---|
| `pdp.query` | `pdp.request_id`, `pdp.as_of`, `pdp.language`, `pdp.variant`, `pdp.verdict`, `pdp.claims.generated`, `pdp.claims.surviving` |
| `pdp.state.<name>` (normalize, plan, retrieve, expand, rerank, crag, rewrite, generate, verify_citations, verify_entailment, aggregate) | state-specific: `retrieve.k_bm25`, `retrieve.k_dense`, `expand.nodes_added`, `expand.max_hops`, `crag.decision`, `verify.dropped`, … |
| `pdp.graph.query` | `db.system=neo4j`, `pdp.query_name`, row count |
| `pdp.search` | `db.system=opensearch`, index, hits |
| `aux.embed` / `aux.rerank` / `aux.nli` | batch size, model |
| `tierline.request` | `tierline.tenant`, `tierline.data_class`, `tierline.task`, `tierline.cache`, `tierline.chosen_tier`, `tierline.final_tier`, `tierline.fallback_count`, `tierline.cost_usd`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |
| `tierline.policy` / `tierline.cache.lookup` / `tierline.route` / `tierline.upstream` | decision details, similarity, scores, tier, `ttft_ms`, status |

### 4.2 Metrics (Prometheus)

| Metric | Type | Labels |
|---|---|---|
| `tierline_requests_total` | counter | `tenant`, `data_class`, `final_tier`, `status` |
| `tierline_request_duration_seconds` | histogram | `final_tier`, `stream` |
| `tierline_ttft_seconds` | histogram | `final_tier` |
| `tierline_gateway_overhead_seconds` | histogram | — |
| `tierline_tokens_total` | counter | `tenant`, `tier`, `direction` (in/out) |
| `tierline_cost_usd_total` | counter | `tenant`, `tier` |
| `tierline_cache_events_total` | counter | `result` |
| `tierline_fallbacks_total` | counter | `from_tier`, `to_tier`, `reason` |
| `tierline_breaker_state` | gauge (0 closed, 1 half, 2 open) | `tier` |
| `tierline_policy_denials_total` | counter | `code` |
| `tierline_router_score` | histogram | `tier` |
| `pdp_queries_total` | counter | `verdict`, `variant` |
| `pdp_stage_duration_seconds` | histogram | `stage` |
| `pdp_claims_dropped_total` | counter | `reason` (citation, entailment, contradiction) |
| `pdp_abstentions_total` | counter | `reason` |
| llama.cpp native metrics | — | scraped as-is |
| `tierline_tier_rate_limited` | gauge | `tier` |
| `tierline_pii_escalations_total` | counter | `tenant` |

### 4.3 Dashboards (`deploy/grafana/`, provisioned)

1. **Gateway overview**: RPS by tier, error rate, p50/p95/p99 latency, TTFT, overhead, breaker states, fallbacks.
2. **Cost**: cost/hour by tenant and tier, tokens by tier, cache savings estimate, budget burn-down.
3. **PDPGraph quality ops**: verdict distribution, abstention rate, dropped-claim rate by reason, stage latency breakdown.
4. **Backends**: T1 slots busy/queued, tokens/s, CPU utilization; T2/T3 in-flight, TTFT, 429 rate.

### 4.4 Logging

JSON logs (structlog), fields: `ts`, `level`, `service`, `request_id`, `trace_id`, `event`, plus redacted context. No message content for sensitive classes.

## 5. Environments

| Env | Purpose | Notes |
|---|---|---|
| `local` | Development and reference runs | CPU-only; `core` + `local-llm` (+ `obs`, `mock`) profiles; T2/T3 via API keys in `.env` |
| `ci` | GitHub Actions | No GPU; replay cassettes; Neo4j/OpenSearch/Postgres/Redis as service containers |

## 6. Hardware profiles (record in every report)

| Profile | Expected config |
|---|---|
| `cpu-local` | Reference. Record CPU model, cores/threads, RAM, OS. T1 llama.cpp (record model + quant), models-aux on CPU, T2/T3 external (record provider + model ID + price date) |
| `ci` | GitHub Actions runners; replay only |
| `cloud-notebook` | [STRETCH] free notebook GPU, time-boxed, public data only; vLLM engine benchmark; reported as a separate profile, never mixed with `cpu-local` numbers |

## 7. Operations runbook (summary)

- `make up` / `make up-llm` / `make up-obs` / `make up-mock` — compose profiles.
- `make up-test` — throwaway Neo4j for integration tests (`127.0.0.1:7688`, tmpfs); `make test-int` needs `make up` + `make up-test`.
- `make ingest SOURCE=uu27-2022` — full ingestion with snapshot checks.
- `make eval-smoke` (replay), `make eval-full PROFILE=cpu-local BUDGET_USD=<cap>`, `make eval-record`.
- `make loadtest PROFILE=mock SCENARIO=sweep`; `make chaos`.
- `make router-train` → new artifact under `router/<version>/` + router eval report; `curl -X POST /admin/router/reload`.
- Backups: Neo4j and Postgres volumes are reproducible from source + ingestion; eval reports are committed to git; no backup required for MVP.
