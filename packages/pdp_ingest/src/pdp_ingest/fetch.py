# SPDX-License-Identifier: Apache-2.0
"""`fetch` stage (03 §5.1, M1.1): download the primary text and the reference document, verify
both against the registry, store them under `data/raw/<source_id>/<sha256>.<ext>`, and write a
provenance record per file to `data/processed/<source_id>/fetch.jsonl`.

Nothing is written unless every file verifies (SEC-14). Verified local files are reused, so a
re-run with the files present needs no network. Later stages read files via `load_verified`.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx

from pdp_ingest.canonical import (
    CANONICALIZATION_VERSION,
    EXTRACTION_METHOD,
    InvariantError,
    blocks,
    canonical_sha256,
    check_invariants,
)
from pdp_ingest.registry import SourceEntry

MAX_BYTES = 50 * 1024 * 1024
USER_AGENT = f"pdpgraph-ingest/{version('pdp-ingest')} (+https://github.com/Fqih/pdpgraph)"


class SourceIntegrityError(Exception):
    """A source file does not match its registry hash, or cannot be parsed for verification."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def element_inner_html(page: str, element_id: str) -> str:
    """Exact inner HTML of the element with `id="<element_id>"` (same-tag nesting counted)."""
    start = re.search(rf'<(\w+)\b[^>]*\bid="{re.escape(element_id)}"[^>]*>', page)
    if start is None:
        raise SourceIntegrityError(f"no element with id {element_id!r}")
    tag = start.group(1)
    depth = 1
    for m in re.finditer(rf"<(/?){tag}\b[^>]*>", page[start.end() :], flags=re.IGNORECASE):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return page[start.end() : start.end() + m.start()]
    raise SourceIntegrityError(f"element {element_id!r} is not closed")


def verify_body(page_bytes: bytes, entry: SourceEntry, label: str) -> dict[str, Any]:
    """Check the content invariants, then the canonical body hash; return the record fields."""
    body = element_inner_html(page_bytes.decode("utf-8"), entry.primary.body_element_id)
    try:
        report = check_invariants(blocks(body), entry.primary.invariants)
    except InvariantError as exc:
        raise SourceIntegrityError(f"{label}: content invariant failed: {exc}") from exc
    digest = canonical_sha256(body)
    if digest != entry.primary.body_sha256:
        raise SourceIntegrityError(
            f"{label}: law body sha256 {digest[:12]} does not match the registry "
            f"({entry.primary.body_sha256[:12]}); review the upstream change and re-pin"
        )
    return {
        "body_sha256": digest,
        "extraction_method": EXTRACTION_METHOD,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "invariants": report,
    }


def _get(client: httpx.Client, url: str) -> tuple[bytes, httpx.Response]:
    with client.stream("GET", url) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise SourceIntegrityError(f"{url} exceeds {MAX_BYTES} bytes")
            chunks.append(chunk)
        return b"".join(chunks), response


def _record(
    role: str, data: bytes, response: httpx.Response | None, **extra: Any
) -> dict[str, Any]:
    return {
        "role": role,
        "url": str(response.url) if response is not None else None,
        "fetched_at": datetime.now(UTC).isoformat() if response is not None else None,
        "http_status": response.status_code if response is not None else None,
        "content_type": response.headers.get("content-type") if response is not None else None,
        "etag": response.headers.get("etag") if response is not None else None,
        "last_modified": response.headers.get("last-modified") if response is not None else None,
        "bytes": len(data),
        "raw_sha256": sha256(data),
        **extra,
        "fetcher": USER_AGENT.split(" ")[0],
    }


def _verified_html(path: Path, entry: SourceEntry) -> tuple[bytes, dict[str, Any]]:
    data = path.read_bytes()
    if sha256(data) != path.stem:
        raise SourceIntegrityError(f"{path.name}: content does not match its file name hash")
    return data, verify_body(data, entry, path.name)


def _local_html(raw: Path, entry: SourceEntry) -> tuple[Path, bytes, dict[str, Any]] | None:
    pinned = raw / f"{entry.primary.snapshot_sha256}.html"
    candidates = sorted(raw.glob("*.html"), key=lambda p: p != pinned)  # pinned first
    for path in candidates:
        return path, *_verified_html(path, entry)  # any present file must verify (no skipping)
    return None


def _local_pdf(raw: Path, entry: SourceEntry) -> bytes | None:
    path = raw / f"{entry.reference.sha256}.pdf"
    if not path.is_file():
        return None
    data = path.read_bytes()
    if sha256(data) != entry.reference.sha256:
        raise SourceIntegrityError(f"{path.name}: reference PDF does not match the registry")
    return data


def _primary(client: httpx.Client, raw: Path, entry: SourceEntry) -> tuple[bytes, dict[str, Any]]:
    local = _local_html(raw, entry)
    if local is not None:
        path, data, verified = local
        pinned = path.stem == entry.primary.snapshot_sha256
        return data, _record("primary", data, None, **verified) | {"pinned_snapshot": pinned}
    data, response = _get(client, str(entry.primary.url))
    record = _record("primary", data, response, **verify_body(data, entry, entry.source_id))
    return data, record | {"pinned_snapshot": sha256(data) == entry.primary.snapshot_sha256}


def _reference(client: httpx.Client, raw: Path, entry: SourceEntry) -> tuple[bytes, dict[str, Any]]:
    local = _local_pdf(raw, entry)
    if local is not None:
        return local, _record("reference", local, None)
    failures = []
    for url in entry.reference.urls:
        try:
            data, response = _get(client, str(url))
        except (httpx.HTTPError, SourceIntegrityError) as exc:
            failures.append(f"{url}: {type(exc).__name__}")
            continue
        if sha256(data) == entry.reference.sha256:
            return data, _record("reference", data, response)
        failures.append(f"{url}: sha256 mismatch")
    raise SourceIntegrityError(
        f"{entry.source_id} reference: no mirror served the registered file ({'; '.join(failures)})"
    )


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


_DOWNLOAD_FIELDS = ("url", "fetched_at", "http_status", "content_type", "etag", "last_modified")


def _carry_forward(records: list[dict[str, Any]], log_path: Path) -> list[dict[str, Any]]:
    """A reused local file keeps the provenance of the download that produced it; verification
    fields always come from the current run."""
    if not log_path.is_file():
        return records
    prior = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        prior[(rec["role"], rec["raw_sha256"])] = rec
    out = []
    for rec in records:
        earlier = prior.get((rec["role"], rec["raw_sha256"]))
        if rec["url"] is None and earlier is not None:
            rec = rec | {k: earlier.get(k) for k in _DOWNLOAD_FIELDS}
        out.append(rec)
    return out


def fetch_source(entry: SourceEntry, *, raw_dir: Path, processed_dir: Path) -> list[dict[str, Any]]:
    raw = raw_dir / entry.source_id
    log_path = processed_dir / entry.source_id / "fetch.jsonl"
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=60, follow_redirects=True) as client:
        html, primary = _primary(client, raw, entry)
        pdf, reference = _reference(client, raw, entry)
    # Write only after both files verified.
    _write(raw / f"{primary['raw_sha256']}.html", html)
    _write(raw / f"{reference['raw_sha256']}.pdf", pdf)
    records = _carry_forward([primary, reference], log_path)
    lines = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in records)
    _write(log_path, lines.encode("utf-8"))
    return records


def load_verified(entry: SourceEntry, raw_dir: Path) -> tuple[Path, Path]:
    """Paths of the primary HTML and reference PDF, re-verified against the registry."""
    raw = raw_dir / entry.source_id
    local = _local_html(raw, entry) if raw.is_dir() else None
    pdf = raw / f"{entry.reference.sha256}.pdf"
    if local is None or _local_pdf(raw, entry) is None:
        raise FileNotFoundError(
            f"{entry.source_id}: verified raw files missing; "
            f"run make ingest SOURCE={entry.source_id}"
        )
    return local[0], pdf
