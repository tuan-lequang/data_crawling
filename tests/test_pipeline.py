"""Demo-mode pipeline tests (no network, no token)."""
import pandas as pd
import pytest

from config import STANDARD_COLUMNS
from crawler.base import EmptyResultError
from crawler.demo_provider import DemoProvider
from pipeline import run_pipeline, sort_dataframe
from utils.cleaning import fallback_key
from utils.csv_exporter import dataframe_to_csv_bytes, verify_csv_bytes

KW = "giày sneaker nam"


def run(keyword=KW, limit=20, sort="relevancy", **kw):
    return run_pipeline(DemoProvider(), keyword, limit, sort, **kw)


def test_demo_keyword_search():                                    # tests 1, 11
    r = run()
    assert r.data_source == "demo" and set(r.df["data_source"]) == {"demo"}
    assert list(r.df.columns) == STANDARD_COLUMNS
    assert (r.df["keyword"] == KW).all()
    assert r.df["product_name"].str.contains("Sneaker Nam").all()


def test_accented_and_unaccented_keywords_match_the_same_products():   # test 3
    a, b = run("giày sneaker nam", 50), run("giay sneaker nam", 50)
    assert a.df["product_id"].tolist() == b.df["product_id"].tolist()
    assert run("GIÀY   SNEAKER  NAM", 50).stats.final == 50


def test_empty_keyword_is_rejected():                              # test 4
    for bad in ["", "   ", "\n\t", None]:
        with pytest.raises(ValueError, match="enter a keyword"):
            run(bad)


def test_invalid_limit_and_sort_rejected():
    with pytest.raises(ValueError):
        run(limit=0)
    with pytest.raises(ValueError):
        run(limit=True)
    with pytest.raises(ValueError):
        run(sort="nonsense")


@pytest.mark.parametrize("limit", [10, 20, 50, 100])               # tests 5, 6
def test_requested_counts(limit):
    r = run(limit=limit)
    assert r.stats.final == len(r.df) == limit
    assert r.warnings == []


def test_metrics_are_consistent():
    s = run(limit=50).stats
    assert s.fetched == s.valid + s.invalid
    assert s.unique == s.valid - s.duplicates_removed
    assert s.final == min(s.unique, 50)
    assert s.invalid == 4 and s.duplicates_removed == 14           # injected problems are detected


def test_no_duplicates_remain_by_id_or_fallback_key():             # test 8, 9
    df = run(limit=100).df
    ids = df["product_id"].dropna()
    assert ids.is_unique
    no_id = df[df["product_id"].isna()]
    id_keys = {fallback_key(s, n) for s, n in zip(df[df["product_id"].notna()]["shop_id"],
                                                  df[df["product_id"].notna()]["product_name"])}
    for sid, name in zip(no_id["shop_id"], no_id["product_name"]):
        assert fallback_key(sid, name) not in id_keys               # copies without ID were removed


def test_duplicates_visible_even_with_small_request():
    assert run(limit=10).stats.duplicates_removed > 0


def test_fewer_products_than_requested_is_reported_not_padded():
    r = run("bàn phím cơ", limit=50)
    assert 0 < r.stats.final < 50 and len(r.df) == r.stats.final
    assert any(f"Only {r.stats.final} valid unique products" in w for w in r.warnings)


def test_keyword_without_results():                                # test 3 (no result)
    with pytest.raises(EmptyResultError) as exc:
        run("xyzabc không tồn tại")
    assert "No products in the Demo Dataset" in str(exc.value)


def test_missing_fields_do_not_crash():                            # test 7
    df = run(limit=100).df
    assert df["sold"].isna().any() and df["rating"].isna().any()
    assert df["shop_name"].isna().any() and df["product_url"].isna().any()
    assert df["product_url"].dropna().str.startswith("https://demo.invalid/").all()   # never a fake shopee URL
    assert not df["product_url"].dropna().str.contains("shopee").any()
    assert df["product_name"].notna().all() and df["product_id"].notna().sum() > 0


def test_text_formatted_numbers_are_normalized():
    df = run(limit=100).df
    assert str(df["price"].dtype) == "Int64" and str(df["sold"].dtype) == "Int64"
    assert df["price"].dropna().between(10_000, 5_000_000).all()    # no 199.000 -> 199 mistakes
    assert df["rating"].dropna().between(0, 5).all()


@pytest.mark.parametrize("sort, col, asc", [("price_asc", "price", True), ("price_desc", "price", False),
                                            ("sales", "sold", False), ("rating", "rating", False)])
def test_local_sorting(sort, col, asc):
    df = run(limit=50, sort=sort).df
    values = df[col].dropna().astype(float).tolist()
    assert values == sorted(values, reverse=not asc)
    assert df[col].isna().tolist() == sorted(df[col].isna().tolist())     # missing values last


def test_sort_is_applied_before_trimming():
    """'price_asc' must return the cheapest products overall, not the cheapest of the first N."""
    cheapest_overall = run(limit=100, sort="price_asc").df["price"].min()
    assert run(limit=10, sort="price_asc").df["price"].iloc[0] == cheapest_overall


def test_sort_dataframe_handles_empty():
    assert sort_dataframe(pd.DataFrame(columns=STANDARD_COLUMNS), "price_asc").empty


def test_progress_callback_reports_real_stages():
    stages = []
    run(on_progress=lambda stage, msg: stages.append(stage))
    assert [s for s in dict.fromkeys(stages)] == ["connect", "collect", "provider", "parse", "clean",
                                                  "dedupe", "prepare", "done"]


def test_presentation_pause_is_optional(monkeypatch):
    sleeps = []
    monkeypatch.setattr("pipeline.time.sleep", sleeps.append)
    run()
    assert sleeps == []
    run(presentation_pause=True)
    assert len(sleeps) == 4


def test_full_pipeline_to_csv_and_back():                          # test 20 (demo)
    r = run(limit=50)
    data = dataframe_to_csv_bytes(r.df)
    ok, msg = verify_csv_bytes(data, r.df)
    assert ok, msg
    back = pd.read_csv(pd.io.common.BytesIO(data), encoding="utf-8-sig")
    assert len(back) == 50 and "Giày" in back.loc[0, "product_name"]
