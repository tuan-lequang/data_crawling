"""PARSER: fixes the SHAPE of the data.

raw provider JSON (nested, ~50 fields)  ->  flat record with the 20 standard columns.

Rules
* Missing / null source fields stay None. Nothing is invented.
* Values are NOT converted here (that is the cleaning step); we only pick fields.
* A record without a product name (or that is not a dict) is invalid and is skipped.
* product_url is used only if the record explicitly contains a URL; otherwise None.
"""
from __future__ import annotations

from typing import Any

from config import URL_FIELD_CANDIDATES


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith(("http://", "https://"))


def extract_first_image(images: Any):
    """images[0] if it is a URL (string, or dict with url/src). Otherwise None."""
    if isinstance(images, (list, tuple)) and images:
        first = images[0]
        if isinstance(first, dict):
            first = first.get("url") or first.get("src")
        if _is_http_url(first):
            return first.strip()
    return None


def extract_first_category(categories: Any):
    """Name of the first category entry that has a non-empty name."""
    if isinstance(categories, (list, tuple)):
        for entry in categories:
            name = entry.get("name") if isinstance(entry, dict) else entry
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def extract_source_url(raw: dict):
    """A URL only if the record explicitly provides one. Never constructed."""
    for key in URL_FIELD_CANDIDATES:
        if _is_http_url(raw.get(key)):
            return raw[key].strip()
    return None


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def parse_record(raw: Any, keyword: str, crawl_time: str, data_source: str):
    """Return a standard record (dict) or None if the raw item is malformed."""
    if not isinstance(raw, dict) or not _has_text(raw.get("title")):
        return None
    shop = _as_dict(raw.get("shop"))
    shop_id = raw.get("shop_id")
    if shop_id is None:
        shop_id = shop.get("shopid")        # nested id, only if the top-level one is absent
    record = {
        "product_id": raw.get("item_id"),
        "product_name": raw.get("title"),
        "shop_id": shop_id,
        "shop_name": shop.get("name"),
        "shop_location": shop.get("location"),
        "price": raw.get("price"),
        "price_min": raw.get("price_min"),
        "price_max": raw.get("price_max"),
        "original_price": raw.get("price_before_discount"),
        "discount_pct": raw.get("discount_pct"),
        "sold": raw.get("sold"),
        "rating": raw.get("rating_star"),
        "image_url": extract_first_image(raw.get("images")),
        "product_url": extract_source_url(raw),
        "category": extract_first_category(raw.get("categories")),
        "is_official_shop": shop.get("is_official_shop"),
        "is_shopee_verified": shop.get("is_shopee_verified"),
        "keyword": keyword,
        "crawl_time": crawl_time,
        "data_source": data_source,
    }
    return record


def parse_records(raw_items: list, keyword: str, crawl_time: str,
                  data_source: str) -> tuple[list[dict], int]:
    """Parse every raw item. Returns (records, invalid_count). One bad item never stops the rest."""
    records, invalid = [], 0
    for raw in raw_items:
        try:
            record = parse_record(raw, keyword, crawl_time, data_source)
        except Exception:      # defensive: a surprising structure must not kill the batch
            record = None
        if record is None:
            invalid += 1
        else:
            records.append(record)
    return records, invalid
