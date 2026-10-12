"""DEMO provider: reads data/demo_products.json (SYNTHETIC data, NOT from Shopee).

Works offline and needs no account or token.
Matching: a record matches when every keyword word is the start of a word in its title
or category names (accent-insensitive: "giay" matches "Giày").
Records in the file that are malformed (not objects / no title) are returned too, exactly
like a real feed can contain broken items, so the parser's "invalid" metric is meaningful.
"""
from __future__ import annotations

import json
from pathlib import Path

from config import DEMO_FILE, SOURCE_DEMO
from crawler.base import BaseProvider, EmptyResultError, ProviderError, StatusCallback
from utils.cleaning import normalize_text


def _is_malformed(raw) -> bool:
    return not isinstance(raw, dict) or not str(raw.get("title") or "").strip()


def _tokens(raw: dict) -> list[str]:
    """Normalized words of the title + category names."""
    cats = raw.get("categories")
    names = [c.get("name") or "" for c in cats if isinstance(c, dict)] if isinstance(cats, list) else []
    return normalize_text(f"{raw.get('title')} {' '.join(names)}").split()


def _matches(raw: dict, words: list[str]) -> bool:
    tokens = _tokens(raw)
    return all(any(t.startswith(w) for t in tokens) for w in words)


class DemoProvider(BaseProvider):
    display_name = "Demo Dataset (local file)"
    data_source = SOURCE_DEMO

    def __init__(self, path: Path = DEMO_FILE):
        self.path = Path(path)

    def _load(self) -> list:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ProviderError(f"Demo file not found: {self.path.name}") from None
        except (OSError, json.JSONDecodeError):
            raise ProviderError("The demo dataset file could not be read.") from None
        if not isinstance(data, list):
            raise ProviderError("The demo dataset file has an unexpected structure.")
        return data

    def fetch(self, keyword: str, limit: int, sort: str,
              on_status: StatusCallback = None) -> list:
        data = self._load()
        words = normalize_text(keyword).split()
        matches = [r for r in data if not _is_malformed(r) and _matches(r, words)]
        if not matches:
            raise EmptyResultError(
                f"No products in the Demo Dataset match “{keyword}”. "
                "Try: giày sneaker nam, áo thun nam, balo laptop, tai nghe bluetooth, "
                "chuột không dây or bàn phím cơ.")
        broken = [r for r in data if _is_malformed(r)]
        if on_status:
            on_status(f"Demo Dataset: {len(matches)} records matched “{keyword}”.")
        return matches + broken

    def needs_local_sort(self, sort: str) -> bool:
        # The demo file has no ranking of its own: "Relevancy" = file order,
        # every other sort is applied locally (this is NOT Shopee's ranking).
        return sort != "relevancy"
