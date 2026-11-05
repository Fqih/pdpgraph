# 09 — Engineering Conventions

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-11-05 |

---

## 1. Language & tooling

- Python 3.12; `uv` for env, deps, workspace, and running (`uv run …`). No `pip install` in docs or scripts.
- Lint/format: `ruff` (lint + format), line length 100.
- Types: `mypy --strict` for `pdp_core`, `tierline`, `common`; regular mode elsewhere. No `Any` in public signatures.
- Tests: `pytest`, `pytest-asyncio`, `hypothesis` (property tests), `respx` (httpx mocking), `testcontainers` only for integration markers.
- Pre-commit: ruff, ruff-format, mypy (changed files), gitleaks, end-of-file/trailing-whitespace.
- UI: TypeScript strict, ESLint, Prettier, Vitest; Playwright for smoke.

## 2. Code style

- Async-first for I/O. Never block the event loop (CPU-heavy work → `asyncio.to_thread` or the aux service).
- Pydantic v2 models for every boundary (API, MCP, LLM outputs, configs, dataset rows). Internal data passed as models or frozen dataclasses, not dicts.
- Pure functions for policy, verification, aggregation, ID handling — no I/O inside them; easy to property-test.
- Dependency injection via constructor args / FastAPI dependencies; no module-level singletons except settings and telemetry.
- Errors: domain exceptions in `<pkg>/errors.py`, mapped to API error envelope in one place.
- Logging: `structlog`, never `print`. Log events as `snake_case` verbs (`retrieval_completed`).
- No hidden network calls in tests: every external call is mocked or replayed.
- Prompts are files (`prompts/<name>.md` with front-matter `version`, `task_tag`, `schema`), never inline strings > 3 lines.
- Magic numbers belong in `configs/*.yaml` with a comment and an `[TUNE]` marker if not yet calibrated.

## 3. Testing strategy

| Layer | What | Marker |
|---|---|---|
| Unit | Pure logic: ids, segment grammar, refs, policy, breaker, cache guard, verification, aggregation | default |
| Property | ids round-trip, policy invariants (no sensitive → T3), budget counters monotonic | default |
| Snapshot | Ingestion outputs on the real UU 27/2022 source (counts, sampled texts) | `snapshot` |
| Contract | Backend adapters vs mock OpenAI-compatible servers; OpenAPI schema snapshot | default |
| Integration | API ↔ DBs via compose/testcontainers, LLM via cassettes | `integration` |
| Eval smoke | 30-item replay eval | `eval_smoke` |
| Load/chaos | Locust, fault proxy, `mock` profile — manual | not in CI |

Coverage target: ≥ 80% on deterministic modules (NFR-10). Don't chase coverage on glue code.

## 4. Git & PRs

- Trunk-based: short-lived branches `feat/M1.10-hybrid-retrieval`, `fix/…`, `docs/…`, `eval/…`.
- Conventional Commits: `feat(retrieval): add RRF fusion (M1.10, FR-PDP-08)`.
- One roadmap task per PR when possible; PR ≤ ~400 changed lines excluding generated files/datasets.
- PR description template (`.github/pull_request_template.md`):
  - Task ID(s) and requirement IDs
  - What changed / why
  - Tests added
  - **Eval delta** (required if prompts, models, thresholds, retrieval, routing changed — EV-06)
  - Docs updated (`.context/` files touched)
  - Risks / follow-ups
- CI must be green; no force-push to `main`.

## 5. Definition of Done (every task)

1. Code + tests merged; CI green (lint, types, unit, integration, replay smoke, policy suite).
2. Requirement IDs referenced in code docstrings or test names where relevant (e.g., `test_fr_pdp_12_rejects_invented_node_id`).
3. Telemetry: new I/O paths emit spans/metrics per 07 §4.
4. Config: new knobs in YAML with defaults and comments.
5. Docs: affected `.context/` documents updated in the same PR; schema changes reflected in 04/05.
6. `progress.md` updated (task status, notes, measured numbers if any).
7. If a design decision changed: new ADR in 10-adr.md.

## 6. Data & datasets

- Raw sources in `data/raw/` are git-ignored if large; registry + SHA-256 committed; a `scripts/fetch_sources.py` reproduces them.
- Processed artifacts are reproducible and git-ignored, except small snapshot fixtures under `tests/fixtures/`.
- Eval datasets are committed, versioned, immutable. Never edit a published version; create `v<n+1>`.
- No real personal data anywhere. Synthetic examples only; use obviously fake names/numbers.

## 7. Working agreement for Claude Code

- **Read before acting:** `.context/00-README.md`, the documents relevant to the task, and `progress.md`.
- **Plan first** for any task larger than a small fix: list files to touch, tests to write, and requirement IDs; then implement.
- **Tests first** for deterministic modules (ids, grammar, refs, policy, verification).
- **Stay in scope:** do the current roadmap task; note discoveries as follow-ups in `progress.md` instead of expanding scope.
- **Never fabricate results:** do not write numbers into README, reports, or docs unless produced by a run in this repo; mark expected values `[TARGET]`.
- **Never weaken a safety control** (policy matrix, T3 guard, verification, redaction) to make a test pass. Stop and report instead.
- **Ask when** a requirement is ambiguous, a [VERIFY] fact is blocking, a dependency needs credentials or paid API usage, or a change would alter a public schema.
- **Leave the repo runnable** at the end of every session; update `progress.md` with what's done, what's next, open questions.
