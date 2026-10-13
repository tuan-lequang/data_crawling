"""Select an on-demand review provider based on the product data source."""
from __future__ import annotations

from config import SOURCE_DEMO, SOURCE_LIVE
from crawler.apify_reviews import Memo23ShopeeReviewProvider
from crawler.demo_reviews import DemoReviewProvider
from crawler.review_base import BaseReviewProvider, ReviewProviderError


def get_review_provider(product_data_source: str) -> BaseReviewProvider:
    """Never return synthetic reviews for Live products; Live uses the selected real provider."""
    if product_data_source == SOURCE_DEMO:
        return DemoReviewProvider()
    if product_data_source == SOURCE_LIVE:
        return Memo23ShopeeReviewProvider()
    raise ReviewProviderError("This product data source has no configured review provider.")
