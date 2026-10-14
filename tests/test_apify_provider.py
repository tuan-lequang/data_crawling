"""Live provider tests. Everything is mocked: no network, no token, no Apify credits."""
import logging
import math

import pytest

pytest.importorskip("apify_client")

from config import SOURCE_LIVE
from crawler.apify_shopee import MSG_NO_TOKEN, ApifyShopeeProvider, build_run_input
from crawler.base import ConfigError, EmptyResultError, ProviderError
from pipeline import run_pipeline
from tests.fakes import FakeClient, FakeClock, api_error

TOKEN = "SECRET-TOKEN-123"


def provider(client, **kw):
    return ApifyShopeeProvider(token=TOKEN, client_factory=client.factory(),
                               clock=client.clock, **kw)


def many(records, n):
    """n distinct raw items built from the real-structure fixture."""
    out = []
    for i in range(n):
        item = dict(records["full"])
        item["item_id"] = 1000 + i
        item["title"] = f"Giày Sneaker Nam Mã {i}"
        item["price"] = 100000 + i * 1000
        item["sold"] = i * 10 if i % 4 else None
        item["rating_star"] = round(3 + (i % 20) / 10, 1)
        out.append(item)
    return out


# ------------------------------------------------------------------ token handling
def test_missing_token_is_a_readable_config_error(monkeypatch):    # test 13
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    called = []
    p = ApifyShopeeProvider(client_factory=lambda t: called.append(t))
    with pytest.raises(ConfigError) as exc:
        p.fetch("giày", 10, "relevancy")
    assert str(exc.value) == MSG_NO_TOKEN == "Apify API token is not configured. Please use Demo Dataset."
    assert called == []                        # no client created, no request attempted


def test_blank_token_counts_as_missing(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "   ")
    assert ApifyShopeeProvider.is_configured() is False
    with pytest.raises(ConfigError):
        ApifyShopeeProvider().fetch("giày", 10, "relevancy")


def test_token_comes_from_environment(monkeypatch, records):
    monkeypatch.setenv("APIFY_API_TOKEN", "from-env")
    client = FakeClient(items=many(records, 3))
    ApifyShopeeProvider(client_factory=client.factory(), clock=client.clock).fetch("giày", 10, "relevancy")
    assert client.token == "from-env"


# ---------------------------------------------------------------------- Actor input
def test_run_input_matches_actor_schema():
    run_input = build_run_input("giày sneaker nam", 50, "sales")
    assert run_input == {"country": "vn", "mode": "keyword", "keyword": "giày sneaker nam",
                         "sort": "sales", "maxProducts": 60, "fetchDetail": True, "delay": 1}


@pytest.mark.parametrize("sort, actor_sort", [("relevancy", "relevancy"), ("sales", "sales"),
                                              ("price_asc", "price_asc"), ("price_desc", "price_desc"),
                                              ("rating", "relevancy")])
def test_sort_mapping(sort, actor_sort):
    assert build_run_input("x", 10, sort)["sort"] == actor_sort


def test_max_products_has_buffer_and_cap():
    assert build_run_input("x", 10, "relevancy")["maxProducts"] == 12
    assert build_run_input("x", 100, "relevancy")["maxProducts"] == 120
    assert build_run_input("x", 500, "relevancy")["maxProducts"] == 500      # Actor maximum


def test_fast_mode_disables_detail_and_keeps_duplicate_buffer():
    run_input = build_run_input("điện thoại", 20, "relevancy", fetch_detail=False, buffer_ratio=1.2)
    assert run_input["fetchDetail"] is False
    assert run_input["maxProducts"] == 24


def test_enriched_mode_keeps_detail_and_skips_extra_buffer():
    run_input = build_run_input("điện thoại", 20, "relevancy", fetch_detail=True, buffer_ratio=1.0)
    assert run_input["fetchDetail"] is True
    assert run_input["maxProducts"] == 20


def test_fetch_detail_mode_is_applied_by_provider(records):
    fast_client = FakeClient(items=many(records, 2))
    fast = ApifyShopeeProvider(token=TOKEN, client_factory=fast_client.factory(),
                               clock=fast_client.clock, fetch_detail=False, buffer_ratio=1.2)
    fast.fetch("điện thoại", 10, "relevancy")
    assert fast_client.run_input["fetchDetail"] is False
    assert fast_client.run_input["maxProducts"] == 12

    enriched_client = FakeClient(items=many(records, 2))
    enriched = ApifyShopeeProvider(token=TOKEN, client_factory=enriched_client.factory(),
                                   clock=enriched_client.clock, fetch_detail=True, buffer_ratio=1.0)
    enriched.fetch("điện thoại", 10, "relevancy")
    assert enriched_client.run_input["fetchDetail"] is True
    assert enriched_client.run_input["maxProducts"] == 10


def test_fetch_uses_the_right_actor_and_returns_items(records):    # test 2 (mocked)
    client = FakeClient(items=many(records, 5))
    status = []
    items = provider(client).fetch("giày sneaker nam", 20, "relevancy", on_status=status.append)
    assert client.requested_actor == "xtracto/shopee-scraper"
    assert client.run_input["keyword"] == "giày sneaker nam" and client.run_input["country"] == "vn"
    assert len(items) == 5
    assert any("SUCCEEDED" in m for m in status) and any("elapsed" in m for m in status)


# --------------------------------------------------------------------- error handling
@pytest.mark.parametrize("status, fragment", [
    (401, "rejected the API token"),                                # test 14: invalid token
    (403, "denied access"),
    (402, "usage or billing limit"),
    (429, "rate limit"),
    (500, "temporarily unavailable"),
    (503, "temporarily unavailable"),
    (400, "Unable to retrieve Shopee data from Apify"),
])
def test_http_errors_become_readable_messages(status, fragment):
    client = FakeClient(start_error=api_error(status, f"details containing {TOKEN}"))
    with pytest.raises(ProviderError) as exc:
        provider(client).fetch("giày", 10, "relevancy")
    assert fragment in str(exc.value)
    assert TOKEN not in str(exc.value) and "details" not in str(exc.value)   # no raw text leaks


def test_network_error(records):
    client = FakeClient(start_error=ConnectionError(f"cannot reach host with {TOKEN}"))
    with pytest.raises(ProviderError) as exc:
        provider(client).fetch("giày", 10, "relevancy")
    assert "Unable to reach Apify" in str(exc.value) and TOKEN not in str(exc.value)


def test_timeout_error_during_polling():
    client = FakeClient(wait_error=TimeoutError("slow"))
    with pytest.raises(ProviderError) as exc:
        provider(client).fetch("giày", 10, "relevancy")
    assert "timed out" in str(exc.value)


def test_actor_failure():
    client = FakeClient(statuses=["RUNNING", "FAILED"])
    with pytest.raises(ProviderError) as exc:
        provider(client).fetch("giày", 10, "relevancy")
    assert "Unable to retrieve Shopee data from Apify" in str(exc.value) and "FAILED" in str(exc.value)


@pytest.mark.parametrize("status", ["ABORTED", "TIMED-OUT"])
def test_actor_aborted_or_timed_out(status):
    with pytest.raises(ProviderError):
        provider(FakeClient(statuses=[status])).fetch("giày", 10, "relevancy")


def test_run_that_never_finishes_is_aborted_so_it_stops_costing_money():
    clock = FakeClock()
    client = FakeClient(statuses=["RUNNING"], clock=clock)
    p = ApifyShopeeProvider(token=TOKEN, client_factory=client.factory(), clock=clock,
                            timeout_secs=20, poll_secs=5)
    with pytest.raises(ProviderError) as exc:
        p.fetch("giày", 10, "relevancy")
    assert "too long" in str(exc.value)
    assert client.aborted is True
    assert client.wait_calls <= 6                      # bounded loop, not an infinite wait


def test_empty_dataset():                                          # test 15
    client = FakeClient(items=[])
    with pytest.raises(EmptyResultError) as exc:
        provider(client).fetch("giày", 10, "relevancy")
    assert str(exc.value) == "The scraper returned no products."


def test_dataset_read_failure():
    client = FakeClient(items=[{"a": 1}], dataset_error=api_error(500))
    with pytest.raises(ProviderError):
        provider(client).fetch("giày", 10, "relevancy")


def test_token_never_logged(caplog, records):
    client = FakeClient(start_error=ConnectionError(TOKEN))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderError):
            provider(client).fetch("giày", 10, "relevancy")
    assert TOKEN not in caplog.text


# ------------------------------------------------------- live data through the pipeline
def test_live_pipeline_end_to_end_with_real_structure(records):    # test 20 (live, mocked)
    # limit 20 -> the Actor is asked for 24; it returns 20 unique + 1 duplicate + 3 malformed
    items = many(records, 20) + [many(records, 1)[0]] + [None, "broken", {}]
    client = FakeClient(items=items)
    result = run_pipeline(provider(client), "giày sneaker nam", 20, "relevancy")
    assert client.run_input["maxProducts"] == 24
    assert result.data_source == SOURCE_LIVE == "live_apify"
    assert set(result.df["data_source"]) == {"live_apify"}
    s = result.stats
    assert (s.fetched, s.invalid, s.valid, s.duplicates_removed, s.final) == (24, 3, 21, 1, 20)
    assert result.warnings == []
    assert result.df["product_name"].is_unique
    assert result.df.loc[0, "shop_name"] == "Sneaker House VN"
    assert result.df.loc[0, "price"] == 100000          # no price scaling


def test_dataset_read_is_bounded_by_max_products(records):
    client = FakeClient(items=many(records, 40))
    assert len(provider(client).fetch("giày", 10, "relevancy")) == 12


def test_live_returns_fewer_than_requested_is_reported_not_padded(records):   # requirement 7
    client = FakeClient(items=many(records, 7))
    result = run_pipeline(provider(client), "giày", 50, "relevancy")
    assert result.stats.final == 7 and len(result.df) == 7
    assert any("Only 7 valid unique products" in w for w in result.warnings)


def test_top_rated_is_sorted_locally_for_live(records):
    client = FakeClient(items=many(records, 15))
    result = run_pipeline(provider(client), "giày", 10, "rating")
    ratings = result.df["rating"].tolist()
    assert ratings == sorted(ratings, reverse=True)
    assert client.run_input["sort"] == "relevancy"      # Actor has no top-rated sort


def test_actor_order_is_preserved_for_supported_sorts(records):
    items = many(records, 6)
    client = FakeClient(items=items)
    result = run_pipeline(provider(client), "giày", 10, "price_desc")
    assert result.df["product_id"].tolist() == [str(i["item_id"]) for i in items]   # not re-sorted locally
    assert client.run_input["sort"] == "price_desc"


def test_live_null_sold_and_rating_stay_missing(records):          # tests 10, 11 (live)
    sparse = records["sparse"]
    client = FakeClient(items=[records["full"], sparse])
    df = run_pipeline(provider(client), "giày", 10, "relevancy").df
    row = df[df["product_id"] == "33000000001"].iloc[0]
    assert row["product_name"] == "Áo Thun Nam Cotton Cổ Tròn"      # whitespace cleaned
    assert row["sold"] is __import__("pandas").NA and math.isnan(row["rating"])
    assert row["price"] == 183200
