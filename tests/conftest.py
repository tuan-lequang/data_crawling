import copy
import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "apify_records.json"


@pytest.fixture
def records():
    """Records shaped like the real Apify/Shopee VN fetchDetail output (deep copies)."""
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
