"""Provider interface + user-facing error types.

Every message carried by a ProviderError is written by us and is safe to show in
the UI (it never contains tokens, headers or raw exception text).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

StatusCallback = Optional[Callable[[str], None]]


class ProviderError(Exception):
    """Any failure to obtain raw data. str(error) is a readable UI message."""


class ConfigError(ProviderError):
    """Provider is not configured (e.g. missing token)."""


class EmptyResultError(ProviderError):
    """The source answered, but there were no (valid) products."""


class BaseProvider(ABC):
    """A provider returns a list of RAW product dicts. Nothing more.

    Parsing, cleaning and de-duplication are NOT its job; that keeps the live and
    demo paths identical after this point.
    """

    display_name: str = "Provider"
    data_source: str = ""        # written to the data_source column

    @abstractmethod
    def fetch(self, keyword: str, limit: int, sort: str,
              on_status: StatusCallback = None) -> list:
        """Return raw records (may include malformed items; the parser handles them)."""

    def needs_local_sort(self, sort: str) -> bool:
        """True if the pipeline must sort the cleaned DataFrame itself."""
        return False
