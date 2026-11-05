# SPDX-License-Identifier: Apache-2.0
"""Shared usage limiter (M0.5, NFR-12)."""

import pytest

from common.llm import UsageLimiter, UsageLimitExceededError


def test_call_cap_aborts_the_next_call() -> None:
    limiter = UsageLimiter(max_calls=2, max_total_tokens=1_000)
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(UsageLimitExceededError, match=r"call cap reached: 2/2"):
        limiter.acquire()
    assert limiter.calls == 2


def test_token_cap_aborts_once_reached() -> None:
    limiter = UsageLimiter(max_calls=10, max_total_tokens=100)
    limiter.acquire()
    limiter.add_tokens(60)
    limiter.acquire()
    limiter.add_tokens(40)
    with pytest.raises(UsageLimitExceededError, match=r"token cap reached: 100/100"):
        limiter.acquire()


@pytest.mark.parametrize(("calls", "tokens"), [(0, 1), (1, 0), (-1, 5)])
def test_caps_must_be_positive(calls: int, tokens: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        UsageLimiter(max_calls=calls, max_total_tokens=tokens)


def test_negative_tokens_rejected() -> None:
    with pytest.raises(ValueError, match="tokens"):
        UsageLimiter(max_calls=1, max_total_tokens=1).add_tokens(-1)
