"""Streamlit UI for product crawling and offline synthetic review exploration."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from config import (
    DEFAULT_PRODUCT_COUNT, DEFAULT_REVIEW_COUNT, DEFAULT_REVIEW_FIELDS,
    DISPLAY_COLUMNS, EXPORT_DIR, MAX_PRODUCTS, MAX_REVIEWS_PER_PRODUCT,
    PREVIOUS_PRODUCT_FIELDS, PRODUCT_COUNT_OPTIONS, PRODUCT_FIELD_LABELS,
    REVIEW_CACHE_DIR, REVIEW_COLUMNS, REVIEW_COUNT_OPTIONS, REVIEW_FIELD_LABELS,
    SORT_OPTIONS, SOURCE_DEMO, SOURCE_LIVE, STANDARD_COLUMNS, UI_SOURCE_DEMO,
    UI_SOURCE_LIVE,
)
from crawler.apify_shopee import ApifyShopeeProvider
from crawler.base import ProviderError
from crawler.demo_provider import DemoProvider
from crawler.review_access import get_review_provider
from crawler.review_base import ReviewRequest, ReviewProviderError
from crawler.apify_reviews import estimate_memo23_max_charge
from pipeline import PipelineResult, run_pipeline
from review_pipeline import run_review_pipeline
from utils.cost_disclosure import demo_cost_message
from utils.csv_exporter import export_csv, export_excel, verify_csv_bytes, verify_excel_bytes
from utils.field_selection import select_columns, selection_matches
from utils.review_cache import ReviewCache
from utils.review_exporter import export_review_csv, export_review_excel
from utils.validators import validate_review_count, validate_selected_columns

load_dotenv()
log = logging.getLogger(__name__)

st.set_page_config(page_title="Shopee Product Data Crawler", page_icon="🛒", layout="wide")

PRODUCT_PRESET_ALL = "All 20 (default)"
PRODUCT_PRESET_PREVIOUS = "Previous table view"
PRODUCT_PRESET_CUSTOM = "Custom"
PRODUCT_FIELD_KEY_PREFIX = "product_field__"
REVIEW_FIELD_KEY_PREFIX = "review_field__"


def _product_field_key(column: str) -> str:
    return f"{PRODUCT_FIELD_KEY_PREFIX}{column}"


def _review_field_key(column: str) -> str:
    return f"{REVIEW_FIELD_KEY_PREFIX}{column}"


def _init_selection_state() -> None:
    if "product_fields_preset" not in st.session_state:
        st.session_state["product_fields_preset"] = PRODUCT_PRESET_ALL
    for column in STANDARD_COLUMNS:
        st.session_state.setdefault(_product_field_key(column), True)
    st.session_state.setdefault("product_select_all", True)

    for column in REVIEW_COLUMNS:
        st.session_state.setdefault(_review_field_key(column), column in DEFAULT_REVIEW_FIELDS)
    st.session_state.setdefault("review_select_all", all(st.session_state[_review_field_key(c)] for c in REVIEW_COLUMNS))
    st.session_state.setdefault("enable_review_viewing", False)
    st.session_state.setdefault("review_count_choice", str(DEFAULT_REVIEW_COUNT))
    st.session_state.setdefault("custom_review_count", DEFAULT_REVIEW_COUNT)


def _selected_product_fields() -> list[str]:
    return [column for column in STANDARD_COLUMNS if st.session_state.get(_product_field_key(column), False)]


def _selected_review_fields() -> list[str]:
    return [column for column in REVIEW_COLUMNS if st.session_state.get(_review_field_key(column), False)]


def _apply_product_preset() -> None:
    preset = st.session_state.get("product_fields_preset", PRODUCT_PRESET_ALL)
    if preset == PRODUCT_PRESET_ALL:
        chosen = set(STANDARD_COLUMNS)
    elif preset == PRODUCT_PRESET_PREVIOUS:
        chosen = set(PREVIOUS_PRODUCT_FIELDS)
    else:
        return
    for column in STANDARD_COLUMNS:
        st.session_state[_product_field_key(column)] = column in chosen
    st.session_state["product_select_all"] = len(chosen) == len(STANDARD_COLUMNS)


def _product_select_all_changed() -> None:
    selected = bool(st.session_state.get("product_select_all", False))
    for column in STANDARD_COLUMNS:
        st.session_state[_product_field_key(column)] = selected
    st.session_state["product_fields_preset"] = PRODUCT_PRESET_ALL if selected else PRODUCT_PRESET_CUSTOM


def _sync_product_preset() -> None:
    selected = _selected_product_fields()
    st.session_state["product_select_all"] = len(selected) == len(STANDARD_COLUMNS)
    if selection_matches(selected, STANDARD_COLUMNS):
        st.session_state["product_fields_preset"] = PRODUCT_PRESET_ALL
    elif selection_matches(selected, PREVIOUS_PRODUCT_FIELDS):
        st.session_state["product_fields_preset"] = PRODUCT_PRESET_PREVIOUS
    else:
        st.session_state["product_fields_preset"] = PRODUCT_PRESET_CUSTOM


def _review_select_all_changed() -> None:
    selected = bool(st.session_state.get("review_select_all", False))
    for column in REVIEW_COLUMNS:
        st.session_state[_review_field_key(column)] = selected


def _sync_review_select_all() -> None:
    st.session_state["review_select_all"] = len(_selected_review_fields()) == len(REVIEW_COLUMNS)


def render_sidebar() -> bool:
    """Returns True if the presentation pause is enabled."""
    with st.sidebar:
        st.header("Settings")
        if ApifyShopeeProvider.is_configured():
            st.success("Apify token: configured ✅")
        else:
            st.warning("Apify token: not configured ❌\n\nLive mode is unavailable. Demo Dataset works without it.")
        st.caption("The token is read from the `.env` file and is never displayed.")
        pause = st.checkbox(
            "Presentation pause",
            help="Adds a short pause after each local processing stage so an audience can follow. "
                 "It does not slow down the Apify request.",
            key="presentation_pause",
        )
        st.divider()
        st.caption("**Live product** mode runs the existing Apify scraper and uses your Apify credits. "
                   "**Demo** mode is local, free and offline.")
    return pause


def count_literal_question_marks(df: pd.DataFrame) -> int:
    """Count cells containing '?' which can indicate source-side text loss."""
    candidate_columns = [col for col in ("product_name", "shop_name", "shop_location", "category", "keyword") if col in df.columns]
    if not candidate_columns:
        return 0
    return int(sum(df[col].astype("string").fillna("").str.contains("?", regex=False).sum() for col in candidate_columns))


def _display_product_frame(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={c: PRODUCT_FIELD_LABELS.get(c, c) for c in df.columns})


def _product_column_config(columns: list[str]) -> dict:
    config = {}
    if "price" in columns:
        config[PRODUCT_FIELD_LABELS["price"]] = st.column_config.NumberColumn("Price (₫)", format="%d")
    if "original_price" in columns:
        config[PRODUCT_FIELD_LABELS["original_price"]] = st.column_config.NumberColumn("Original Price (₫)", format="%d")
    if "price_min" in columns:
        config[PRODUCT_FIELD_LABELS["price_min"]] = st.column_config.NumberColumn("Minimum Price (₫)", format="%d")
    if "price_max" in columns:
        config[PRODUCT_FIELD_LABELS["price_max"]] = st.column_config.NumberColumn("Maximum Price (₫)", format="%d")
    if "discount_pct" in columns:
        config[PRODUCT_FIELD_LABELS["discount_pct"]] = st.column_config.NumberColumn("Discount %", format="%d%%")
    if "sold" in columns:
        config[PRODUCT_FIELD_LABELS["sold"]] = st.column_config.NumberColumn("Sold", format="%d")
    if "rating" in columns:
        config[PRODUCT_FIELD_LABELS["rating"]] = st.column_config.NumberColumn("Rating", format="%.2f")
    if "product_url" in columns:
        config[PRODUCT_FIELD_LABELS["product_url"]] = st.column_config.LinkColumn("Product URL")
    if "image_url" in columns:
        config[PRODUCT_FIELD_LABELS["image_url"]] = st.column_config.LinkColumn("Image URL")
    return config


def _safe_id(value) -> str:
    if value is None or value is pd.NA:
        return ""
    text = str(value).strip()
    return "" if text in {"", "<NA>", "nan", "None"} else text


def _review_button_key(product_id: str, index: int) -> str:
    digest = hashlib.sha256(product_id.encode("utf-8")).hexdigest()[:10]
    return f"view_reviews_{digest}_{index}"


def _open_reviews(row: pd.Series) -> None:
    st.session_state["review_target"] = {
        "product_id": _safe_id(row.get("product_id")),
        "shop_id": _safe_id(row.get("shop_id")),
        "product_name": str(row.get("product_name") or "Unnamed product"),
        "product_url": _safe_id(row.get("product_url")),
    }
    st.session_state["current_view"] = "reviews"
    st.session_state.pop("active_review_result", None)
    st.session_state.pop("active_review_exports", None)
    st.rerun()


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
            "UTF-8-SIG preserves Unicode, but cannot reconstruct characters already lost in the source."
        )

    selected = st.session_state.get("result_product_fields", list(STANDARD_COLUMNS))
    try:
        visible_df = select_columns(result.df, selected, STANDARD_COLUMNS)
    except ValueError:
        visible_df = result.df.copy()
        selected = list(STANDARD_COLUMNS)
    display_df = _display_product_frame(visible_df)
    st.subheader("Data preview")
    st.dataframe(display_df, hide_index=True, width="stretch", column_config=_product_column_config(selected))
    st.caption("Empty cells mean the source did not provide that value; nothing is estimated. "
               f"Sort: {result.sort} · Source: {result.source_name}")
    with st.expander("Full internal dataset"):
        st.caption("This view keeps all 20 standard columns internally, even if some are hidden from the selected output.")
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

    st.divider()
    st.subheader("Product review explorer")
    if not st.session_state.get("result_review_enabled", False):
        st.caption("Review viewing was not enabled before this crawl. Enable it in Review settings and run the product crawl again.")
        return
    if result.df.empty:
        st.caption("No products are available to open.")
        return

    page_size = 10
    page_count = max(1, (len(result.df) + page_size - 1) // page_size)
    page_choice = st.selectbox(
        "Product page",
        options=list(range(1, page_count + 1)),
        format_func=lambda x: f"Page {x} of {page_count}",
        key="product_results_page",
    )
    start = (page_choice - 1) * page_size
    page_df = result.df.iloc[start:start + page_size]
    for relative_index, (_, row) in enumerate(page_df.iterrows()):
        col_info, col_action = st.columns([6, 1])
        product_name = _safe_id(row.get("product_name")) or "Unnamed product"
        product_id = _safe_id(row.get("product_id"))
        shop_id = _safe_id(row.get("shop_id"))
        col_info.markdown(f"**{product_name}**")
        col_info.caption(f"Product ID: {product_id or 'unavailable'} · Shop ID: {shop_id or 'unavailable'}")
        index = start + relative_index
        disabled = not (product_id and shop_id)
        if col_action.button("View reviews", key=_review_button_key(product_id or f"missing-{index}", index), disabled=disabled):
            _open_reviews(row)
        if disabled:
            col_action.caption("IDs missing")


def run_and_store(
    source: str, keyword: str, limit: int, sort: str, pause: bool,
    export_csv_selected: bool, export_excel_selected: bool,
    selected_product_fields: list[str], review_enabled: bool,
    review_limit: int, selected_review_fields: list[str],
) -> None:
    provider = ApifyShopeeProvider() if source == UI_SOURCE_LIVE else DemoProvider()
    error_message = None
    with st.status("Running data pipeline...", expanded=True) as status:
        live_line = None

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
        except ValueError as exc:
            error_message = str(exc)
        except ProviderError as exc:
            error_message = str(exc)
        except Exception as exc:
            log.error("Unexpected product-pipeline error: %s", type(exc).__name__)
            error_message = "Something unexpected went wrong while processing the data. Please try again or use the Demo Dataset."
        if error_message:
            status.update(label="Pipeline stopped", state="error", expanded=True)
        else:
            status.update(label="Dataset ready", state="complete", expanded=False)

    if error_message:
        for key in ("result", "result_product_fields", "result_review_fields", "result_review_enabled",
                    "result_review_count", "result_export_formats", "review_target", "active_review_result",
                    "active_review_exports"):
            st.session_state.pop(key, None)
        st.session_state["current_view"] = "products"
        st.error(f"❌ {error_message}")
        return

    csv_bytes = csv_name = csv_message = None
    excel_bytes = excel_name = excel_message = None
    export_time = datetime.now()
    if export_csv_selected:
        try:
            csv_path = export_csv(result.df, EXPORT_DIR, now=export_time, columns=selected_product_fields)
            csv_bytes = csv_path.read_bytes()
            csv_name = csv_path.name
            ok, message = verify_csv_bytes(csv_bytes, result.df, selected_product_fields)
            csv_message = (message if ok else f"⚠ {message}") + f" Saved to project: data/exports/{csv_name}"
        except Exception as exc:
            log.error("CSV export failed: %s", type(exc).__name__)
            csv_message = "CSV could not be saved to data/exports. Check folder permissions and selected fields."
    if export_excel_selected:
        try:
            excel_path = export_excel(result.df, EXPORT_DIR, now=export_time, columns=selected_product_fields)
            excel_bytes = excel_path.read_bytes()
            excel_name = excel_path.name
            ok, message = verify_excel_bytes(excel_bytes, result.df, selected_product_fields)
            excel_message = (message if ok else f"⚠ {message}") + f" Saved to project: data/exports/{excel_name}"
        except Exception as exc:
            log.error("Excel export failed: %s", type(exc).__name__)
            excel_message = "Excel could not be saved to data/exports. Check folder permissions and selected fields."

    st.session_state["result"] = (
        result, csv_bytes, csv_name, csv_message,
        excel_bytes, excel_name, excel_message,
    )
    st.session_state["result_product_fields"] = list(selected_product_fields)
    st.session_state["result_review_fields"] = list(selected_review_fields)
    st.session_state["result_review_enabled"] = bool(review_enabled)
    st.session_state["result_review_count"] = int(review_limit)
    st.session_state["result_export_formats"] = {"csv": bool(export_csv_selected), "excel": bool(export_excel_selected)}
    st.session_state["current_view"] = "products"
    st.session_state.pop("review_target", None)
    st.session_state.pop("active_review_result", None)
    st.session_state.pop("active_review_exports", None)
    st.session_state["product_results_page"] = 1


def _review_cache_identity(target: dict, count: int, include_images: bool, source: str = "") -> str:
    return "|".join((source, str(target.get("product_id")), str(target.get("shop_id")), str(count), str(bool(include_images))))


def _safe_df_records(df: pd.DataFrame) -> list[dict]:
    return df.astype(object).where(pd.notna(df), None).to_dict(orient="records")


def _build_review_exports(active: dict, product_id: str, selected_fields: list[str], formats: dict) -> dict:
    """Write selected review exports once per active review result; raw provider rows are never exported."""
    exports: dict = {}
    df = pd.DataFrame(active.get("records", []), columns=REVIEW_COLUMNS)
    if df.empty:
        return exports
    if formats.get("csv"):
        path = export_review_csv(df, product_id, EXPORT_DIR, columns=selected_fields)
        exports["csv"] = {"name": path.name, "bytes": path.read_bytes(), "path": str(path)}
    if formats.get("excel"):
        path = export_review_excel(df, product_id, EXPORT_DIR, columns=selected_fields)
        exports["excel"] = {"name": path.name, "bytes": path.read_bytes(), "path": str(path)}
    return exports


def render_review_page() -> None:
    st.title("Customer Reviews")
    target = st.session_state.get("review_target") or {}
    result_tuple = st.session_state.get("result")
    if not result_tuple:
        st.info("No product dataset is available. Return to the crawler and run a product search first.")
        if st.button("← Back to products", key="review_back_no_result"):
            st.session_state["current_view"] = "products"
            st.rerun()
        return
    product_result: PipelineResult = result_tuple[0]
    source = product_result.data_source
    c_back, c_clear = st.columns([1, 2])
    if c_back.button("← Back to products", key="review_back"):
        st.session_state["current_view"] = "products"
        st.session_state.pop("review_target", None)
        st.rerun()
    if c_clear.button("Clear local review cache and return", key="clear_review_cache"):
        removed = ReviewCache().clear()
        st.session_state.pop("active_review_result", None)
        st.session_state.pop("active_review_exports", None)
        st.session_state["current_view"] = "products"
        st.session_state.pop("review_target", None)
        st.success(f"Removed {removed} local cached review file(s).")
        st.rerun()

    product_id = _safe_id(target.get("product_id"))
    shop_id = _safe_id(target.get("shop_id"))
    product_name = str(target.get("product_name") or "Unnamed product")
    st.subheader(product_name)
    st.caption(f"Product ID: {product_id or 'unavailable'} · Shop ID: {shop_id or 'unavailable'} · Product source: {source}")

    max_reviews = int(st.session_state.get("result_review_count", DEFAULT_REVIEW_COUNT))
    selected_fields = st.session_state.get("result_review_fields", list(DEFAULT_REVIEW_FIELDS))
    formats = st.session_state.get("result_export_formats", {"csv": True, "excel": False})
    include_images = "review_images" in selected_fields
    request = ReviewRequest(
        product_id=product_id,
        shop_id=shop_id,
        product_name=product_name,
        max_reviews=max_reviews,
        include_review_images=include_images,
        product_url=_safe_id(target.get("product_url")) or None,
    )
    cache = ReviewCache()
    provider = get_review_provider(source)
    active_key = _review_cache_identity(target, max_reviews, include_images, provider.data_source)
    active = st.session_state.get("active_review_result")

    def remember_result(pipeline_result) -> dict:
        payload = {
            "key": active_key,
            "records": _safe_df_records(pipeline_result.df),
            "requested": pipeline_result.requested,
            "fetched": pipeline_result.fetched,
            "redacted_text_cells": pipeline_result.redacted_text_cells,
            "duplicates_removed": pipeline_result.duplicates_removed,
            "from_cache": pipeline_result.from_cache,
            "source_name": pipeline_result.source_name,
            "attribution": pipeline_result.attribution,
            "ordering": pipeline_result.ordering,
            "coverage": pipeline_result.coverage,
            "warnings": pipeline_result.warnings,
        }
        st.session_state["active_review_result"] = payload
        st.session_state.pop("active_review_exports", None)
        return payload

    if source == SOURCE_DEMO:
        st.info("🧪 SYNTHETIC DEMO REVIEWS — these are generated locally and are not customer reviews from Shopee.")
        st.caption(demo_cost_message())
        if not active or active.get("key") != active_key:
            try:
                pipeline_result = run_review_pipeline(provider, request, cache=cache)
                active = remember_result(pipeline_result)
            except (ReviewProviderError, ValueError) as exc:
                st.warning(str(exc))
                return
            except Exception as exc:
                log.error("Unexpected review-pipeline error: %s", type(exc).__name__)
                st.error("The review demo could not be prepared. Please return to products and try again.")
                return
    else:
        st.warning("LIVE REVIEWS — this invokes the third-party memo23 Actor and may incur Apify charges. "
                   "The Actor reads a shop-level review feed, so coverage for one product can be partial and is not guaranteed to be newest-first.")
        if not product_id or not shop_id:
            st.error("This product has no valid product_id/shop_id, so review retrieval cannot be safely attributed.")
            return

        if not active or active.get("key") != active_key:
            # Check the local cache before presenting an actionable paid-fetch button.
            cached = cache.get(request, provider.data_source)
            if cached is not None:
                try:
                    pipeline_result = run_review_pipeline(provider, request, cache=cache)
                    active = remember_result(pipeline_result)
                    st.info("Loaded the previously cached, redacted review sample. No new Actor run was started.")
                except (ReviewProviderError, ValueError) as exc:
                    st.warning(str(exc))
                    return
            else:
                try:
                    estimate, charge_cap = estimate_memo23_max_charge(max_reviews)
                except ValueError as exc:
                    st.error(str(exc))
                    return
                st.markdown("**Cost estimate before fetching**")
                st.write(f"Requested maximum: **{max_reviews} written reviews**")
                st.write(f"Estimated charge using the Actor's published Free-tier rate: **${estimate:.4f} USD**")
                st.write(f"Per-run charge cap sent to Apify: **${charge_cap:.4f} USD**")
                st.caption("Estimate assumptions: $3.50 per 1,000 delivered review rows and an assumed $0.005 start event. "
                           "The start-event billing unit and your account's applicable rate are not independently confirmed. "
                           "Prices can change; check the Actor Pricing tab. The request fails closed if the installed Apify client cannot send a charge cap.")
                st.caption("Only written comments are requested. The Actor may return fewer reviews than requested because it reads a shop-level feed and filters by product ID.")
                token_configured = ApifyShopeeProvider.is_configured()
                if not token_configured:
                    st.error("Apify API token is not configured. Check APIFY_API_TOKEN in your .env file before fetching Live reviews.")
                confirm_key = "confirm_live_reviews_" + hashlib.sha256(f"{shop_id}:{product_id}".encode("utf-8")).hexdigest()[:12]
                confirmed = st.checkbox(
                    "I understand this starts a third-party Apify Actor run and may incur charges.",
                    key=confirm_key,
                )
                fetch_clicked = st.button(
                    f"Fetch up to {max_reviews} Live reviews (cap ${charge_cap:.4f})",
                    type="primary", key="fetch_live_reviews", disabled=(not confirmed or not token_configured),
                )
                if not fetch_clicked:
                    st.caption("No Live review request has been made yet. Choose Fetch only when you are ready.")
                    return

                try:
                    with st.status("Fetching Live reviews from Apify...", expanded=True) as status:
                        progress_line = st.empty()

                        def on_review_status(message: str) -> None:
                            progress_line.write("⏳ " + message)

                        pipeline_result = run_review_pipeline(
                            provider, request, cache=cache, on_status=on_review_status
                        )
                        status.update(label="Review dataset ready", state="complete", expanded=False)
                    active = remember_result(pipeline_result)
                except (ReviewProviderError, ValueError) as exc:
                    log.warning("Live review fetch stopped (%s)", type(exc).__name__)
                    st.error(str(exc))
                    return
                except Exception as exc:
                    log.error("Unexpected Live review error: %s", type(exc).__name__)
                    st.error("The Live review request failed unexpectedly. Check Apify Console; no automatic retry was performed.")
                    return

    if not active or active.get("key") != active_key:
        st.info("No review result is available yet. Choose Fetch reviews above for Live data, or use Demo mode.")
        return

    review_df = pd.DataFrame(active.get("records", []), columns=REVIEW_COLUMNS)
    m1, m2, m3 = st.columns(3)
    m1.metric("Reviews returned", len(review_df))
    m2.metric("Requested maximum", active.get("requested", max_reviews))
    m3.metric("Duplicates removed", active.get("duplicates_removed", 0))
    st.caption(f"Provider: {active.get('source_name')} · {active.get('coverage')} · "
               f"Ordering: {active.get('ordering')} · Cache: {'hit' if active.get('from_cache') else 'miss'}")
    if active.get("redacted_text_cells", 0):
        st.warning(f"Automatic privacy redaction was applied to {active['redacted_text_cells']} text field(s). Original text is not shown or stored locally.")
    for warning in active.get("warnings", []):
        st.warning(warning)

    try:
        visible_review_df = select_columns(review_df, selected_fields, REVIEW_COLUMNS)
    except ValueError:
        st.error("No review output fields are selected. Return to the crawler and enable at least one review field.")
        return
    visible_review_df = visible_review_df.rename(columns={c: REVIEW_FIELD_LABELS.get(c, c) for c in visible_review_df.columns})
    if review_df.empty:
        if source == SOURCE_DEMO:
            st.info("The synthetic provider has no review sample for this product. No rows were invented to fill the requested count.")
        else:
            st.info("The Live source returned no product-attributed written reviews. This can happen when the shop feed does not include reviews for this product or the source is temporarily limited. No data was fabricated.")
    else:
        st.dataframe(visible_review_df, hide_index=True, width="stretch")

    active_exports = st.session_state.get("active_review_exports")
    if active_exports is None:
        try:
            active_exports = _build_review_exports(active, product_id, selected_fields, formats)
            st.session_state["active_review_exports"] = active_exports
        except Exception as exc:
            log.error("Review export failed: %s", type(exc).__name__)
            active_exports = {}
            st.session_state["active_review_exports"] = active_exports
            st.warning("Review data could not be saved under data/exports. Check folder permissions and field selection.")
    if active_exports:
        st.subheader("Review exports")
        if "csv" in active_exports:
            item = active_exports["csv"]
            st.download_button("⬇ Download reviews CSV", data=item["bytes"], file_name=item["name"],
                               mime="text/csv", key="download_reviews_csv")
            st.caption(f"Saved to project: data/exports/{item['name']}")
        if "excel" in active_exports:
            item = active_exports["excel"]
            st.download_button("⬇ Download reviews Excel", data=item["bytes"], file_name=item["name"],
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="download_reviews_excel")
            st.caption(f"Saved to project: data/exports/{item['name']}")


def _render_product_fields() -> None:
    with st.expander("Product output fields", expanded=False):
        st.radio(
            "Product field preset",
            [PRODUCT_PRESET_ALL, PRODUCT_PRESET_PREVIOUS, PRODUCT_PRESET_CUSTOM],
            key="product_fields_preset",
            horizontal=True,
            on_change=_apply_product_preset,
        )
        st.checkbox("Select all product fields", key="product_select_all", on_change=_product_select_all_changed)
        cols = st.columns(4)
        for index, column in enumerate(STANDARD_COLUMNS):
            cols[index % 4].checkbox(
                PRODUCT_FIELD_LABELS.get(column, column),
                key=_product_field_key(column),
                on_change=_sync_product_preset,
            )
        chosen = _selected_product_fields()
        st.caption(f"Selected {len(chosen)} of {len(STANDARD_COLUMNS)} product fields. Internal IDs remain available for linking and deduplication.")


def _render_review_settings() -> tuple[bool, int, list[str]]:
    with st.expander("Review settings", expanded=False):
        enabled = st.checkbox("Enable review viewing", key="enable_review_viewing")
        if not enabled:
            st.caption("Off by default. Demo review data is loaded only when you open a product's review page.")
            return False, DEFAULT_REVIEW_COUNT, _selected_review_fields()

        st.caption("Demo reviews work offline. For Live products, reviews are fetched only after a separate confirmation on the review page and may incur Apify charges.")
        count_options = [str(n) for n in REVIEW_COUNT_OPTIONS] + ["Custom"]
        choice = st.selectbox("Maximum reviews per product", count_options, key="review_count_choice")
        if choice == "Custom":
            review_limit = int(st.number_input(
                "Custom review count", min_value=1, max_value=MAX_REVIEWS_PER_PRODUCT,
                step=1, key="custom_review_count",
                help=f"Choose any whole number from 1 to {MAX_REVIEWS_PER_PRODUCT}.",
            ))
        else:
            review_limit = int(choice)

        st.markdown("**Review output fields**")
        st.checkbox("Select all review fields", key="review_select_all", on_change=_review_select_all_changed)
        cols = st.columns(3)
        for index, column in enumerate(REVIEW_COLUMNS):
            cols[index % 3].checkbox(
                REVIEW_FIELD_LABELS.get(column, column),
                key=_review_field_key(column),
                on_change=_sync_review_select_all,
            )
        chosen = _selected_review_fields()
        st.caption(f"Selected {len(chosen)} of {len(REVIEW_COLUMNS)} review fields. Review image URLs are excluded by default.")
        return True, validate_review_count(review_limit), chosen


def main() -> None:
    pause = render_sidebar()
    _init_selection_state()

    if st.session_state.get("current_view") == "reviews":
        render_review_page()
        return

    st.title("🛒 Shopee Product Data Crawler")
    st.caption("Keyword → collect → parse → clean → remove duplicates → DataFrame → CSV/Excel")
    keyword = st.text_input("Keyword", value="giày sneaker nam", key="keyword")
    col_count, col_sort, col_source = st.columns(3)
    count_options = [str(n) for n in PRODUCT_COUNT_OPTIONS] + ["Custom"]
    count_choice = col_count.selectbox(
        "Number of Products", count_options,
        index=PRODUCT_COUNT_OPTIONS.index(DEFAULT_PRODUCT_COUNT), key="product_count_choice",
    )
    if count_choice == "Custom":
        if "custom_product_count" not in st.session_state:
            st.session_state["custom_product_count"] = DEFAULT_PRODUCT_COUNT
        limit = int(col_count.number_input(
            "Custom number", min_value=1, max_value=MAX_PRODUCTS, step=1,
            key="custom_product_count", help=f"Enter any whole number from 1 to {MAX_PRODUCTS} before starting the crawl.",
        ))
    else:
        limit = int(count_choice)
    sort_label = col_sort.selectbox("Sort By", list(SORT_OPTIONS), key="sort_choice")
    source = col_source.selectbox("Data Source", [UI_SOURCE_DEMO, UI_SOURCE_LIVE], key="data_source_choice")

    st.markdown("**Export format**")
    export_col1, export_col2 = st.columns(2)
    export_csv_selected = export_col1.checkbox("CSV", value=True, key="export_csv")
    export_excel_selected = export_col2.checkbox("Excel (.xlsx)", value=False, key="export_excel")
    st.caption("Choose CSV, Excel, or both. Files are saved automatically under data/exports/ and remain available through download buttons.")

    _render_product_fields()
    review_enabled, review_limit, selected_review_fields = _render_review_settings()
    selected_product_fields = _selected_product_fields()

    submitted = st.button("🚀 Start Crawling", type="primary", key="start_crawling")
    if submitted:
        validation_error = None
        try:
            selected_product_fields = validate_selected_columns(selected_product_fields, STANDARD_COLUMNS, "product output")
            if review_enabled:
                selected_review_fields = validate_selected_columns(selected_review_fields, REVIEW_COLUMNS, "review output")
                review_limit = validate_review_count(int(review_limit))
            if not (export_csv_selected or export_excel_selected):
                raise ValueError("Please select at least one export format: CSV or Excel.")
        except ValueError as exc:
            validation_error = str(exc)
        if validation_error:
            st.error(f"❌ {validation_error}")
        else:
            run_and_store(
                source, keyword, limit, SORT_OPTIONS[sort_label], pause,
                export_csv_selected, export_excel_selected, selected_product_fields,
                review_enabled, review_limit, selected_review_fields,
            )

    if "result" in st.session_state:
        render_result(*st.session_state["result"])


main()
