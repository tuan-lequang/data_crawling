"""Streamlit UI. Contains no data logic: it collects input, calls run_pipeline(), shows results."""
import logging
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from config import (DEFAULT_PRODUCT_COUNT, DISPLAY_COLUMNS, EXPORT_DIR, MAX_PRODUCTS,
                    PRODUCT_COUNT_OPTIONS, SORT_OPTIONS, SOURCE_LIVE,
                    UI_SOURCE_DEMO, UI_SOURCE_LIVE)
from crawler.apify_shopee import ApifyShopeeProvider
from crawler.base import ProviderError
from crawler.demo_provider import DemoProvider
from pipeline import PipelineResult, run_pipeline
from utils.csv_exporter import (export_csv, export_excel, verify_csv_bytes,
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


def count_literal_question_marks(df: pd.DataFrame) -> int:
    """Count text cells containing literal '?', which can indicate loss before export.

    The exporter uses UTF-8-SIG and verifies round-trips. If a source/API has already
    replaced Vietnamese characters with '?', no encoding can infer the lost characters.
    """
    candidate_columns = [
        col for col in ("product_name", "shop_name", "shop_location", "category", "keyword")
        if col in df.columns
    ]
    if not candidate_columns:
        return 0
    return int(sum(
        df[col].astype("string").fillna("").str.contains("?", regex=False).sum()
        for col in candidate_columns
    ))


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

    questionable_text_cells = count_literal_question_marks(result.df)
    if questionable_text_cells:
        st.warning(
            f"Unicode data-quality check: {questionable_text_cells} text cell(s) contain a literal '?'. "
            "The exporter preserves Unicode with UTF-8-SIG and verifies the exported text. "
            "If a Vietnamese character was already replaced by '?' in the source/input, "
            "it cannot be reconstructed reliably during export."
        )

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
    elif csv_message:
        st.warning(csv_message)

    if excel_bytes is not None and excel_name is not None:
        st.download_button("⬇ Download Excel", data=excel_bytes, file_name=excel_name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="download_excel")
        if excel_message:
            st.caption(excel_message)
    elif excel_message:
        st.warning(excel_message)


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
    export_time = datetime.now()  # matching basename when both CSV and Excel are selected

    if export_csv_selected:
        try:
            # Save a project copy automatically, then serve the same file through the browser button.
            csv_path = export_csv(result.df, EXPORT_DIR, now=export_time)
            csv_bytes = csv_path.read_bytes()
            csv_name = csv_path.name
            ok, message = verify_csv_bytes(csv_bytes, result.df)
            csv_message = (message if ok else f"⚠ {message}") + f" Saved to project: exports/{csv_name}"
        except Exception as exc:
            log.error("CSV export failed: %s", type(exc).__name__)
            csv_message = "CSV could not be saved to the project exports folder. Check folder permissions."

    if export_excel_selected:
        try:
            excel_path = export_excel(result.df, EXPORT_DIR, now=export_time)
            excel_bytes = excel_path.read_bytes()
            excel_name = excel_path.name
            ok, message = verify_excel_bytes(excel_bytes, result.df)
            excel_message = (message if ok else f"⚠ {message}") + f" Saved to project: exports/{excel_name}"
        except Exception as exc:
            log.error("Excel export failed: %s", type(exc).__name__)
            excel_message = "Excel could not be saved to the project exports folder. Check folder permissions."

    st.session_state["result"] = (
        result, csv_bytes, csv_name, csv_message,
        excel_bytes, excel_name, excel_message,
    )


# ---------------------------------------------------------------------------- page
def main() -> None:
    pause = render_sidebar()
    st.title("🛒 Shopee Product Data Crawler")
    st.caption("Keyword → collect → parse → clean → remove duplicates → DataFrame → export")

    keyword = st.text_input("Keyword", value="giày sneaker nam")
    col_count, col_sort, col_source = st.columns(3)

    count_options = [str(n) for n in PRODUCT_COUNT_OPTIONS] + ["Custom"]
    count_choice = col_count.selectbox(
        "Number of Products",
        count_options,
        index=PRODUCT_COUNT_OPTIONS.index(DEFAULT_PRODUCT_COUNT),
        key="product_count_choice",
    )
    if count_choice == "Custom":
        # This widget is outside a Streamlit form, so it appears as soon as Custom is selected.
        if "custom_product_count" not in st.session_state:
            st.session_state["custom_product_count"] = DEFAULT_PRODUCT_COUNT
        limit = int(col_count.number_input(
            "Custom number",
            min_value=1,
            max_value=MAX_PRODUCTS,
            step=1,
            key="custom_product_count",
            help=f"Enter any whole number from 1 to {MAX_PRODUCTS} before starting the crawl.",
        ))
    else:
        limit = int(count_choice)

    sort_label = col_sort.selectbox("Sort By", list(SORT_OPTIONS), key="sort_choice")
    source = col_source.selectbox("Data Source", [UI_SOURCE_DEMO, UI_SOURCE_LIVE], key="data_source_choice")

    st.markdown("**Export format**")
    export_col1, export_col2 = st.columns(2)
    export_csv_selected = export_col1.checkbox("CSV", value=True, key="export_csv")
    export_excel_selected = export_col2.checkbox("Excel (.xlsx)", value=False, key="export_excel")
    st.caption("Choose CSV, Excel, or both. Files are also saved automatically to the project’s exports/ folder.")

    submitted = st.button("🚀 Start Crawling", type="primary", key="start_crawling")

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
