# SPDX-License-Identifier: Apache-2.0
"""Law-body extraction: inner HTML of the element with a given id, byte-exact."""

import pytest

from pdp_ingest.fetch import SourceIntegrityError, element_inner_html

PAGE = (
    '<html><body><div class="nav">menu</div>'
    '<div id="produk-content" class="produk-content"><p>Pasal 1</p>'
    "<div><div>nested</div></div><ol><li>a</li></ol></div>"
    '<div class="sidebar">x</div></body></html>'
)


def test_returns_exact_inner_html_with_nested_same_tags() -> None:
    assert element_inner_html(PAGE, "produk-content") == (
        "<p>Pasal 1</p><div><div>nested</div></div><ol><li>a</li></ol>"
    )


def test_missing_element_is_an_integrity_error() -> None:
    with pytest.raises(SourceIntegrityError, match="no element with id 'other'"):
        element_inner_html(PAGE, "other")


def test_unclosed_element_is_an_integrity_error() -> None:
    with pytest.raises(SourceIntegrityError, match="not closed"):
        element_inner_html('<div id="c"><div>x</div>', "c")


def test_id_must_match_exactly() -> None:
    page = '<div id="c-2">no</div><div id="c">yes</div>'
    assert element_inner_html(page, "c") == "yes"
