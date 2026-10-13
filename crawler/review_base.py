"""Interfaces and request/result types shared by Demo and Live review providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


class ReviewProviderError(Exception):
    """Safe-to-display review provider error."""


class LiveReviewsNotAvailableError(ReviewProviderError):
    """Compatibility exception reserved for an explicitly disabled Live provider."""


@dataclass(frozen=True)
class ReviewRequest:
    product_id: str
    shop_id: str
    product_name: str
    market: str = "vn"
    max_reviews: int = 5
    include_review_images: bool = False
    product_url: str | None = None


@dataclass
class ReviewBatch:
    records: list[dict[str, Any]]
    source_name: str
    attribution: str = "product-specific"
    ordering: str = "synthetic-deterministic"
    coverage: str = "synthetic sample"
    warnings: list[str] = field(default_factory=list)


class BaseReviewProvider(ABC):
    display_name: str = "Review provider"
    data_source: str = ""

    @abstractmethod
    def fetch(self, request: ReviewRequest, on_status: Callable[[str], None] | None = None) -> ReviewBatch:
        """Return review-like records for one product; must not persist raw payloads."""
