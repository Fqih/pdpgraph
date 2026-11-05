# CLAUDE.md

Project: **PDPGraph + Tierline** — grounded compliance intelligence for Indonesia's PDP Law (UU 27/2022) on top of a cost-aware, policy-enforcing multi-tier LLM gateway.

## Source of truth

All requirements, architecture, schemas, and plans live in `.context/`. **Read `.context/00-README.md` and `.context/progress.md` at the start of every session**, then the documents relevant to the task:

| Working on… | Read |
|---|---|
| Anything | `09-conventions.md` (DoD, working agreement) |
| Ingestion, graph, search | `03-architecture.md` §5.1, `04-data-model.md` |
| Query pipeline / gap analysis | `02-PRD.md` FR-PDP, `03-architecture.md` §5.2–5.3, `04-data-model.md` §5 |
| Endpoints / MCP | `05-api-spec.md` |
| Gateway | `02-PRD.md` FR-GW, `03-architecture.md` §6, `07-nfr-security-ops.md` §3 |
| Prompts, models, thresholds, routing | `06-eval-plan.md` (eval delta required) |
| Tracing / metrics / deployment | `07-nfr-security-ops.md` §4–7 |
| Choosing the next task | `08-roadmap.md` |
| Deviating from a design | `10-adr.md` (add an ADR) |

If code and `.context/` disagree, stop and flag it; fix both in the same change.

## Commands

```bash
make up            # compose core profile: stores only (neo4j, opensearch, postgres, valkey)
make down          # compose down -v (removes project volumes)
make up-llm        # + llama.cpp T1 (CPU) + models-aux (CPU)
make up-mock       # + mock upstream + fault proxy (gateway benchmarks)
make up-obs        # + otel collector, phoenix, prometheus, grafana
make lint          # ruff + mypy
make test          # unit + property + contract
make test-int      # integration (needs `make up`)
make eval-smoke    # 30-item replay eval (no model/API)
make ingest SOURCE=uu27-2022
```

(Create these targets in M0.1 if they don't exist yet.)

## Non-negotiables

0. **There is no GPU.** Everything must run on CPU; T2/T3 are external APIs. Don't introduce GPU-only dependencies.
1. **Never send `confidential`/`pii` data to any external tier (T2 hosted open-weight or T3 frontier).** Never weaken the policy matrix, the external-adapter guard, citation/entailment verification, or log redaction to make something pass. Stop and report instead.
2. **Never fabricate results.** No numbers in README/reports/docs unless produced by a run in this repo. Expected values are marked `[TARGET]`.
3. **Never stream unverified claims** to users.
4. **Every LLM output that feeds logic** uses guided JSON decoding + Pydantic validation.
5. **No real personal data** in the repo; synthetic only. No secrets in code; use `.env` (git-ignored).
6. Outputs carry the "not legal advice" disclaimer.

## How to work

- One roadmap task at a time (`M<phase>.<n>`). Plan (files, tests, requirement IDs) before coding anything non-trivial.
- Tests first for deterministic modules (ids, segmentation grammar, references, policy, breakers, cache guard, verification).
- Use `uv run …`; Python 3.12; ruff; mypy strict on `pdp_core`, `tierline`, `common`.
- Conventional commits referencing task + requirement IDs, e.g. `feat(policy): deny T3 for pii (M2.3, FR-GW-03)`.
- Ask before: changing a public schema/API, adding a new service or heavy dependency, anything needing credentials or paid API usage, or resolving a `[VERIFY]` fact by guesswork.
- End every session by updating `.context/progress.md` (status, measured numbers, follow-ups, open questions) and leaving the repo runnable.
