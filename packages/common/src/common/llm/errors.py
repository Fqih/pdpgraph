# SPDX-License-Identifier: Apache-2.0
"""LLMClient errors. Messages never contain prompt text, the upstream host, or the key."""


class LLMError(Exception):
    """Base class for LLMClient failures."""


class LLMHTTPError(LLMError):
    """The upstream call failed (transport error, non-2xx status, or malformed response)."""


class OutputValidationError(LLMError):
    """The model output did not match the requested schema, even after the retry."""


class CassetteMissError(LLMError):
    """Replay mode found no cassette for the request."""


class CassetteWriteRefusedError(LLMError):
    """A cassette entry would contain PII or a configured secret."""


class UsageLimitExceededError(LLMError):
    """A shared call or token cap was reached."""
