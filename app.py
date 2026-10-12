"""Streamlit UI. Contains no data logic: it collects input, calls run_pipeline(), shows results."""
import logging

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from config import (DEFAULT_PRODUCT_COUNT, DISPLAY_COLUMNS, PRODUCT_COUNT_OPTIONS,
                    SORT_OPTIONS, SOURCE_LIVE, UI_SOURCE_DEMO, UI_SOURCE_LIVE)
from crawler.apify_shopee import ApifyShopeeProvider
from crawler.base import ProviderError
from crawler.demo_provider import DemoProvider
from pipeline import PipelineResult, run_pipeline
from utils.csv_exporter import (dataframe_to_csv_bytes, dataframe_to_excel_bytes,
                                make_excel_filename, make_filename, verify_csv_bytes,
                                verify_excel_bytes)

load_dotenv()
log = logging.getLogger(__name__)

st.set_page_config(page_title="Shopee Product Data Crawler", page_icon="🛒", layout="wide")


# ------------------------------------------------------------------------- sidebar
def render_sidebar() -> bool:
    """Returns True if the presentation pause is enabled."""
    with st.sidebar:
        st.header("Settings")
        if ApifyShopeeProvider.is_configured():
            st.success("Apify token: configured ✅")
        else:
            st.warning("Apify token: not configured ❌\n\nLive mode is unavailable. "
                       "Demo Dataset works without it.")
        st.caption("The token is read from the `.env` file and is never displayed.")
        pause = st.checkbox(
            "Presentation pause",
            help="Adds a short pause after each local processing stage so an audience can "
                 "follow. It does not slow down the Apify request.")
        st.divider()
        st.caption("**Live** mode runs a scraper on Apify and uses your Apify credits "
                   "(detailed product data is requested). **Demo** mode is local, free "
                   "and offline.")
    return pause


# --------------------------------------------------------------------------- result
def display_frame(df: pd.DataFrame) -> pd.DataFrame:
    return df[[col for _, col in DISPLAY_COLUMNS]].rename(
        columns={col: label for label, col in DISPLAY_COLUMNS})


def render_result(
    result: PipelineResult,
    csv_bytes: bytes | None,
    csv_name: str | None,
    csv_message: str | None,
    excel_bytes: bytes | None,
    excel_name: str | None,
    excel_message: str | None,
) -> None:
    if result.data_source == SOURCE_LIVE:
        st.success("🟢 LIVE — Shopee via Apify")
    else:
        st.info("🧪 DEMO DATASET — not live Shopee data. Records are synthetic samples.")

    s = result.stats
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Products fetched", s.fetched)
    c2.metric("Valid products", s.valid)
    c3.metric("Duplicates removed", s.duplicates_removed)
    c4.metric("Final products", s.final)
    for warning in result.warnings:
        st.warning(warning)

    st.subheader("Data preview")
    st.dataframe(
        display_frame(result.df), hide_index=True, width="stretch",
        column_config={
            "Price": st.column_config.NumberColumn("Price (₫)", format="%d"),
            "Original Price": st.column_config.NumberColumn("Original Price (₫)", format="%d"),
            "Discount %": st.column_config.NumberColumn("Discount %", format="%d%%"),
            "Sold": st.column_config.NumberColumn("Sold", format="%d"),
            "Rating": st.column_config.NumberColumn("Rating", format="%.2f"),
            "Product URL": st.column_config.LinkColumn("Product URL"),
        })
    st.caption("Empty cells mean the source did not provide that value (nothing is estimated). "
               f"Sort: {result.sort} · Source: {result.source_name}")
    with st.expander("All 20 columns (exactly what is exported)"):
        st.dataframe(result.df, hide_index=True, width="stretch")

    if csv_bytes is not None and csv_name is not None:
        st.download_button("⬇ Download CSV", data=csv_bytes, file_name=csv_name, mime="text/csv",
                           type="primary", key="download_csv")
        if csv_message:
            st.caption(csv_message)

    if excel_bytes is not None and excel_name is not None:
        st.download_button("⬇ Download Excel", data=excel_bytes, file_name=excel_name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="download_excel")
        if excel_message:
            st.caption(excel_message)


# ---------------------------------------------------------------------------- run
def run_and_store(
    source: str, keyword: str, limit: int, sort: str, pause: bool,
    export_csv_selected: bool, export_excel_selected: bool,
) -> None:
    provider = ApifyShopeeProvider() if source == UI_SOURCE_LIVE else DemoProvider()
    error_message = None
    with st.status("Running data pipeline...", expanded=True) as status:
        live_line = None        # one line that is overwritten by each Apify status update

        def on_progress(stage: str, message: str) -> None:
            nonlocal live_line
            if stage == "provider":
                if live_line is None:
                    live_line = st.empty()
                live_line.write("⏳ " + message)
            else:
                st.write(message)

        try:
            result = run_pipeline(provider, keyword, limit, sort,
                                  on_progress=on_progress, presentation_pause=pause)
        except ValueError as exc:                       # invalid input
            error_message = str(exc)
        except ProviderError as exc:                    # readable, token-free messages
            error_message = str(exc)
        except Exception as exc:                        # never show a traceback to the user
            log.error("Unexpected error: %s", type(exc).__name__)
            error_message = ("Something unexpected went wrong while processing the data. "
                             "Please try again or use the Demo Dataset.")
        if error_message:
            status.update(label="Pipeline stopped", state="error", expanded=True)
        else:
            status.update(label="Dataset ready", state="complete", expanded=False)

    if error_message:
        st.session_state.pop("result", None)
        st.error(f"❌ {error_message}")
        return

    csv_bytes = csv_name = csv_message = None
    excel_bytes = excel_name = excel_message = None

    if export_csv_selected:
        csv_bytes = dataframe_to_csv_bytes(result.df)
        ok, message = verify_csv_bytes(csv_bytes, result.df)
        csv_name = make_filename()
        csv_message = message if ok else f"⚠ {message}"

    if export_excel_selected:
        excel_bytes = dataframe_to_excel_bytes(result.df)
        ok, message = verify_excel_bytes(excel_bytes, result.df)
        excel_name = make_excel_filename()
        excel_message = message if ok else f"⚠ {message}"

    st.session_state["result"] = (
        result, csv_bytes, csv_name, csv_message,
        excel_bytes, excel_name, excel_message,
    )


# ---------------------------------------------------------------------------- page
def main() -> None:
    pause = render_sidebar()
    st.title("🛒 Shopee Product Data Crawler")
    st.caption("Keyword → collect → parse → clean → remove duplicates → DataFrame → export")

    with st.form("crawl_form"):
        keyword = st.text_input("Keyword", value="giày sneaker nam")
        col_count, col_sort, col_source = st.columns(3)
        count_options = [str(n) for n in PRODUCT_COUNT_OPTIONS] + ["Custom"]
        count_choice = col_count.selectbox(
            "Number of Products",
            count_options,
            index=PRODUCT_COUNT_OPTIONS.index(DEFAULT_PRODUCT_COUNT),
        )
        if count_choice == "Custom":
            limit = col_count.number_input(
                "Custom number", min_value=1, max_value=500, value=DEFAULT_PRODUCT_COUNT, step=1,
                help="Enter any number from 1 to 500. The system will never pad missing products.",
            )
        else:
            limit = int(count_choice)
        sort_label = col_sort.selectbox("Sort By", list(SORT_OPTIONS))
        source = col_source.selectbox("Data Source", [UI_SOURCE_DEMO, UI_SOURCE_LIVE])

        st.markdown("**Export format**")
        export_col1, export_col2 = st.columns(2)
        export_csv_selected = export_col1.checkbox("CSV", value=True)
        export_excel_selected = export_col2.checkbox("Excel (.xlsx)", value=False)
        st.caption("Choose CSV, Excel, or both. At least one format is required.")

        submitted = st.form_submit_button("🚀 Start Crawling", type="primary")

    if submitted:
        if not (export_csv_selected or export_excel_selected):
            st.error("❌ Please select at least one export format: CSV or Excel.")
        else:
            run_and_store(
                source, keyword, limit, SORT_OPTIONS[sort_label], pause,
                export_csv_selected, export_excel_selected,
            )

    if "result" in st.session_state:       # survives reruns (e.g. clicking Download)
        render_result(*st.session_state["result"])


main()
