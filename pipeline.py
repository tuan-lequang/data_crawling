"""PIPELINE: the whole data flow in one readable place.

    provider.fetch  ->  parse  ->  clean  ->  remove duplicates  ->  sort  ->  trim  ->  DataFrame

The UI (app.py) only calls run_pipeline(); tests call it too (no Streamlit needed).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Callable, Optional

import pandas as pd

from config import (CRAWL_TIME_FORMAT, LOCAL_SORT_COLUMN, PRESENTATION_PAUSE_SECS,
                    STANDARD_COLUMNS)
from crawler.base import BaseProvider, EmptyResultError, ProviderError
from crawler.parser import parse_records
from utils.cleaning import clean_dataframe, remove_duplicates
from utils.validators import validate_keyword, validate_limit, validate_sort

ProgressCallback = Optional[Callable[[str, str], None]]   # (stage, message)


@dataclass
class PipelineStats:
    requested: int = 0
    fetched: int = 0              # raw items returned by the provider
    valid: int = 0                # items that the parser could turn into a record
    invalid: int = 0              # malformed items skipped by the parser
    duplicates_removed: int = 0
    unique: int = 0               # valid minus duplicates
    final: int = 0                # after trimming to the requested count


@dataclass
class PipelineResult:
    df: pd.DataFrame
    stats: PipelineStats
    data_source: str
    source_name: str
    keyword: str
    sort: str
    warnings: list[str] = field(default_factory=list)

    def stats_dict(self) -> dict:
        return asdict(self.stats)


def sort_dataframe(df: pd.DataFrame, sort: str) -> pd.DataFrame:
    """Local sort on cleaned numeric columns. Missing values always go last."""
    if sort not in LOCAL_SORT_COLUMN or df.empty:
        return df
    column, ascending = LOCAL_SORT_COLUMN[sort]
    return df.sort_values(column, ascending=ascending, na_position="last",
                          kind="stable").reset_index(drop=True)


def run_pipeline(provider: BaseProvider, keyword: str, limit: int, sort: str = "relevancy",
                 on_progress: ProgressCallback = None, presentation_pause: bool = False,
                 now: Optional[datetime] = None) -> PipelineResult:
    """Run the full flow. Raises ValueError (bad input) or ProviderError (no usable data)."""
    keyword, limit, sort = validate_keyword(keyword), validate_limit(limit), validate_sort(sort)
    crawl_time = (now or datetime.now()).strftime(CRAWL_TIME_FORMAT)
    stats = PipelineStats(requested=limit)

    def emit(stage: str, message: str, pause: bool = False) -> None:
        if on_progress:
            on_progress(stage, message)
        if pause and presentation_pause:      # optional pause so an audience can follow
            time.sleep(PRESENTATION_PAUSE_SECS)

    # 1-2. connect + collect (the only step that talks to an external system)
    emit("connect", f"🔄 Connecting to data source: {provider.display_name}")
    emit("collect", f"📦 Collecting products for “{keyword}”...")
    raw_items = provider.fetch(keyword, limit, sort,
                               on_status=lambda msg: emit("provider", msg))
    if not isinstance(raw_items, list):
        raise ProviderError("The data source returned an unexpected response.")
    stats.fetched = len(raw_items)
    if not raw_items:
        raise EmptyResultError("The data source returned no products.")
    emit("collect", f"📦 Received {stats.fetched} raw records.", pause=True)

    # 3. parse: raw JSON -> standard records (fixes the SHAPE)
    emit("parse", "🔎 Parsing raw data into the standard schema...")
    records, stats.invalid = parse_records(raw_items, keyword, crawl_time, provider.data_source)
    stats.valid = len(records)
    if not records:
        raise EmptyResultError("The data source returned records, but none contained a product name.")
    emit("parse", f"🔎 {stats.valid} valid records ({stats.invalid} malformed skipped).", pause=True)

    # 4. clean: strings -> numbers, ranges, whitespace (fixes the VALUES)
    emit("clean", "🧹 Cleaning data...")
    df = clean_dataframe(pd.DataFrame(records, columns=STANDARD_COLUMNS))
    emit("clean", "🧹 Prices, sold, rating and text normalized.", pause=True)

    # 5. de-duplicate
    emit("dedupe", "🔍 Removing duplicates...")
    df, stats.duplicates_removed = remove_duplicates(df)
    stats.unique = len(df)
    emit("dedupe", f"🔍 {stats.duplicates_removed} duplicates removed.", pause=True)

    # 6. sort (only when the provider could not do it) and trim -- never pad
    emit("prepare", "📊 Preparing DataFrame...")
    if provider.needs_local_sort(sort):
        df = sort_dataframe(df, sort)
    df = df.head(limit).reset_index(drop=True)
    stats.final = len(df)

    warnings: list[str] = []
    if stats.final < limit:
        warnings.append(f"Only {stats.final} valid unique products were available "
                        f"(you requested {limit}). The dataset was not padded.")
    emit("done", f"✅ Dataset ready: {stats.final} products.")
    return PipelineResult(df=df, stats=stats, data_source=provider.data_source,
                          source_name=provider.display_name, keyword=keyword, sort=sort,
                          warnings=warnings)
