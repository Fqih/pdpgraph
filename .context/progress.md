# progress.md — Living Work Log

Claude Code updates this file at the end of every session. Newest entry on top of the log.

## Current status

| Field | Value |
|---|---|
| Phase | 0 — Foundations |
| Current task | M0.4 next (M0.7 blocked; awaiting go-ahead) |
| Last updated | 2026-11-05 |
| Release | none |

## Task board

| ID | Status | Notes |
|---|---|---|
| M0.1 | done (PR #1) | uv workspace, 8 packages, ruff/mypy/pytest, pre-commit, CI green |
| M0.2 | done (PR #5) | compose `core`: 4 stores, healthchecks, mem limits, loopback ports, non-root, digests pinned; CI integration job |
| M0.3 | done (PR #3) | config, logging + redaction, telemetry, ids, pii; 142 tests; `make cov` gate |
| M0.4 | todo | fp32 CPU baseline first; int8/ONNX only as measured optimization with eval delta |
| M0.5 | done (PR #8) | `common/llm/`: async `LLMClient`, cassettes (replay/record/live), `UsageLimiter`, one span per call |
| M0.6 | done (PR #6) | Alembic `0001_initial` = 04 §6 SQL verbatim; `make migrate` idempotent; upgrade/downgrade/re-upgrade tested |
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

| Date | What | Value | Command |
|---|---|---|---|
| 2026-11-05 | Cold `make up` to all 4 stores healthy (M0.2, cpu-local laptop: Ryzen 7 PRO 4750U, 21 GB RAM) | 21.8 s | `time make up` on fresh volumes |
| 2026-11-05 | Idle store memory after start (M0.2) | neo4j 1.40 GiB, opensearch 1.40 GiB, postgres 22 MiB, valkey 3.9 MiB | `docker stats --no-stream` |
| 2026-11-05 | Branch coverage, `common` (M0.3) | 98.89% (271 stmts, 88 branches) | `make cov` |
| 2026-11-05 | Branch coverage, `common` (M0.5) | 99.04% (572 stmts, 156 branches) | `make cov` |

## Follow-ups discovered

- ruff 0.17 formats code blocks inside Markdown by default; ruff config and pre-commit hooks are limited to `.py`/`.pyi` so tooling never rewrites `.context/`.
- Global `core.hooksPath` on the dev machine points elsewhere, so `pre-commit install` refuses; it stays untouched. Run `make check` before every commit; CI runs the same hooks plus a full-history gitleaks scan.
- 04 §2.1 grammar is implemented exactly as written (owner-approved): it also accepts `#pj` on Bab/def/obl/`pj-umum` and huruf/angka directly under a Pasal. Tighten only via a spec change.
- PII patterns (`common/pii.py`) are [TUNE] and favour recall. Two rules: (1) unlabeled digit runs must not touch a letter or digit, so hex IDs, hashes, and UUIDs never match (a CI run had caught a trace ID redacted as NPWP); (2) labeled values (`NIK`, `KTP`, `No. KTP`, `nomor induk kependudukan`, `NPWP`, any case, optional space/colon/dash/dot) match even when glued to letters. **Known limitations (for README):** an unlabeled NIK/NPWP glued to letters (e.g. `abc3171…`) is missed; NIK written with internal spaces is missed unless it also passes the card Luhn check; no structural NIK validation; only mobile numbers (no landlines); no detection of names, addresses, KK/passport numbers, or other free-text PII. Any standalone 15-digit run or Luhn-valid 13–19 digit run escalates (false positives cost latency only). Measure the escalation rate on the golden set (ADR-015).
- Migrations are hand-written SQL copied verbatim from 04 §6 (no ORM metadata, so `alembic check` / autogenerate do not apply). A schema change in 04 means a new revision with the same SQL. The integration test compares columns, types, nullability, defaults, PKs, the FK, `numeric(12,6)`, and index definitions against 04 §6.
- mypy uses the `pydantic.mypy` plugin so settings fields filled from the environment type-check.
- `.env` entries that are not fields of a settings class are ignored (one `.env` serves all services); YAML keys stay strict.
- OpenSearch built-in `indonesian` analyzer stems aggressively (observed: `pengendali`→`endali`, `pribadi`→`pribad`, `memberitahukan`→`itahu`).
- **M1.6 plan (owner):** multi-field index: `text` = standard tokenizer + lowercase, no stemming; `text.stem` = `indonesian`; optional `text.shingle` for phrases. Query all with boosts tuned on the dev split only. Protect legal terms from the stemmer with a `keyword_marker` filter whose term list is generated from the graph's Definition nodes plus actor names (pengendali, prosesor, subjek data, ...). Measure each choice as a retrieval-recall ablation: no-stem vs stem vs multi-field vs multi-field + protected terms.
- **M2.11 plan (owner), extend `common/pii.py`:** structural NIK validation (province/regency code shape; birth date with the +40 day offset for women), which then makes it safe to detect space- and dash-separated NIK formats; labeled KK (Kartu Keluarga) and passport numbers; tests for each new pattern plus the existing hex/UUID property test. Names and addresses stay out of scope for deterministic detection (documented known limitation).
- M0.5 `LLMClient` limits: (1) closed in PR #10: `confidential`/`pii` are refused unless the `base_url` host is in `local_base_urls` (default 127.0.0.1, ::1, localhost); replay is exempt because it sends nothing. The M0.7 catalog and Tierline policy (M2) tighten this further; never relax it. (2) The token cap stops the *next* call, so the total can overshoot by the calls in flight. (3) `complete_json` sends `strict: true`; whether each upstream accepts pydantic-generated schemas is checked by the M0.7 probe. (4) The cassette writer applies the logging sanitizer, so a recorded body can differ from the live one if it contained secret-shaped text; PII and configured secrets are refused outright. (5) A replayed call reports the recorded latency.
- **M1.16:** reservation-based `UsageLimiter` for concurrent runs: reserve estimated prompt tokens + `max_tokens` before each call, reconcile with actual usage after.
- Cassette entries get `sanitized: true` when redaction changed any content.
- **M0.7:** `complete_json` sends `strict: true` only when the model's catalog capability flag says it is supported; no silent fallback.
- `vm.max_map_count` is 1048576 on the dev host (Fedora default), above OpenSearch's 262144, so no sysctl change was needed.
- Merges use the GitHub squash-merge button (owner decision); the recorded author/committer name is accepted as is. PR #3 was squash-merged locally (`8f03aa0`) and shows as closed.
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
| 2026-11-05 | Merge with the GitHub squash button; no local squash or force-push workflows | 09 §4 |
| 2026-11-05 | Labeled PII patterns added so `NIK3171…`-style glued values are caught | FR-GW-17 |
| 2026-11-05 | M0.7 probe hard caps: abort at 200 calls or 200,000 total tokens, whichever first | M0.7 |
| 2026-11-05 | `LLMClient` fails closed: `confidential`/`pii` only to hosts in `local_base_urls` (record/live); never relax | ADR-013, ADR-015 |
| 2026-11-05 | `LLMClient` is async (httpx), `LLM_*` settings, mode defaults to `replay`; cassette key = SHA-256 of canonical request incl. attempt; secrets checked before PII; `make eval-record` stub until M1.16 | M0.5, NFR-06, NFR-12 |

## Session log

### 2026-11-05 — M0.5 LLM client
- `common/llm/` (`client.py`, `cassette.py`, `limiter.py`, `settings.py`, `errors.py`), `evals/cassettes/`, `make eval-record` stub; dev deps `respx`, `pytest-asyncio`.
- Tests first with respx and the socket guard (RED on import, then GREEN): 60 new, 220 total. Mutation checks: dropping the error from the retry prompt and letting replay fall through to live each fail a test.
- PR #7 (04 §6 vs `0001` SQL sync test) merged first.

### 2026-11-05 — M0.6 migrations
- `common/db.py` (`PostgresSettings`, same `POSTGRES_*` vars as compose), `alembic.ini`, `migrations/` (`env.py`, `0001_initial`), `make migrate`; CI integration job runs `make migrate` twice.
- Tests first: `test_db.py` (3) and `tests/integration/test_migrations.py` (3, throwaway database per test).

### 2026-11-05 — M0.2 core stores
- `deploy/compose/compose.yaml` (`core` profile), `make up` / `make down`, `.env.example` store passwords, `tests/integration/test_core_stores.py` (14 tests, written first).
- M0.3 follow-up merged as PR #4 (labeled PII patterns, 07 §4.1 tracing note).

### 2026-11-05 — M0.3 common
- `common/`: `config.py` (YAML settings base), `logging.py` (JSON + SEC-12 redaction incl. runtime secret values), `telemetry.py`, `ids.py` (04 §2), `pii.py` (shared PII patterns), `errors.py`.
- Tests first (RED on import, then GREEN): 142 pass; branch coverage 98.89%.
- CI found a PII false positive inside a random trace ID; fixed at the root (identifier-safe boundaries) with regression and property tests.
- Licensing and `make check` landed in PR #2.

### 2026-11-05 — M0.1 scaffold
- Workspace, tooling, and CI added; `make lint test` and `pre-commit run --all-files` pass locally; CI green on PR #1.
- `KICKOFF_PROMPT.md` and `scratch/` are git-ignored (personal infra references).
- Next: M0.3 after owner confirmation.

### 2026-11-05 — Project initialized
- `.context/` documents v1.0 created.
- v1.1: CPU-only compute strategy; fixes from the kickoff review (items A–P).
