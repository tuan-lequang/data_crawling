"""Live review provider backed by the documented memo23 Apify Actor.

The Actor is invoked only when the user explicitly clicks the Live review fetch
button. Raw rows are held in memory only, non-review fields are discarded, and
remote default storage is deleted best-effort after retrieval.
"""
from __future__ import annotations

import logging
import os
import re
import time
from decimal import Decimal
from datetime import timedelta
from typing import Any, Callable
from urllib.parse import urlparse

from config import (
    APIFY_MAX_RETRIES,
    APIFY_TOKEN_ENV,
    MEMO23_REVIEW_ACTOR_ID,
    MEMO23_REVIEW_COST_BUFFER_USD,
    MEMO23_REVIEW_POLL_SECS,
    MEMO23_REVIEW_RATE_PER_1000_USD,
    MEMO23_REVIEW_START_FEE_USD,
    MEMO23_REVIEW_TIMEOUT_SECS,
    MAX_REVIEW_RUN_CHARGE_USD,
)
from crawler.review_base import BaseReviewProvider, ReviewBatch, ReviewProviderError, ReviewRequest
from utils.cost_disclosure import CostModel, estimate_max_charge

log = logging.getLogger(__name__)

TERMINAL_OK = {"SUCCEEDED"}
TERMINAL_FAIL = {"FAILED", "ABORTED", "TIMED-OUT"}


def _field(obj: Any, name: str):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def memo23_cost_model() -> CostModel:
    """Published Free-tier estimate; user-visible copy states that pricing can change."""
    return CostModel(
        provider_name="memo23/shopee-reviews-scraper (published Free-tier estimate)",
        per_1000_delivered=MEMO23_REVIEW_RATE_PER_1000_USD,
        start_fee=MEMO23_REVIEW_START_FEE_USD,
        is_synthetic=False,
    )


def estimate_memo23_max_charge(review_count: int) -> tuple[float, float]:
    """Return (estimated amount, spend cap) using the conservative published Free rate.

    The $0.005 start event is only an estimate; the public pricing page does not
    unambiguously establish its billing unit. A configurable buffer is added to
    the Actor charge cap. Never silently run without the cap.
    """
    estimate = estimate_max_charge(review_count, memo23_cost_model())
    cap = min(float(MAX_REVIEW_RUN_CHARGE_USD), round(estimate + MEMO23_REVIEW_COST_BUFFER_USD, 6))
    if cap <= 0 or estimate > float(MAX_REVIEW_RUN_CHARGE_USD):
        raise ValueError("Requested review count exceeds the configured per-run cost cap.")
    return estimate, cap


def resolve_shopee_product_url(product_url: str | None, shop_id: str, product_id: str, market: str = "vn") -> tuple[str, bool]:
    """Return a verified Shopee product URL and whether it was constructed.

    The URL is used internally only for the review Actor; it never populates the
    product table's public product_url field. IDs must be numeric to avoid
    accidentally querying another product.
    """
    if market.lower() != "vn":
        raise ReviewProviderError("Live review fetching is currently configured for Shopee Vietnam only.")
    shop = str(shop_id).strip()
    product = str(product_id).strip()
    if not shop.isdigit() or not product.isdigit():
        raise ReviewProviderError("This product cannot be resolved for review retrieval because its IDs are missing or invalid.")

    if product_url:
        parsed = urlparse(str(product_url).strip())
        if parsed.scheme == "https" and parsed.hostname in {"shopee.vn", "www.shopee.vn"}:
            path = parsed.path
            match = re.search(r"/product/(\d+)/(\d+)(?:/|$)", path)
            if not match:
                match = re.search(r"-i\.(\d+)\.(\d+)(?:$|[/?])", path)
            if match and match.group(1) == shop and match.group(2) == product:
                return str(product_url).strip(), False

    # This format is explicitly accepted by the Actor input schema.
    return f"https://shopee.vn/product/{shop}/{product}", True


def build_memo23_input(request: ReviewRequest, product_url: str) -> dict[str, Any]:
    """Build the documented actor input. Zero is never emitted."""
    if isinstance(request.max_reviews, bool) or not isinstance(request.max_reviews, int) or request.max_reviews < 1:
        raise ValueError("Number of reviews must be a whole number greater than zero.")
    if request.max_reviews > 100:
        raise ValueError("The Live review limit is 100 per product in this version.")
    return {
        "startUrls": [product_url],
        "maxReviewsPerShop": request.max_reviews,
        "starRatings": ["5", "4", "3", "2", "1"],
        "onlyWithText": True,
        "onlyWithMedia": False,
        "includeShopSummary": True,
        "maxConcurrency": 1,
    }


def _default_client_factory(token: str):
    try:
        from apify_client import ApifyClient
    except ImportError:
        raise ReviewProviderError("The 'apify-client' package is missing. Run: python -m pip install -r requirements.txt") from None
    return ApifyClient(token, max_retries=APIFY_MAX_RETRIES)


def _api_error_message(exc: Exception) -> str | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        return None
    if status == 401:
        return "Apify rejected the API token. Check APIFY_API_TOKEN in your .env file."
    if status == 402:
        return "Apify reports a usage or billing limit. Check your remaining credits and plan."
    if status == 403:
        return "Apify denied access to the review Actor or resource. Check Actor access and token permissions."
    if status == 429:
        return "Apify rate limit reached. Wait a moment before trying again."
    if status >= 500:
        return "The review Actor service is temporarily unavailable. Try later or use Demo reviews."
    return "Apify rejected the review request. Check the product IDs and review Actor input requirements."


class Memo23ShopeeReviewProvider(BaseReviewProvider):
    """Collect a bounded sample of written reviews for one Shopee Vietnam product."""
    display_name = "Apify (memo23/shopee-reviews-scraper)"
    data_source = "live_apify_reviews_memo23"

    def __init__(
        self,
        token: str | None = None,
        client_factory: Callable[[str], Any] = _default_client_factory,
        timeout_secs: int = MEMO23_REVIEW_TIMEOUT_SECS,
        poll_secs: int = MEMO23_REVIEW_POLL_SECS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._token = token
        self._client_factory = client_factory
        self._timeout = int(timeout_secs)
        self._poll = int(poll_secs)
        self._clock = clock

    def _get_token(self) -> str:
        token = (self._token if self._token is not None else os.getenv(APIFY_TOKEN_ENV, "")).strip()
        if not token:
            raise ReviewProviderError("Apify API token is not configured. Check APIFY_API_TOKEN in the .env file.")
        return token

    def fetch(self, request: ReviewRequest, on_status: Callable[[str], None] | None = None) -> ReviewBatch:
        say = on_status or (lambda _message: None)
        estimate, charge_cap = estimate_memo23_max_charge(request.max_reviews)
        product_url, constructed = resolve_shopee_product_url(
            getattr(request, "product_url", None), request.shop_id, request.product_id, request.market
        )
        run_input = build_memo23_input(request, product_url)
        token = self._get_token()
        try:
            client = self._client_factory(token)
            return self._run_actor(client, run_input, request, say, estimate, charge_cap, constructed)
        except ReviewProviderError:
            raise
        except Exception as exc:
            log.warning("Apify review run failed (%s)", type(exc).__name__)
            message = _api_error_message(exc)
            if message:
                raise ReviewProviderError(message) from None
            if isinstance(exc, TimeoutError):
                raise ReviewProviderError("The Live review request timed out. No review data was shown; use Demo mode or retry later.") from None
            if isinstance(exc, (InvalidOperation, ValueError)):
                raise ReviewProviderError("The Live review request could not be prepared safely. Check the review settings.") from None
            raise ReviewProviderError("Unable to reach the Apify review Actor. Check your connection and try again.") from None

    def _run_actor(self, client, run_input: dict, request: ReviewRequest, say, estimate: float,
                   charge_cap: float, constructed_url: bool) -> ReviewBatch:
        say("Preparing a capped Live review request...")
        say(f"Starting {MEMO23_REVIEW_ACTOR_ID} (maximum charge cap: ${charge_cap:.4f})...")
        try:
            run = client.actor(MEMO23_REVIEW_ACTOR_ID).start(
                run_input=run_input,
                run_timeout=timedelta(seconds=self._timeout),
                max_items=request.max_reviews + 2,  # allow one summary row plus a small error allowance
                max_total_charge_usd=Decimal(str(charge_cap)),
            )
        except TypeError:
            # Fail closed: never retry the run without a spend limit.
            raise ReviewProviderError(
                "The installed apify-client does not support the required per-run charge cap. "
                "Update apify-client from requirements.txt before using Live reviews."
            ) from None

        run_id = _field(run, "id")
        if not run_id:
            raise ReviewProviderError("Apify returned an unexpected response without a run ID.")
        run_client = client.run(run_id)
        started = self._clock()
        while True:
            current = run_client.wait_for_finish(wait_duration=timedelta(seconds=self._poll))
            if current is None:
                raise ReviewProviderError("The Apify review run is no longer available.")
            status = str(_field(current, "status") or "UNKNOWN")
            elapsed = int(self._clock() - started)
            say(f"Review Actor status: {status} ({elapsed}s elapsed)")
            if status in TERMINAL_OK or status in TERMINAL_FAIL:
                run = current
                break
            if self._clock() - started > self._timeout:
                try:
                    run_client.abort()
                except Exception:
                    log.warning("Could not abort the timed-out review Actor run.")
                cleanup_ok = self._delete_remote_storage(
                    client,
                    _field(current, "default_dataset_id") or _field(current, "defaultDatasetId"),
                    _field(current, "default_key_value_store_id") or _field(current, "defaultKeyValueStoreId"),
                )
                message = "The Live review Actor exceeded its time limit and was aborted."
                if not cleanup_ok:
                    message += f" Remote storage cleanup was not confirmed for run {run_id}; delete its output dataset in Apify Console."
                raise ReviewProviderError(message)

        if status in TERMINAL_FAIL:
            cleanup_ok = self._delete_remote_storage(
                client,
                _field(run, "default_dataset_id") or _field(run, "defaultDatasetId"),
                _field(run, "default_key_value_store_id") or _field(run, "defaultKeyValueStoreId"),
            )
            message = f"The Live review Actor ended with status {status}. Check the run in Apify Console."
            if not cleanup_ok:
                message += f" Remote storage cleanup was not confirmed for run {run_id}; delete its output dataset in Apify Console."
            raise ReviewProviderError(message)

        dataset_id = _field(run, "default_dataset_id") or _field(run, "defaultDatasetId")
        key_value_store_id = _field(run, "default_key_value_store_id") or _field(run, "defaultKeyValueStoreId")
        if not dataset_id:
            raise ReviewProviderError("The review Actor completed but returned no dataset ID.")

        say("Reading review rows and discarding summary/personal identifier fields...")
        try:
            raw_items = list(client.dataset(dataset_id).iterate_items(limit=request.max_reviews + 2))
        except Exception:
            cleanup_ok = self._delete_remote_storage(client, dataset_id, key_value_store_id)
            message = "The review Actor finished, but its result dataset could not be read."
            if not cleanup_ok:
                message += f" Remote storage cleanup was not confirmed for run {run_id}; delete dataset {dataset_id} in Apify Console."
            raise ReviewProviderError(message) from None

        review_rows: list[dict] = []
        without_product_id = 0
        summary_rows: list[dict] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").lower()
            if item_type == "shop-summary":
                summary_rows.append(item)
                continue
            if item_type != "review":
                if item.get("error") or item.get("errorKind"):
                    log.info("Review Actor returned a non-review error row.")
                continue
            product_id = item.get("productId") or item.get("itemId") or item.get("product_id")
            if product_id is None or not str(product_id).strip():
                without_product_id += 1
                continue
            # Only canonical product-attributed rows pass through to the local parser.
            # Whitelist only fields required by the canonical parser. In particular,
            # reviewerName, orderId, buyerRegion and author-related fields never leave
            # this adapter, even transiently in ReviewBatch/session state.
            allowed = (
                "reviewId", "productId", "shopId", "rating", "text", "createdAt",
                "variation", "sellerReply", "imageUrls", "type",
            )
            row = {key: item.get(key) for key in allowed if key in item}
            row["data_source"] = self.data_source
            review_rows.append(row)

        cleanup_ok = self._delete_remote_storage(client, dataset_id, key_value_store_id)
        summary = summary_rows[0] if summary_rows else {}
        warnings = [
            "The Actor reads reviews from a shop-level feed. Product attribution is checked, but coverage may be partial and results are not guaranteed to be the newest reviews.",
            f"Estimated cost at the published Free-tier rate: about ${estimate:.4f}; the request used a maximum charge cap of ${charge_cap:.4f}. Actual pricing and billing may differ; check Apify Console.",
        ]
        if constructed_url:
            warnings.append("The source product URL was empty or did not match the IDs, so a documented internal request URL was constructed from shop_id and product_id. The product table's product_url was not changed.")
        if without_product_id:
            warnings.append(f"{without_product_id} review row(s) without a product ID were ignored to avoid misattribution.")
        coverage_text = str(summary.get("coverage") or "sample from shop-level review feed")
        if summary.get("reviewsCollected") is not None:
            coverage_text += f"; Actor summary reports {summary.get('reviewsCollected')} review row(s) collected across the feed"
        if not cleanup_ok:
            warnings.append(
                f"Apify dataset cleanup could not be confirmed for run {run_id} (dataset {dataset_id}). "
                "Open Apify Console and delete the run's output dataset manually. Remote logs or backups may have separate retention."
            )
        else:
            warnings.append("Apify confirmed deletion of the available default output storage after retrieval; this does not verify backup or log retention.")
        if not review_rows:
            warnings.append("The Actor returned no product-attributed review rows. Its product coverage can be partial; no rows were invented.")

        # Only review-shaped rows with a product ID escape the provider. Summary and
        # error payloads, author fields and order IDs are not returned to the pipeline.
        return ReviewBatch(
            records=review_rows,
            source_name=self.display_name,
            attribution="productId checked against the requested product",
            ordering="star-stratified; not guaranteed newest-first",
            coverage=coverage_text,
            warnings=warnings,
        )

    @staticmethod
    def _delete_remote_storage(client, dataset_id: str | None, key_value_store_id: str | None) -> bool:
        """Best-effort deletion after data is read; never claim deletion unless API confirms."""
        successful = True
        targets = []
        if dataset_id:
            targets.append(("dataset", lambda: client.dataset(dataset_id)))
        if key_value_store_id:
            targets.append(("key-value store", lambda: client.key_value_store(key_value_store_id)))
        for label, factory in targets:
            try:
                storage = factory()
                delete = getattr(storage, "delete", None)
                if not callable(delete):
                    successful = False
                    continue
                delete()
            except Exception as exc:
                successful = False
                log.warning("Could not delete remote Apify %s (%s)", label, type(exc).__name__)
        return successful
