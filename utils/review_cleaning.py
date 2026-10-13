"""Cleaning, privacy redaction and de-duplication for normalized review records."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from config import REVIEW_COLUMNS, REVIEW_ID_COLUMNS, REVIEW_TEXT_COLUMNS
from utils.pii_redaction import redact_pii_text


def _missing(value) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _clean_text(value) -> str | None:
    if _missing(value):
        return None
    text = unicodedata.normalize("NFC", str(value))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


def _safe_int(value, minimum: int = 0, maximum: int | None = None):
    if _missing(value):
        return pd.NA
    try:
        number = int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError, OverflowError):
        return pd.NA
    if number < minimum or (maximum is not None and number > maximum):
        return pd.NA
    return number


def _utc_datetime(value) -> str | None:
    if _missing(value):
        return None
    try:
        # Numeric epoch timestamps are accepted only when they're plausibly seconds or ms.
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
            dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        else:
            dt = pd.to_datetime(value, utc=True, errors="coerce")
            if pd.isna(dt):
                return None
            dt = dt.to_pydatetime()
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def clean_review_dataframe(records: Iterable[dict]) -> tuple[pd.DataFrame, int]:
    """Clean and redact in memory. Returns (safe DataFrame, number of redacted text cells)."""
    frame = pd.DataFrame(list(records or []), columns=REVIEW_COLUMNS).reset_index(drop=True)
    redacted_cells = 0
    for column in REVIEW_ID_COLUMNS:
        frame[column] = pd.Series([_clean_text(v) for v in frame[column]], dtype="string")
    for column in REVIEW_TEXT_COLUMNS:
        values: list[str | None] = []
        for value in frame[column]:
            cleaned = _clean_text(value)
            # Free-text comments/replies can include contacts. Structured image URLs are
            # only retained if the user selected them; do not redact the URL itself.
            if column in {"comment", "seller_reply"}:
                safe, replacement_count = redact_pii_text(cleaned)
                if replacement_count:
                    redacted_cells += 1
            else:
                safe = cleaned
            values.append(safe)
        frame[column] = pd.Series(values, dtype="string")
    frame["rating"] = pd.Series([_safe_int(v, 1, 5) for v in frame["rating"]], dtype="Int64")
    frame["like_count"] = pd.Series([_safe_int(v, 0) for v in frame["like_count"]], dtype="Int64")
    frame["review_image_count"] = pd.Series([_safe_int(v, 0) for v in frame["review_image_count"]], dtype="Int64")
    frame["created_at"] = pd.Series([_utc_datetime(v) for v in frame["created_at"]], dtype="string")
    for col in ("data_source", "scraped_at"):
        frame[col] = pd.Series([_clean_text(v) for v in frame[col]], dtype="string")
    # Missing required IDs are not useful for reliable linkage/export.
    frame = frame[frame["product_id"].notna() & frame["shop_id"].notna()]
    return frame.reset_index(drop=True), redacted_cells


def _fallback_review_key(row: pd.Series) -> str:
    values = []
    for column in ("product_id", "shop_id", "rating", "comment", "created_at"):
        value = row.get(column)
        values.append("" if _missing(value) else str(value))
    source = "|".join(values)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def remove_duplicate_reviews(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Deduplicate by review_id; use a hash of stable visible fields if ID is missing."""
    if df.empty:
        return df.copy(), 0
    seen: set[str] = set()
    keep: list[bool] = []
    for _, row in df.iterrows():
        review_id = row.get("review_id")
        if _missing(review_id) or not str(review_id).strip():
            key = "fallback:" + _fallback_review_key(row)
        else:
            key = "id:" + str(review_id)
        duplicate = key in seen
        if not duplicate:
            seen.add(key)
        keep.append(not duplicate)
    mask = pd.Series(keep, index=df.index, dtype=bool)
    return df.loc[mask].reset_index(drop=True), int((~mask).sum())
