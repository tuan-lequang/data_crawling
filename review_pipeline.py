"""Shared review parsing, redaction, cleaning, deduplication and cache workflow."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from config import REVIEW_COLUMNS
from crawler.review_base import BaseReviewProvider, ReviewRequest
from crawler.review_parser import parse_review_records
from utils.review_cache import ReviewCache
from utils.review_cleaning import clean_review_dataframe, remove_duplicate_reviews
from utils.validators import validate_review_count


@dataclass
class ReviewPipelineResult:
    df: pd.DataFrame
    requested: int
    fetched: int
    redacted_text_cells: int
    duplicates_removed: int
    from_cache: bool
    source_name: str
    attribution: str
    ordering: str
    coverage: str
    warnings: list[str] = field(default_factory=list)


def _frame_from_cache(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=REVIEW_COLUMNS).reset_index(drop=True)


def run_review_pipeline(
    provider: BaseReviewProvider,
    request: ReviewRequest,
    cache: ReviewCache | None = None,
    on_status: Callable[[str], None] | None = None,
) -> ReviewPipelineResult:
    """Fetch only on demand; only cleaned/redacted rows are written to the local cache."""
    validate_review_count(request.max_reviews)
    cache = cache or ReviewCache()
    cached = cache.get(request, provider.data_source)
    if cached is not None:
        frame = _frame_from_cache(cached.records).head(request.max_reviews).reset_index(drop=True)
        source = cached.metadata.get("source_name", provider.display_name)
        return ReviewPipelineResult(
            df=frame, requested=request.max_reviews, fetched=len(frame),
            redacted_text_cells=int(cached.metadata.get("redacted_text_cells", 0)),
            duplicates_removed=int(cached.metadata.get("duplicates_removed", 0)),
            from_cache=True, source_name=source,
            attribution=cached.metadata.get("attribution", "product-specific (synthetic)"),
            ordering=cached.metadata.get("ordering", "synthetic-deterministic"),
            coverage=cached.metadata.get("coverage", "synthetic sample; not Shopee data"),
            warnings=list(cached.metadata.get("warnings", [])),
        )

    batch = provider.fetch(request, on_status=on_status)
    raw = batch.records
    parsed, mismatched = parse_review_records(raw, request, include_review_images=request.include_review_images)
    clean_df, redacted_count = clean_review_dataframe(parsed)
    clean_df, duplicates = remove_duplicate_reviews(clean_df)
    clean_df = clean_df.head(request.max_reviews).reset_index(drop=True)
    warnings = list(batch.warnings)
    if mismatched:
        warnings.append(f"{mismatched} review row(s) attributed to a different product were skipped.")
    if len(clean_df) < request.max_reviews and not any("returned" in w.lower() for w in warnings):
        warnings.append(f"The source returned {len(clean_df)} of up to {request.max_reviews} requested reviews.")

    safe_records: list[dict[str, Any]] = clean_df.astype(object).where(pd.notna(clean_df), None).to_dict(orient="records")
    metadata = {
        "source_name": batch.source_name,
        "attribution": batch.attribution,
        "ordering": batch.ordering,
        "coverage": batch.coverage,
        "warnings": warnings,
        "redacted_text_cells": redacted_count,
        "duplicates_removed": duplicates,
    }
    cache.put(request, provider.data_source, safe_records, request.max_reviews, metadata)
    return ReviewPipelineResult(
        df=clean_df, requested=request.max_reviews, fetched=len(raw),
        redacted_text_cells=redacted_count, duplicates_removed=duplicates,
        from_cache=False, source_name=batch.source_name, attribution=batch.attribution,
        ordering=batch.ordering, coverage=batch.coverage, warnings=warnings,
    )
