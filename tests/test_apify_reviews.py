"""Live-review provider contract tests using fake Apify clients only."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from crawler.apify_reviews import (
    Memo23ShopeeReviewProvider,
    build_memo23_input,
    estimate_memo23_max_charge,
    resolve_shopee_product_url,
)
from crawler.review_base import ReviewProviderError, ReviewRequest
from review_pipeline import run_review_pipeline
from utils.review_cache import ReviewCache


class FakeDataset:
    def __init__(self, client):
        self.client = client

    def iterate_items(self, *, limit=None, **kwargs):
        self.client.iterate_limit = limit
        yield from self.client.items[:limit]

    def delete(self):
        self.client.dataset_deleted = True
        return {"ok": True}


class FakeStore:
    def __init__(self, client):
        self.client = client

    def delete(self):
        self.client.store_deleted = True
        return {"ok": True}


class FakeActor:
    def __init__(self, client):
        self.client = client

    def start(self, **kwargs):
        self.client.actor_kwargs = kwargs
        return SimpleNamespace(id="run-live-reviews-1", status="READY", default_dataset_id="ds-1",
                               default_key_value_store_id="kvs-1")


class FakeRunClient:
    def __init__(self, client):
        self.client = client

    def wait_for_finish(self, *, wait_duration=None):
        self.client.wait_calls += 1
        if wait_duration:
            self.client.clock += wait_duration.total_seconds()
        return SimpleNamespace(id="run-live-reviews-1", status="SUCCEEDED", default_dataset_id="ds-1",
                               default_key_value_store_id="kvs-1")

    def abort(self):
        self.client.aborted = True


class FakeClient:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.actor_kwargs = None
        self.requested_actor = None
        self.dataset_deleted = False
        self.store_deleted = False
        self.iterate_limit = None
        self.wait_calls = 0
        self.clock = 0.0

    def actor(self, actor_id):
        self.requested_actor = actor_id
        return FakeActor(self)

    def run(self, run_id):
        assert run_id == "run-live-reviews-1"
        return FakeRunClient(self)

    def dataset(self, _dataset_id):
        return FakeDataset(self)

    def key_value_store(self, _store_id):
        return FakeStore(self)


def request(max_reviews=5, product_url=None):
    return ReviewRequest(product_id="123456", shop_id="98765", product_name="Điện thoại", 
                         max_reviews=max_reviews, product_url=product_url)


def review(review_id, product_id="123456", **extra):
    return {
        "type": "review",
        "reviewId": review_id,
        "productId": product_id,
        "shopId": "98765",
        "rating": 5,
        "text": "Điện thoại tốt, giao hàng nhanh",
        "createdAt": "2026-10-12T12:00:00.000Z",
        "variation": "128GB",
        "sellerReply": "Shop cảm ơn bạn",
        "imageUrls": ["https://image.invalid/review.jpg"],
        "reviewerName": "masked-user",
        "orderId": "private-order-id",
        "buyerRegion": "HCMC",
        **extra,
    }


def test_build_input_is_bounded_and_asks_for_written_reviews():
    url, constructed = resolve_shopee_product_url(None, "98765", "123456")
    assert constructed and url == "https://shopee.vn/product/98765/123456"
    data = build_memo23_input(request(5), url)
    assert data["startUrls"] == [url]
    assert data["maxReviewsPerShop"] == 5
    assert data["onlyWithText"] is True
    assert data["includeShopSummary"] is True
    assert "proxyConfiguration" not in data
    for invalid in (0, -1, True, 101):
        with pytest.raises(ValueError):
            build_memo23_input(request(invalid), url)


def test_product_url_only_reuses_a_url_matching_both_ids():
    valid = "https://shopee.vn/product/98765/123456"
    assert resolve_shopee_product_url(valid, "98765", "123456") == (valid, False)
    wrong = "https://shopee.vn/product/98765/999999"
    assert resolve_shopee_product_url(wrong, "98765", "123456") == (
        "https://shopee.vn/product/98765/123456", True
    )
    with pytest.raises(ReviewProviderError):
        resolve_shopee_product_url(None, "shop-x", "123456")


def test_cost_estimate_and_charge_cap_are_bounded():
    estimate5, cap5 = estimate_memo23_max_charge(5)
    estimate100, cap100 = estimate_memo23_max_charge(100)
    assert estimate5 > 0 and cap5 > estimate5
    assert cap100 <= 0.40 and cap100 > estimate100
    with pytest.raises(ValueError):
        estimate_memo23_max_charge(0)


def test_live_provider_maps_real_actor_shape_and_deletes_remote_output():
    client = FakeClient([
        review("r1"),
        review("r2", product_id="999999"),
        {"type": "shop-summary", "shopId": "98765", "reviewsCollected": 2,
         "coverage": "Stopped at maxReviewsPerShop."},
    ])
    provider = Memo23ShopeeReviewProvider(token="test-token", client_factory=lambda _token: client,
                                          poll_secs=1, timeout_secs=10)
    batch = provider.fetch(request(5))

    assert client.requested_actor == "memo23/shopee-reviews-scraper"
    sent = client.actor_kwargs
    assert sent["run_input"]["maxReviewsPerShop"] == 5
    assert sent["max_items"] == 7
    assert isinstance(sent["max_total_charge_usd"], Decimal)
    assert sent["max_total_charge_usd"] > 0
    assert len(batch.records) == 2  # matching and mismatched product rows; pipeline drops mismatches
    assert "reviewerName" not in batch.records[0] and "orderId" not in batch.records[0]
    assert batch.records[0]["data_source"] == "live_apify_reviews_memo23"
    assert "partial" in batch.warnings[0].lower()
    assert client.dataset_deleted and client.store_deleted


def test_live_review_pipeline_redacts_and_caches_only_minimal_rows(tmp_path):
    client = FakeClient([review("r1", text="Gọi 0912345678, mail private@example.invalid; điện thoại tốt")])
    provider = Memo23ShopeeReviewProvider(token="test-token", client_factory=lambda _token: client,
                                          poll_secs=1, timeout_secs=10)
    cache = ReviewCache(tmp_path / "cache")
    result = run_review_pipeline(provider, request(5), cache=cache)
    assert len(result.df) == 1
    assert result.df.loc[0, "data_source"] == "live_apify_reviews_memo23"
    assert "0912345678" not in str(result.df.loc[0, "comment"])
    assert "private@example.invalid" not in str(result.df.loc[0, "comment"])
    contents = b"".join(p.read_bytes() for p in (tmp_path / "cache").glob("*.json"))
    assert b"reviewerName" not in contents and b"orderId" not in contents
    assert b"0912345678" not in contents and b"private@example.invalid" not in contents
    assert client.dataset_deleted and client.store_deleted


def test_live_provider_requires_token_before_constructing_client(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "")
    made = []
    provider = Memo23ShopeeReviewProvider(client_factory=lambda token: made.append(token))
    with pytest.raises(ReviewProviderError, match="API token is not configured"):
        provider.fetch(request())
    assert made == []
