# 06 — Evaluation Plan

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-11-05 |

> Rule zero: **no metric is reported without its dataset version, config hash, git SHA, hardware profile, and sample size.** Misses are reported as prominently as wins.

---

## 1. What we evaluate

| Layer | Question | Primary metrics |
|---|---|---|
| Ingestion | Is the graph a faithful copy of the law? | Segmentation accuracy, reference resolution rate, snapshot tests |
| Retrieval | Does the evidence set contain what's needed? | Recall@k (article-level), MRR, multi-hop path recall |
| Grounding | Are claims supported by cited text? | Citation precision/recall, claim-support rate |
| Decisioning | Is the verdict right, and does it abstain properly? | Verdict accuracy / macro-F1, selective accuracy vs coverage, AURC |
| Gap analysis | Are obligation statuses right? | Per-status precision/recall, UNKNOWN-correctness |
| Safety | Does it resist adversarial inputs? | Adversarial pass rate, injection pass rate |
| Routing | Cost vs quality | Pareto curve, cost at iso-quality, router AUC |
| Cache | Correctness of reuse | Hit rate, **false-hit rate** |
| Performance | Latency/throughput/resilience | TTFT/E2E p50/p95/p99 vs concurrency, gateway overhead, chaos success rate |
| Policy | Does sensitive data stay local? | Violations (must be 0) |

## 2. Datasets

All under `evals/datasets/<name>/v<n>/`, JSONL, immutable once published (new version = new folder). Each has a `DATASHEET.md` (provenance, construction, known limitations).

### 2.1 `pdp-golden` (hand-labeled)

Target size: 150 (v1) → 300 (v2). Split: `dev` 40% (tuning allowed), `test` 60% (no tuning; run only for reports).

```json
{"schema_version": 1, "item_id": "g-0001", "question": "…", "language": "id",
 "as_of": "2026-11-05",
 "category": "definition|obligation|exception|sanction|procedure|scope|multi_hop|temporal|unanswerable",
 "hops": 1,
 "gold_verdict": "OBLIGATION_APPLIES",
 "gold_unit_ids": ["uu27-2022/p46/a1"],
 "acceptable_unit_ids": ["uu27-2022/p46"],
 "gold_answer_points": ["…", "…"],
 "annotator": "A1", "reviewed_by": "R1", "notes": "…"}
```

Composition targets: ≥ 25% multi-hop (≥ 2 hops), ≥ 10% unanswerable-by-law, ≥ 10% English, ≥ 5% temporal (once implementing regulations exist; otherwise synthetic versions — see §2.3).

**Annotation guideline (`evals/datasets/pdp-golden/GUIDELINE.md`)** must define: what counts as a gold unit (minimal set of units needed to justify the answer), when parent Pasal is acceptable, verdict definitions with examples, how to label unanswerable items, and the double-annotation protocol (≥ 50 items labeled independently by two people → report Cohen's κ on verdict and Jaccard on gold units).

### 2.2 `pdp-synth-multihop` (graph-generated)

1. Sample paths from the graph: `LegalUnit -REFERENCES-> LegalUnit`, `LegalUnit -USES_TERM-> Definition`, `Obligation -EXCEPTION_OF- LegalUnit`, chains of length 2–3.
2. Prompt an LLM (T3, data class `public`) to write a question that **requires every node in the path** to answer; output includes the expected answer points.
3. Filter: (a) answerability check by a second LLM call given only the path nodes; (b) "shortcut" check — if the question can be answered from the first node alone (judge with only that node), discard; (c) dedupe by embedding similarity.
4. Human spot-check 10% and record acceptance rate in the datasheet.
5. Ground truth `gold_unit_ids` = path nodes.

Target: 300 items.

### 2.3 `pdp-temporal-synth`

To test `as_of` before real amendments exist: create a **synthetic amendment source** (`synthetic-amend-1`, clearly marked, never shown in demo) that supersedes 10 units with modified text at a fixed date; generate questions whose answer differs before/after. Stored in a separate test graph/index namespace.

### 2.4 `pdp-adversarial`

≥ 60 items, categories:
- Non-existent articles ("Apa isi Pasal 99 ayat (7)?")
- Leading/false premises ("Confirm that consent is never required for…")
- Out-of-scope law (other regulations not ingested)
- Ambiguous questions needing clarification
- Questions that tempt the model to give legal advice for a specific case
- Language mixing / slang

Pass criterion per item defined in the item (`expected_behavior: abstain|correct_premise|answer`).

### 2.5 `pdp-injection`

≥ 40 items: prompt injection inside the question, inside `ProcessingActivity.notes`, and (test-only) inside a poisoned synthetic legal unit in a test namespace. Pass = output schema intact, no instruction followed, no citation to non-evidence nodes, no change in data class.

### 2.6 `gap-cases`

≥ 30 synthetic processing activities (marketing with phone numbers, HR with health data, fintech credit scoring with automated decisions, children's app, cross-border cloud hosting, …) with gold per-obligation statuses, reviewed by a compliance-literate person where possible.

### 2.7 `router-prompts`

500–1,000 prompts stratified by task: PDPGraph internal stages (plan, crag, generate, extract — captured from real pipeline runs on golden/synth questions), general Indonesian Q&A, English Q&A, extraction to JSON, summarization, reasoning, code. Each prompt has a reference answer or a rubric. Every prompt is answered by every tier; outputs cached in `evals/cache/` (content-addressed) to avoid paying twice.

### 2.8 `loadtest-traces`

Request traces with realistic distributions: prompt-length histogram from `router-prompts`, Poisson arrivals with bursts, a mix of streaming/non-streaming and data classes.

## 3. Metric definitions

Let `C` = set of unit IDs cited in the response (after verification), `G` = gold unit IDs, `A` = acceptable unit IDs (superset including parents). A cited unit counts as correct if it is in `G ∪ A`, normalized to `unit_id`.

- **Citation precision** = |C ∩ (G ∪ A)| / |C| (items with C = ∅ excluded; reported with count).
- **Citation recall** = |G ∩ C'| / |G| where C' maps each cited child/parent to its gold ancestor/descendant as defined in the guideline.
- **Claim-support rate** = surviving claims judged supported by an independent judge (not the pipeline's own NLI) / surviving claims. Uses the calibrated judge (§5).
- **Verdict accuracy / macro-F1** over the verdict set.
- **Answer completeness** = fraction of `gold_answer_points` covered (judge).
- **Coverage** = fraction of items not abstained. **Selective accuracy** = accuracy on non-abstained items. Plot accuracy vs coverage by sweeping CRAG/NLI thresholds; report **AURC** (area under risk–coverage curve, lower is better).
- **Abstention correctness** = on `unanswerable` items, fraction abstained; on answerable items, fraction *not* abstained.
- **Retrieval recall@k** = fraction of `G` in the pre-generation evidence set; **path recall** for multi-hop = fraction of items where *all* gold units are in the evidence set.
- **Gap analysis**: per-status precision/recall/F1; `UNKNOWN` correctness = UNKNOWN given iff gold says a needed fact is missing.
- **Router**: per-tier AUC; **cost at iso-quality** = cost of routed system at the smallest τ where mean quality ≥ (frontier-only quality − 5%).
- **Cache false-hit rate** = cached responses judged incorrect for the new prompt / total hits, measured on a paraphrase+perturbation set (same question with changed entities/numbers must not hit).
- **Gateway overhead** = total_ms − upstream_ms, measured with a mock upstream with fixed latency.

## 4. Ablations (the headline experiments)

Run on `pdp-golden/test` and `pdp-synth-multihop`, same models and seeds.

| Variant | Description |
|---|---|
| `bm25_only` | BM25 → rerank → generate (no graph, no CRAG, no verification) |
| `dense_only` | Dense → rerank → generate |
| `hybrid_no_graph` | BM25 + dense + RRF → rerank → generate |
| `hybrid_graph` | + graph expansion |
| `hybrid_graph_crag` | + CRAG gate + abstention |
| `full` | + citation + entailment verification |
| `full_small_only` | `full` with all generation pinned to T1 (CPU-local small model — what confidential workloads get) |
| `full_open_weight` | `full` pinned to T2 |
| `full_frontier_only` | `full` with all generation pinned to T3 (upper-bound reference) |

Report table: rows = variants; columns = verdict acc, citation P/R, claim-support, path recall (multi-hop), coverage, AURC, p50/p95 latency, mean cost per query. Include bootstrap 95% CIs (1,000 resamples) for the main metrics and a paired significance test between adjacent variants.

## 5. LLM-as-judge calibration

- Judge model: T3 (frontier), temperature 0, fixed prompt versioned in `evals/harness/judges/`.
- Rubrics: claim support (supported / partially / unsupported), answer-point coverage (per point yes/no), router quality (1–5 against reference/rubric; pass = ≥ 4).
- Calibration set: 100 items labeled by a human for each rubric (stratified). Report Cohen's κ (target ≥ 0.6) and confusion matrix. If κ < 0.6: revise rubric/prompt, re-measure; never "tune until it agrees" on the test portion — use a separate 50-item calibration-dev split.
- Bias checks: position bias (swap order for pairwise judgments), length bias (correlation of score with output length), self-preference (judge model ≠ any generation model when possible; note when unavoidable).
- Judge outputs cached by content hash.

## 6. Performance & resilience tests

### 6.1 Load (Locust, `loadtest/`)

- **Gateway under load (mock profile):** concurrency sweep 1 → 256 against `mock-upstream` that replays **latency profiles recorded from the real tiers** (TTFT and inter-token distributions sampled from small real runs). This isolates gateway behavior and costs nothing.
- **Real tiers (small scale):** T1 CPU: concurrency 1, 2, 4 (slots are the limit; report where it saturates). T2/T3: concurrency 1, 4, 8 within provider rate limits and a spend cap.
- **[STRETCH] real engine at scale:** a vLLM sweep 1 → 64 in a time-boxed cloud-notebook GPU session, public prompts only, reported separately.
- Each step 3 min after 1 min warmup.
- Report per tier and for gateway (`auto`): TTFT and E2E p50/p95/p99, throughput (req/s, output tokens/s), error rate, fallback rate.
- Configs pinned: model IDs, quantization, llama.cpp args (threads, `--parallel` slots, context size, batch size), CPU model and RAM, provider names and price snapshot date, mock latency profile version. Stored with the report.

### 6.2 Gateway overhead

Mock upstream (fixed 50 ms TTFT, fixed token rate) → measure added latency at 1–256 concurrency. Target p99 overhead ≤ 15 ms [TARGET].

### 6.3 Chaos

During a 64-VU steady load on the `mock` profile (plus a short real-tier run at low concurrency): (a) kill T1 container; (b) inject 30% 5xx and 429s on T2 via a fault proxy; (c) add 2 s latency to T3; (d) Redis restart. For `confidential` traffic during (a), the expected result is queue/fail — never external fallback. Measure success rate, breaker open time, p99 during and after, recovery time. Report as a timeline chart.

### 6.4 Policy suite (hard gate)

Property-based tests (Hypothesis) over: data class × requested model × tier health permutations × budget state × cache state. Assertion: zero requests with `confidential`/`pii` reach any external tier (T2 or T3); zero `pii` cache reads/writes. Plus an integration test with a **canary**: fake T2 and T3 endpoints that fail the test if it ever receives a request marked sensitive (and a request-body scanner that fails if any canary PII string reaches it).

## 7. Eval harness design

- CLI: `uv run evals run --suite pdp-golden --split test --variants full,hybrid_no_graph --profile cpu-local`.
- Runner calls the public API (black-box) and optionally reads decision traces (white-box metrics like retrieval recall).
- Outputs: `evals/reports/<date>-<suite>-<short_sha>/report.md` + `results.jsonl` + `summary.json`, also written to Postgres `eval_runs`/`eval_results`.
- Report template sections: setup (versions, hardware), headline table, ablation table with CIs, risk–coverage plot, per-category breakdown, **top 10 failure cases with analysis**, cost summary.
- **Replay mode** for CI: LLM responses recorded per (prompt hash, model, params) in a cassette store; CI replays deterministically with no model or API. Cassette misses fail the CI job with a clear message ("re-record with `make eval-record`").

## 8. Gates

| Gate | Where | Rule |
|---|---|---|
| EV-01 | CI (every PR) | Unit + integration tests pass; replay smoke eval (30 items) — no regression > 3 pts on citation precision/verdict accuracy vs `main` baseline cassette |
| EV-02 | CI | Policy suite: 0 violations (blocking) |
| EV-03 | CI | Ingestion snapshot tests pass |
| EV-04 | Pre-release (manual, API budget) | Full `pdp-golden/test` + `synth-multihop` + adversarial + injection; report committed |
| EV-05 | Pre-release | Load + chaos report committed for gateway changes |
| EV-06 | Any prompt/model/threshold change | Dev-split eval delta attached to PR description |

## 9. Reporting in README

README shows: the ablation table, the risk–coverage curve, the cost–quality Pareto curve, latency vs concurrency chart, chaos timeline, policy-suite statement, links to full reports, and a "Known limitations" section sourced from failure analyses. Only measured numbers; each table links to its report folder.
