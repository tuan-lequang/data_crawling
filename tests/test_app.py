"""Headless UI tests. Run when Streamlit is installed; all tests remain offline."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from config import STANDARD_COLUMNS, UI_SOURCE_DEMO, UI_SOURCE_LIVE

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def widget(items, key):
    for item in items:
        if getattr(item, "key", None) == key:
            return item
    raise AssertionError(f"Widget with key {key!r} was not found")


@pytest.fixture
def app():
    return AppTest.from_file(APP, default_timeout=60).run()


def metrics(at):
    return {m.label: m.value for m in at.metric}


def test_app_loads_without_token(app):
    assert not app.exception
    assert app.title[0].value.endswith("Shopee Product Data Crawler")
    assert list(widget(app.selectbox, "product_count_choice").options) == ["10", "20", "50", "100", "Custom"]
    assert widget(app.selectbox, "data_source_choice").value == UI_SOURCE_DEMO
    assert any("not configured" in w.value for w in app.sidebar.warning)


def test_demo_run_shows_metrics_table_and_banner(app):
    widget(app.selectbox, "product_count_choice").set_value("50")
    widget(app.button, "start_crawling").click().run()
    assert not app.exception and not app.error
    m = metrics(app)
    assert m["Final products"] == "50" and int(m["Duplicates removed"]) > 0
    assert set(m) == {"Products fetched", "Valid products", "Duplicates removed", "Final products"}
    assert any("DEMO DATASET" in i.value and "not live" in i.value for i in app.info)
    assert not any("LIVE" in s.value for s in app.success)
    assert any("CSV verified" in c.value and "UTF-8-SIG" in c.value for c in app.caption)
    assert len(app.dataframe) >= 1


def test_empty_keyword_shows_message_not_traceback(app):
    widget(app.text_input, "keyword").set_value("   ")
    widget(app.button, "start_crawling").click().run()
    assert not app.exception
    assert any("Please enter a keyword" in e.value for e in app.error)


def test_no_results_message(app):
    widget(app.text_input, "keyword").set_value("khong co san pham nay")
    widget(app.button, "start_crawling").click().run()
    assert not app.exception
    assert any("No products in the Demo Dataset" in e.value for e in app.error)


def test_live_mode_without_token_is_a_friendly_error(app):
    widget(app.selectbox, "data_source_choice").set_value(UI_SOURCE_LIVE)
    widget(app.button, "start_crawling").click().run()
    assert not app.exception
    assert any("Apify API token is not configured. Please use Demo Dataset." in e.value for e in app.error)
    assert not app.metric


def test_failed_run_clears_previous_result(app):
    widget(app.button, "start_crawling").click().run()
    assert app.metric
    widget(app.text_input, "keyword").set_value("")
    widget(app.button, "start_crawling").click().run()
    assert not app.metric and app.error


def test_result_survives_a_rerun(app):
    widget(app.button, "start_crawling").click().run()
    app.run()
    assert metrics(app)["Final products"] == "20"


def test_fewer_products_warning_is_shown(app):
    widget(app.text_input, "keyword").set_value("bàn phím cơ")
    widget(app.selectbox, "product_count_choice").set_value("100")
    widget(app.button, "start_crawling").click().run()
    assert not app.exception
    assert any("Only" in w.value and "were available" in w.value for w in app.warning)


def test_custom_product_count_appears_before_starting_crawl(app):
    widget(app.selectbox, "product_count_choice").set_value("Custom").run()
    assert not app.exception
    assert len(app.number_input) >= 1
    custom = widget(app.number_input, "custom_product_count")
    assert custom.min == 1 and custom.max == 500
    assert not app.metric
    custom.set_value(37)
    widget(app.button, "start_crawling").click().run()
    assert not app.exception and not app.error
    assert metrics(app)["Final products"] == "37"


def test_export_options_have_stable_keys_and_expected_defaults(app):
    csv, excel = widget(app.checkbox, "export_csv"), widget(app.checkbox, "export_excel")
    assert csv.label == "CSV" and csv.value is True
    assert excel.label == "Excel (.xlsx)" and excel.value is False
    assert {w.key for w in app.checkbox if str(getattr(w, "key", "")).startswith("export_")} == {"export_csv", "export_excel"}


def test_no_export_format_stops_before_pipeline(app):
    widget(app.checkbox, "export_csv").set_value(False)
    widget(app.checkbox, "export_excel").set_value(False)
    widget(app.button, "start_crawling").click().run()
    assert not app.exception
    assert any("Please select at least one export format" in e.value for e in app.error)


def test_demo_run_can_select_excel_only(app):
    widget(app.checkbox, "export_csv").set_value(False)
    widget(app.checkbox, "export_excel").set_value(True)
    widget(app.button, "start_crawling").click().run()
    assert not app.exception and not app.error
    assert len(app.download_button) == 1
    assert app.download_button[0].label == "⬇ Download Excel"


def test_product_field_select_all_updates_and_zero_selection_blocks_crawl(app):
    widget(app.checkbox, "product_select_all").set_value(False).run()
    assert all(not widget(app.checkbox, f"product_field__{col}").value for col in STANDARD_COLUMNS)
    widget(app.button, "start_crawling").click().run()
    assert not app.exception
    assert any("Please select at least one product output field" in e.value for e in app.error)
    assert not app.metric




def test_all_product_fields_are_selected_by_default(app):
    from config import STANDARD_COLUMNS
    assert all(widget(app.checkbox, f"product_field__{column}").value for column in STANDARD_COLUMNS)
    assert widget(app.radio, "product_fields_preset").value == "All 20 (default)"


def test_crawl_does_not_fetch_reviews_until_a_product_is_opened(app, tmp_path, monkeypatch):
    from config import REVIEW_CACHE_DIR
    widget(app.checkbox, "enable_review_viewing").set_value(True).run()
    widget(app.button, "start_crawling").click().run()
    # The test conftest redirects cache to a temporary directory; product crawl alone
    # must not create review cache entries.
    assert not list(REVIEW_CACHE_DIR.glob("*.json"))


def test_custom_review_count_is_visible_before_product_start(app):
    widget(app.checkbox, "enable_review_viewing").set_value(True).run()
    widget(app.selectbox, "review_count_choice").set_value("Custom").run()
    assert not app.exception
    custom = widget(app.number_input, "custom_review_count")
    assert custom.min == 1 and custom.max == 100
    custom.set_value(7)
    assert not app.metric


def test_demo_review_navigation_and_back_preserves_product_result(app):
    widget(app.checkbox, "enable_review_viewing").set_value(True).run()
    widget(app.button, "start_crawling").click().run()
    assert metrics(app)["Final products"] == "20"
    review_buttons = [b for b in app.button if str(getattr(b, "key", "")).startswith("view_reviews_")]
    assert review_buttons, "Expected per-product review buttons"
    review_buttons[0].click().run()
    assert not app.exception
    assert any("SYNTHETIC DEMO REVIEWS" in info.value for info in app.info)
    assert any(t.value == "Customer Reviews" for t in app.title)
    widget(app.button, "review_back").click().run()
    assert any(t.value.endswith("Shopee Product Data Crawler") for t in app.title)
    assert metrics(app)["Final products"] == "20"


def test_live_review_provider_is_real_provider_and_does_not_fallback_to_demo():
    from crawler.review_access import get_review_provider
    from crawler.apify_reviews import Memo23ShopeeReviewProvider
    assert isinstance(get_review_provider("live_apify"), Memo23ShopeeReviewProvider)
    assert get_review_provider("demo").data_source == "demo_synthetic"
