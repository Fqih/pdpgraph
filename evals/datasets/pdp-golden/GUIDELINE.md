# pdp-golden annotation guideline (v0)

Status: draft for the owner's review (M1.7). This guideline governs `pdp-golden` labels; the schema
is 06-eval-plan §2.1 and `packages/pdp_eval/src/pdp_eval/golden.py`.

## 1. Roles

- **Gold labels come from the annotator only** (`annotator: faqih`). Gold labels are
  `gold_verdict`, `gold_unit_ids`, `acceptable_unit_ids`, and `gold_answer_points`.
  Claude builds the pipeline being evaluated, so Claude never writes gold labels. Claude may
  propose questions (`proposed_by: claude`) and tooling.
- v0 has **one annotator**. There is no second annotator, so v0 reports intra-annotator
  test-retest agreement (§7), not inter-annotator κ.
- Labels describe what UU 27/2022 says. They are not legal advice.

## 2. Gold units

- A gold unit is the **minimal set of legal units needed to justify the answer**. Use the
  deepest unit that contains the needed text: huruf before ayat, ayat before Pasal.
- Unit ids follow 04 §2.1 and are version-free. Examples: `uu27-2022/p46/a1`,
  `uu27-2022/p4/a3/hc`, `uu27-2022/p1/n4`.
- `:show N` in the CLI prints Pasal N with the id of every line in brackets. Copy ids from there.
  The CLI rejects ids that do not exist in the source.
- Allowed: Pasal, ayat, huruf, and angka units; a Penjelasan unit (`…#pj`); and
  `uu27-2022/pj-umum`.
- Not used in v0: BAB, Bagian, definition, or obligation ids.
- **Penjelasan:** add a `#pj` unit as gold only when the answer depends on the elucidation,
  for example the meaning of "kegagalan Pelindungan Data Pribadi" (Penjelasan Pasal 46). Never
  cite a Penjelasan that only says "Cukup jelas".
- **Cross-references:** if a unit says "sebagaimana dimaksud dalam Pasal X" and the answer needs
  the content of Pasal X, the referenced unit is gold too. This is what makes an item multi-hop.

### 2.1 When the parent Pasal is acceptable

`acceptable_unit_ids` lists units that a correct citation may use instead of the gold units.
Add the parent Pasal (or ayat) when:

- the question concerns the Pasal as a whole, for example "what does Pasal 16 cover"; or
- the answer needs most of the parent's children, so citing the parent is not misleading.

Do not add a parent when the answer turns on one specific huruf. Illustration: whether data
unrelated to a pending case must be destroyed turns on Pasal 44 ayat (1) huruf c only.

## 3. Verdicts (04 §5.1)

Pick the verdict for the actor and situation in the question, as of `as_of`. The examples below
illustrate the definitions only. They use provisions that no candidate item asks about, they are
not labels for any item, and the owner should confirm them.

| Verdict | Use when | Illustration |
|---|---|---|
| `OBLIGATION_APPLIES` | The law imposes a duty ("wajib") on the actor in the situation asked about | "Must a controller tell the data subject it deleted their data?" (Pasal 45) |
| `PROHIBITED` | The conduct is forbidden ("dilarang"), including conduct that carries a criminal penalty | "May I create fake personal data for profit?" (Pasal 66) |
| `PERMITTED` | The conduct is allowed ("dapat", "berhak") and no duty compels it | "May the public take part in supporting data protection?" (Pasal 63) |
| `NOT_APPLICABLE` | The law or the provision does not reach the situation: a scope exclusion, an exemption that removes the duty, or an `as_of` before the provision was in force | "Must the controller notify a deletion when an exemption for national defence applies?" (Pasal 45 with Pasal 50) |
| `INFORMATIONAL` | A definitional or descriptive question with no normative verdict | "What are the tasks of the lembaga?" (Pasal 59) |
| `INSUFFICIENT_EVIDENCE` | The corpus does not answer the question (§4) | "Does UU PDP regulate cookie banners?" |

If two verdicts seem to fit, prefer the more specific one. Explain the choice in the note.

## 4. Unanswerable items

- Category `unanswerable` means UU 27/2022 does not answer the question. Either the law is
  silent, or it delegates the matter to a Peraturan Pemerintah/Presiden that is not in the corpus.
- Label these `INSUFFICIENT_EVIDENCE`; the schema enforces this.
- `gold_unit_ids` may be empty. If a provision explicitly delegates the matter (for example "…
  diatur dalam Peraturan Pemerintah"), put it in `acceptable_unit_ids`.
- Answer points state what the law does not provide, for example "UU PDP tidak menetapkan
  masa retensi maksimum".
- If you find that the law does answer an `unanswerable` candidate, `drop` it, or note it and
  leave it for re-categorisation. Do not force the label.

## 5. Answer points and hops

- Write 1–5 atomic points, each verifiable from the gold units alone. Write them in the language
  of the question. Do not give advice, and do not add facts that are not in the cited text.
- `hops` is the number of distinct Pasal needed; a Penjelasan counts with its own Pasal. The CLI
  asks for hops and keeps the proposed value if you press Enter. `multi_hop` items need
  `hops >= 2`.

## 6. `as_of` and provisions flagged as possibly affected

- Default `as_of` is the labeling date. Gold labels describe the law in force on `as_of`.
- Later instruments amend, adjust, or reinterpret some provisions of UU 27/2022, and the corpus
  does not contain them yet. Follow the v0 rule in the table below. Candidate items touching
  these provisions carry a `FLAG …` note and already have the pinned `as_of`.
- For a new question you write on one of these provisions, apply the same rule yourself (the CLI
  asks for `as_of`).

<!-- FLAGGED-PROVISIONS:START -->
Source: amendment research of 2026-11-05 (`.context/research/2026-11-05-uu27-amendments.md`).
Owner decision of 2026-11-05. These changes are listed in `configs/pending_changes.yaml`
(FR-PDP-20) until they are modeled in M4.4 (ADR-017, ADR-019).

| Provision | Change | v0 rule |
|---|---|---|
| Pasal 53 ayat (1) huruf b | Putusan MK 151/PUU-XXII/2024 (2025-07-30): "dan" is read as "dan/atau" | Keep, with `as_of = 2025-07-29` (2022 text) and the note "re-label with as_of=today after M4.4" |
| Pasal 67 ayat (1)–(3), Pasal 68 | UU 1/2026 Lampiran I no. 137 (2026-01-02): fines become kategori IV (Pasal 67) and V (Pasal 68) | Keep, with `as_of = 2025-07-29` and the same note |
| Pasal 70 ayat (3) | The corporate cap multiplies the adjusted maximum | 2022-text questions: keep, with `as_of = 2025-07-29` and the same note. Questions on the interplay with KUHP Pasal 121: deferred |
| Pasal 57 with Pasal 67–70 | KUHP Pasal 613 ayat (3) (added by UU 1/2026) puts administrative sanctions first | Deferred (open legal question; ADR-019) |
| Pasal 58 ayat (5), Pasal 61 | Perkara 236/PUU-XXIV/2026 appears pending | Avoid |
| Provisions implemented by PP 33/2026 (Pasal 10(2), 12(2), 13(3), 16(3), 34(3), 48(5), 54(3), 56(5), 57(5), 61) | PP 33/2026 takes effect 2027-01-16, so it is not in force today | No PP-level detail; no `as_of` on or after 2027-01-16 |

- **Pinned items:** after M4.4, each one gets a twin with `as_of` = the re-labeling date. That
  turns it into a real before/after temporal pair.
- **Deferred items** live in `v0/deferred.jsonl` with the reason in `notes`. They are not part of
  v0 and are not labeled.
- Questions on Pasal 57 alone, without the criminal provisions, are not flagged.
<!-- FLAGGED-PROVISIONS:END -->

## 7. Test-retest protocol (single annotator)

1. Label the items (first pass). The CLI logs each label with a timestamp in
   `v0/annotation-log.jsonl`.
2. At least **7 days** later, run `relabel`. It draws **20 items at random** from labeled
   items whose latest first-pass label is ≥ 7 days old. It prints and logs the sample seed.
3. **Blind mode:** the CLI shows only the question, the metadata, and the law text (`:show`).
   It never shows the earlier verdict, units, answer points, or notes. You record a verdict and
   gold units.
4. Run `agreement`. It reports **verdict agreement (%)** and **mean Jaccard on gold units**,
   labeled "intra-annotator test-retest". The numbers go into the datasheet as reported. They
   are not inter-annotator κ.
5. Disagreements are not edited automatically. Review them afterwards. If a first-pass label was
   wrong, fix it with `label --item`, and say so in the datasheet.

## 8. Workflow

```bash
uv run python -m pdp_eval show 46                # Pasal 46 with unit ids + Penjelasan
uv run python -m pdp_eval label                  # label unlabeled items in order
uv run python -m pdp_eval label --item g-0012    # revisit one item (shows its labels)
uv run python -m pdp_eval validate               # schema + unit existence + composition
uv run python -m pdp_eval relabel                # blind re-label (>= 7 days later)
uv run python -m pdp_eval agreement              # intra-annotator agreement
```

The CLI needs the verified source snapshot (`make ingest SOURCE=uu27-2022`).

- **Verdict prompt:** Enter skips the item; `drop` removes it after confirmation.
- **Any prompt:** `:show N`, `:umum`, and `:quit` work everywhere.
- **v0 selection:** there are 72 proposed candidates in `dev.jsonl` (3 more are deferred). Keep about 50 by dropping the rest, and
  keep the 06 §2.1 composition targets in view: ≥ 25% multi-hop, ≥ 10% unanswerable, ≥ 10%
  English, ≥ 5% temporal. `validate` prints these percentages.
