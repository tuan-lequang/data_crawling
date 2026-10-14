"""Crawl-mode configuration tests; no Streamlit, network, token, or Apify SDK required."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from config import APIFY_ACTOR_ID
from crawler.apify_shopee import ApifyShopeeProvider, build_run_input


def test_fast_mode_uses_basic_results_and_20_percent_buffer():
    run_input = build_run_input(
        "điện thoại", 20, "relevancy", fetch_detail=False, buffer_ratio=1.2
    )
    assert run_input["fetchDetail"] is False
    assert run_input["maxProducts"] == 24


def test_enriched_mode_uses_details_without_fetch_buffer():
    run_input = build_run_input(
        "điện thoại", 20, "relevancy", fetch_detail=True, buffer_ratio=1.0
    )
    assert run_input["fetchDetail"] is True
    assert run_input["maxProducts"] == 20


def test_legacy_defaults_remain_enriched_with_previous_buffer():
    run_input = build_run_input("x", 10, "relevancy")
    assert run_input["fetchDetail"] is True
    assert run_input["maxProducts"] == 12


def test_buffer_ratio_below_one_is_rejected():
    with pytest.raises(ValueError, match="at least 1.0"):
        build_run_input("x", 10, "relevancy", fetch_detail=True, buffer_ratio=0.9)


class _FakeRunClient:
    def __init__(self, client):
        self.client = client

    def wait_for_finish(self, *, wait_duration=None):
        return {"id": "run-1", "status": "SUCCEEDED", "default_dataset_id": "dataset-1"}

    def abort(self):
        self.client.aborted = True


class _FakeDataset:
    def iterate_items(self, *, limit=None, **kwargs):
        yield {"item_id": "1", "title": "Test Product", "price": 1000}


class _FakeActor:
    def __init__(self, client):
        self.client = client

    def start(self, *, run_input=None, run_timeout=None, **kwargs):
        self.client.run_input = run_input
        self.client.run_timeout = run_timeout
        self.client.actor_id = self.client.requested_actor
        assert isinstance(run_timeout, timedelta)
        return {"id": "run-1", "status": "READY", "default_dataset_id": "dataset-1"}


class _FakeClient:
    def __init__(self):
        self.run_input = None
        self.run_timeout = None
        self.actor_id = None
        self.requested_actor = None
        self.aborted = False

    def actor(self, actor_id):
        self.requested_actor = actor_id
        return _FakeActor(self)

    def run(self, run_id):
        return _FakeRunClient(self)

    def dataset(self, dataset_id):
        return _FakeDataset()


@pytest.mark.parametrize(
    "fetch_detail,ratio,expected_detail,expected_count",
    [(False, 1.2, False, 12), (True, 1.0, True, 10)],
)
def test_provider_passes_mode_settings_to_actor(
    monkeypatch, fetch_detail, ratio, expected_detail, expected_count
):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy-test-token")
    client = _FakeClient()
    provider = ApifyShopeeProvider(
        client_factory=lambda token: client,
        fetch_detail=fetch_detail,
        buffer_ratio=ratio,
    )
    result = provider.fetch("điện thoại", 10, "relevancy")
    assert len(result) == 1
    assert client.requested_actor == APIFY_ACTOR_ID
    assert client.run_input["fetchDetail"] is expected_detail
    assert client.run_input["maxProducts"] == expected_count
