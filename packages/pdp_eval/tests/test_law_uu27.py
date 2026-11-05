# SPDX-License-Identifier: Apache-2.0
"""Law view on the real UU 27/2022 snapshot: unit ids land on the right text (M1.7, M1.2).

Needs `make ingest SOURCE=uu27-2022`; run with `make test-snapshot`.
"""

from pathlib import Path

import pytest

from pdp_eval.law import LawText

pytestmark = [pytest.mark.snapshot, pytest.mark.usefixtures("no_network")]

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def law() -> LawText:
    return LawText.from_source(
        "uu27-2022",
        REPO / "configs" / "sources",
        REPO / "data" / "raw",
        REPO / "data" / "overrides",
    )


@pytest.mark.parametrize(
    ("unit_id", "starts"),
    [
        ("uu27-2022/p1/n1", "Data Pribadi adalah data tentang orang perseorangan"),
        ("uu27-2022/p1/n11", "Pemerintah Pusat"),
        ("uu27-2022/p2/a1/hb/n2", "bagi Subjek Data Pribadi warga negara Indonesia"),
        ("uu27-2022/p4/a3/hc", "kewarganegaraan;"),
        ("uu27-2022/p20/a2/ha", "persetujuan yang sah secara eksplisit"),
        ("uu27-2022/p46/a1/hb", "lembaga."),
        ("uu27-2022/p57/a3", "Sanksi administratif berupa denda administratif"),
        ("uu27-2022/p60/ho", "meminta bantuan hukum kepada kejaksaan"),
        ("uu27-2022/p70/a4/hh", "pembubaran Korporasi."),
    ],
)
def test_suggested_unit_ids(law: LawText, unit_id: str, starts: str) -> None:
    n = int(unit_id.split("/")[1].removeprefix("p"))
    texts = {line.unit_id: line.text for line in law.pasal(n)}
    assert texts[unit_id].startswith(starts)


def test_every_pasal_has_a_view_and_explanation(law: LawText) -> None:
    for n in range(1, 77):
        assert law.pasal(n)[0].unit_id == f"uu27-2022/p{n}"
        assert law.explanation(n), f"Penjelasan Pasal {n} empty"
