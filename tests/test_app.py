"""Headless UI tests (Streamlit AppTest): the app loads and handles user flows without a traceback."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from config import UI_SOURCE_DEMO, UI_SOURCE_LIVE

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    return AppTest.from_file(APP, default_timeout=60).run()


def metrics(at):
    return {m.label: m.value for m in at.metric}


def test_app_loads_without_token(app):
    assert not app.exception
    assert app.title[0].value.endswith("Shopee Product Data Crawler")
    assert list(app.selectbox[0].options) == ["10", "20", "50", "100", "Custom"]
    assert app.selectbox[2].value == UI_SOURCE_DEMO                    # demo is the default
    assert any("not configured" in w.value for w in app.sidebar.warning)


def test_demo_run_shows_metrics_table_and_banner(app):
    app.selectbox[0].set_value("50")
    app.button[0].click().run()
    assert not app.exception and not app.error
    m = metrics(app)
    assert m["Final products"] == "50" and int(m["Duplicates removed"]) > 0
    assert set(m) == {"Products fetched", "Valid products", "Duplicates removed", "Final products"}
    assert any("DEMO DATASET" in i.value and "not live" in i.value for i in app.info)
    assert not any("LIVE" in s.value for s in app.success)
    assert any("CSV verified" in c.value and "UTF-8-SIG" in c.value for c in app.caption)
    assert len(app.dataframe) >= 1


def test_empty_keyword_shows_message_not_traceback(app):
    app.text_input[0].set_value("   ")
    app.button[0].click().run()
    assert not app.exception
    assert any("Please enter a keyword" in e.value for e in app.error)


def test_no_results_message(app):
    app.text_input[0].set_value("khong co san pham nay")
    app.button[0].click().run()
    assert not app.exception
    assert any("No products in the Demo Dataset" in e.value for e in app.error)


def test_live_mode_without_token_is_a_friendly_error(app):          # test 13 (UI)
    app.selectbox[2].set_value(UI_SOURCE_LIVE)
    app.button[0].click().run()
    assert not app.exception
    assert any("Apify API token is not configured. Please use Demo Dataset." in e.value for e in app.error)
    assert not app.metric                                           # nothing shown as if it were live data


def test_failed_run_clears_previous_result(app):
    app.button[0].click().run()
    assert app.metric
    app.text_input[0].set_value("")
    app.button[0].click().run()
    assert not app.metric and app.error


def test_result_survives_a_rerun(app):
    app.button[0].click().run()
    app.run()                                                       # e.g. what clicking Download triggers
    assert metrics(app)["Final products"] == "20"


def test_fewer_products_warning_is_shown(app):
    app.text_input[0].set_value("bàn phím cơ")
    app.selectbox[0].set_value("100")
    app.button[0].click().run()
    assert not app.exception
    assert any("Only" in w.value and "were available" in w.value for w in app.warning)


def test_custom_product_count_appears_before_starting_crawl(app):
    app.selectbox[0].set_value("Custom").run()
    assert not app.exception
    assert len(app.number_input) == 1
    assert app.number_input[0].min == 1
    assert app.number_input[0].max == 500
    assert not app.metric  # selecting Custom must not start the pipeline
    app.number_input[0].set_value(37)
    app.button[0].click().run()
    assert not app.exception and not app.error
    assert metrics(app)["Final products"] == "37"


def test_export_options_default_to_csv_and_allow_excel(app):
    assert len(app.checkbox) == 2
    assert app.checkbox[0].label == "CSV" and app.checkbox[0].value is True
    assert app.checkbox[1].label == "Excel (.xlsx)" and app.checkbox[1].value is False


def test_no_export_format_stops_before_pipeline(app):
    app.checkbox[0].set_value(False)
    app.checkbox[1].set_value(False)
    app.button[0].click().run()
    assert not app.exception
    assert any("Please select at least one export format" in e.value for e in app.error)


def test_demo_run_can_select_excel_only(app):
    app.checkbox[0].set_value(False)
    app.checkbox[1].set_value(True)
    app.button[0].click().run()
    assert not app.exception and not app.error
    assert len(app.download_button) == 1
    assert app.download_button[0].label == "⬇ Download Excel"


def test_unexpected_exception_hides_traceback(app, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("internal detail with secret-ish text")
    monkeypatch.setattr("pipeline.parse_records", boom)
    app.button[0].click().run()
    assert not app.exception
    assert any("Something unexpected went wrong" in e.value for e in app.error)
    assert not any("secret-ish" in e.value for e in app.error)
