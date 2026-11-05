# SPDX-License-Identifier: Apache-2.0
"""Deterministic PII patterns shared by the LLMClient cassette guard and the Tierline scanner.

FR-GW-17, SEC-16. All values are synthetic.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from common import pii
from common.pii import PiiKind

POSITIVES: list[tuple[str, PiiKind]] = [
    ("NIK saya 3171012345678901 ya", PiiKind.NIK),
    ("nik:3171012345678901.", PiiKind.NIK),
    ("hubungi 081234567890", PiiKind.PHONE),
    ("hubungi 0812-3456-7890", PiiKind.PHONE),
    ("hubungi 0812 3456 789", PiiKind.PHONE),
    ("call +6281234567890 now", PiiKind.PHONE),
    ("call +62 812-3456-7890", PiiKind.PHONE),
    ("wa 6281234567890", PiiKind.PHONE),
    ("email budi.santoso+test@contoh.co.id", PiiKind.EMAIL),
    ("NPWP 01.234.567.8-901.234", PiiKind.NPWP),
    ("npwp 012345678901234", PiiKind.NPWP),
    ("kartu 4111 1111 1111 1111", PiiKind.CARD),
    ("kartu 4111-1111-1111-1111", PiiKind.CARD),
    ("amex 378282246310005", PiiKind.CARD),
]

NEAR_MISSES = [
    "Pasal 20 ayat (2) huruf b UU 27/2022",
    "uu27-2022/p20/a2/hb@1",
    "tanggal 2024-06-01 pukul 08:30",
    "versi 1.2.3, kode 12345",
    "nomor 123456789012345678901234",  # 24 digits: not a NIK/NPWP/card shape
    "angka 31710123456781",  # 14 digits, Luhn-invalid
    "angka 31710123456789012",  # 17 digits, Luhn-invalid
    "telepon 0812345",  # too short for a mobile number
    "telepon 021-5551234",  # landline, not +62/08 mobile
    "kartu 4111 1111 1111 1112",  # grouped digits failing Luhn
    "user@localhost",  # no TLD
    "Rp 1.500.000,00",
    # Digit runs inside identifiers are not PII (regression: CI run 41962135000).
    "trace a817ff3c188e7f68a376158472152526",
    "sha256 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "sha 0e3171012345678901ab and x4111111111111111y",
    "uuid 123e4567-e89b-12d3-a456-426614174000",
]


@pytest.mark.parametrize(("text", "kind"), POSITIVES)
def test_fr_gw_17_detects_synthetic_pii(text: str, kind: PiiKind) -> None:
    kinds = {m.kind for m in pii.find_pii(text)}
    assert kind in kinds
    assert pii.contains_pii(text)


@pytest.mark.parametrize("text", NEAR_MISSES)
def test_sec_16_near_misses_are_not_pii(text: str) -> None:
    assert pii.find_pii(text) == []
    assert not pii.contains_pii(text)


def test_sec_16_match_never_carries_matched_text() -> None:
    (match,) = pii.find_pii("NIK 3171012345678901")
    assert "3171012345678901" not in repr(match)
    assert match.start == 4
    assert match.end == 20


def test_fr_gw_17_redact_replaces_every_match_with_its_kind() -> None:
    text = "NIK 3171012345678901, hp 081234567890, email a.b@contoh.id"
    assert pii.redact_pii(text) == "NIK [REDACTED:NIK], hp [REDACTED:PHONE], email [REDACTED:EMAIL]"


def test_fr_gw_17_overlapping_matches_redact_once() -> None:
    # A Luhn-valid 16-digit number is both NIK-shaped and card-shaped.
    assert pii.redact_pii("x 4111111111111111 y") == "x [REDACTED:NIK] y"


def test_luhn() -> None:
    assert pii.luhn_valid("4111111111111111")
    assert not pii.luhn_valid("4111111111111112")


synthetic_pii = st.one_of(
    st.from_regex(r"[1-9][0-9]{15}", fullmatch=True),
    st.from_regex(r"(\+62|62|0)8[1-9][0-9]{8,9}", fullmatch=True),
    st.from_regex(r"[a-z]{1,8}@[a-z]{1,8}\.(id|com|co\.id)", fullmatch=True),
)
filler = st.text(st.sampled_from("abc xyz .,;()-/\n"), max_size=12)


@given(st.lists(st.tuples(filler, synthetic_pii), min_size=1, max_size=4), filler)
def test_fr_gw_17_redaction_leaves_no_detectable_pii(
    parts: list[tuple[str, str]], tail: str
) -> None:
    # Values are space-separated: two digit runs glued together form a different number.
    text = "".join(f"{f} {p} " for f, p in parts) + tail
    assert pii.contains_pii(text)
    redacted = pii.redact_pii(text)
    assert pii.find_pii(redacted) == []
    assert pii.redact_pii(redacted) == redacted


@given(st.from_regex(r"[0-9a-f]{32}|[0-9a-f]{64}", fullmatch=True))
def test_sec_16_hex_identifiers_are_never_pii(hex_id: str) -> None:
    # Trace IDs and hashes appear in logs and prompts; they must not escalate or be redacted.
    assert pii.find_pii(f"id {hex_id} end") == []
