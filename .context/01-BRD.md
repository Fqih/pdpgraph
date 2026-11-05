# 01 — Business Requirements Document (BRD)

| Field | Value |
|---|---|
| Project | PDPGraph + Tierline |
| Owner | Faqih Hakim |
| Version | 1.1 |
| Date | 2026-11-05 |
| Status | Approved for build |

---

## 1. Executive summary

Indonesian organizations must now comply with UU No. 27/2022 (UU PDP) after its two-year transition period ended in October 2024 [VERIFY exact dates]. Compliance work is manual, expensive, and depends on scarce privacy specialists who cross-reference dense legal text against how systems actually process data.

General-purpose LLM chatbots are unsuitable for this work: they hallucinate article numbers, miss cross-references, ignore which version of a rule applies, and send sensitive company data to third-party APIs — itself a potential PDP issue.

This project delivers two layered systems:

- **PDPGraph** — answers compliance questions and performs gap analysis with **clause-level citations, verifiable grounding, and explicit abstention**.
- **Tierline** — a self-hostable inference gateway that keeps sensitive data on local models, routes easy work to cheap models, and degrades gracefully when a model tier fails.

Secondary objective: the project is a public engineering portfolio. Every claim in its README must be backed by a reproducible evaluation.

## 2. Problem statement

| # | Problem | Who feels it | Consequence |
|---|---|---|---|
| P1 | Legal text is cross-referential ("sebagaimana dimaksud dalam Pasal X ayat (Y)") and definition-scoped; answers need multi-hop reading | DPOs, compliance consultants | Slow, error-prone manual analysis |
| P2 | LLM chatbots fabricate citations and give confident wrong answers | Anyone using AI for compliance | Legal exposure; loss of trust in AI tooling |
| P3 | Regulations change (implementing regulations, amendments); answers must reflect the version in force on a given date | Compliance teams | Outdated advice |
| P4 | Company artifacts (ROPA, schemas, policies) are confidential/personal data; sending them to external APIs creates risk | Security & legal teams | Teams forbid AI use entirely |
| P5 | Running frontier models for every request is expensive; running only small local models is low-quality | Engineering / platform teams | Either cost blowout or poor quality |
| P6 | Teams cannot measure whether an AI system is right; no evals, no traces | Engineering leadership | Systems can't be trusted or improved |

## 3. Business objectives

| ID | Objective | Measured by |
|---|---|---|
| BO-1 | Answer UU PDP questions with verifiable, clause-level grounding | Citation precision/recall and claim-support rate on the golden set (06-eval) |
| BO-2 | Refuse to answer when evidence is insufficient, rather than guess | Selective accuracy vs coverage curve; adversarial-set pass rate |
| BO-3 | Keep confidential/personal data on local infrastructure, by enforced policy | Zero policy violations in the routing-policy test suite (hard gate) |
| BO-4 | Reduce inference cost at near-frontier quality | Cost–quality Pareto curve vs frontier-only baseline |
| BO-5 | Operate reliably under load and upstream failure | p99 latency vs concurrency; success rate during chaos tests |
| BO-6 | Be reproducible and inspectable by a technical reviewer in < 15 minutes | `make demo` works from clean clone; README eval tables link to reports |

## 4. Stakeholders & personas

| Stakeholder | Interest |
|---|---|
| **Data Protection Officer / compliance analyst** (primary user) | Fast, cited answers; gap analysis of processing activities |
| **Privacy consultant** | Reusable analysis across client engagements; explainable reasoning to show clients |
| **Platform / ML engineer** (Tierline user) | Drop-in OpenAI-compatible gateway with cost control and policy enforcement |
| **Security lead** | Proof that sensitive data never reaches external APIs |
| **Technical hiring manager / reviewer** (portfolio audience) | Evidence of architecture maturity, rigorous evals, honest failure analysis |

## 5. Scope

### 5.1 In scope (MVP + full build)

- Ingestion and structural parsing of UU No. 27/2022 (body + Penjelasan) from an official source.
- Temporal knowledge graph of articles, paragraphs, definitions, obligations, actors, data categories, sanctions, and cross-references.
- Hybrid retrieval (BM25 + dense + reranker) with graph expansion.
- CRAG-gated question answering with structured output, deterministic citation checks, NLI entailment checks, and abstention.
- Gap analysis of a user-supplied processing activity (ROPA-style JSON/YAML) against obligations.
- Decision-trace visualization.
- MCP server exposing PDPGraph tools.
- Tierline gateway: OpenAI-compatible API, policy layer, learned router, load-aware dispatch, semantic cache with correctness guard, budgets, circuit breakers, streaming.
- Evaluation harness, golden sets, ablations, judge calibration, load and chaos tests.
- OpenTelemetry tracing, Prometheus metrics, Grafana dashboards.
- Docker Compose deployment for local/single-node use.

### 5.2 Out of scope

- Legal advice, legal opinions, or certification of compliance.
- Regulations beyond UU PDP and its implementing regulations (other sectors' rules are a [STRETCH] extension).
- Multi-tenant SaaS hosting, billing, user management beyond API keys.
- Kubernetes deployment (documented as a future path only).
- Automatic parsing of arbitrary company documents (PDF policies, contracts). MVP accepts structured ROPA input; free-text policy ingestion is [STRETCH].
- Fine-tuning or training LLMs (the router classifier is the only trained model).

## 6. Business requirements

| ID | Requirement | Priority |
|---|---|---|
| BR-01 | The system shall answer natural-language questions (Indonesian and English) about UU PDP obligations. | Must |
| BR-02 | Every factual claim in an answer shall cite the specific Pasal/ayat/huruf it relies on, and the cited text shall be verifiable against the source. | Must |
| BR-03 | The system shall abstain with `INSUFFICIENT_EVIDENCE` and state what is missing when evidence does not support an answer. | Must |
| BR-04 | The system shall resolve cross-references and definitions that an answer depends on. | Must |
| BR-05 | The system shall answer "as of" a given date, using only provisions in force on that date. | Should |
| BR-06 | The system shall perform gap analysis of a described processing activity and list applicable obligations, satisfied/unsatisfied/unknown, each with citations. | Must |
| BR-07 | The system shall show the reasoning path (sub-questions → evidence → claims → verdict) for every answer. | Must |
| BR-08 | Data classified `confidential` or `pii` shall never be sent to an external model API. This is enforced by the gateway, not by caller convention. | Must |
| BR-09 | The gateway shall route requests to the cheapest tier predicted to meet a configurable quality threshold. | Must |
| BR-10 | The gateway shall enforce per-tenant token/cost budgets. | Must |
| BR-11 | The gateway shall continue serving when one tier fails (fallback, circuit breaking). | Must |
| BR-12 | The gateway shall expose an OpenAI-compatible API so existing clients work unchanged. | Must |
| BR-13 | Every request shall be traceable end-to-end with cost, latency, tokens, model, and routing decision. | Must |
| BR-14 | All quality, cost, and latency claims shall be reproducible from versioned eval datasets and configs. | Must |
| BR-15 | PDPGraph capabilities shall be available to agent clients via MCP. | Should |
| BR-16 | The full stack shall run on a single CPU-only machine (16 GB RAM) via Docker Compose, with external model APIs configured by environment variables. | Must |

## 7. Success criteria

All numeric values are **[TARGET]** — to be measured and reported honestly, including misses.

| ID | Criterion | Target |
|---|---|---|
| SC-1 | Article-level citation precision on golden set | ≥ 0.90 |
| SC-2 | Article-level citation recall on golden set | ≥ 0.80 |
| SC-3 | Claim-support rate (claims entailed by cited spans) | ≥ 0.95 |
| SC-4 | Selective accuracy at ≥ 80% coverage | ≥ 0.90 |
| SC-5 | Multi-hop question accuracy improvement, hybrid+graph vs vector-only | ≥ +15 pts absolute |
| SC-6 | Data-policy violations in routing test suite | **0** (hard gate) |
| SC-7 | Cost reduction vs frontier-only at quality within 5% of frontier-only | ≥ 40% |
| SC-8 | Gateway added latency (p99, excluding upstream) | ≤ 15 ms |
| SC-9 | Request success rate while one tier is killed mid-load | ≥ 99% |
| SC-10 | LLM-judge agreement with human labels (Cohen's κ) | ≥ 0.6 |
| SC-11 | Clean-clone to working demo | ≤ 15 minutes, one command after model download |

## 8. Assumptions

- A-1: The official text of UU No. 27/2022 and its Penjelasan are publicly available from official government legal databases (e.g., peraturan.bpk.go.id / JDIH) [VERIFY source and licensing for redistribution of derived data].
- A-2: Implementing regulations may or may not be finalized; the graph must support adding them later without schema changes [VERIFY current status at build time].
- A-3: **No owned GPU.** Local inference runs on CPU (llama.cpp, small quantized models). Mid-size open-weight models are consumed through hosted, pay-per-token APIs. Free cloud notebook GPUs (Colab/Kaggle) are used only for occasional, time-boxed benchmark sessions on public data (ADR-013).
- A-4: A frontier model API key and a hosted open-weight API key, each with a modest budget, are available for T2/T3 and for judge labeling.
- A-5: At least one person with legal/compliance knowledge can review a subset (≥ 50) of golden-set labels.

## 9. Constraints

- C-1: Single developer, part-time; MVP of PDPGraph in ~3 weeks, full system in ~3–4 months.
- C-2: CPU-only local inference → the local tier is limited to small quantized models (~1.5–4B, Q4/Q5) with low throughput. Confidential/PII workloads (gap analysis) therefore run on a small model; this quality trade-off is measured and reported, not hidden.
- C-3: API budget is limited → judge calls, T2/T3 traffic, and router labeling must be cached (content-addressed) and capped per run.
- C-4: Public repository → no real company data, no secrets, synthetic ROPA examples only.

## 10. Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-1 | Legal PDF parsing is inconsistent (OCR, layout) | High | High | Prefer text-layer sources; snapshot tests per article; manual fix-up file for edge cases |
| R-2 | Golden-set labels are wrong (no legal expertise) | Medium | High | Annotation guideline; expert review of subset; report inter-annotator agreement |
| R-3 | Small local models fail at structured output | High | Medium | Constrained decoding (llama.cpp JSON schema/grammar); 1 retry; for `public` work escalate tier; for `confidential` fail closed and report |
| R-4 | Router labels are expensive to produce | Medium | Medium | Label once, cache all tier outputs; start with 500 prompts |
| R-5 | Scope creep (UI polish, extra regulations) | High | Medium | Roadmap gates; [STRETCH] items only after gates pass |
| R-6 | Misrepresenting outputs as legal advice | Low | High | Disclaimer in UI/API/README; framing as research tool |
| R-7 | No GPU; CPU local tier is slow and weak | High | Medium | Keep local tier for sensitive data only; route public work to hosted APIs; cassettes for tests; report small-model quality honestly |
| R-9 | Hosted API rate limits, price or model changes | Medium | Medium | Provider-agnostic adapters; pin model IDs; record prices with date in reports; aggressive caching |
| R-8 | Prompt injection via ingested documents or user-supplied ROPA | Medium | Medium | Treat ingested text as data; output schema enforcement; injection test suite (07-NFR SEC) |

## 11. Approval

Scope, objectives, and success criteria in this BRD govern all downstream documents. Changes require an ADR entry (10-adr.md) and a version bump here.
