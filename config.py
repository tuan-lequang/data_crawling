"""Central configuration: every constant lives here (no magic numbers elsewhere)."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEMO_FILE = BASE_DIR / "data" / "demo_products.json"
EXPORT_DIR = BASE_DIR / "data" / "exports"

# ---------------------------------------------------------------- data sources
SOURCE_LIVE = "live_apify"   # value written to the data_source column
SOURCE_DEMO = "demo"

UI_SOURCE_DEMO = "Demo Dataset"
UI_SOURCE_LIVE = "Live Shopee via Apify"

# ------------------------------------------------------------- user-facing inputs
PRODUCT_COUNT_OPTIONS = [10, 20, 50, 100]
DEFAULT_PRODUCT_COUNT = 20
MAX_PRODUCTS = 500           # Apify Actor's documented maxProducts upper bound
MAX_KEYWORD_LENGTH = 100

# UI label -> internal sort key
SORT_OPTIONS = {
    "Relevancy": "relevancy",
    "Best selling": "sales",
    "Price: Low → High": "price_asc",
    "Price: High → Low": "price_desc",
    "Top rated": "rating",
}
# internal sort key -> Actor `sort` value (documented enum:
# relevancy | sales | newest | price_asc | price_desc).
# The Actor has NO "top rated" sort, so we fetch by relevancy and sort locally.
ACTOR_SORT_MAP = {
    "relevancy": "relevancy",
    "sales": "sales",
    "price_asc": "price_asc",
    "price_desc": "price_desc",
    "rating": "relevancy",
}
LOCAL_SORT_COLUMN = {          # sort key -> (column, ascending)
    "sales": ("sold", False),
    "price_asc": ("price", True),
    "price_desc": ("price", False),
    "rating": ("rating", False),
}

# ------------------------------------------------------------------ Apify (live)
APIFY_TOKEN_ENV = "APIFY_API_TOKEN"
APIFY_ACTOR_ID = "xtracto/shopee-scraper"
APIFY_COUNTRY = "vn"
APIFY_MODE = "keyword"
APIFY_FETCH_DETAIL = True    # real run showed detail gives sold, shop.name, location, ...
APIFY_DELAY_SECONDS = 1      # Actor `delay` (0-10): pause between its own requests
FETCH_BUFFER_RATIO = 1.2     # ask for 20% extra to leave room for duplicates
APIFY_TIMEOUT_SECS = 300     # hard limit for the whole run; the run is aborted after this
APIFY_POLL_SECS = 5          # how often we check the run status (and update the UI)
APIFY_MAX_RETRIES = 3        # HTTP retries inside apify-client (default is higher)

# ------------------------------------------------------------------ parsing
# Source URL is NOT consistently present in fetchDetail output. We only use a URL
# when one of these keys exists AND holds an http(s) URL. Otherwise product_url = None.
# If your records use a different key for the URL, add it here.
URL_FIELD_CANDIDATES = ("product_url", "url", "item_url", "link")

# ------------------------------------------------------------------ dataset schema
STANDARD_COLUMNS = [
    "product_id", "product_name", "shop_id", "shop_name", "shop_location",
    "price", "price_min", "price_max", "original_price", "discount_pct",
    "sold", "rating", "image_url", "product_url", "category",
    "is_official_shop", "is_shopee_verified",
    "keyword", "crawl_time", "data_source",
]
ID_COLUMNS = ["product_id", "shop_id"]
TEXT_COLUMNS = ["product_name", "shop_name", "shop_location", "image_url",
                "product_url", "category", "keyword", "crawl_time", "data_source"]
PRICE_COLUMNS = ["price", "price_min", "price_max", "original_price"]
BOOL_COLUMNS = ["is_official_shop", "is_shopee_verified"]

# Columns shown in the UI table (UI label, dataframe column)
DISPLAY_COLUMNS = [
    ("Product Name", "product_name"),
    ("Price", "price"),
    ("Original Price", "original_price"),
    ("Discount %", "discount_pct"),
    ("Sold", "sold"),
    ("Rating", "rating"),
    ("Shop", "shop_name"),
    ("Shop Location", "shop_location"),
    ("Category", "category"),
    ("Shopee Verified", "is_shopee_verified"),
    ("Product URL", "product_url"),
]

# ------------------------------------------------------------------ misc
CRAWL_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
CSV_ENCODING = "utf-8-sig"
FILENAME_PREFIX = "shopee_products"
FILENAME_TIME_FORMAT = "%Y%m%d_%H%M%S"
PRESENTATION_PAUSE_SECS = 0.7


# ------------------------------------------------------------------ review workflow
# On-demand Live review source; a user must explicitly confirm each uncached Actor run.
REVIEW_CACHE_DIR = BASE_DIR / "data" / "cache" / "reviews"
REVIEW_CACHE_SCHEMA_VERSION = "2"
REVIEW_CACHE_TTL_SECONDS = 24 * 60 * 60
REVIEW_EMPTY_CACHE_TTL_SECONDS = 30 * 60
REVIEW_COUNT_OPTIONS = [5, 10, 20, 50]
DEFAULT_REVIEW_COUNT = 5
MAX_REVIEWS_PER_PRODUCT = 100  # Hard UI + validator + pipeline bound; zero is never valid.
# Memo23 public Free-tier price snapshot (13 Oct 2026). The Actor's start-event
# billing unit is not fully clear, so UI labels all estimates and the charge cap
# adds a configurable buffer. Re-check the Actor Pricing tab before a Live fetch.
MEMO23_REVIEW_ACTOR_ID = "memo23/shopee-reviews-scraper"
MEMO23_REVIEW_RATE_PER_1000_USD = 3.50
MEMO23_REVIEW_START_FEE_USD = 0.005
MEMO23_REVIEW_COST_BUFFER_USD = 0.01
MAX_REVIEW_RUN_CHARGE_USD = 0.40
MEMO23_REVIEW_TIMEOUT_SECS = 180
MEMO23_REVIEW_POLL_SECS = 3

REVIEW_COLUMNS = [
    "review_id", "product_id", "shop_id", "rating", "comment", "created_at",
    "purchased_variant", "like_count", "seller_reply", "review_image_count",
    "review_images", "data_source", "scraped_at",
]
REVIEW_ID_COLUMNS = ["review_id", "product_id", "shop_id"]
REVIEW_TEXT_COLUMNS = ["comment", "purchased_variant", "seller_reply", "review_images"]
DEFAULT_REVIEW_FIELDS = [column for column in REVIEW_COLUMNS if column != "review_images"]

PRODUCT_FIELD_LABELS = {
    "product_id": "Product ID",
    "product_name": "Product Name",
    "shop_id": "Shop ID",
    "shop_name": "Shop Name",
    "shop_location": "Shop Location",
    "price": "Price",
    "price_min": "Minimum Price",
    "price_max": "Maximum Price",
    "original_price": "Original Price",
    "discount_pct": "Discount %",
    "sold": "Sold",
    "rating": "Rating",
    "image_url": "Image URL",
    "product_url": "Product URL",
    "category": "Category",
    "is_official_shop": "Official Shop",
    "is_shopee_verified": "Shopee Verified",
    "keyword": "Keyword",
    "crawl_time": "Crawl Time",
    "data_source": "Data Source",
}
PREVIOUS_PRODUCT_FIELDS = [column for _, column in DISPLAY_COLUMNS]
REVIEW_FIELD_LABELS = {
    "review_id": "Review ID",
    "product_id": "Product ID",
    "shop_id": "Shop ID",
    "rating": "Rating",
    "comment": "Comment",
    "created_at": "Created At (UTC)",
    "purchased_variant": "Purchased Variant",
    "like_count": "Like Count",
    "seller_reply": "Seller Reply",
    "review_image_count": "Review Image Count",
    "review_images": "Review Image URLs (optional)",
    "data_source": "Review Data Source",
    "scraped_at": "Collected At (UTC)",
}
REVIEW_EXPORT_PREFIX = "shopee_reviews"
