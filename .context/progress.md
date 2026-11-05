# progress.md — Living Work Log

Claude Code updates this file at the end of every session. Newest entry on top of the log.

## Current status

| Field | Value |
|---|---|
| Phase | 0 — Foundations |
| Current task | M0.3 (next, awaiting go-ahead) |
| Last updated | 2026-11-05 |
| Release | none |

## Task board

| ID | Status | Notes |
|---|---|---|
| M0.1 | done (PR #1) | uv workspace, 8 packages, ruff/mypy/pytest, pre-commit, CI green |
| M0.2 | todo | |
| M0.3 | todo | next |
| M0.4 | todo | fp32 CPU baseline first; int8/ONNX only as measured optimization with eval delta |
| M0.5 | todo | |
| M0.6 | todo | |
| M0.7 | blocked (billing class per 9router provider prefix pending from owner) | 9router alignment (ADR-016); tracked here only, not in 08-roadmap; does not block other tasks |

Approved order: M0.1 → M0.3 → M0.7 → M0.2 → M0.6 → M0.5 → M0.4.

Statuses: `todo`, `in-progress`, `blocked (<reason>)`, `done (<PR/commit>)`.

## Open questions

- [VERIFY] Official source URL and redistribution terms for UU 27/2022 text and Penjelasan.
- [VERIFY] Status of PDP implementing regulation(s) at build time.
- Which hosted open-weight provider for T2 (price, Indonesian quality, structured-output support, data-retention terms)? [VERIFY]
- Monthly API budget cap for evals and T2/T3 traffic?
- M0.7: billing class per 9router provider prefix (owner).
- GitHub profile display name (owner decides): squash merges done on GitHub take the profile name as commit author.

## Measured results (only real numbers from runs in this repo)

_None yet._

## Follow-ups discovered

- ruff 0.17 formats code blocks inside Markdown by default; ruff config and pre-commit hooks are limited to `.py`/`.pyi` so tooling never rewrites `.context/`.
- Global `core.hooksPath` on the dev machine points elsewhere, so `pre-commit install` refuses; it stays untouched. Run `make check` before every commit; CI runs the same hooks plus a full-history gitleaks scan.
- Commit `9df2b74` on `main` has author name `FaqihHakim` (GitHub squash merge used the profile display name). Accepted as is by the owner; no history rewrite. Later PRs are squashed to one commit locally and merged with `--rebase`, which keeps the author `Fqih` and still lands one commit per PR.

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
| 2026-11-05 | Public repo Fqih/pdpgraph; one branch + PR per task, squash-merge after green CI | 09 §4 |
| 2026-11-05 | M0.4 models approved (bge-m3, bge-reranker-v2-m3, mDeBERTa NLI); fp32 baseline first | 08 M0.4 |
| 2026-11-05 | Shared deterministic PII patterns in `common/pii.py` (LLMClient cassette guard + Tierline scanner) | FR-GW-17, M0.5 |
| 2026-11-05 | Within-tier alternates deferred to ADR-017 in M2.2 | FR-GW-02, FR-GW-09 |
| 2026-11-05 | Code Apache-2.0 (SPDX header per file); own datasets CC BY 4.0; statute text cited to official source | 09 §2, README |
| 2026-11-05 | M0.7 probe hard caps: abort at 200 calls or 200,000 total tokens, whichever first | M0.7 |

## Session log

### 2026-11-05 — M0.1 scaffold
- Workspace, tooling, and CI added; `make lint test` and `pre-commit run --all-files` pass locally; CI green on PR #1.
- `KICKOFF_PROMPT.md` and `scratch/` are git-ignored (personal infra references).
- Next: M0.3 after owner confirmation.

### 2026-11-05 — Project initialized
- `.context/` documents v1.0 created.
- v1.1: CPU-only compute strategy; fixes from the kickoff review (items A–P).
