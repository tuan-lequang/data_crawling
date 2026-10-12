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
