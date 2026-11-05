# SPDX-License-Identifier: Apache-2.0
"""Domain exceptions for the common package."""


class InvalidIdError(ValueError):
    """A string or component does not match the ID grammar (04-data-model §2.1)."""
