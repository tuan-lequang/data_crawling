"""Shared fixtures: tests are isolated from the developer's .env and filesystem."""
import copy
import json
import socket
from pathlib import Path

import pytest

import config
import dotenv
import utils.csv_exporter as csv_exporter
import utils.review_cache as review_cache

FIXTURE = Path(__file__).parent / "fixtures" / "apify_records.json"


@pytest.fixture
def records():
    """Records shaped like the real Apify/Shopee VN fetchDetail output (deep copies)."""
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture(autouse=True)
def isolate_environment_and_outputs(monkeypatch, tmp_path):
    """No real .env token, no network, and no exports/cache written into the source tree."""
    monkeypatch.setenv("APIFY_API_TOKEN", "")
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)

    export_dir = tmp_path / "exports"
    cache_dir = tmp_path / "cache" / "reviews"
    monkeypatch.setattr(config, "EXPORT_DIR", export_dir)
    monkeypatch.setattr(csv_exporter, "EXPORT_DIR", export_dir)
    monkeypatch.setattr(config, "REVIEW_CACHE_DIR", cache_dir)
    monkeypatch.setattr(review_cache, "REVIEW_CACHE_DIR", cache_dir)

    def block_network(*args, **kwargs):
        raise AssertionError("Network access is prohibited in automated tests.")

    monkeypatch.setattr(socket, "create_connection", block_network)
    monkeypatch.setattr(socket.socket, "connect", block_network)
