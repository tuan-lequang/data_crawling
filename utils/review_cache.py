"""Atomic local cache for already-normalized, redacted review rows only."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import REVIEW_CACHE_DIR, REVIEW_CACHE_SCHEMA_VERSION, REVIEW_CACHE_TTL_SECONDS, REVIEW_EMPTY_CACHE_TTL_SECONDS
from crawler.review_base import ReviewRequest


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any):
    if value is None:
        return None
    try:
        import pandas as pd
        if value is pd.NA or pd.isna(value):
            return None
    except (ImportError, TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


@dataclass
class ReviewCacheEntry:
    records: list[dict]
    requested_limit: int
    fetched_at: str
    metadata: dict


class ReviewCache:
    def __init__(self, directory: Path | None = None, ttl_seconds: int = REVIEW_CACHE_TTL_SECONDS,
                 empty_ttl_seconds: int = REVIEW_EMPTY_CACHE_TTL_SECONDS):
        self.directory = Path(directory or REVIEW_CACHE_DIR)
        self.ttl_seconds = int(ttl_seconds)
        self.empty_ttl_seconds = int(empty_ttl_seconds)

    def _key(self, request: ReviewRequest, data_source: str) -> str:
        raw = "|".join((data_source, request.market, str(request.shop_id), str(request.product_id),
                        REVIEW_CACHE_SCHEMA_VERSION, str(bool(request.include_review_images))))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _path(self, request: ReviewRequest, data_source: str) -> Path:
        return self.directory / f"{self._key(request, data_source)}.json"

    def get(self, request: ReviewRequest, data_source: str) -> ReviewCacheEntry | None:
        path = self._path(request, data_source)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            records = payload.get("records", [])
            ttl = self.empty_ttl_seconds if not records else self.ttl_seconds
            if (_utc_now() - fetched_at).total_seconds() > ttl:
                path.unlink(missing_ok=True)
                return None
            requested = int(payload.get("requested_limit", 0))
            # Reuse if this entry can satisfy N, or if the source already returned fewer than asked.
            covers = len(records) >= request.max_reviews or len(records) < requested
            if not covers:
                return None
            return ReviewCacheEntry(records=records[:request.max_reviews], requested_limit=requested,
                                    fetched_at=payload["fetched_at"], metadata=payload.get("metadata", {}))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            return None

    def put(self, request: ReviewRequest, data_source: str, records: list[dict],
            requested_limit: int, metadata: dict | None = None) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(request, data_source)
        payload = {
            "schema_version": REVIEW_CACHE_SCHEMA_VERSION,
            "data_source": data_source,
            "market": request.market,
            "product_id": str(request.product_id),
            "shop_id": str(request.shop_id),
            "include_review_images": bool(request.include_review_images),
            "requested_limit": int(requested_limit),
            "fetched_at": _utc_now().isoformat(),
            "records": _json_safe(records),
            "metadata": _json_safe(metadata or {}),
        }
        # Atomic replacement prevents partial JSON after interruption.
        fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                json.dump(payload, handle, ensure_ascii=False, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return path

    def clear(self) -> int:
        """Delete local review cache files, returning the number deleted."""
        if not self.directory.exists():
            return 0
        removed = 0
        for path in self.directory.glob("*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        for path in self.directory.glob(".*.tmp"):
            try:
                path.unlink()
            except OSError:
                continue
        return removed

    def purge_expired(self) -> int:
        """Remove expired/corrupt entries. The method is safe to call before displaying cache."""
        if not self.directory.exists():
            return 0
        removed = 0
        for path in self.directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                fetched = datetime.fromisoformat(payload["fetched_at"])
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)
                ttl = self.empty_ttl_seconds if not payload.get("records") else self.ttl_seconds
                expired = (_utc_now() - fetched).total_seconds() > ttl
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                expired = True
            if expired:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed
