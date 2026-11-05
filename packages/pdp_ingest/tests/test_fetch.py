# SPDX-License-Identifier: Apache-2.0
"""`fetch` stage: download, verify against the registry, store raw + provenance (M1.1, SEC-14)."""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from pdp_ingest.canonical import canonical_sha256
from pdp_ingest.fetch import SourceIntegrityError, fetch_source, load_verified
from pdp_ingest.registry import SourceEntry

pytestmark = pytest.mark.usefixtures("no_network")

PRIMARY_URL = "https://jdih.example.go.id/uu27"
MIRRORS = ["https://bpk.example.go.id/uu27.pdf", "https://pergo.example.go.id/uu27.pdf"]
BODY = (
    "<p>UNDANG-UNDANG</p><p>BAB I</p><p>Pasal 1</p><ol><li>Data Pribadi adalah ...</li></ol>"
    "<p>PENJELASAN</p><p>Pasal 1</p><p>Cukup jelas.</p>"
)
INVARIANTS = {
    "starts_with": ["UNDANG-UNDANG"],
    "ends_with": ["Pasal 1", "Cukup jelas."],
    "explanation_marker": "PENJELASAN",
    "pasal_headings": 1,
    "bab_headings": 1,
    "cukup_jelas": 1,
    "items": [{"pasal": 1, "path": [1], "text": "Data Pribadi adalah ..."}],
}


def _page(nonce: str) -> str:
    return (
        f'<html><head><style nonce="{nonce}"></style></head><body>'
        f'<div id="produk-content">{BODY}</div></body></html>'
    )


PDF = b"%PDF-1.3 synthetic salinan"


def _sha(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def _entry(snapshot: str | None = None) -> SourceEntry:
    return SourceEntry.model_validate(
        {
            "source_id": "uu27-2022",
            "title": "UU 27/2022",
            "instrument_type": "UU",
            "number": 27,
            "year": 2022,
            "enacted_on": "2022-10-17",
            "promulgated_on": "2022-10-17",
            "effective_from": "2022-10-17",
            "primary": {
                "url": PRIMARY_URL,
                "format": "html",
                "body_element_id": "produk-content",
                "extraction_method": "html-element-blocks",
                "canonicalization_version": 1,
                "body_sha256": canonical_sha256(BODY),
                "invariants": INVARIANTS,
                "snapshot_sha256": snapshot or _sha(_page("n0")),
            },
            "reference": {"format": "pdf", "sha256": _sha(PDF), "urls": MIRRORS},
        }
    )


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


def test_fetch_stores_verified_raw_files_and_provenance(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    mock.get(PRIMARY_URL).mock(return_value=httpx.Response(200, text=_page("n1")))
    mock.get(MIRRORS[0]).mock(return_value=httpx.Response(200, content=PDF))
    records = fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "proc")

    primary, reference = records
    raw_html = tmp_path / "raw" / "uu27-2022" / f"{_sha(_page('n1'))}.html"
    raw_pdf = tmp_path / "raw" / "uu27-2022" / f"{_sha(PDF)}.pdf"
    assert raw_html.read_text(encoding="utf-8") == _page("n1")
    assert raw_pdf.read_bytes() == PDF
    assert primary["role"] == "primary"
    assert primary["url"] == PRIMARY_URL
    assert primary["raw_sha256"] == _sha(_page("n1"))
    assert primary["body_sha256"] == canonical_sha256(BODY)
    assert primary["extraction_method"] == "html-element-blocks"
    assert primary["canonicalization_version"] == 1
    assert primary["invariants"]["pasal_headings_body"] == 1
    assert primary["pinned_snapshot"] is False  # nonce differs from the pinned snapshot
    assert primary["fetched_at"].endswith("+00:00")
    assert reference["role"] == "reference"
    assert reference["url"] == MIRRORS[0]
    assert reference["raw_sha256"] == _sha(PDF)
    lines = (tmp_path / "proc" / "uu27-2022" / "fetch.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in lines] == records


def test_body_hash_mismatch_refuses_and_writes_nothing(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    changed = _page("n1").replace("<p>BAB I</p>", "<p>BAB I</p><p>KETENTUAN BARU</p>")
    mock.get(PRIMARY_URL).mock(return_value=httpx.Response(200, text=changed))
    with pytest.raises(SourceIntegrityError, match=r"law body .* does not match the registry"):
        fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "proc")
    assert not (tmp_path / "raw").exists()
    assert not (tmp_path / "proc").exists()


def test_invariant_violation_refuses_and_writes_nothing(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    changed = _page("n1").replace("<p>BAB I</p>", "")
    mock.get(PRIMARY_URL).mock(return_value=httpx.Response(200, text=changed))
    with pytest.raises(SourceIntegrityError, match=r"content invariant failed: BAB headings"):
        fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "proc")
    assert not (tmp_path / "raw").exists()


def test_markup_only_upstream_change_still_verifies(tmp_path: Path, mock: respx.MockRouter) -> None:
    restyled = _page("n1").replace("<p>", '<p style="margin:0px;">').replace("</p>", "</p>\n")
    mock.get(PRIMARY_URL).mock(return_value=httpx.Response(200, text=restyled))
    mock.get(MIRRORS[0]).mock(return_value=httpx.Response(200, content=PDF))
    primary, _ = fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "p")
    assert primary["body_sha256"] == canonical_sha256(BODY)


def test_reference_falls_back_to_next_mirror(tmp_path: Path, mock: respx.MockRouter) -> None:
    mock.get(PRIMARY_URL).mock(return_value=httpx.Response(200, text=_page("n1")))
    mock.get(MIRRORS[0]).mock(side_effect=httpx.ConnectError("down"))
    mock.get(MIRRORS[1]).mock(return_value=httpx.Response(200, content=PDF))
    _, reference = fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "p")
    assert reference["url"] == MIRRORS[1]


def test_reference_hash_mismatch_on_every_mirror_refuses(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    mock.get(PRIMARY_URL).mock(return_value=httpx.Response(200, text=_page("n1")))
    for url in MIRRORS:
        mock.get(url).mock(return_value=httpx.Response(200, content=b"%PDF tampered"))
    with pytest.raises(SourceIntegrityError, match="reference: no mirror served"):
        fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "p")
    assert not list((tmp_path / "raw").rglob("*.pdf"))


def test_http_error_status_is_an_error(tmp_path: Path, mock: respx.MockRouter) -> None:
    mock.get(PRIMARY_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "p")


def test_verified_local_files_are_reused_without_network(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    raw = tmp_path / "raw" / "uu27-2022"
    raw.mkdir(parents=True)
    (raw / f"{_sha(_page('n0'))}.html").write_text(_page("n0"), encoding="utf-8")
    (raw / f"{_sha(PDF)}.pdf").write_bytes(PDF)
    primary, reference = fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path)
    assert mock.calls.call_count == 0
    assert primary["pinned_snapshot"] is True
    assert primary["url"] is None  # local, not re-fetched
    assert reference["url"] is None


def test_load_verified_detects_tampering(tmp_path: Path, mock: respx.MockRouter) -> None:
    mock.get(PRIMARY_URL).mock(return_value=httpx.Response(200, text=_page("n1")))
    mock.get(MIRRORS[0]).mock(return_value=httpx.Response(200, content=PDF))
    entry = _entry()
    fetch_source(entry, raw_dir=tmp_path / "raw", processed_dir=tmp_path / "p")
    html_path, pdf_path = load_verified(entry, tmp_path / "raw")
    assert html_path.suffix == ".html"
    assert pdf_path.suffix == ".pdf"
    html_path.write_text(_page("n1").replace("Pasal 1", "Pasal 9"), encoding="utf-8")
    with pytest.raises(SourceIntegrityError):
        load_verified(entry, tmp_path / "raw")


def test_load_verified_without_files_says_how_to_fetch(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="make ingest SOURCE=uu27-2022"):
        load_verified(_entry(), tmp_path)


def test_rerun_keeps_original_download_provenance(tmp_path: Path, mock: respx.MockRouter) -> None:
    mock.get(PRIMARY_URL).mock(return_value=httpx.Response(200, text=_page("n1")))
    mock.get(MIRRORS[0]).mock(return_value=httpx.Response(200, content=PDF))
    first = fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "p")
    calls = mock.calls.call_count
    second = fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "p")
    assert mock.calls.call_count == calls  # no network on re-run
    assert second == first  # url, fetched_at, headers of the original download survive


def test_rerun_takes_verification_fields_from_the_current_run(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    mock.get(PRIMARY_URL).mock(return_value=httpx.Response(200, text=_page("n1")))
    mock.get(MIRRORS[0]).mock(return_value=httpx.Response(200, content=PDF))
    first, _ = fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "p")
    log = tmp_path / "p" / "uu27-2022" / "fetch.jsonl"
    stale = [
        {k: v for k, v in json.loads(line).items() if k != "extraction_method"}
        | {"body_sha256": "0" * 64}
        for line in log.read_text().splitlines()
    ]
    log.write_text("".join(json.dumps(r) + "\n" for r in stale))
    second, _ = fetch_source(_entry(), raw_dir=tmp_path / "raw", processed_dir=tmp_path / "p")
    assert second["fetched_at"] == first["fetched_at"]
    assert second["body_sha256"] == canonical_sha256(BODY)
    assert second["extraction_method"] == "html-element-blocks"
