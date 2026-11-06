# Known-item queries: uu27-2022 (M1.6)

Proposed by Claude for the M1.6 smoke check (`pdp_eval.known_items`). Each query has one
expected unit. Only items with `verdict: confirmed` count in the known-item test; the queries
are never used for tuning.

Verdicts: `confirmed`, `wrong_expected` (put the right unit in the `Expected:` line, then set
`confirmed`), `drop`. Edit only the `Expected:` and `Review:` lines.

Mix: 2 exact references, 2 term queries, 3 Indonesian paraphrases, 3 English paraphrases.

## 1. Queries

### `ki01` exact reference

Query: Pasal 46 ayat (1)
Expected: `uu27-2022/p46/a1`

Why: the label of the unit itself (breach notification within 3 x 24 hours).

Review: reviewed_by: - | verdict: -

### `ki02` exact reference

Query: Pasal 4 ayat (2)
Expected: `uu27-2022/p4/a2`

Why: the label of the unit itself (lead-in of the specific data categories).

Review: reviewed_by: - | verdict: -

### `ki03` term

Query: definisi Prosesor Data Pribadi
Expected: `uu27-2022/p1/n5`

Why: the definition item of the term in Pasal 1.

Review: reviewed_by: - | verdict: -

### `ki04` term

Query: dasar pemrosesan Data Pribadi
Expected: `uu27-2022/p20/a1`

Why: "Pengendali Data Pribadi wajib memiliki dasar pemrosesan Data Pribadi."

Review: reviewed_by: - | verdict: -

### `ki05` Indonesian paraphrase

Query: kewajiban memberi tahu kebocoran data dalam 3 x 24 jam
Expected: `uu27-2022/p46/a1`

Why: notification duty after a failure of personal data protection.

Review: reviewed_by: - | verdict: -

### `ki06` Indonesian paraphrase

Query: hak subjek data untuk menghapus dan memusnahkan data pribadinya
Expected: `uu27-2022/p8`

Why: right to end processing, erase and/or destroy (Pasal 8 has no ayat).

Review: reviewed_by: - | verdict: -

### `ki07` Indonesian paraphrase

Query: hak menarik kembali persetujuan pemrosesan
Expected: `uu27-2022/p9`

Why: right to withdraw consent (Pasal 9 has no ayat).

Review: reviewed_by: - | verdict: -

### `ki08` English paraphrase

Query: right to data portability in a commonly used machine-readable format
Expected: `uu27-2022/p13/a1`

Why: right to obtain and use one's data in a common, machine-readable format.

Review: reviewed_by: - | verdict: -

### `ki09` English paraphrase

Query: when must a controller appoint a data protection officer
Expected: `uu27-2022/p53/a1`

Why: duty to appoint an officer for personal data protection, and the cases.

Review: reviewed_by: - | verdict: -

### `ki10` English paraphrase

Query: transferring personal data to a controller outside Indonesia
Expected: `uu27-2022/p56/a1`

Why: transfer of personal data outside Indonesian jurisdiction.

Review: reviewed_by: - | verdict: -
