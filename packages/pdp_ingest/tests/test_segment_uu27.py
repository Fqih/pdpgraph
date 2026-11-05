# SPDX-License-Identifier: Apache-2.0
"""Segmentation snapshot on the real UU 27/2022 text (M1.2 DoD, FR-PDP-01).

Needs the verified raw files: `make ingest SOURCE=uu27-2022`, then `make test-snapshot`.

The ayat counts agree with the "(n)" markers in the salinan PDF text layer for every sampled
Pasal except 4 and 70, where OCR garbles the markers or the heading. The unit texts (overrides
applied) are pending the owner's check against the PDF page images
(`data/review/uu27-2022/crosscheck.md` §3).
"""

from collections import Counter
from pathlib import Path

import pytest

from pdp_ingest.pipeline import TextResult, run_text_stages
from pdp_ingest.registry import SourceEntry, load_source
from pdp_ingest.review import SNAPSHOT_UNITS, read_reviews, review_markdown

pytestmark = [pytest.mark.snapshot, pytest.mark.usefixtures("no_network")]

REPO = Path(__file__).resolve().parents[3]
AYAT_COUNTS = {2: 2, 4: 3, 22: 5, 26: 3, 48: 5, 51: 6, 57: 5, 64: 4, 70: 4, 71: 5}
TEXTS = {
    "p1/n1": (
        "Data Pribadi adalah data tentang orang perseorangan yang teridentifikasi atau "
        "dapat diidentifikasi secara tersendiri atau dikombinasi dengan informasi lainnya "
        "baik secara langsung maupun tidak langsung melalui sistem elektronik atau "
        "nonelektronik."
    ),
    "p53/a1/hb": (
        "kegiatan inti Pengendali Data Pribadi memiliki sifat, ruang lingkup, dan/atau "
        "tujuan yang memerlukan pemantauan secara teratur dan sistematis atas Data Pribadi "
        "dengan skala besar; dan"
    ),
    "p5": (
        "Subjek Data Pribadi berhak mendapatkan Informasi tentang kejelasan identitas, "
        "dasar kepentingan hukum, tujuan permintaan dan penggunaan Data Pribadi, dan "
        "akuntabilitas pihak yang meminta Data Pribadi."
    ),
    "p20/a2/hc": (
        "pemenuhan kewajiban hukum dari Pengendali Data Pribadi sesuai dengan ketentuan "
        "peraturan perundang-undangan;"
    ),
    "p26/a2": (
        "Pemrosesan Data Pribadi penyandang disabilitas sebagaimana dimaksud pada ayat (1) "
        "dilakukan melalui komunikasi dengan menggunakan cara tertentu sesuai dengan "
        "ketentuan peraturan perundang-undangan."
    ),
    "p46/a3": (
        "Dalam hal tertentu, Pengendali Data Pribadi wajib memberitahukan kepada masyarakat"
        " mengenai kegagalan Pelindungan Data Pribadi."
    ),
    "p57/a3": (
        "Sanksi administratif berupa denda administratif sebagaimana dimaksud pada ayat (2)"
        " huruf d paling tinggi 2 (dua) persen dari pendapatan tahunan atau penerimaan "
        "tahunan terhadap variabel pelanggaran."
    ),
    "p67/a1": (
        "Setiap Orang yang dengan sengaja dan melawan hukum memperoleh atau mengumpulkan "
        "Data Pribadi yang bukan miliknya dengan maksud untuk menguntungkan diri sendiri "
        "atau orang lain yang dapat mengakibatkan kerugian Subjek Data Pribadi sebagaimana "
        "dimaksud dalam Pasal 65 ayat (1) dipidana dengan pidana penjara paling lama 5 "
        "(lima) tahun dan/atau pidana denda paling banyak Rp5.000.000.000,00 (lima miliar "
        "rupiah)."
    ),
    "p76": ("Undang-Undang ini mulai berlaku pada tanggal diundangkan."),
    "p57/a3#pj": (
        'Yang dimaksud dengan "pendapatan" adalah arus masuk bruto dari manfaat ekonomi '
        "yang timbul dari aktivitas normal entitas selama periode jika arus masuk tersebut "
        "mengakibatkan kenaikan ekuitas yang tidak berasal dari kontribusi penanam modal."
    ),
}


@pytest.fixture(scope="module")
def entry() -> SourceEntry:
    return load_source("uu27-2022", REPO / "configs" / "sources")


@pytest.fixture(scope="module")
def result(entry: SourceEntry) -> TextResult:
    return run_text_stages(
        entry, raw_dir=REPO / "data" / "raw", overrides_dir=REPO / "data" / "overrides"
    )


def test_unit_counts(result: TextResult) -> None:
    kinds = Counter(u.kind for u in result.units)
    assert kinds == {"PASAL": 76, "AYAT": 122, "HURUF": 144, "ANGKA": 13, "PENJELASAN": 164}
    assert Counter(s.kind for s in result.segmented.structures) == {"BAB": 16, "BAGIAN": 6}
    pasal = [u.unit_id for u in result.units if u.kind == "PASAL"]
    assert pasal == [f"uu27-2022/p{n}" for n in range(1, 77)]


def test_ayat_counts_of_sampled_pasal(result: TextResult) -> None:
    ayat = Counter(u.parent_id for u in result.units if u.kind == "AYAT")
    assert {n: ayat[f"uu27-2022/p{n}"] for n in AYAT_COUNTS} == AYAT_COUNTS


def test_sampled_unit_texts(result: TextResult) -> None:
    assert tuple(TEXTS) == SNAPSHOT_UNITS["uu27-2022"]
    units = {u.unit_id: u.text for u in result.units}
    assert {k: units[f"uu27-2022/{k}"] for k in TEXTS} == TEXTS


def test_every_pasal_has_a_penjelasan(result: TextResult) -> None:
    explained = {u.parent_id for u in result.units if u.kind == "PENJELASAN"}
    for n in range(1, 77):
        pid = f"uu27-2022/p{n}"
        assert pid in explained or any(e and e.startswith(pid + "/") for e in explained), pid


def test_committed_review_list_is_current(entry: SourceEntry, result: TextResult) -> None:
    committed = REPO / "data" / "review" / "uu27-2022" / "crosscheck.md"
    text = committed.read_text(encoding="utf-8")
    assert text == review_markdown(entry, result, read_reviews(text))
