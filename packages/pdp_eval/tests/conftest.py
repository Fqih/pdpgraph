# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures: a small synthetic law in the Komdigi page shape."""

import pytest

from pdp_eval.law import LawText
from pdp_ingest.canonical import blocks
from pdp_ingest.segment import Unit, segment

HTML = (
    "<p>UNDANG-UNDANG</p><p>BAB I</p><p>KETENTUAN UMUM</p>"
    "<p>Pasal 1</p><p>Dalam Undang-Undang ini yang dimaksud dengan:</p>"
    "<ol><li><p>Data Pribadi adalah data.</p></li><li><p>Subjek adalah orang.</p></li></ol>"
    "<p>Pasal 2</p><ol><li><p>Berlaku untuk:</p><ol><li><p>di dalam;</p></li>"
    "<li><p>di luar, yang berakibat:</p><ol><li><p>di wilayah;</p></li></ol></li></ol></li>"
    "<li><p>Tidak berlaku untuk rumah tangga.</p></li></ol>"
    "<p>Bagian Kesatu</p><p>Umum</p>"
    "<p>Pasal 3</p><p>Asas:</p><ol><li><p>pelindungan;</p></li><li><p>kepastian.</p></li></ol>"
    "<p>Agar setiap orang mengetahuinya, memerintahkan pengundangan.</p>"
    "<p>PENJELASAN</p><p>I. UMUM</p><p>Latar belakang.</p><p>II. PASAL DEMI PASAL</p>"
    "<p>Pasal 1</p><p>Cukup jelas.</p><p>Pasal 2</p><p>Ayat (1)</p><p>Huruf b</p>"
    "<p>Akibat hukum.</p><p>Pasal 3</p><p>Cukup jelas.</p>"
)


# A small law with every reference kind, for the reference sample tests (M1.3).
REFS_HTML = (
    "<p>BAB I</p><p>UMUM</p>"
    "<p>Pasal 1</p><p>Pengendali wajib menjaga data dengan cara yang aman dan patut. "
    "Hal ini berlaku menurut Undang-Undang ini.</p>"
    "<p>Pasal 2</p><ol><li><p>Prosesor wajib membantu Pengendali sebagaimana dimaksud dalam "
    "Pasal 1.</p></li><li><p>Ketentuan sebagaimana dimaksud pada ayat (1) diatur dalam Peraturan "
    "Pemerintah.</p></li></ol>"
    "<p>Pasal 3</p><p>Pelanggaran Pasal 1 sampai dengan Pasal 2 dikenai sanksi administratif yang "
    "ditetapkan oleh lembaga yang berwenang.</p>"
    "<p>PENJELASAN</p><p>I UMUM</p><p>Penjelasan umum ini menguraikan latar belakang dan tujuan "
    "pengaturan secara lengkap.</p><p>II PASAL DEMI PASAL</p>"
    "<p>Pasal 1</p><p>Cukup jelas.</p><p>Pasal 2</p><p>Cukup jelas.</p><p>Pasal 3</p>"
    "<p>Cukup jelas.</p>"
)


@pytest.fixture
def ref_units() -> list[Unit]:
    return segment("s", blocks(REFS_HTML), explanation_marker="PENJELASAN").units


@pytest.fixture
def law() -> LawText:
    return LawText(
        "uu27-2022", segment("uu27-2022", blocks(HTML), explanation_marker="PENJELASAN").units
    )
