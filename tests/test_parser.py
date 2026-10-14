"""Parser tests, using the real Apify/Shopee VN record structure as the fixture."""
import pytest

from config import STANDARD_COLUMNS
from crawler.parser import (extract_first_category, extract_first_image, extract_source_url,
                            parse_record, parse_records)

KW, TS, SRC = "giày sneaker nam", "2026-10-07 10:00:00", "live_apify"


def parse(raw):
    return parse_record(raw, KW, TS, SRC)


def test_real_schema_full_mapping(records):                      # test 16
    rec = parse(records["full"])
    assert list(rec) == STANDARD_COLUMNS and len(rec) == 20
    assert rec["product_id"] == 22093519050
    assert rec["product_name"].startswith("Giày Sneaker Nam")
    assert rec["shop_id"] == 123456789
    assert rec["price"] == 219000 and rec["price_min"] == 219000 and rec["price_max"] == 249000
    assert rec["original_price"] == 289000          # price_before_discount
    assert rec["discount_pct"] == 24
    assert rec["sold"] == 1530
    assert rec["rating"] == 4.8                     # rating_star
    assert rec["keyword"] == KW and rec["crawl_time"] == TS and rec["data_source"] == SRC


def test_nested_shop_fields(records):                            # test 17
    rec = parse(records["full"])
    assert rec["shop_name"] == "Sneaker House VN"
    assert rec["shop_location"] == "TP. Hồ Chí Minh"
    assert rec["is_official_shop"] is True
    assert rec["is_shopee_verified"] is True


def test_missing_shop_object_does_not_crash(records):
    rec = parse(records["no_shop"])
    assert rec["shop_name"] is None and rec["shop_location"] is None
    assert rec["shop_id"] is None
    assert rec["is_official_shop"] is None and rec["is_shopee_verified"] is None


def test_shop_id_falls_back_to_nested_shopid(records):
    raw = records["full"]
    del raw["shop_id"]
    assert parse(raw)["shop_id"] == 123456789


def test_category_extraction(records):                           # test 18
    assert parse(records["full"])["category"] == "Thời Trang Nam"
    assert extract_first_category([]) is None
    assert extract_first_category(None) is None
    assert extract_first_category([{"name": "  "}, {"name": "Giày Dép Nam"}]) == "Giày Dép Nam"
    assert extract_first_category(["Balo"]) == "Balo"


def test_image_extraction(records):                              # test 19
    assert parse(records["full"])["image_url"] == "https://example.test/img/a1.jpg"
    assert extract_first_image([]) is None
    assert extract_first_image(None) is None
    assert extract_first_image([{"url": "https://x.test/i.jpg"}]) == "https://x.test/i.jpg"
    # a bare identifier is not a URL and must not be turned into one
    assert extract_first_image(["abc123hash"]) is None


def test_product_url_is_never_invented(records):
    rec = parse(records["full"])                 # has item_id and shop_id, but no URL field
    assert rec["product_url"] is None
    assert parse(records["with_url"])["product_url"] == "https://example.test/product/123456789/22093519051"
    assert extract_source_url({"url": "not-a-url"}) is None


def test_null_fields_stay_none(records):                         # tests 7, 10, 11
    rec = parse(records["sparse"])
    assert rec["sold"] is None
    assert rec["rating"] is None
    assert rec["original_price"] is None and rec["discount_pct"] is None
    assert rec["image_url"] is None and rec["category"] is None
    assert rec["shop_name"] is None


@pytest.mark.parametrize("bad", [None, "text", 42, [], {}, {"item_id": 1}, {"title": "   "}, {"title": None}])
def test_malformed_records_are_rejected(bad):
    assert parse(bad) is None


def test_parse_records_counts_invalid(records):
    items = [records["full"], None, "oops", records["sparse"], {}]
    parsed, invalid = parse_records(items, KW, TS, SRC)
    assert len(parsed) == 2 and invalid == 3


def test_record_without_item_id_is_still_valid(records):
    raw = records["full"]
    del raw["item_id"]
    rec = parse(raw)
    assert rec is not None and rec["product_id"] is None


def test_fast_mode_flat_record_schema_is_supported():
    raw = {
        "item_id": "99001122",
        "name": "Điện thoại mẫu",
        "shop_id": "880077",
        "shop_name": "Shop Demo",
        "location": "Hồ Chí Minh",
        "price": 455000,
        "original_price": 535000,
        "discount_pct": 15,
        "sold_count": 140,
        "rating": 4.8,
        "image_url": "https://example.test/phone.jpg",
        "url": "https://shopee.vn/example-product",
        "is_official_shop": False,
        "is_shopee_verified": True,
    }
    rec = parse(raw)
    assert list(rec) == STANDARD_COLUMNS
    assert rec["product_id"] == "99001122"
    assert rec["product_name"] == "Điện thoại mẫu"
    assert rec["shop_name"] == "Shop Demo"
    assert rec["shop_location"] == "Hồ Chí Minh"
    assert rec["original_price"] == 535000
    assert rec["sold"] == 140
    assert rec["rating"] == 4.8
    assert rec["image_url"] == raw["image_url"]
    assert rec["product_url"] == raw["url"]
    assert rec["is_shopee_verified"] is True
    # The Actor didn't provide details such as categories or price range; do not invent them.
    assert rec["category"] is None
    assert rec["price_min"] is None and rec["price_max"] is None
