# SPDX-License-Identifier: Apache-2.0
"""LLMClient with cassette record/replay and shared usage caps (08 M0.5)."""

from common.llm.cassette import CassetteStore, canonical_request, cassette_key
from common.llm.client import Completion, LLMClient, Usage
from common.llm.errors import (
    CassetteMissError,
    CassetteWriteRefusedError,
    LLMError,
    LLMHTTPError,
    OutputValidationError,
    UsageLimitExceededError,
)
from common.llm.limiter import UsageLimiter
from common.llm.settings import DataClass, LLMSettings

__all__ = [
    "CassetteMissError",
    "CassetteStore",
    "CassetteWriteRefusedError",
    "Completion",
    "DataClass",
    "LLMClient",
    "LLMError",
    "LLMHTTPError",
    "LLMSettings",
    "OutputValidationError",
    "Usage",
    "UsageLimitExceededError",
    "UsageLimiter",
    "canonical_request",
    "cassette_key",
]
