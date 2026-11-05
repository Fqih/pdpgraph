# SPDX-License-Identifier: Apache-2.0
"""Committed list of unresolved, external, delegation and self mentions (M1.3)."""

from pdp_ingest.refs import Mention
from pdp_ingest.refs_review import refs_markdown
from pdp_ingest.segment import Unit

UNITS = [
    Unit("s/p1", "PASAL", "Pasal 1", "Lihat Pasal 9 dan Pasal 2.", None, 0),
    Unit("s/p2", "PASAL", "Pasal 2", "Hal itu diatur dalam Peraturan Pemerintah.", None, 1),
    Unit("s/p3", "PASAL", "Pasal 3", "Sesuai KUHP | Undang-Undang ini.", None, 2),
]
MENTIONS = [
    Mention(
        "s/p1",
        6,
        25,
        "Pasal 9 dan Pasal 2",
        "REFERENCE",
        "UNRESOLVED",
        ("s/p2",),
        None,
        ("absolute", "list"),
        ("Pasal 9",),
    ),
    Mention(
        "s/p2",
        8,
        41,
        "diatur dalam Peraturan Pemerintah",
        "DELEGATION",
        "EXTERNAL_UNRESOLVED",
        (),
        "Peraturan Pemerintah",
        ("delegation",),
    ),
    Mention("s/p3", 7, 11, "KUHP", "REFERENCE", "EXTERNAL_UNRESOLVED", (), "KUHP", ("external",)),
    Mention("s/p3", 14, 31, "Undang-Undang ini", "REFERENCE", "SELF", (), None, ("self",)),
]


def test_sections_counts_and_rows() -> None:
    md = refs_markdown("s", MENTIONS, UNITS)
    heads = [line for line in md.splitlines() if line.startswith("## ")]
    assert heads == [
        "## 1. Unresolved internal references",
        "## 2. External references",
        "## 3. Delegations",
        "## 4. Self references",
    ]
    assert "Mentions: 4 (REFERENCE 3, DELEGATION 1). Internal targets: 1." in md
    assert "Resolution: EXACT 0, UNRESOLVED 1, SELF 1, EXTERNAL_UNRESOLVED 2." in md
    assert "| `s/p1` | Pasal 9 dan Pasal 2 | Pasal 9 | Lihat **Pasal 9 dan Pasal 2**. |" in md
    assert (
        "| `s/p2` | Peraturan Pemerintah | Hal itu **diatur dalam Peraturan Pemerintah**. |" in md
    )
    assert "| `s/p3` | KUHP | Sesuai **KUHP** \\| Undang-Undang ini. |" in md


def test_empty_sections_say_none() -> None:
    md = refs_markdown("s", [], UNITS)
    assert md.count("None.") == 4
