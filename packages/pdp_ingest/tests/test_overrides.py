# SPDX-License-Identifier: Apache-2.0
"""Overrides apply exact, single-occurrence fixes and fail on stale entries (M1.2)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pdp_ingest.overrides import (
    Override,
    OverrideError,
    apply_overrides,
    counts,
    load_overrides,
)
from pdp_ingest.segment import Unit

UNITS = [
    Unit("s/p1", "PASAL", "Pasal 1", "Data hadan publik.", "s/bab1", 0),
    Unit("s/p2", "PASAL", "Pasal 2", "Tidak berubah.", "s/bab1", 1),
]


def _o(unit_id: str = "s/p1", find: str = "hadan", rep: str = "badan") -> Override:
    return Override(unit_id=unit_id, find=find, replace=rep, reason="typo", pdf_page=2)


def test_apply_replaces_and_keeps_other_units() -> None:
    out = apply_overrides(UNITS, [_o()])
    assert out[0].text == "Data badan publik."
    assert out[1] is UNITS[1]
    assert UNITS[0].text == "Data hadan publik."  # input not mutated


def test_overrides_on_one_unit_apply_in_order() -> None:
    out = apply_overrides(UNITS, [_o(), _o(find="badan publik", rep="badan publik dan organisasi")])
    assert out[0].text == "Data badan publik dan organisasi."


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (_o(unit_id="s/p9"), "missing unit"),
        (_o(find="absent"), "occurs 0 times"),
        (_o(find="a"), "occurs 4 times"),
    ],
)
def test_stale_or_ambiguous_overrides_fail(override: Override, message: str) -> None:
    with pytest.raises(OverrideError, match=message):
        apply_overrides(UNITS, [override])


def test_load(tmp_path: Path) -> None:
    assert load_overrides(tmp_path / "none.yaml") == []
    path = tmp_path / "s.yaml"
    path.write_text(
        "- {unit_id: s/p1, find: hadan, replace: badan, reason: typo, pdf_page: 2,"
        " confirmed_by: null}\n- {unit_id: s/p2, find: x, replace: y, reason: r, pdf_page: 3,"
        " confirmed_by: faqih, changes_meaning: true}\n",
        encoding="utf-8",
    )
    got = load_overrides(path)
    assert got[0] == _o()
    assert not got[0].changes_meaning
    assert got[1].changes_meaning
    assert counts(got) == (2, 1)
    assert counts([]) == (0, 0)


def test_schema_rejects_unknown_fields_and_bad_page(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text("- {unit_id: a, find: b, replace: c, reason: d, pdf_page: 0}\n", "utf-8")
    with pytest.raises(ValidationError):
        load_overrides(path)
    path.write_text("- {unit_id: a, find: b, replace: c, reason: d, pdf_page: 1, x: 1}\n", "utf-8")
    with pytest.raises(ValidationError):
        load_overrides(path)
