"""CLEANING: fixes the VALUES (strings -> numbers, ranges, whitespace) + de-duplication.

The parser (crawler/parser.py) has already fixed the SHAPE of each record.
Rules here never invent data: anything that cannot be parsed becomes NaN / NA / None.
Prices are plain VND values (the Apify output is already in VND; no scaling).
"""
from __future__ import annotations

import math
import re
import unicodedata

import pandas as pd

from config import (BOOL_COLUMNS, ID_COLUMNS, PRICE_COLUMNS, STANDARD_COLUMNS,
                    TEXT_COLUMNS)

# ----------------------------------------------------------------------------- text
def _fold(text: str) -> str:
    """lowercase + remove accents, but KEEP punctuation (numbers need their '.' and ',')."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D").lower()


def normalize_text(value) -> str:
    """lowercase, accent-free, punctuation-free text used for matching & dedupe keys."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _fold(str(value))).split())


def clean_text(value):
    """Trim + collapse whitespace, keep Vietnamese accents (NFC). Empty -> None."""
    if value is None or value is pd.NA or (isinstance(value, float) and math.isnan(value)):
        return None
    text = " ".join(unicodedata.normalize("NFC", str(value)).split())
    return text or None


def to_id_string(value):
    """IDs are kept as strings (long ints are not safe as floats / in Excel)."""
    if value is None or value is pd.NA or isinstance(value, bool):
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return str(int(value)) if value.is_integer() else str(value)
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".")[0]
    return text or None


# --------------------------------------------------------------------------- numbers
_NUMBER_GROUP = re.compile(r"\d[\d.,]*")
_THOUSANDS = re.compile(r"\d{1,3}(?:[.,]\d{3})+")
_DECIMAL = re.compile(r"\d+(?:[.,]\d+)?")
_COUNT = re.compile(r"(\d[\d.,]*)\s*(k|m|tr|nghin|trieu)?\b")
_MULTIPLIER = {"k": 1_000, "nghin": 1_000, "m": 1_000_000, "tr": 1_000_000, "trieu": 1_000_000}


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _group_to_float(group: str):
    """'199.000' / '1,250' -> thousands separators; '4.8' / '4,8' -> decimal."""
    group = group.rstrip(".,")
    if _THOUSANDS.fullmatch(group):
        return float(re.sub(r"[.,]", "", group))
    if _DECIMAL.fullmatch(group):
        return float(group.replace(",", "."))
    return None


def parse_price(value) -> float:
    """VND price. 219000, '₫199.000', '199,000', '199.000đ', '₫1.000 - ₫2.000' -> number.

    A range takes the lowest value. Zero/negative/unparseable -> NaN
    (Shopee uses 0 for "no original price").
    """
    if value is None or isinstance(value, bool):
        return math.nan
    if _is_number(value):
        number = float(value)
        return number if math.isfinite(number) and number > 0 else math.nan
    if isinstance(value, str):
        numbers = [_group_to_float(g) for g in _NUMBER_GROUP.findall(value)]
        numbers = [n for n in numbers if n is not None and n > 0]
        return min(numbers) if numbers else math.nan
    return math.nan


def parse_count(value):
    """Sold / counts. 850, '1.2K', '1,5K', 'Đã bán 2,3k', '1.250' -> int; null -> pd.NA."""
    if value is None or isinstance(value, bool):
        return pd.NA
    if _is_number(value):
        if not math.isfinite(value) or value < 0:
            return pd.NA
        return int(round(value))
    if isinstance(value, str):
        match = _COUNT.search(_fold(value))
        if not match:
            return pd.NA
        group, suffix = match.groups()
        if suffix:  # '1.2k' / '1,5k': the separator is a decimal point
            try:
                number = float(group.replace(",", ".")) * _MULTIPLIER[suffix]
            except ValueError:
                return pd.NA
        else:
            parsed = _group_to_float(group)
            if parsed is None:
                return pd.NA
            number = parsed
        return int(round(number))
    return pd.NA


def parse_rating(value) -> float:
    """Rating must be within 0-5, otherwise NaN. Accepts 4.8, '4,8', '4.8/5'."""
    if value is None or isinstance(value, bool):
        return math.nan
    number = math.nan
    if _is_number(value):
        number = float(value)
    elif isinstance(value, str):
        match = _NUMBER_GROUP.search(value)
        if match:
            try:
                number = float(match.group().rstrip(".,").replace(",", "."))
            except ValueError:
                number = math.nan
    return number if math.isfinite(number) and 0 <= number <= 5 else math.nan


def parse_discount(value) -> float:
    """Percentage 0-100. Accepts 20, '20%', '-20%' (display sign). Otherwise NaN."""
    if value is None or isinstance(value, bool):
        return math.nan
    number = math.nan
    if _is_number(value):
        number = float(value)
    elif isinstance(value, str):
        match = _NUMBER_GROUP.search(value)
        if match:
            try:
                number = float(match.group().rstrip(".,").replace(",", "."))
            except ValueError:
                number = math.nan
    return number if math.isfinite(number) and 0 <= number <= 100 else math.nan


def parse_bool(value):
    if isinstance(value, bool):
        return value
    if _is_number(value) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return pd.NA


# ------------------------------------------------------------------------ DataFrame
def _int64(values) -> pd.Series:
    """Nullable integer column (VND has no minor unit, so prices are rounded)."""
    converted = [pd.NA if (v is pd.NA or (isinstance(v, float) and math.isnan(v)))
                 else int(round(v)) for v in values]
    return pd.Series(converted, dtype="Int64")


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply every value rule. Never raises because of one bad cell."""
    out = df.reindex(columns=STANDARD_COLUMNS).reset_index(drop=True)
    for col in ID_COLUMNS:
        out[col] = pd.Series([to_id_string(v) for v in out[col]], dtype="string")
    for col in TEXT_COLUMNS:
        out[col] = pd.Series([clean_text(v) for v in out[col]], dtype="string")
    for col in PRICE_COLUMNS:
        out[col] = _int64([parse_price(v) for v in out[col]])
    out["sold"] = _int64([parse_count(v) for v in out["sold"]])
    out["rating"] = pd.Series([parse_rating(v) for v in out["rating"]], dtype="float64")
    out["discount_pct"] = pd.Series([parse_discount(v) for v in out["discount_pct"]],
                                    dtype="float64")
    for col in BOOL_COLUMNS:
        out[col] = pd.Series([parse_bool(v) for v in out[col]], dtype="boolean")
    return out


# ---------------------------------------------------------------------- de-duplication
def fallback_key(shop_id, product_name) -> str:
    return f"{shop_id if shop_id is not None and shop_id is not pd.NA else ''}|{normalize_text(product_name)}"


def remove_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Keep the FIRST valid record of each product; return (frame, duplicates_removed).

    * Record has a product_id -> duplicate only if that product_id was already seen.
      (Two different IDs are different listings, even with the same title.)
    * Record has NO product_id -> fallback key = shop_id + normalized product name;
      duplicate if an earlier record (with or without ID) had the same fallback key.
    """
    seen_ids: set[str] = set()
    seen_fallback: set[str] = set()
    keep: list[bool] = []
    for pid, sid, name in zip(df["product_id"], df["shop_id"], df["product_name"]):
        fb = fallback_key(sid, name)
        if pid is not pd.NA and pid is not None:
            is_dup = pid in seen_ids
            if not is_dup:
                seen_ids.add(pid)
                seen_fallback.add(fb)
        else:
            is_dup = fb in seen_fallback
            if not is_dup:
                seen_fallback.add(fb)
        keep.append(not is_dup)
    mask = pd.Series(keep, index=df.index, dtype=bool)
    return df[mask].reset_index(drop=True), int((~mask).sum())
