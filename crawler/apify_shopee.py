"""LIVE provider: runs the Apify Actor `xtracto/shopee-scraper` (Shopee Vietnam, keyword mode).

Flow:  start run -> poll status (real elapsed time shown in the UI) -> read the run's
default dataset -> return the raw items.

Security: the token is read from the environment (.env) only. It is never logged, never
shown in the UI, and error messages shown to the user are written here (we never forward
the text of an exception, which could contain request details).

Written for apify-client 3.x (typed `Run` objects, timedelta arguments).
"""
from __future__ import annotations

import logging
import math
import os
import time
from datetime import timedelta
from typing import Any, Callable

from config import (ACTOR_SORT_MAP, APIFY_ACTOR_ID, APIFY_COUNTRY, APIFY_DELAY_SECONDS,
                    APIFY_FETCH_DETAIL, APIFY_MAX_RETRIES, APIFY_MODE, APIFY_POLL_SECS,
                    APIFY_TIMEOUT_SECS, APIFY_TOKEN_ENV, FETCH_BUFFER_RATIO, MAX_PRODUCTS,
                    SOURCE_LIVE)
from crawler.base import (BaseProvider, ConfigError, EmptyResultError, ProviderError,
                          StatusCallback)

log = logging.getLogger(__name__)

TERMINAL_OK = {"SUCCEEDED"}
TERMINAL_FAIL = {"FAILED", "ABORTED", "TIMED-OUT"}
MSG_NO_TOKEN = "Apify API token is not configured. Please use Demo Dataset."


def _default_client_factory(token: str):
    """Imported lazily so Demo mode works even if apify-client is not installed."""
    try:
        from apify_client import ApifyClient
    except ImportError:
        raise ProviderError("The 'apify-client' package is not installed. "
                            "Run: pip install -r requirements.txt") from None
    return ApifyClient(token, max_retries=APIFY_MAX_RETRIES)


def _field(obj: Any, name: str):
    """Read a field from a typed model (attribute) or a plain dict."""
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def build_run_input(keyword: str, limit: int, sort: str) -> dict:
    """Input for the Actor. Field names follow the Actor's published input schema."""
    max_products = min(math.ceil(limit * FETCH_BUFFER_RATIO), MAX_PRODUCTS)
    return {
        "country": APIFY_COUNTRY,
        "mode": APIFY_MODE,
        "keyword": keyword,
        "sort": ACTOR_SORT_MAP.get(sort, "relevancy"),
        "maxProducts": max_products,
        "fetchDetail": APIFY_FETCH_DETAIL,
        "delay": APIFY_DELAY_SECONDS,
    }


def _api_error_message(exc: Exception) -> str | None:
    """Readable message for an Apify HTTP error (by status code), else None."""
    status = getattr(exc, "status_code", None)
    if status is None:
        return None
    if status == 401:
        return "Apify rejected the API token. Check APIFY_API_TOKEN in your .env file."
    if status == 402:
        return "Apify reports a usage or billing limit. Check your Apify account credits."
    if status == 403:
        return "Apify denied access to this Actor or resource. Check your token permissions."
    if status == 429:
        return "Apify rate limit reached. Please wait a moment and try again."
    if status >= 500:
        return "Apify is temporarily unavailable. Please try again later."
    return "Unable to retrieve Shopee data from Apify."


class ApifyShopeeProvider(BaseProvider):
    display_name = "Apify (xtracto/shopee-scraper)"
    data_source = SOURCE_LIVE

    def __init__(self, token: str | None = None,
                 client_factory: Callable[[str], Any] = _default_client_factory,
                 timeout_secs: int = APIFY_TIMEOUT_SECS,
                 poll_secs: int = APIFY_POLL_SECS,
                 clock: Callable[[], float] = time.monotonic):
        self._token = token
        self._client_factory = client_factory
        self._timeout = timeout_secs
        self._poll = poll_secs
        self._clock = clock

    # -- configuration -----------------------------------------------------------------
    def _get_token(self) -> str:
        token = (self._token if self._token is not None else os.getenv(APIFY_TOKEN_ENV, "")).strip()
        if not token:
            raise ConfigError(MSG_NO_TOKEN)
        return token

    @staticmethod
    def is_configured() -> bool:
        return bool(os.getenv(APIFY_TOKEN_ENV, "").strip())

    def needs_local_sort(self, sort: str) -> bool:
        return sort == "rating"      # the Actor has no "top rated" sort

    # -- main entry --------------------------------------------------------------------
    def fetch(self, keyword: str, limit: int, sort: str,
              on_status: StatusCallback = None) -> list:
        token = self._get_token()
        say = on_status or (lambda _msg: None)
        try:
            client = self._client_factory(token)
            return self._run_actor(client, build_run_input(keyword, limit, sort), say)
        except ProviderError:
            raise
        except Exception as exc:           # translate anything else into a readable message
            log.warning("Apify call failed: %s", type(exc).__name__)   # class only: no details
            message = _api_error_message(exc)
            if message:
                raise ProviderError(message) from None
            if isinstance(exc, TimeoutError):
                raise ProviderError("The request to Apify timed out.") from None
            raise ProviderError("Unable to reach Apify. Check your internet connection "
                                "and try again.") from None

    # -- internals ---------------------------------------------------------------------
    def _run_actor(self, client, run_input: dict, say) -> list:
        say("Starting the Shopee scraper on Apify...")
        run = client.actor(APIFY_ACTOR_ID).start(
            run_input=run_input, run_timeout=timedelta(seconds=self._timeout))
        run_id = _field(run, "id")
        if not run_id:
            raise ProviderError("Apify returned an unexpected response.")
        run_client = client.run(run_id)

        started = self._clock()
        while True:
            run = run_client.wait_for_finish(wait_duration=timedelta(seconds=self._poll))
            if run is None:      # the run no longer exists
                raise ProviderError("Apify returned an unexpected response.")
            status = str(_field(run, "status") or "UNKNOWN")
            elapsed = int(self._clock() - started)
            say(f"Apify run status: {status} ({elapsed}s elapsed)")
            if status in TERMINAL_OK or status in TERMINAL_FAIL:
                break
            if self._clock() - started > self._timeout:
                self._abort_quietly(run_client)
                raise ProviderError("The scraper took too long and was stopped. "
                                    "Try fewer products or use the Demo Dataset.")

        if status in TERMINAL_FAIL:
            raise ProviderError("Unable to retrieve Shopee data from Apify "
                                f"(the scraper run ended with status {status}).")

        dataset_id = _field(run, "default_dataset_id")
        if not dataset_id:
            raise ProviderError("Apify returned an unexpected response (no dataset).")
        say("Reading results from the Apify dataset...")
        items = list(client.dataset(dataset_id).iterate_items(limit=run_input["maxProducts"]))
        if not items:
            raise EmptyResultError("The scraper returned no products.")
        return items

    @staticmethod
    def _abort_quietly(run_client) -> None:
        """Stop the run so it does not keep consuming credits. Failure here is not fatal."""
        try:
            run_client.abort()
        except Exception:
            log.warning("Could not abort the Apify run.")
