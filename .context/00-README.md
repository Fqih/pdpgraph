# .context — Project Knowledge Base

This folder is the **single source of truth** for the PDPGraph + Tierline project. It is written for two readers:

1. **Humans** (the author, reviewers, recruiters) who want to understand *why* and *how* the system is built.
2. **Claude Code**, which must read these documents before planning or writing code, and keep them up to date.

## Project in one paragraph

**PDPGraph** is a grounded compliance-intelligence system for Indonesia's Personal Data Protection Law (UU No. 27 Tahun 2022, "UU PDP"). It parses the regulation into a temporal knowledge graph, retrieves evidence with hybrid search + graph expansion, and produces **structured, clause-cited verdicts** with calibrated abstention. **Tierline** is the cost-aware, multi-tier inference gateway underneath it: an OpenAI-compatible proxy that routes each request across a semantic cache, a CPU-local small open-weight model (llama.cpp), hosted open-weight models, and a frontier API, under data-classification policy (personal/confidential data never leaves local tiers), budgets, and circuit breakers. Both layers are evaluated with golden datasets, ablations, calibrated LLM judges, and load tests, and are fully traced with OpenTelemetry.

## Reading order

| # | Document | Read when |
|---|---|---|
| 01 | [BRD — Business Requirements](01-BRD.md) | Understanding the *why*, scope, success criteria |
| 02 | [PRD — Product Requirements](02-PRD.md) | Implementing any user-facing behavior |
| 03 | [Architecture](03-architecture.md) | Before touching any component |
| 04 | [Data Model](04-data-model.md) | Before touching storage, schemas, IDs |
| 05 | [API Specification](05-api-spec.md) | Before touching any endpoint or MCP tool |
| 06 | [Evaluation Plan](06-eval-plan.md) | Before changing prompts, models, retrieval, routing |
| 07 | [NFR, Security & Operations](07-nfr-security-ops.md) | Before touching policy, tracing, deployment |
| 08 | [Roadmap](08-roadmap.md) | Picking the next task |
| 09 | [Engineering Conventions](09-conventions.md) | Always (coding standards, Definition of Done) |
| 10 | [Architecture Decision Records](10-adr.md) | Before deviating from any design choice |
| — | [progress.md](progress.md) | Start and end of every work session (living log) |

## Requirement ID scheme

IDs are stable and referenced from code, tests, and PRs.

| Prefix | Meaning | Defined in |
|---|---|---|
| `BR-xx` | Business requirement | 01-BRD |
| `FR-PDP-xx` | PDPGraph functional requirement | 02-PRD |
| `FR-GW-xx` | Tierline gateway functional requirement | 02-PRD |
| `NFR-xx` | Non-functional requirement | 07-NFR |
| `SEC-xx` | Security control | 07-NFR |
| `EV-xx` | Evaluation item / gate | 06-eval |
| `M<phase>.<n>` | Roadmap task | 08-roadmap |
| `ADR-xxx` | Architecture decision | 10-adr |

## Glossary

| Term | Meaning |
|---|---|
| UU PDP | Undang-Undang No. 27 Tahun 2022 tentang Pelindungan Data Pribadi (Indonesia's PDP Law) |
| Bab / Bagian / Paragraf | Chapter / part / sub-part — structural grouping units |
| Pasal / Ayat / huruf | Article / paragraph / lettered item — the citable legal units |
| Penjelasan | Official elucidation attached to a law (article-by-article explanation) |
| Pengendali Data Pribadi | Data controller |
| Prosesor Data Pribadi | Data processor |
| Data Pribadi spesifik | Specific (sensitive) personal data category |
| ROPA | Record of Processing Activities |
| CRAG | Corrective Retrieval-Augmented Generation — a retrieval-quality gate before generation |
| Abstention | System returns `INSUFFICIENT_EVIDENCE` instead of guessing |
| Tier | A routing destination: T0 semantic cache, T1 CPU-local small model (llama.cpp — the only tier allowed for `confidential`/`pii`), T2 hosted open-weight API, T3 frontier API |
| Local vs external | "Local" = runs on the machine running the stack. Hosted APIs and cloud notebooks are **external**. |
| Data class | `public`, `internal`, `confidential`, `pii` — governs where a request may be routed |
| Valkey | BSD-licensed Redis-compatible store; "Redis" in these docs means Valkey 8 |
| PII escalation | Tierline raises a request's data class to `pii` when its scanner detects personal data |
| Golden set | Hand-labeled evaluation questions with gold article IDs and verdicts |

## Status markers used in documents

- **[TARGET]** — a goal to be measured, not a claim. Never copy a target into the public README as a result.
- **[VERIFY]** — a fact to confirm against an official source during implementation.
- **[STRETCH]** — out of MVP scope; build only after core gates pass.

## Disclaimer

PDPGraph is an engineering/research project. Its outputs are **not legal advice**. This disclaimer must appear in the UI, in API responses (`disclaimer` field), and in the public README.
