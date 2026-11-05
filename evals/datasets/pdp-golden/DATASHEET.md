# pdp-golden datasheet (v0, draft)

Status: draft (M1.7). The candidate questions exist; labeling has not started. Every number
marked `[TARGET]` is a goal, not a result.

## Motivation

`pdp-golden` is a hand-labeled question set for evaluating PDPGraph answers on UU 27/2022
(Pelindungan Data Pribadi). It covers retrieval of the right legal units, the verdict, and the
answer content (06-eval-plan §2.1, §3).

## Composition

- **Size:** v0 `dev` split, about 50 items `[TARGET]`, selected by the annotator from 72
  candidates in `v0/dev.jsonl`. v1 target is 150 items, split 40% dev / 60% test.
- **Categories:** definition, obligation, exception, sanction, procedure, scope, multi_hop,
  temporal, unanswerable.
- **Composition targets** (06 §2.1) `[TARGET]`: ≥ 25% multi-hop, ≥ 10% unanswerable,
  ≥ 10% English, ≥ 5% temporal. `uv run python -m pdp_eval validate` reports the actual figures.
- **Candidate pool as proposed:** 72 items. Multi-hop 31.9%, unanswerable 11.1%, English 12.5%,
  temporal 5.6% (output of `validate` on the unlabeled pool, not on the final set).
- **Legal corpus:** UU 27/2022 only. The text is the JDIH Komdigi page, canonical body SHA-256
  `0d6f94b59455ace74f3f95e5df2ae6196e83392a4a7438dd6d9f2f7a0e079a40`. It is cross-checked against
  the salinan PDF (`configs/sources/uu27-2022.yaml`).
- **Personal data:** none. Questions are generic or use fictional roles; no real individuals.

## Collection and labeling

- **Questions:** proposed by Claude (`proposed_by: claude`). The annotator selects, drops, or
  rewrites them; rewritten or new items use `proposed_by: faqih`.
- **Gold labels:** written by one annotator (`annotator: faqih`) with the labeling CLI
  (`packages/pdp_eval`), following `GUIDELINE.md`. Claude writes no gold labels, because Claude
  builds the system under evaluation.
- **`as_of`:** the labeling date, unless an item pins an earlier date (GUIDELINE §6).

## Agreement

- **Inter-annotator κ: pending a second annotator in v1.** v0 has a single annotator, so no
  Cohen's κ is reported.
- **v0 reports intra-annotator test-retest agreement only:** 20 random items are re-labeled blind
  at least 7 days after the first pass. Reported as verdict agreement % and mean Jaccard on gold
  units (GUIDELINE §7).
- Results: not yet measured.

## Known limitations

- **Single annotator:** labels carry one person's reading, and test-retest measures consistency,
  not correctness.
- **Amendments:** the corpus holds only the 2022 text. Since then, UU 1/2026 has adjusted the
  Pasal 67–68 fines, and Putusan MK 151/PUU-XXII/2024 has set a binding reading of Pasal 53(1)
  huruf b. Until those are ingested, items on flagged provisions are skipped or pinned to an
  earlier `as_of` (GUIDELINE §6).
- **Temporal items** on the Constitutional Court reading of Pasal 53 need ADR-017 ingestion
  (M4.4) before they can be evaluated.
- **Unit ids** shown by the CLI are inferred from the source page's list nesting until
  segmentation (M1.3) provides the authoritative units.

## License

CC BY 4.0 (`evals/datasets/LICENSE`). The legal text quoted in answer points is public law.
