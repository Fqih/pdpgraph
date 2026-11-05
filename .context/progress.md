# progress.md — Living Work Log

Claude Code updates this file at the end of every session. Newest entry on top of the log.

## Current status

| Field | Value |
|---|---|
| Phase | 0 — Foundations |
| Current task | M0.1 |
| Last updated | 2026-11-05 |
| Release | none |

## Task board

| ID | Status | Notes |
|---|---|---|
| M0.1 | todo | |
| M0.2 | todo | |
| M0.3 | todo | |
| M0.4 | todo | |
| M0.5 | todo | |
| M0.6 | todo | |

Statuses: `todo`, `in-progress`, `blocked (<reason>)`, `done (<PR/commit>)`.

## Open questions

- [VERIFY] Official source URL and redistribution terms for UU 27/2022 text and Penjelasan.
- [VERIFY] Status of PDP implementing regulation(s) at build time.
- Which hosted open-weight provider for T2 (price, Indonesian quality, structured-output support, data-retention terms)? [VERIFY]
- Monthly API budget cap for evals and T2/T3 traffic?

## Measured results (only real numbers from runs in this repo)

_None yet._

## Follow-ups discovered

_None yet._

## Decisions log

| Date | Decision | Where |
|---|---|---|
| 2026-11-05 | No GPU anywhere: T1 = llama.cpp on CPU (local), T2 = hosted open-weight (external), T3 = frontier (external) | ADR-013 |
| 2026-11-05 | Full ID grammar (Bab/Bagian/Paragraf, ayat (1a), angka under huruf, `#pj` before `@`, `pj-umum`, definition slugs) | 04 §2 |
| 2026-11-05 | `core` compose profile = stores only; app services in `app` profile; `make down` runs `compose down -v` | 03 §7, 08 M0.2 |
| 2026-11-05 | Store ports bound to 127.0.0.1 | SEC-15 |
| 2026-11-05 | `src/` layout per package; top-level `migrations/` + `alembic.ini`; named indexes | 03 §8, 04 §6 |
| 2026-11-05 | `LLMClient` in `common/llm/`; required data class; retry appends validation error; cassettes in `evals/cassettes/`; never record `pii` | 08 M0.5 |
| 2026-11-05 | mypy strict also covers `common` | NFR-10 |
| 2026-11-05 | User question text is `internal`; deterministic PII scanner escalates to `pii`; demo tenant opts `internal` into T2/T3 | ADR-015, FR-GW-17 |
| 2026-11-05 | Cache always tenant-scoped (incl. `public`) | 03 §6.2 |
| 2026-11-05 | Tierline errors use OpenAI error shape; admin paths `/admin/...` in both services | 05 |
| 2026-11-05 | Valkey 8 instead of Redis 7.4 | ADR-014 |
| 2026-11-05 | Keep OpenSearch 2.x and Neo4j 5.26 LTS (newer majors deferred) | ADR-003/004 |

## Session log

### 2026-11-05 — Project initialized
- `.context/` documents v1.0 created.
- v1.1: CPU-only compute strategy; fixes from the kickoff review (items A–P).
