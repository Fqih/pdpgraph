# 08 — Roadmap & Task Breakdown

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-11-05 |
| Horizon | ~14 weeks part-time; PDPGraph MVP in weeks 1–3 |

Each task has an ID (`M<phase>.<n>`), a Definition of Done (DoD), and requirement traces. Work in roadmap order unless a task is blocked; record status in `progress.md`. A phase is complete only when its **exit gate** passes.

**Model access before Tierline exists (Phase 1):** PDPGraph uses one `LLMClient` (OpenAI-compatible, `base_url` from config) that already sends `x-data-class` and `x-tierline-task` headers. In Phase 1 it points directly at one model endpoint chosen by config (hosted open-weight API for `public` stages; local llama.cpp available for testing); in Phase 2 it is switched to Tierline by config only. Phase 1 has no `confidential` workloads, so no policy risk before Tierline exists.

---

## Phase 0 — Foundations (days 1–3)

| ID | Task | DoD | Traces |
|---|---|---|---|
| M0.1 | Monorepo scaffold: `uv` workspace, packages per 03-architecture §8, ruff, mypy, pytest, pre-commit (ruff, mypy, gitleaks), Makefile | Git repo with GitHub remote; `make lint test` passes on empty packages; `pre-commit run --all-files` passes; CI green on first push | NFR-10, SEC-11 |
| M0.2 | Compose `core` profile (stores only): Neo4j 5.26 LTS, OpenSearch 2.x, Postgres 16, Valkey 8; healthchecks; memory limits; store ports on 127.0.0.1 | `make up` → all healthy; OpenSearch `indonesian` analyzer `_analyze` works; `make down` (runs `compose down -v`) leaves no project volumes | BR-16, SEC-15 |
| M0.3 | `common/`: config loader (pydantic-settings + YAML), structured logging with redaction, OTel setup, ID utilities with round-trip tests | Tests for `ids.py` cover all examples in 04 §2 plus property tests | FR-PDP-02, SEC-12 |
| M0.4 | `models-aux` service on CPU: `/embed`, `/rerank`, `/nli` with dynamic batching; ONNX/int8 where it helps; measure per-call latency | Integration test returns correct dims/scores on fixtures | 05 §4 |
| M0.5 | `common/llm/`: `LLMClient` with required `data_class` (no default), `x-tierline-task`, timeouts, JSON-schema output helper, **one retry that appends the validation error to the prompt**, cassette record/replay in `evals/cassettes/` (stable keys; refuses to record `pii`) | Unit tests with a fake server; replay works with networking blocked | FR-PDP-11, FR-PDP-18 |
| M0.6 | Postgres migrations (Alembic) for 04 §6 | `make migrate` idempotent | — |

## Phase 1 — PDPGraph MVP "Grounded" (weeks 1–3) → v0.1

### Week 1 — corpus & graph

| ID | Task | DoD | Traces |
|---|---|---|---|
| M1.1 | Source registry + `fetch` stage; obtain official UU 27/2022 text (prefer text-layer PDF/HTML) [VERIFY source] | Raw file + SHA-256 + provenance stored | FR-PDP-01, SEC-14 |
| M1.2 | `extract` + `segment` stages (grammar state machine) incl. Penjelasan mapping; overrides file | Snapshot tests: total Pasal count, ayat counts for 10 sampled Pasal, exact text of 10 sampled units match manual check | FR-PDP-01 |
| M1.3 | `refs` stage: reference grammar + resolver; report unresolved | ≥ 95% of internal reference mentions resolved on manual sample of 50 [TARGET]; unresolved list committed | FR-PDP-03 |
| M1.4 | `defs` stage: definitions + term usage linking | All Pasal 1 definitions extracted; usage links spot-checked (20) | FR-PDP-04 |
| M1.5 | `load_graph` + constraints + canonical Cypher queries with tests | Queries in 04 §3.4 tested against fixture graph | FR-PDP-06 |
| M1.6 | `index` stage: OpenSearch mapping + embeddings + alias swap | Hybrid query returns expected unit for 10 known-item queries | FR-PDP-07 |
| M1.7 | **Golden set v0**: annotation guideline + first 50 items (dev) — *write before the generator exists* | 50 items valid against schema; datasheet drafted | EV, BR-14 |

### Week 2 — pipeline

| ID | Task | DoD | Traces |
|---|---|---|---|
| M1.8 | Pipeline state machine framework (states, transitions, context, persistence to `decision_traces`, OTel span per state) | Unit tests for transitions incl. bounded rewrite loop and abstain paths | FR-PDP-14 |
| M1.9 | Normalize + Plan (guided JSON, skip heuristic) | Plan schema always valid on dev set (with retry) | FR-PDP-09 |
| M1.10 | Retrieve (BM25 + dense + RRF, as_of filter, explicit-reference hints) + Rerank | Retrieval recall@k on golden dev reported | FR-PDP-08 |
| M1.11 | Expand (graph expansion with budget and path recording) | Multi-hop path recall reported vs no-expansion | FR-PDP-08 |
| M1.12 | CRAG gate (thresholds + LLM adjudication) + Rewrite (max 1) | Thresholds calibrated on dev; decision distribution logged | FR-PDP-10 |
| M1.13 | Generate (evidence blocks, guided JSON `GeneratedAnswer`) | Valid JSON rate ≥ 99% on dev after retry | FR-PDP-11 |
| M1.14 | VerifyCitations (deterministic) + VerifyEntailment (NLI + optional LLM) + Aggregate (incl. currency guard) + Abstain | Unit tests with adversarial fakes: invented IDs, paraphrased quotes, and out-of-evidence citations are all dropped. Currency-guard tests: a claim on an affected unit with `as_of ≥ effective_on` is dropped as `unmodeled_change`, an emptied answer abstains naming the change, and `as_of < effective_on` passes. 4 `pdp-adversarial` items ask about current UU PDP criminal fines and Pasal 53(1)(b) with `as_of` = today | FR-PDP-12, FR-PDP-13, FR-PDP-20 |
| M1.15 | `POST /v1/query` (+SSE), `GET /v1/articles`, `GET /v1/trace`, health; OpenAPI snapshot test | E2E test against compose stack with cassettes | FR-PDP-16 |

### Week 3 — evaluation & first report

| ID | Task | DoD | Traces |
|---|---|---|---|
| M1.16 | Eval harness core: runner, metrics (§3 of 06), report generator, Postgres persistence, replay mode | `make eval-smoke` runs offline in CI | EV-01 |
| M1.17 | Golden set to 150 items (dev/test split), adversarial v1 (≥ 60), injection v1 (≥ 40) | Schema-valid; datasheets complete | 06 §2 |
| M1.18 | Synthetic multi-hop generator + 300 items with filters | Acceptance rate and spot-check recorded | 06 §2.2 |
| M1.19 | Judge prompts + calibration on 100 human-labeled items | κ reported per rubric | 06 §5 |
| M1.20 | Ablation run (06 §4) on dev, then once on test; failure analysis | Report committed; README draft with real numbers | SC-1..SC-5 |
| M1.21 | Obligation extraction stage + review queue (can trail into Phase 2) | ≥ 80% of obligations reviewed | FR-PDP-05 |

**Exit gate v0.1:** EV-01, EV-03 pass; ablation report on test split committed (targets may be missed but must be reported); README shows measured table.
Also: `overrides_unconfirmed = 0` for every ingested source (sources row and eval report setup); every manual text override has been checked by the owner against the reference page image.

## Phase 2 — Tierline MVP "Routed" (weeks 4–6) → v0.2

| ID | Task | DoD | Traces |
|---|---|---|---|
| M2.1 | Gateway skeleton: OpenAI-compatible endpoints (stream + non-stream), auth → tenant, request IDs, response headers | OpenAI Python SDK integration test passes (both modes) | FR-GW-01, FR-GW-15 |
| M2.2 | Tier registry + backend adapters (vllm, llamacpp, openai_compatible, frontier) | Contract tests against mock servers | FR-GW-02 |
| M2.3 | Policy engine (pure) + data-class matrix + property-based suite + T3 adapter second guard + canary test | **0 violations** (EV-02) | FR-GW-03, FR-GW-04, SEC-01..03 |
| M2.4 | Budgets + rate limiting (Redis) with `reject`/`downgrade` | Tests at boundary conditions; admin endpoint | FR-GW-12, SEC-09 |
| M2.5 | Circuit breakers + fallback chains + timeouts (connect/TTFT/total) + retries (non-stream) | Fault-injection tests (mock upstream returning 5xx/timeouts) | FR-GW-09, FR-GW-10 |
| M2.6 | Static router (task tag → tier) as baseline | Config-driven; explain endpoint shows rule | FR-GW-06 |
| M2.7 | Request log + explain endpoint + Prometheus metrics + OTel spans | Explain JSON matches 05 §3.3 | FR-GW-13, FR-GW-14 |
| M2.8 | Switch PDPGraph to Tierline; set data classes per call site; re-run smoke eval | Smoke eval unchanged within noise; traces show gateway spans nested | FR-PDP-18 |
| M2.9 | Compose `local-llm` (llama.cpp T1, memory-limited) + `obs` + `mock` profiles; Grafana dashboards 1 & 4 | Dashboards render with live traffic | 07 §4.3 |
| M2.11 | PII scanner with escalation (FR-GW-17) + synthetic PII test set incl. near-misses | Escalation tests pass; no matched text in logs | FR-GW-17, SEC-16 |
| M2.10 | Gateway overhead benchmark with mock upstream | Report committed | NFR-02, NFR-03 |

**Exit gate v0.2:** EV-02 (0 policy violations) passes in CI; PDPGraph runs fully through Tierline; overhead report committed.

## Phase 3 — Router, cache, performance "Measured" (weeks 7–9) → v0.3

| ID | Task | DoD | Traces |
|---|---|---|---|
| M3.1 | Build `router-prompts` dataset (incl. prompts captured from PDPGraph stages) | 500+ prompts with references/rubrics | 06 §2.7 |
| M3.2 | Label pipeline: run every prompt on every tier (cached), judge, store labels | Label table + cost of labeling recorded | 06 §5 |
| M3.3 | Feature extraction + router training (`tierline_router_train`), versioned artifact, router eval (AUC, calibration plot) | Artifact + metadata + report | FR-GW-06, FR-GW-16 |
| M3.4 | Learned router in gateway + τ knob + hot reload | Explain shows scores; reload without downtime | FR-GW-06 |
| M3.5 | Pareto experiment: sweep τ; baselines (random, length heuristic, always-T1, always-T3, static rules) | Pareto chart + table committed | SC-7, BO-4 |
| M3.6 | Load-aware dispatch (llama.cpp slots/metrics scraper, external in-flight + 429 tracking, penalty, saturation skip) | Load test shows reduced p99 vs load-blind at high concurrency | FR-GW-07 |
| M3.7 | Semantic cache + entity/number guard + perturbation test set | Hit rate and false-hit rate reported; guard ablation | FR-GW-05 |
| M3.8 | Record real-tier latency profiles; Locust sweep on `mock` + small real-tier runs (06 §6.1) | Report with pinned configs | NFR-01, NFR-04 |
| M3.9 | Chaos tests (06 §6.3) with fault proxy | Timeline chart + report | SC-9 |
| M3.10 | Grafana dashboards 2 & 3 | Provisioned | 07 §4.3 |

**Exit gate v0.3:** Pareto, load, chaos, cache reports committed; router artifact versioned.

## Phase 4 — Product completeness "Integrated" (weeks 10–13) → v1.0

| ID | Task | DoD | Traces |
|---|---|---|---|
| M4.1 | Gap analysis: candidate obligations Cypher + per-obligation assessment (map-reduce, bounded concurrency) + verification | `gap-cases` eval: per-status F1 reported | FR-PDP-15 |
| M4.2 | `POST /v1/gap-analysis` (+SSE, YAML input) | E2E tests | FR-PDP-15 |
| M4.3 | MCP server (stdio + streamable HTTP), tools + resource template | Conformance smoke test with reference client; demo with an agent client | FR-PDP-17 |
| M4.4 | As-of support end-to-end + `pdp-temporal-synth` dataset in isolated namespace | Temporal accuracy reported | FR-PDP-06, BR-05 |
| M4.5 | Implementing regulation ingestion if available [VERIFY status]; otherwise document how to add | Either ingested with tests or ADR explaining deferral | A-2 |
| M4.6 | UI: query view, citation chips, source panel, reasoning graph (Cytoscape), gap-analysis table, disclaimer | Manual QA checklist; Playwright smoke test | FR-PDP-19 |
| M4.7 | Full eval rerun on final config (EV-04) | Reports committed | BR-14 |

## Phase 5 — Polish & publication (week 14)

| ID | Task | DoD |
|---|---|---|
| M5.1 | Public README: problem, architecture diagram, demo GIF, headline tables/charts from reports, known limitations, how to reproduce | Reviewed against BRD SC list |
| M5.2 | `DESIGN.md` (public condensed version of 03 + key ADRs + rejected alternatives) | — |
| M5.3 | `make demo`: clean clone → running demo with small models in ≤ 15 min (after model download) | Tested on fresh machine/container (SC-11) |
| M5.4 | Write-up (blog post / LinkedIn article) on the ablation and policy findings | Draft published |
| M5.5 | Tag v1.0, release notes | — |

## Stretch backlog (only after v1.0 gates)

- Confidence-gated cascade + hedged requests (FR-GW-08)
- Mid-stream failover (FR-GW-11)
- Tool-call pass-through in gateway
- Free-text company policy ingestion (PDF) with PII scrubbing
- Additional regulations (sectoral rules) and cross-regulation references
- Time-boxed vLLM engine benchmark on a free cloud-notebook GPU (public data only)
- Go rewrite of gateway hot path with benchmark comparison (ADR-002 follow-up)
- Kubernetes manifests + HPA on queue depth
