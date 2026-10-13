"""Offline synthetic review provider. Records are fictional and never from Shopee."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Callable

from crawler.review_base import BaseReviewProvider, ReviewBatch, ReviewRequest


class DemoReviewProvider(BaseReviewProvider):
    display_name = "Synthetic Demo Reviews"
    data_source = "demo_synthetic"

    def fetch(self, request: ReviewRequest, on_status: Callable[[str], None] | None = None) -> ReviewBatch:
        """Generate a stable sample keyed by product ID; make empty/few-result paths testable."""
        if not isinstance(request.max_reviews, int) or isinstance(request.max_reviews, bool) or request.max_reviews < 1:
            raise ValueError("Review count must be a whole number greater than zero.")

        digest = hashlib.sha256(str(request.product_id).encode("utf-8")).hexdigest()
        mode = int(digest[:8], 16) % 10
        if mode == 0:
            count = 0
        elif mode in (1, 2):
            count = min(3, request.max_reviews)
        else:
            count = request.max_reviews

        now = datetime.now(timezone.utc).replace(microsecond=0)
        comments = [
            "Sản phẩm đúng mô tả, đóng gói cẩn thận. (ĐÁNH GIÁ MÔ PHỎNG)",
            "Chất lượng ổn, dùng thử thấy khá hài lòng. (ĐÁNH GIÁ MÔ PHỎNG)",
            "Giao hàng nhanh, ngoại hình giống phần mô tả. (ĐÁNH GIÁ MÔ PHỎNG)",
            "Nếu cần hỗ trợ, liên hệ Zalo: demo_contact_123 hoặc demo.review@example.invalid. (MÔ PHỎNG)",
            "Mình đã dùng vài ngày; sản phẩm ở mức ổn. (ĐÁNH GIÁ MÔ PHỎNG)",
        ]
        records: list[dict] = []
        for index in range(count):
            created = now - timedelta(days=index * 3 + 1)
            image_count = index % 3
            records.append({
                "review_id": f"demo-review-{request.product_id}-{index + 1}",
                "product_id": str(request.product_id),
                "shop_id": str(request.shop_id),
                "rating": [5, 4, 5, 3, 5][index % 5],
                "comment": comments[index % len(comments)],
                "created_at": created.isoformat(),
                "purchased_variant": ["Màu đen", "Dung lượng 128GB", "Size M"][index % 3],
                "like_count": index % 8,
                "seller_reply": "Shop cảm ơn bạn đã phản hồi. (PHẢN HỒI MÔ PHỎNG)" if index % 2 == 0 else None,
                "review_image_count": image_count,
                "review_images": (
                    "\n".join(f"https://demo.invalid/reviews/{request.product_id}/{index + 1}/{n + 1}.jpg"
                              for n in range(image_count))
                    if request.include_review_images else None
                ),
                "data_source": self.data_source,
                "scraped_at": now.isoformat(),
            })
        warnings = []
        if count < request.max_reviews:
            warnings.append(f"The synthetic provider returned {count} of up to {request.max_reviews} requested reviews.")
        return ReviewBatch(
            records=records,
            source_name=self.display_name,
            attribution="product-specific (synthetic)",
            ordering="synthetic-deterministic",
            coverage="synthetic sample; not Shopee data",
            warnings=warnings,
        )
