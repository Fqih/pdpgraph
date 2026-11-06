# progress.md — Living Work Log

Claude Code updates this file at the end of every session. Newest entry on top of the log.

## Current status

| Field | Value |
|---|---|
| Phase | 1 — PDPGraph MVP (week 1) |
| Current task | M1.5 follow-up (CI structure graph, test isolation, context_of relations); next: M1.6 |
| Last updated | 2026-11-06 |
| Release | none |

## Task board

| ID | Status | Notes |
|---|---|---|
| M0.1 | done (PR #1) | uv workspace, 8 packages, ruff/mypy/pytest, pre-commit, CI green |
| M0.2 | done (PR #5) | compose `core`: 4 stores, healthchecks, mem limits, loopback ports, non-root, digests pinned; CI integration job |
| M0.3 | done (PR #3) | config, logging + redaction, telemetry, ids, pii; 142 tests; `make cov` gate |
| M0.4 | done (PR #11) | models-aux fp32 CPU: `/embed`, `/rerank`, `/nli`, dynamic batching; pinned revisions in `configs/models_aux.yaml`; compose `local-llm`; offline runtime |
| M0.5 | done (PR #8) | `common/llm/`: async `LLMClient`, cassettes (replay/record/live), `UsageLimiter`, one span per call |
| M0.6 | done (PR #6) | Alembic `0001_initial` = 04 §6 SQL verbatim; `make migrate` idempotent; upgrade/downgrade/re-upgrade tested |
| M1.5 | done (PR #25) | `load_graph` (`pdp_ingest/graph_load.py`) + `pdp_core/graph` (constraints, canonical queries); 568 nodes, 1661 edges for UU 27/2022; counts equal artifacts |
| M1.4 link flags | done (PR #24) | `nested_in_informal` / `ambiguous_case` on defined links; term sample rebuilt with those quotas (unlabeled); DataCategory modeling + UNKNOWN rule documented |
| M1.4 | done (PR #23) | `defs` stage: 11 definitions (1 alias), 400 USES_TERM links, 15 informal, 15 DataCategory candidates (proposed); review list + 40-item link sample built, labels pending |
| M1.3 label protocol | done (PR #22) | label all 114 mentions (stratified 50 first), targeted + random negatives, overlapping slices, Wilson 95% intervals; set rebuilt (unlabeled) |
| M1.3 | done (PR #21) | `refs` stage: 114 mentions (103 REFERENCE, 11 DELEGATION), 146 internal targets, 0 unresolved; 70-item owner sample built, labels pending |
| M1.2 safeguards | done (PR #20) | `overrides_total`/`overrides_unconfirmed` on `sources` (migration 0002) and in eval reports (06 §7); v0.1 gate needs 0 unconfirmed; review lines in crosscheck.md survive regeneration |
| M1.2 | done (PR #19) | extract → segment → overrides → crosscheck stages; 519 units; 31 overrides (unconfirmed); 83 units flagged for owner review |
| M1.1 | done (PR #16) | source registry + `fetch` stage; Komdigi HTML primary (body hash verified), salinan PDF reference; Postgres `sources` row |
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
| 2026-11-05 | models-aux load time per model, fp32, warm OS page cache (cpu-local: Ryzen 7 PRO 4750U 8C/16T, torch 8 threads, 21 GB RAM, Fedora 43, Docker 29.9.1) | bge-m3 6.96 s, bge-reranker-v2-m3 3.61 s, mDeBERTa NLI 3.53 s | service log `model_loaded` after `make up-llm` |
| 2026-11-05 | `make up-llm` from stopped stack to all 5 services healthy (cpu-local: Ryzen 7 PRO 4750U 8C/16T, torch 8 threads, 21 GB RAM, Fedora 43, Docker 29.9.1) | 27.7 s | `time make up-llm` |
| 2026-11-05 | models-aux process RSS after load / after benchmark, all 3 models (cpu-local: Ryzen 7 PRO 4750U 8C/16T, torch 8 threads, 21 GB RAM, Fedora 43, Docker 29.9.1) | 4.67 GiB (2.31 GiB anon + 2.36 GiB file-backed mmap); high-water 4.73 GiB. `docker stats` shows only 2.23–2.34 GiB because it excludes file pages | `/proc/1/status` in container; `docker stats` |
| 2026-11-05 | models-aux latency, sequential, 30 runs after 3 warm-up, HTTP via compose; passages 51 tokens avg, query 13 (cpu-local: Ryzen 7 PRO 4750U 8C/16T, torch 8 threads, 21 GB RAM, Fedora 43, Docker 29.9.1) | `/embed` 1 query p50 328.8 / p95 392.8 ms; `/embed` 32 passages p50 5797.5 / p95 6570.3 ms; `/rerank` 1×30 p50 6993.3 / p95 7825.8 ms; `/nli` 8 pairs p50 1034.2 / p95 1425.5 ms | `scripts/bench_models_aux.py --runs 30` |
| 2026-11-05 | models-aux after bge-m3 safetensors re-pin (same hardware) | load 7.00 / 3.86 / 3.98 s; RSS 4.66 GiB (2.31 anon + 2.35 file); high-water 4.69 GiB | service log; `/proc/1/status` |
| 2026-11-05 | `make ingest SOURCE=uu27-2022` (fetch stage, live download of HTML 353,736 B + PDF 2,977,828 B, both verified, sources row upserted) | 2.7 s wall | `time make ingest SOURCE=uu27-2022` |
| 2026-11-05 | `make ingest SOURCE=uu27-2022`, local verified files, stages fetch..crosscheck + sources upsert | 1.63 s wall | `time make ingest SOURCE=uu27-2022` |
| 2026-11-05 | UU 27/2022 segmentation (M1.2) | 831 blocks; 16 BAB, 6 Bagian; units PASAL 76, AYAT 122, HURUF 144, ANGKA 13, PENJELASAN 164 (519) | `make ingest SOURCE=uu27-2022` |
| 2026-11-05 | PDF cross-check, overrides applied (M1.2) | 83 of 519 units flagged (coverage < 0.9 or a diff not attributed to OCR); diffs: pdf 123, unclear 65, html 1 (Pasal 33 huruf b: the PDF layer carries the next item marker "c") | `make ingest`, `data/processed/uu27-2022/crosscheck.jsonl` |
| 2026-11-05 | Branch coverage of new M1.2 modules (unit + snapshot tests) | crosscheck 100%, overrides 100%, segment 98%, pipeline 87%, pdp_eval law 100% | `pytest --cov` incl. `-m snapshot` |
| 2026-11-05 | UU 27/2022 reference mentions (M1.3) | 114 mentions: REFERENCE 103, DELEGATION 11 (PP 10, Perpres 1); EXACT 75, SELF 26, EXTERNAL_UNRESOLVED 13 (11 delegations + 2 UUD 1945), UNRESOLVED 0; 146 internal targets | `make ingest`, `data/processed/uu27-2022/refs.jsonl` |
| 2026-11-05 | Reference label set (M1.3, 06 §2.9, rebuilt in PR #22), seed 20261105 | 164 items: all 114 mentions (first batch 50: absolute 10/18, relative 20/58, list 8/12, range 3/3, sebagaimana 29/75, self 12/26, external 2/2, delegation 7/11, penjelasan 3/3), 40 targeted negatives of 63 candidates (ketentuan 32, peraturan 18, sebagaimana 5, undang-undang 3), 10 random negatives. Precision/recall: not yet measured (labels pending) | `python -m pdp_eval refs-sample` |
| 2026-11-05 | Core stores next to models-aux (same run) | neo4j 1.49 GiB, opensearch 1.38 GiB, postgres 20 MiB, valkey 7 MiB; host 8.3 GB available with desktop apps running | `docker stats`, `free -m` |
| 2026-11-05 | UU 27/2022 definitions and term uses (M1.4) | 11 definitions (Pemerintah Pusat has alias Pemerintah); defined uses: 400 unit-term links, 490 occurrences (Data Pribadi 208, Pengendali Data Pribadi 83, Subjek Data Pribadi 65, Pelindungan Data Pribadi 62); informal: 15 links, 21 occurrences; 15 DataCategory candidates (2 classes, 7 specific, 6 general) | `make ingest`, `data/processed/uu27-2022/term_uses.jsonl` |
| 2026-11-06 | Term-link flags (M1.4) | defined links with a nested occurrence: 1 of 400 (Data Pribadi in Pasal 1 angka 2); with a sentence-initial occurrence: 69 of 400 | `make ingest`, `term_uses.jsonl` |
| 2026-11-06 | Term-link label set (M1.4, 06 §2.10, rebuilt in PR #24), seed 20261105 | 40 items: 30 of 400 defined links (11 terms; 1 of 1 nested, 12 of 69 ambiguous_case), 10 of 15 informal (7 terms). Link precision: not yet measured (labels pending) | `python -m pdp_eval terms-sample` |
| 2026-11-06 | UU 27/2022 graph (M1.5) | 568 nodes (Source 1, Structure 22: BAB 16 + Bagian 6, LegalUnit 519, Definition 11, DataCategory 15) and 1661 edges (PART_OF 361, IN_SOURCE 567, EXPLAINED_BY 163, REFERENCES 146, DEFINES 11, USES_TERM 400, SUBCATEGORY_OF 13); graph counts equal artifact counts | `make load-graph SOURCE=uu27-2022` |
| 2026-11-06 | load_graph time (M1.5), Neo4j 5.26 community in compose, laptop Ryzen 7 PRO 4750U (16 threads), batch 500 | fresh load (source subgraph removed first, constraints existing): 0.58 s, 0.37 s, 0.80 s over 3 runs; first-ever load incl. constraint creation: 2.07 s; re-run on a loaded graph: 0.27 to 0.51 s | `python -m pdp_ingest.graph_load` |

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
- M0.5 `LLMClient` limits: (1) closed in PR #10: `confidential`/`pii` are refused unless the `base_url` host is in `local_base_urls` (default 127.0.0.1, ::1, localhost); the same check applies in replay (PR #12), so a misconfigured call path fails in tests; replaying `confidential` cassettes needs a loopback `base_url`. The M0.7 catalog and Tierline policy (M2) tighten this further; never relax it. (2) The token cap stops the *next* call, so the total can overshoot by the calls in flight. (3) `complete_json` sends `strict: true`; whether each upstream accepts pydantic-generated schemas is checked by the M0.7 probe. (4) The cassette writer applies the logging sanitizer, so a recorded body can differ from the live one if it contained secret-shaped text; PII and configured secrets are refused outright. (5) A replayed call reports the recorded latency.
- **M0.4 memory vs 03 §7 budget:** models-aux RSS is 4.67 GiB against the 2–3 GB line in 03 §7 (owner to decide; not changed). Stack now ≈ 7.6 GiB (stores ≈ 2.9 GiB + models-aux); llama.cpp T1 (M2.9, 2–4 GB) would bring it to ≈ 10–12 GiB. Options for later, each a measured change with an eval delta: int8/ONNX, or dropping the separate reranker. `mem_limit: 8g` is [TUNE].
- **Memory: revisit after M2.9 + rerank experiment.** BR-16 (16 GB) stays the target; 03 §7 now carries the measured models-aux RSS.
- **M1.10 rerank experiment (owner plan; not implemented):** on the dev split, measure retrieval recall@k, path recall, and stage latency p50/p95 on `cpu-local` over this matrix: candidates to rerank 10 / 15 / 30; passage `max_length` 256 / 384 / 512; scorer = bge-reranker-v2-m3 vs bge-m3 ColBERT multi-vector late-interaction (passage vectors precomputed at index time and cached; corpus is small) vs no rerank; optionally a smaller multilingual cross-encoder (check licence; reject non-commercial). Pick by recall first, latency second; record with an eval delta.
- **M0.4 latency:** `/rerank` 1×30 ≈ 7 s p50 and `/embed` 32 passages ≈ 5.8 s p50 on CPU; per-sub-question rerank cost dominates the online path (M1 planning). Ingest-time embedding of the corpus is a one-off batch.
- **M0.4 / SEC-13:** bge-m3 re-pinned (PR #13) from `5617a9f6` (pickle `pytorch_model.bin` only) to `7b44caba`, the last official BAAI commit on `main` that ships `model.safetensors` (a later commit deleted it, no reason given). Verified: 391 fp32 tensors bit-identical to the `.bin`, file SHA-256 `993b2248…e38e7e` equals the LFS oid, and config/tokenizer files are identical. All three models now load with `use_safetensors=True`; no conversion step was needed.
- **M0.4:** real-weights tests (`make test-models`, marker `models`) are not run in CI: they need the 4.9 GB weights. CI runs the 30 fake-model unit tests. Load times are with a warm page cache; a cold read is slower (not measured; would need dropping caches).
- **M4.4 (ADR-017):** implement `PUTUSAN_MK` ingestion, `MODIFIES_READING` expansion, `as_of` tests, minimal ruling-path grammar + ID round-trip tests, and the citable node for the operative quote. First case: Putusan MK 151/PUU-XXII/2024 → `uu27-2022/p53/a1/hb`, effective 2025-07-30 [owner confirms operative part from the official MK PDF before ingestion]. Add a golden-set temporal item for it.
- **M1.7:** second annotator still open (owner's answer had a placeholder). If none: v0 ships without κ, the datasheet says so, and GUIDELINE.md adds the test-retest protocol (20 random items re-labeled blind ≥ 7 days later; verdict agreement + Jaccard on gold units, reported as intra-annotator); the CLI gets a blind re-label mode.
- **M1.1 → M1.2:** the Komdigi HTML differs from the salinan in small ways seen so far: `PRESIDEN REPUBLIK INDONESIA,` appears twice after the preamble; the `Menimbang`/`Mengingat` labels are lowercase or absent (list structure only); the LN/TLN footer lines are not inside `div#produk-content`. The per-Pasal tab widget on the page lists Pasal 65–68, 71, 72 twice; it is outside the body and ignored. The M1.2 cross-check against the PDF covers all of this.
- **M1.1:** raw page bytes differ per fetch only by CSP nonces; `snapshot_sha256` names the archived page (`87a0cbbd…`). Reused local files keep the provenance record of the download that produced them.
- **M1.16:** reservation-based `UsageLimiter` for concurrent runs: reserve estimated prompt tokens + `max_tokens` before each call, reconcile with actual usage after.
- Cassette entries get `sanitized: true` when redaction changed any content.
- **M0.7:** `complete_json` sends `strict: true` only when the model's catalog capability flag says it is supported; no silent fallback.
- `vm.max_map_count` is 1048576 on the dev host (Fedora default), above OpenSearch's 262144, so no sysctl change was needed.
- Merges use the GitHub squash-merge button (owner decision); the recorded author/committer name is accepted as is. PR #3 was squash-merged locally (`8f03aa0`) and shows as closed.
- Commit `9df2b74` on `main` has author name `FaqihHakim` (GitHub squash merge used the profile display name). Accepted as is by the owner; no history rewrite. Later PRs are squashed to one commit locally and merged with `--rebase`, which keeps the author `Fqih` and still lands one commit per PR.

- M1.2 cross-check: Komdigi transcription errors are corrected in `data/overrides/uu27-2022.yaml` (31 entries, each with the PDF page; `confirmed_by` pending the owner). Three change meaning: "dan" for "dari" in Pasal 20(2)(c), 51(5) and the Penjelasan Umum; Pasal 26(2) lacks "peraturan". The rest are OCR-style typos (hadan, hares, hams, din, balk, anis, tidal(, dikumpullcan, seFuai, PaSal, Edvokasi), split words, and stray periods (Pasal 15(1), 67(1)). Penjelasan Pasal 46 "Ayat 2" (no parentheses) is handled by the segment grammar.
- **M1.2 cross-check limits:** the PDF text layer is OCR as well, so coverage is a screen, not a verdict; an error shared by both texts is not detected. "menggunakan" is often missing from the PDF layer (Pasal 13, 26, 39), so those diffs are `unclear`. Units under three words have no PDF page (no trigram). Ayat counts in the snapshot agree with the PDF "(n)" markers for 8 of 10 sampled Pasal; Pasal 4 and 70 are garbled in the PDF layer.
- **M1.2 → owner:** review `data/review/uu27-2022/crosscheck.md` in order: §1 the 4 meaning-changing overrides + Pasal 26(2), §2 the other 27 overrides (set `confirmed_by` in the overrides YAML), §3 the 10 snapshot units, §4 the 83 flagged units (edit the `Review:` line per unit). A Komdigi error found there becomes an override. `make ingest` regenerates the file and keeps the review lines; a malformed line fails the run; a snapshot test fails if the committed copy is stale.
- **M1.3 → owner:** label `evals/datasets/pdp-refs/v0/sample.jsonl` with `uv run python -m pdp_eval refs-label` (164 items: stratified 50 mentions, the other 64, 40 targeted and 10 random negatives), then `uv run python -m pdp_eval refs-report --out evals/reports/<date>-pdp-refs-<sha>/report.md`. Targeted negatives here use trigger tokens not covered by any mention (not only sentences with no mention at all, which would give 21 candidates and skip the known "ketentuan Undang-Undang" cases).
- **M1.4 → owner:**
  - Review `data/review/uu27-2022/definitions.md`: 11 definitions (term and text against the PDF; the page is shown) and 15 DataCategory codes (`confirmed` / `code_change` / `not_a_category`).
  - Label `evals/datasets/pdp-terms/v0/sample.jsonl` with `uv run python -m pdp_eval terms-label`, then run `terms-report --out evals/reports/<date>-pdp-terms-<sha>/report.md`.
- **M1.5 real-graph tests in CI:** resolved without committing text: CI loads the committed text-free `tests/fixtures/uu27-2022/structure.json` (04 §3.9). Exact-text tests stay `needs_corpus`. Committing the text itself still waits on the [VERIFY] redistribution question.
- **M1.5 `candidate_obligations`:** implemented and tested on hand-made Obligation nodes in the fixture. No Obligation nodes are loaded until the obligation-extraction task.
- **M1.4 nested quota:** the owner asked for at least 3 nested links in the sample; UU 27/2022 has only 1, which is included. More come with later sources.
- **M1.10/M1.11 Penjelasan glosses:** "Yang dimaksud dengan "x" adalah ..." glosses (37 occurrences in UU 27/2022) may serve as retrieval hints only (query expansion, reranker features). They are never cited as the law's definitions and never become `Definition` nodes.
- **M1.4 linker scope:**
  - Usage linking applies to Pasal 1 definitions only. The Penjelasan's "Yang dimaksud dengan "x" adalah ..." glosses (e.g. "data biometrik") are not `Definition` nodes; the category explanations carry them.
  - A sentence-initial capitalized word counts as defined use ("Informasi" at a sentence start), and the sample will show whether that matters.
  - Definition units do link to other terms they use (e.g. Pelindungan Data Pribadi uses Data Pribadi); only the self-link is skipped.
- **M1.3 resolver scope:** generic phrases that name no instrument ("ketentuan Undang-Undang", "peraturan perundang-undangan", "Undang-Undang tentang Pelindungan Data Pribadi" in the Penjelasan Umum) are not mentions; the negative sentences will show whether that costs recall. One false positive was found on the real text before release and fixed with a test: "diatur dalam Undang-Undang ini" (4×) is SELF, not a delegation. Grammar tuning on the labeled sample is allowed (dev); draw a fresh sample before a public claim.
- `pdp_eval` law view now reads the segmented units (overrides applied), so the labeling CLI shows pipeline ids. `#pj` ids are accepted only where a Penjelasan unit exists (before: any body unit + `#pj`).
- Amendment research (2026-11-05, `.context/research/2026-11-05-uu27-amendments.md`); decisions recorded (FR-PDP-20, ADR-019). The owner will confirm Lampiran I no. 137 and the guideline verdict illustrations separately:
  - UU 1/2026 Penyesuaian Pidana (effective 2026-01-02) adjusts the fines in Pasal 67(1)–(3) to kategori IV and Pasal 68 to kategori V. Recommended mapping: `SUPERSEDES`; consolidated versions need an ADR, and KUHP Pasal 79 is needed for the rupiah values.
  - KUHP Pasal 613(3) (added by UU 1/2026) puts administrative sanctions first; its Penjelasan names UU 27/2022. No relation in the 04 model fits.
  - MK 151/PUU-XXII/2024 confirmed: `MODIFIES_READING` on Pasal 53(1)(b) in M4.4.
  - PP 33/2026 is promulgated but takes effect 2027-01-16.
  - The 2025 challenge to Pasal 65(2)/67(2) (135/PUU-XXIII/2025) was rejected on 2026-01-19.
  - Perkara 236/PUU-XXIV/2026 (Pasal 58(5), 61) appears pending; unconfirmed.

## Watchlist (legal changes not yet in force or not decided)

| Item | Status (checked 2026-11-05) | Trigger for action |
|---|---|---|
| PP 33/2026, Peraturan Pelaksanaan UU 27/2022 (LN 2026/88) | Promulgated 2026-07-16; takes effect **2027-01-16** (Pasal 225). Salinan read from a regional mirror only; TLN unconfirmed | Before 2027-01-16: ingest as its own PP source (official central copy needed). Re-check golden items whose answer depends on PP-level detail, and any `as_of` on or after that date |
| Perkara 236/PUU-XXIV/2026 (Pasal 58(5), 61) | Appears pending; last hearing found 2026-08-11. Status unconfirmed (tracking.mkri.id 403) | When a putusan is pronounced: if granted or conditionally granted, add a `pending_changes.yaml` entry (binding_reading) and plan `MODIFIES_READING` (ADR-017). If rejected or inadmissible, remove from this list. Re-check before the labeling session |
| KUHP Pasal 613(3) interplay with UU PDP sanctions | Open modeling question (ADR-019) | An official interpretation (PP, MK ruling, or guidance from the lembaga) appears. Then decide on a relation and restore the deferred golden items |

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
| 2026-11-05 | Within-tier alternates deferred to ADR-018 in M2.2 (renumbered; ADR-017 = MK rulings) | FR-GW-02, FR-GW-09 |
| 2026-11-05 | Code Apache-2.0 (SPDX header per file); own datasets CC BY 4.0; statute text cited to official source | 09 §2, README |
| 2026-11-05 | Merge with the GitHub squash button; no local squash or force-push workflows | 09 §4 |
| 2026-11-05 | Labeled PII patterns added so `NIK3171…`-style glued values are caught | FR-GW-17 |
| 2026-11-05 | M0.7 probe hard caps: abort at 200 calls or 200,000 total tokens, whichever first | M0.7 |
| 2026-11-05 | models-aux: fp32, transformers only (no sentence-transformers), torch from the CPU index; weights in `~/.cache/pdpgraph/models` via `make models-download`; runtime `HF_HUB_OFFLINE=1` enforced at start + `local_files_only`; rerank score = sigmoid(logit); bge-m3 dense = CLS, L2-normalized; max_length 512 | M0.4 |
| 2026-11-05 | M1.1 primary text source: JDIH Komdigi HTML (registry verifies law-body SHA-256, see correction below; raw snapshot SHA-256 also pinned); authoritative cross-check reference: salinan PDF `ed952dea…` (identical on BPK, peraturan.go.id, Komdigi, Kemenkeu); raw files in git-ignored `data/raw/`; owner checks the M1.2 manual-review list and 10 snapshot units against PDF page images | M1.1, M1.2, SEC-14 |
| 2026-11-05 | **Correction (M1.1):** the body hash `aed0c358…` approved earlier covered only the Penjelasan (ad-hoc extraction started at the first literal `UNDANG-UNDANG REPUBLIK INDONESIA`, which first appears in the Penjelasan heading). Law body is now defined as the inner HTML of `div#produk-content` (title through Penjelasan Pasal 76): SHA-256 `36f26c294d2cd87a42499ab1456ac5424470b764c5bc296548b52fe286a90162`, stable across 5 fetches. Pending owner confirmation | M1.1, SEC-14 |
| 2026-11-05 | MK rulings: `PUTUSAN_MK` source + `MODIFIES_READING` edge; no new text version | ADR-017, 04 §3.5 |
| 2026-11-05 | Golden schema gains optional `proposed_by ∈ {claude, faqih, synthetic}`; `schema_version` stays 1 (unpublished); lands with the M1.7 schema model and 06 §2.1 update | M1.7 |
| 2026-11-05 | `LLMClient` fails closed: `confidential`/`pii` only to hosts in `local_base_urls`, in every mode incl. replay; never relax | ADR-013, ADR-015 |
| 2026-11-05 | `LLMClient` is async (httpx), `LLM_*` settings, mode defaults to `replay`; cassette key = SHA-256 of canonical request incl. attempt; secrets checked before PII; `make eval-record` stub until M1.16 | M0.5, NFR-06, NFR-12 |
| 2026-11-05 | M1.1 body hash is over a canonical form, not raw inner HTML: `extraction_method: html-element-blocks`, `canonicalization_version: 1` (text blocks, NFC, whitespace collapsed, `[ol]`/`[li]` structure kept; `pdp_ingest/canonical.py`), stored in the registry and `fetch.jsonl`. New UU 27/2022 body hash `0d6f94b59455ace74f3f95e5df2ae6196e83392a4a7438dd6d9f2f7a0e079a40` (replaces `36f26c29…`), pending owner confirmation | M1.1, SEC-14 |
| 2026-11-05 | Registry-driven content invariants checked on every fetch before the hash: title block start, ends "Pasal 76 / Cukup jelas.", BAB I..XVI and Pasal 1..76 in the batang tubuh, Pasal 1..76 in the Penjelasan, Pasal 4 ayat (3) huruf c = "kewarganegaraan;", "Cukup jelas" = 126. **Correction:** 252 (stated earlier) was the whole-page count; the page carries the law twice (body plus tab widget); the body has 126. Salinan PDF cross-check: 16 BAB and all 76 Pasal headings present (OCR garbles 7, e.g. "Pasa722", "Pasal2T"); OCR finds 112 exact / 123 fuzzy "Cukup jelas", consistent with 126 | M1.1, SEC-14 |
| 2026-11-05 | Second annotator: none. v0 reports intra-annotator test-retest agreement only; the datasheet says inter-annotator κ is pending a second annotator in v1 | M1.7 |
| 2026-11-05 | Golden tooling lives in a new workspace package `pdp_eval` (schema model, labeling CLI, test-retest log); 03 §8 updated | M1.7 |
| 2026-11-05 | Golden v0: questions on the 2022 text of Pasal 53(1)(b), 67, 68 and 70(3) are pinned to `as_of = 2025-07-29` and noted "re-label with as_of=today after M4.4". Interplay questions (Pasal 57 with 67–70 via KUHP 613(3); 70(3) with KUHP 121) and the post-ruling Pasal 53 temporal item go to `v0/deferred.jsonl`. New Pasal 74 before/after temporal pair (g-0061/g-0075) | M1.7 |
| 2026-11-05 | Currency guard FR-PDP-20: `configs/pending_changes.yaml` (UU 1/2026 Lampiran I no. 137; Putusan MK 151/2024; `confirmed_by` pending the owner). Aggregate step in 03 §5.2; implemented in M1.14 with tests and 4 adversarial items | FR-PDP-20 |
| 2026-11-05 | M1.2 stage artifacts: `extract.jsonl`, `segment.jsonl` (before overrides), `units.jsonl` (overrides applied; input of later stages), `crosscheck.jsonl`. The owner's review list is committed at `data/review/<source_id>/crosscheck.md` (03 §8 tree updated). Overrides are exact single-occurrence text replacements; a stale entry fails the run | M1.2, FR-PDP-01 |
| 2026-11-05 | M1.2 safeguards (owner): unconfirmed overrides stay applied, but the `sources` row (new columns, migration 0002, 04 §6) and every eval report record `overrides_total`/`overrides_unconfirmed`; 08 v0.1 exit gate requires `overrides_unconfirmed = 0`. Overrides gain `changes_meaning` (4 set). `crosscheck.md` follows the owner's review order (meaning-changing overrides + Pasal 26(2), other 27 overrides, 10 snapshot units, 83 flagged units worst-first); each snapshot/flagged unit has a `Review: reviewed_by: <name> \| verdict: komdigi_ok\|override_needed\|ocr_noise` line that regeneration keeps | M1.2 |
| 2026-11-05 | M1.3 (owner): one mention per reference chain with char span, raw text, resolution and explicit range expansion; delegation phrases are mention kind DELEGATION with no graph edge yet; "Undang-Undang ini" is SELF; external instruments EXTERNAL_UNRESOLVED with the instrument kept; Penjelasan refs resolve relative to the explained unit (04 §3.7). Resolver evaluated on an owner-labeled 50+20 sample at target level, recall ≥ 95% / precision ≥ 98% [TARGET] (06 §2.9) | M1.3, FR-PDP-03 |
| 2026-11-06 | M1.5 (owner): load from stage artifacts only, idempotent MERGE in batched transactions; version-1 validity from `effective_from`; edges per 04 §3.2 with REFERENCES span and USES_TERM flags; Source provenance; consistency test; canonical queries on fixture and real graph. DataCategory nodes keyed by `source_id` + `code` so sources and test fixtures never share a category node | M1.5, FR-PDP-06 |
| 2026-11-06 | M1.5 follow-up (owner): CI runs real-graph ID/structure tests on a committed text-free structure artifact, text tests local-only (`needs_corpus`), drift checked by a snapshot test; integration tests use a separate wiped Neo4j test instance, never the dev graph (DataCategory key unchanged, not an isolation mechanism); `context_of` labels Penjelasan relations | M1.5, FR-PDP-06 |
| 2026-11-06 | M1.4 interpretation (owner):
- definition units link other terms (no self-link);
- a defined match inside an informal one is kept and flagged `nested_in_informal`;
- sentence-initial matches are flagged `ambiguous_case`;
- both are sampled (≥ 3, ≥ 5 where available) and reported as slices, with no rule change until labeled;
- Penjelasan glosses are not Definitions;
- DataCategory: `SPESIFIK`/`UMUM` parents with `SUBCATEGORY_OF`; unmappable categories give `UNKNOWN` (03 §5.3) | M1.4, FR-PDP-04 |
| 2026-11-05 | M1.4 (owner): definitions with aliases and node ids via `assign_slugs`; longest-first usage linking, own capitalization = `USES_TERM`, lowercase = `informal` (low confidence, no edge), no self-link, count + spans per unit; terms list exported for M1.6; DataCategory vocabulary derived from Pasal 4, codes `proposed` until confirmed (replaces the [VERIFY] list in 04 §3.1); link precision on an owner-labeled 30 + 10 sample with Wilson intervals (06 §2.10) | M1.4, FR-PDP-04 |
| 2026-11-05 | M1.3 label protocol (owner): label all mentions (stratified 50 first, then the other 64); per-pattern metrics as overlapping slices, headline over unique items, Wilson 95% intervals for every rate; targeted negatives (uncovered trigger tokens, ≤ 40 stratified by trigger) plus 10 random negatives replace the 20 random ones | M1.3, 06 §2.9 |
| 2026-11-05 | pypdf (pure Python, BSD) added to `pdp-ingest` for the PDF text layer; no OCR engine | M1.2 |
| 2026-11-05 | ADR-019: amendments are separate sources linked by `AMENDS`; consolidated text is `derived: true`, for retrieval only, never cited alone; KUHP 613(3) left as an open question. Implementation M4.4 | ADR-019 |

## Session log

### 2026-11-06 — M1.5 follow-up: CI structure graph, test isolation, context_of relations
- `pdp_ingest/graph_structure.py`: text-free export/import; `graph_load --export-structure` / `--from-structure`; `text_sha256` on LegalUnit and Definition.
- `tests/fixtures/uu27-2022/structure.json` (519 units, 1661 edges, no text) committed; snapshot test re-ingests and fails on drift (checked by mutating one count).
- `tests/integration/test_graph_uu27.py` runs in CI on the text-less graph (ids, counts, queries); `test_graph_uu27_corpus.py` holds the text checks (`needs_corpus`).
- `neo4j-test` compose service (profile `test`, `127.0.0.1:7688`, tmpfs), `make up-test`, CI step; `graph_driver` session fixture refuses port 7687 and wipes the test instance per session.
- `context_of` labels Penjelasan `own_explanation` / `ancestor_explanation` / `descendant_explanation`; `definitions_for` orders by definition id and `term` may be null.

### 2026-11-06 — M1.4 link flags (PR #24) + M1.5 load_graph
- PR #24: `nested_in_informal` / `ambiguous_case` flags, term sample rebuilt with quotas, DataCategory modeling and the UNKNOWN rule documented.
- M1.5:
  - `pdp_core/graph` (`constraints.cypher` = 04 §3.3, `queries.cypher` + `queries.py` for the 04 §3.4 queries, `Neo4jSettings`);
  - `pdp_ingest/graph_load.py` (artifacts to rows, batched MERGE load, count check);
  - new artifacts `source.json` and `structures.jsonl`;
  - stage `VERSION` constants;
  - `make load-graph`;
  - neo4j Python driver added to `pdp_core`.
- Tests: 9 unit tests (rows from artifacts), 2 spec-sync tests, 9 fixture-graph integration tests (exact query results, re-run identical, UNKNOWN categories), 8 real-graph integration tests (counts, Pasal 57(1), Pasal 14, definitions for Pasal 40(1), context of Pasal 20(2), version_at, re-run identical).

### 2026-11-05 — M1.3 label protocol (PR #22) + M1.4 definitions
- PR #22: label all 114 reference mentions, targeted + random negatives, overlapping slices, Wilson intervals (06 §2.9).
- M1.4: `pdp_ingest/defs.py` (definitions, linker, data categories), `defs_review.py` (`data/review/uu27-2022/definitions.md`), artifacts `defs.jsonl`, `term_uses.jsonl`, `terms.json`, `data_categories.jsonl`; `pdp_eval/termsample.py` + `terms_cli.py` (`terms-sample`, `terms-label`, `terms-report`); sample at `evals/datasets/pdp-terms/v0/sample.jsonl` (unlabeled).
- Tests: 10 synthetic `defs` tests, 3 review-list tests, 5 snapshot tests on the real text (terms, counts, longest match, categories, committed list current), sample/score/CLI tests.

### 2026-11-05 — M1.2 review safeguards (PR #20) + M1.3 references
- PR #20: `overrides_total`/`overrides_unconfirmed` on `sources` (migration 0002), eval-report rule (06 §7), v0.1 gate line (08); `crosscheck.md` in the owner's review order with per-unit `Review:` lines kept across regeneration.
- M1.3: `pdp_ingest/refs.py` (grammar + resolver), `refs_review.py` (`data/review/uu27-2022/refs.md`), `refs.jsonl` artifact; `pdp_eval/refsample.py` + `refs_cli.py` (`refs-sample`, `refs-label`, `refs-report`); sample committed at `evals/datasets/pdp-refs/v0/sample.jsonl` (unlabeled).
- Tests: 13 grammar tests (synthetic), 7 snapshot tests on the real text (hand-checked targets for Pasal 14, 17(2), 48(5), 50(1), 57(1), 57(3)), sample/score/CLI tests.

### 2026-11-05 — M1.2 extract + segment + PDF cross-check
- `pdp_ingest`: `segment.py` (state machine: BAB/Bagian/Paragraf, Pasal, ayat/huruf/angka from list nesting by drafting convention, Penjelasan mapping to `#pj`), `overrides.py`, `crosscheck.py` (trigram coverage + aligned word diffs + PDF page), `pipeline.py` (stage artifacts + review list); CLI runs fetch → extract → segment → overrides → crosscheck → sources row.
- `data/overrides/uu27-2022.yaml` (31 entries) and `data/review/uu27-2022/crosscheck.md` committed.
- Snapshot tests: 76 Pasal (p1..p76 in order), all unit-kind counts, ayat counts for 10 Pasal, exact text of 10 units (pending the owner's PDF check), every Pasal has a Penjelasan, committed review list is current.
- `pdp_eval/law.py` refactored onto segment output.

### 2026-11-05 — M1.7 golden guideline + labeling CLI, amendment research
- PR #16 (M1.1) merged after the owner confirmed body hash `0d6f94b5…` and "Cukup jelas" = 126.
- M1.7: `packages/pdp_eval` (`golden.py` schema, `law.py` Pasal view with suggested unit ids, `retest.py`, `cli.py`), `evals/datasets/pdp-golden/{GUIDELINE,DATASHEET}.md`, `v0/dev.jsonl` with 72 unlabeled candidates (`proposed_by: claude`, gold fields empty). 54 unit tests; 10 snapshot tests check the suggested ids against the real text.
- Candidate pool: multi-hop 31.9%, unanswerable 11.1%, English 12.5%, temporal 5.6%. Eight items carry FLAG notes for affected provisions.
- Amendment research done (report under `.context/research/`). Owner decision pending.

### 2026-11-05 — Phase 1 kickoff, M1.1
- PR #12 (local-endpoint check in replay), #13 (bge-m3 safetensors re-pin), #14 (03 §7 memory), #15 (ADR-017 MK rulings, docs) merged.
- M1.1: `pdp_ingest` `registry.py`, `fetch.py`, `db.py`, `__main__.py`; `configs/sources/uu27-2022.yaml`; `make ingest`; integration DB fixture moved to `tests/integration/conftest.py`. Tests first: 22 unit (respx + socket guard) + 2 integration.
- M1.1 follow-up: canonicalization v1 + content invariants (`canonical.py`); `make test-snapshot` runs the checks on the real snapshot (2 passed). Unit tests 318 passed; `pdp_ingest` coverage 87%.

### 2026-11-05 — M0.4 models-aux, plus M0.5 follow-ups
- PR #9: spec-drift message now starts "04 §6 changed: write a new migration revision"; follow-ups logged. PR #10: `LLMClient` local-only guard for `confidential`/`pii`.
- M0.4: `models_aux` (`settings`, `batching`, `models`, `app`, `download`, `__main__`), `configs/models_aux.yaml`, `deploy/docker/models-aux.Dockerfile`, compose `local-llm`, `make models-download` / `test-models` / `up-llm`, `scripts/bench_models_aux.py`. Shared `no_network` fixture moved to the repo-root `conftest.py`.
- Tests first: 30 unit tests on fake models (RED on import, then GREEN); 4 real-weights tests offline with the socket guard pass.

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
