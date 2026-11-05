# SPDX-License-Identifier: Apache-2.0
"""Shared usage caps for upstream calls (NFR-12; reused by the 9router probe and eval harness).

`acquire()` reserves a call before it is sent, so the call cap is exact even with concurrent
calls. Tokens are known only after a response, so the token cap stops the *next* call: the
total can overshoot by the calls already in flight.
"""

from dataclasses import dataclass, field

from common.llm.errors import UsageLimitExceededError


@dataclass
class UsageLimiter:
    max_calls: int
    max_total_tokens: int
    calls: int = field(default=0, init=False)
    total_tokens: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.max_calls < 1 or self.max_total_tokens < 1:
            raise ValueError("usage caps must be positive")

    def acquire(self) -> None:
        if self.calls >= self.max_calls:
            raise UsageLimitExceededError(f"call cap reached: {self.calls}/{self.max_calls}")
        if self.total_tokens >= self.max_total_tokens:
            raise UsageLimitExceededError(
                f"token cap reached: {self.total_tokens}/{self.max_total_tokens}"
            )
        self.calls += 1

    def add_tokens(self, tokens: int) -> None:
        if tokens < 0:
            raise ValueError(f"tokens must be >= 0, got {tokens}")
        self.total_tokens += tokens
