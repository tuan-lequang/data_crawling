import math

import pandas as pd
import pytest

from config import STANDARD_COLUMNS
from utils.cleaning import (clean_dataframe, clean_text, normalize_text, parse_bool,
                            parse_count, parse_discount, parse_price, parse_rating,
                            remove_duplicates, to_id_string)


@pytest.mark.parametrize("raw, expected", [                       # test 8
    ("₫199.000", 199000), ("199,000", 199000), ("199.000đ", 199000), ("199000", 199000),
    (199000, 199000), (219000, 219000), (183200, 183200), (183200.0, 183200),
    ("₫199.000 - ₫250.000", 199000), ("199000.5", 199000.5), (" ₫ 1.250.000 ", 1250000),
])
def test_price_parsing(raw, expected):
    assert parse_price(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "Liên hệ", "abc", -5, 0, float("nan"), True, [], {}])
def test_price_invalid_is_nan(raw):
    assert math.isnan(parse_price(raw))


def test_prices_are_not_rescaled():
    """Apify prices are already VND: 219000 must stay 219000 (no /100000)."""
    df = clean_dataframe(pd.DataFrame([{"product_name": "x", "price": 219000, "original_price": 289000}]))
    assert df.loc[0, "price"] == 219000 and df.loc[0, "original_price"] == 289000


@pytest.mark.parametrize("raw, expected", [                       # test 9
    (850, 850), (0, 0), (1530, 1530), ("850", 850), ("1.2K", 1200), ("1,5K", 1500), ("1.5k", 1500),
    ("Đã bán 2,3k", 2300), ("10k+", 10000), ("1.250", 1250), ("1,250", 1250), (12.0, 12),
])
def test_count_parsing(raw, expected):
    assert parse_count(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "n/a", float("nan"), -1, True, []])
def test_count_missing_or_invalid_is_na(raw):                     # test 10
    assert parse_count(raw) is pd.NA


@pytest.mark.parametrize("raw, expected", [(4.8, 4.8), ("4.8", 4.8), ("4,8", 4.8), (5, 5.0), (0, 0.0), ("4.9/5", 4.9)])
def test_rating_parsing(raw, expected):
    assert parse_rating(raw) == expected


@pytest.mark.parametrize("raw", [None, "", 5.1, -1, 48, "abc", float("nan"), True])
def test_rating_invalid_is_nan(raw):                              # test 11
    assert math.isnan(parse_rating(raw))


@pytest.mark.parametrize("raw, expected", [(24, 24.0), ("20%", 20.0), ("-20%", 20.0), (0, 0.0)])
def test_discount(raw, expected):
    assert parse_discount(raw) == expected


def test_discount_out_of_range():
    assert math.isnan(parse_discount(150)) and math.isnan(parse_discount(None))


def test_bool_parsing():
    assert parse_bool(True) is True and parse_bool("false") is False and parse_bool(1) is True
    assert parse_bool(None) is pd.NA and parse_bool("maybe") is pd.NA


def test_text_cleaning_keeps_vietnamese():
    assert clean_text("  Giày   Sneaker \n Nam ") == "Giày Sneaker Nam"
    assert clean_text("") is None and clean_text(None) is None and clean_text(float("nan")) is None
    assert clean_text("Đế Êm Siêu Nhẹ ✓") == "Đế Êm Siêu Nhẹ ✓"


def test_normalize_text_for_matching():
    assert normalize_text("Giày Sneaker Nam!") == "giay sneaker nam"
    assert normalize_text("ĐẾ Êm") == "de em"


def test_id_strings():
    assert to_id_string(22093519050) == "22093519050"
    assert to_id_string(22093519050.0) == "22093519050"
    assert to_id_string("22093519050.0") == "22093519050"
    assert to_id_string(None) is None and to_id_string("  ") is None and to_id_string(True) is None


def test_clean_dataframe_all_missing_does_not_crash():            # test 7
    df = clean_dataframe(pd.DataFrame([{"product_name": "Chỉ có tên"}, {}]))
    assert list(df.columns) == STANDARD_COLUMNS
    assert df.loc[0, "product_name"] == "Chỉ có tên"
    assert df["price"].isna().all() and df["sold"].isna().all() and df["rating"].isna().all()
    assert str(df["price"].dtype) == "Int64" and str(df["rating"].dtype) == "float64"


def test_clean_dataframe_dtypes_and_mixed_formats():
    raw = pd.DataFrame([
        {"product_id": 1, "product_name": " A ", "price": "₫199.000", "sold": "1,5K", "rating": "4,8",
         "discount_pct": "20%", "is_shopee_verified": "true"},
        {"product_id": 2, "product_name": "B", "price": 219000, "sold": None, "rating": None},
    ])
    out = clean_dataframe(raw)
    assert out.loc[0, "price"] == 199000 and out.loc[0, "sold"] == 1500
    assert out.loc[0, "rating"] == 4.8 and out.loc[0, "discount_pct"] == 20.0
    assert bool(out.loc[0, "is_shopee_verified"]) is True
    assert out.loc[0, "product_name"] == "A"
    assert pd.isna(out.loc[1, "sold"]) and pd.isna(out.loc[1, "rating"])
    assert out.loc[1, "price"] == 219000


# ------------------------------------------------------------------------- de-duplication
def frame(rows):
    return clean_dataframe(pd.DataFrame(rows))


def test_dedupe_by_product_id_keeps_first():                      # test 8 (duplicate item_id)
    df = frame([
        {"product_id": 1, "product_name": "A", "sold": 10},
        {"product_id": 2, "product_name": "B"},
        {"product_id": 1, "product_name": "A", "sold": 99},
    ])
    out, removed = remove_duplicates(df)
    assert removed == 1 and out["product_id"].tolist() == ["1", "2"]
    assert out.loc[0, "sold"] == 10                                # first record wins


def test_dedupe_fallback_when_product_id_missing():               # test 9
    df = frame([
        {"product_id": 7, "shop_id": 5, "product_name": "Giày Sneaker Nam Mã 1"},
        {"product_id": None, "shop_id": 5, "product_name": "giay  sneaker nam MÃ 1"},   # same product
        {"product_id": None, "shop_id": 6, "product_name": "Giày Sneaker Nam Mã 1"},    # other shop
        {"product_id": None, "shop_id": 6, "product_name": "Giày Sneaker Nam Mã 1"},    # copy of previous
    ])
    out, removed = remove_duplicates(df)
    assert removed == 2 and len(out) == 2
    assert out["shop_id"].tolist() == ["5", "6"]


def test_same_title_with_different_ids_is_not_a_duplicate():
    df = frame([{"product_id": 1, "shop_id": 5, "product_name": "A"},
                {"product_id": 2, "shop_id": 5, "product_name": "A"}])
    assert remove_duplicates(df)[1] == 0


def test_dedupe_on_empty_frame():
    out, removed = remove_duplicates(clean_dataframe(pd.DataFrame(columns=STANDARD_COLUMNS)))
    assert removed == 0 and out.empty
