"""Normalize the canonical review record shape; discard direct reviewer identifiers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config import REVIEW_COLUMNS
from crawler.review_base import ReviewRequest


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first(raw: dict, *keys: str) -> Any:
    for key in keys:
        if key in raw and raw.get(key) is not None:
            return raw.get(key)
    return None


def parse_review_records(
    raw_records: list[dict],
    request: ReviewRequest,
    include_review_images: bool | None = None,
    scraped_at: str | None = None,
) -> tuple[list[dict], int]:
    """Map accepted canonical/vendor-like fields to the minimal schema.

    Direct author fields are intentionally never copied. Rows explicitly attributed to
    another product are dropped. If product ID is absent, request context supplies the
    join key because the provider was invoked for this product only.
    """
    if include_review_images is None:
        include_review_images = request.include_review_images
    fetched_at = scraped_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    parsed: list[dict] = []
    mismatched = 0
    for raw in raw_records or []:
        if not isinstance(raw, dict):
            continue
        product_id = _text(_first(raw, "product_id", "productId", "itemId", "item_id"))
        if product_id and product_id != str(request.product_id):
            mismatched += 1
            continue
        shop_id = _text(_first(raw, "shop_id", "shopId", "shopid")) or str(request.shop_id)

        variants = _first(raw, "purchased_variant", "purchasedVariant", "variations", "variation")
        if isinstance(variants, list):
            variant_texts = []
            for item in variants:
                if isinstance(item, dict):
                    name = _text(item.get("name") or item.get("name_text"))
                    option = _text(item.get("option") or item.get("value"))
                    val = f"{name}: {option}" if name and option else (option or name)
                    if val:
                        variant_texts.append(val)
                elif _text(item):
                    variant_texts.append(_text(item))
            variants = "; ".join(variant_texts) or None
        else:
            variants = _text(variants)

        image_count_value = _first(raw, "review_image_count", "reviewImageCount")
        images = _first(raw, "images")
        raw_image_urls = _first(raw, "review_images", "imageUrls", "image_urls")
        if isinstance(raw_image_urls, str):
            image_urls = [line.strip() for line in raw_image_urls.splitlines() if line.strip()]
        elif isinstance(raw_image_urls, list):
            images = raw_image_urls
            image_urls = []
        else:
            image_urls = []
        if isinstance(images, list):
            for image in images:
                value = (image.get("url") or image.get("imageUrl")) if isinstance(image, dict) else image
                value = _text(value)
                if value and value.startswith(("https://", "http://")):
                    image_urls.append(value)
        image_urls = list(dict.fromkeys(url for url in image_urls if url.startswith(("https://", "http://"))))
        try:
            image_count = int(image_count_value) if image_count_value is not None else len(images if isinstance(images, list) else image_urls)
        except (TypeError, ValueError):
            image_count = len(images if isinstance(images, list) else image_urls)

        seller_reply = _first(raw, "seller_reply", "sellerReply")
        if seller_reply is None:
            seller_reply = _nested(raw, "shopReply", "comment") or _nested(raw, "shop_reply", "comment")
        elif isinstance(seller_reply, dict):
            seller_reply = seller_reply.get("comment") or seller_reply.get("text")

        rating = _first(raw, "rating", "ratingStar", "rating_star")
        try:
            rating = int(float(str(rating).replace(",", "."))) if rating is not None else None
        except (TypeError, ValueError):
            rating = None
        like_count = _first(raw, "like_count", "likeCount")
        try:
            like_count = int(float(like_count)) if like_count is not None else None
        except (TypeError, ValueError):
            like_count = None

        row = {
            "review_id": _text(_first(raw, "review_id", "reviewId", "cmtid", "commentId")),
            "product_id": product_id or str(request.product_id),
            "shop_id": shop_id,
            "rating": rating,
            "comment": _text(_first(raw, "comment", "text", "content")),
            "created_at": _first(raw, "created_at", "createdAt", "ctime", "timestamp"),
            "purchased_variant": variants,
            "like_count": like_count,
            "seller_reply": _text(seller_reply),
            "review_image_count": image_count,
            "review_images": "\n".join(image_urls) if include_review_images and image_urls else None,
            "data_source": _text(raw.get("data_source")) or "demo_synthetic",
            "scraped_at": _text(_first(raw, "scraped_at", "scrapedAt")) or fetched_at,
        }
        parsed.append({column: row.get(column) for column in REVIEW_COLUMNS})
    return parsed, mismatched
