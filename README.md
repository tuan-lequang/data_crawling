# 🛒 Shopee Product Data Crawler

A small Streamlit app that demonstrates a complete data pipeline:

```
keyword → collect product data → parse → clean → remove duplicates → DataFrame → CSV/Excel
```

It runs in **two clearly separated modes**:

| Mode | Where the data comes from | Needs internet / token? |
|------|---------------------------|-------------------------|
| **Demo Dataset** (default) | `data/demo_products.json` — 500 **synthetic** records shaped like the real Shopee Vietnam output | No |
| **Live Shopee via Apify** | Real Shopee Vietnam products, collected by the Apify Actor `xtracto/shopee-scraper` | Yes (Apify API token) |

The UI always shows which one you are looking at: `🟢 LIVE — Shopee via Apify` or `🧪 DEMO DATASET — not live Shopee data`. The CSV has a `data_source` column (`live_apify` or `demo`) so the two can never be confused.

---

## 1. Architecture and data flow

```
Streamlit UI (app.py)
      │  keyword, number of products, sort, data source
      ▼
pipeline.run_pipeline()          ← reports real progress to the UI
      │
      ├── Provider (one of two, same interface)
      │     • ApifyShopeeProvider → Apify API → xtracto/shopee-scraper → Shopee Vietnam
      │     • DemoProvider        → data/demo_products.json
      ▼   (both return a list of RAW dicts)
Parser           fixes the SHAPE   raw nested JSON → 20 standard columns
Cleaning         fixes the VALUES  text/number formats, ranges, whitespace
Deduplication    by product_id, fallback key if missing
Sort + trim      to the requested number (never padded)
      ▼
Pandas DataFrame → Streamlit table → CSV and/or Excel download
```

Live architecture in one line:
`Streamlit → Apify API → xtracto/shopee-scraper → Shopee Vietnam → Raw JSON → Parser → Cleaning → Pandas → CSV/Excel`

Everything after the provider is identical for live and demo data. That is why the demo is a faithful way to show the processing and export steps.

## 2. Folder structure

```
shopee-crawler/
├── app.py               Streamlit UI only (no data logic)
├── pipeline.py          the whole flow in one readable place
├── config.py            every constant (columns, limits, Actor settings)
├── crawler/
│   ├── base.py          product provider interface + errors
│   ├── apify_shopee.py  existing LIVE product provider (unchanged)
│   ├── demo_provider.py offline product provider
│   ├── parser.py        raw product JSON → 20-column schema
│   ├── review_base.py   review provider interface
│   ├── review_access.py selects the Demo or Live review provider
│   ├── apify_reviews.py  on-demand memo23 Live review provider
│   ├── demo_reviews.py  synthetic offline review provider
│   └── review_parser.py review records → minimal review schema
├── utils/
│   ├── cleaning.py      product value cleaning + de-duplication
│   ├── csv_exporter.py  product CSV/Excel export + verification
│   ├── validators.py   input validation
│   ├── field_selection.py product/review output-field selection
│   ├── review_cleaning.py review cleaning + de-duplication
│   ├── pii_redaction.py best-effort free-text redaction
│   ├── review_cache.py  local cache of normalized, redacted reviews
│   ├── review_exporter.py separate review CSV/Excel export
│   └── cost_disclosure.py provider-agnostic cost estimation helpers
├── review_pipeline.py   review parse/clean/dedupe/cache workflow
├── data/demo_products.json   500 raw demo products (synthetic)
├── data/exports/        generated product/review CSV/XLSX files
├── data/cache/reviews/  runtime cache (ignored by Git)
├── scripts/
│   ├── generate_demo.py      rebuilds the demo file (fixed seed → identical output)
│   └── live_smoke.py         manual REAL product Actor smoke test
├── tests/               product + review tests and fixtures
├── .env.example  .gitignore  requirements.txt  pytest.ini  README.md
```

## 3. Installation

Requires Python 3.10+.

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

macOS / Linux:

```bash
source venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
```

## 4. Run

```bash
streamlit run app.py
```

The browser opens at <http://localhost:8501>. **Demo Dataset works immediately** — no `.env`, no token, no internet.

## 5. Live mode (optional): Apify token

1. Copy `.env.example` to `.env`.
2. Paste your token: `APIFY_API_TOKEN=your_token_here` (Apify Console → Settings → API & Integrations).
3. Restart the app. The sidebar shows **Apify token: configured ✅** (the value itself is never displayed).

Environment variables:

| Variable | Purpose |
|----------|---------|
| `APIFY_API_TOKEN` | Your Apify API token. Only needed for Live mode. |

`.env` is listed in `.gitignore`. Never commit it, paste it in a chat, or show it on screen.

**Check your setup once before the demo** (spends a small amount of Apify credit):

```bash
python scripts/live_smoke.py
```

It runs the real pipeline for 10 products, prints counts and a few rows, and saves a CSV to the `data/exports/` folder.

### How the Apify integration works

- The app starts the Actor `xtracto/shopee-scraper` with: `country=vn`, `mode=keyword`, your keyword, a `sort`, `maxProducts` (your number + 20% buffer for duplicates), `fetchDetail=true`, `delay=1`.
- It polls the run status every 5 seconds (the UI shows the real elapsed time), then reads the run's dataset.
- If the run exceeds 300 seconds it is **aborted** so it stops using credits.
- `fetchDetail=true` is on because the detailed output contains the fields we need (`sold`, `shop.name`, `shop.location`, `categories`, shop verification).
- Sort mapping: Relevancy → `relevancy`, Best selling → `sales`, Price ↑/↓ → `price_asc`/`price_desc`. The Actor has **no "top rated" sort**, so for *Top rated* the app fetches by relevancy and sorts the fetched products locally.

## 6. Data schema (20 columns, also the CSV columns)

`product_id, product_name, shop_id, shop_name, shop_location, price, price_min, price_max, original_price, discount_pct, sold, rating, image_url, product_url, category, is_official_shop, is_shopee_verified, keyword, crawl_time, data_source`

| Column | Source field |
|--------|--------------|
| product_id | `item_id` |
| product_name | `title` |
| shop_id | `shop_id` (falls back to `shop.shopid`) |
| shop_name / shop_location | `shop.name` / `shop.location` |
| price, price_min, price_max | `price`, `price_min`, `price_max` (already VND — **not** rescaled) |
| original_price | `price_before_discount` |
| discount_pct | `discount_pct` |
| sold | `sold` |
| rating | `rating_star` |
| image_url | `images[0]` (only if it is a URL) |
| product_url | a URL **only if the record contains one**, otherwise empty |
| category | first non-empty name in `categories` |
| is_official_shop / is_shopee_verified | `shop.is_official_shop` / `shop.is_shopee_verified` |
| keyword, crawl_time, data_source | set by the pipeline |

**Missing data is never invented.** If Shopee/Apify returns `null` for `sold`, the cell is empty. `rating_count` and `total_ratings` are mostly `null` in real output, so they are not exported. Product URLs are never constructed.

## 7. Cleaning and de-duplication rules

- **Price**: `219000`, `"₫199.000"`, `"199,000"`, `"199.000đ"` → `199000`. A range takes the lowest value. `0`, negative or unparseable → empty. Stored as whole VND.
- **Sold**: `850`, `"1.2K"`, `"1,5K"`, `"Đã bán 2,3k"`, `"1.250"` → integers. `null` stays empty.
- **Rating**: must be between 0 and 5, otherwise empty. `"4,8"` → `4.8`.
- **Discount**: number or `"20%"`, between 0 and 100.
- **Text**: whitespace trimmed, Vietnamese accents preserved.
- **IDs** are kept as text (long numbers are not safe as floats).
- **Duplicates**: a record with a `product_id` is a duplicate only if that ID was already seen. A record **without** an ID uses the fallback key `shop_id + normalized product name`. The **first** record is kept; the number removed is shown in the metrics.

The live Apify output is mostly numeric already; the text-format rules are defensive and are exercised by the demo data, which was **deliberately made messy** (duplicates, missing IDs, nulls, text-formatted numbers, malformed records).

## 8. Demo Dataset

`data/demo_products.json` holds 500 raw records in the structure of the real output (`item_id`, `title`, `price`, `price_before_discount`, `sold`, `rating_star`, `images`, `categories`, nested `shop`, …).

- ~316 shoe records (214 match "giày sneaker nam"), plus shirts, backpacks, headphones, mice, keyboards.
- Fictional brands and shops. Image/product URLs use the reserved `demo.invalid` domain, so none can be mistaken for real Shopee links.
- Injected problems: 14 duplicate `item_id`s, 4 records without `item_id`, 4 malformed records, null `sold`/`rating`/`rating_count`/`total_ratings`, missing shop names, text-formatted numbers, and `url` present in only ~13% of records (as in the real output).
- Try keywords: `giày sneaker nam`, `áo thun nam`, `balo laptop`, `tai nghe bluetooth`, `chuột không dây`, `bàn phím cơ`.
- Demo "Relevancy" means file order, **not** Shopee's ranking. Other sorts are applied locally.

## 9. Export (CSV and/or Excel)

- The UI lets the user choose **CSV**, **Excel (.xlsx)**, or **both**. At least one format must be selected. When a crawl finishes, each selected format is saved to the `data/exports/` folder and is also offered through a browser download button. The browser copy still follows the browser download settings.
- CSV uses **UTF-8 with BOM (`utf-8-sig`)**. The exporter reads the file back and verifies that all text columns (including keyword, shop name/location, and category) survive unchanged.
- The app reports text cells containing a literal `?` because those characters may already have replaced Vietnamese letters in the source/input. Encoding cannot recover characters lost before export. For those records, check the raw Apify item/source rather than blindly replacing `?`.
- CSV file name: `shopee_products_<YYYYMMDD_HHMMSS>.csv`.
- Excel file name: `shopee_products_<YYYYMMDD_HHMMSS>.xlsx`.
- Excel contains one `Products` sheet with all 20 standard columns, frozen headers and an autofilter.
- Long IDs (`product_id`, `shop_id`) are written as **text** in Excel to avoid scientific notation such as `2.2E+10`.
- Before downloads are offered, the app reads each selected format back and verifies row count, 20-column schema and all text columns.

## 10. Testing

```bash
python -m pytest
```

The suite uses mocks, so it needs no token, no internet and costs nothing. It covers the parser (with the real record structure as fixture), all cleaning rules, de-duplication, CSV/Excel export and round-trip verification, the demo pipeline, the Apify provider (missing/invalid token, 401/403/429/5xx, network error, timeout + abort, failed run, empty result), and the Streamlit UI (headless).

## 11. Limitations

- **Live mode depends on a third-party service.** Apify and the `xtracto/shopee-scraper` Actor are not run by Shopee. Output fields, speed, price and availability can change, and scraping Shopee is subject to Shopee's terms. Use it responsibly and for coursework-scale volumes.
- **You may get fewer products than requested.** One version of the Actor documents a cap of about 40 products per search, so the 100 option may return fewer. The app reports the real number (`Only X valid unique products were available`) and never pads.
- **Live requests use Apify credits** (`fetchDetail=true` is heavier) and can take a while.
- **Live path testing**: the live provider is tested with mocks and one real-client failure path; real runs depend on your token. Run `scripts/live_smoke.py` once to confirm.
- `product_url` is often empty, and `image_url` is filled only if the source gives a full URL.
- *Top rated* sorts only the products fetched, not all of Shopee.
- Prices are rounded to whole VND.
- Demo data is synthetic and says so everywhere.

## 12. Presentation workflow

1. Start with **Demo Dataset**, keyword `giày sneaker nam`, 50 products → *Start Crawling*.
2. Point at the stage list, then the metrics (fetched → valid → duplicates removed → final).
3. Demonstrate **Product output fields** using All 20, Previous table view, and Custom. Explain that hidden IDs stay in the internal data for linking.
4. Choose **CSV**, **Excel**, or **both** and download the output from `data/exports/` or the browser buttons.
5. Enable **Review settings**, select a small count such as 5, and open **View reviews** for a Demo product. Make clear these reviews are synthetic, not actual Shopee comments. Show the review table, Back navigation and separate review export.
6. If needed, switch to **Live Shopee via Apify** for the existing product crawl with a small request (10–20 products). For reviews on a Live product, review results are fetched only after a separate confirmation button and a per-run charge cap is sent to Apify.
7. Keep a CSV from an earlier live product run as a backup in case the network fails.

Why Demo exists: *"Live scraping depends on an external service, so the Demo Dataset guarantees the processing and export pipeline can still be demonstrated."*


## 13. Product field selection

Before starting a crawl, expand **Product output fields**. By default, all 20 standard fields are selected. The presets include **All 20 (default)**, **Previous table view** (the previous 11-column preview), and **Custom**. Individual field checkboxes and Select All update immediately. The selected fields control the product table and CSV/Excel exports, while the internal `PipelineResult.df` retains all 20 columns for joins, deduplication and review navigation. The crawl is blocked if no product field is selected.

## 14. Review explorer (Demo and on-demand Live reviews)

Enable **Review settings** before crawling to add a **View reviews** action to each product. Select a review limit (5, 10, 20, 50, or Custom) and select the review output fields independently. Review Custom input appears immediately, before Start Crawling. The maximum is configurable in `config.py`; zero is rejected.

- For Demo products, opening a review page generates deterministic **synthetic example reviews** locally. These are not real Shopee reviews or actual customer statements. All review pages and exports are labelled `demo_synthetic`.
- For Live products, the page uses the `memo23/shopee-reviews-scraper` Apify Actor only after you tick the charge acknowledgement and click the explicit **Fetch Live reviews** button. Opening a product's review page does not start a run.
- The Live provider asks for written comments only, limits the run to the configured review count (1–100), sends `max_items` and `max_total_charge_usd`, and fails closed if the installed Apify client cannot send the charge cap. It does not use cookies, browser automation, proxies or CAPTCHA bypass.
- The Actor reads a shop-level review feed, not a dedicated product review feed. Rows are kept only when a product ID is present, and the common parser drops rows belonging to another product. Results can be partial and the star-rating budget may be spread across ratings, so the returned reviews are not guaranteed to be the latest ones.
- The UI estimate uses the Actor's published Free-tier price snapshot plus an assumed start event; this is not a quote and may not match your account. The per-run charge cap is also sent to Apify. Review the Actor's current Pricing tab and your account balance before fetching. No Live request happens automatically, and the app does not retry failed runs automatically.
- Review records are separate from the product dataset. The page shows review count, requested maximum, cache state, coverage and ordering. You can return to the products without losing the product results.
- Review output has 13 normalized fields: `review_id`, `product_id`, `shop_id`, `rating`, `comment`, `created_at`, `purchased_variant`, `like_count`, `seller_reply`, `review_image_count`, `review_images`, `data_source`, and `scraped_at`. Review image URLs are excluded from the default selection.
- Review CSV and Excel files use the name `shopee_reviews_<product_id>_<YYYYMMDD_HHMMSS>.<csv|xlsx>` and are saved in `data/exports/`.

### Review cache and privacy

Only normalized, best-effort-redacted review records are cached locally, in `data/cache/reviews/`. Non-empty entries expire after 24 hours; empty results expire after 30 minutes. The cache key is hashed so product identifiers are not exposed in the filename. Use **Clear local review cache and return** on the review page to clear the local review cache.

Automatic redaction attempts to replace common phone numbers, email addresses, URLs, long digit runs and explicitly marked contact handles before local cache, display or export. It can miss names, addresses, obfuscated or written-out numbers, and personal information expressed indirectly; it can also redact benign long numbers. It is not a guarantee of anonymization. The synthetic Demo data includes deliberately fake contact strings to exercise this safeguard.

The app stores only normalized, best-effort-redacted review rows locally. The Live provider filters to the small allowlist of fields needed for the review schema and discards reviewer names, order IDs, buyer region and other direct identifiers before returning rows to the pipeline. After reading the default dataset, it attempts to delete the Actor's output dataset and default key-value store; the UI warns if deletion cannot be confirmed. This does not guarantee removal from provider logs or backups, and it does not change the provider's responsibility for remote data retention.

## 15. Review access limitations and compliance note

The existing Live product crawler is preserved and still behaves as before; this upgrade does not add a gate to it. Live review collection uses a third-party Apify Actor, not an official Shopee API, and is invoked only after explicit user confirmation. A third-party scraper does not itself establish permission to collect Shopee content; verify the applicable platform terms and authorization before using it. No CAPTCHA bypass, stealth mode, unauthorized login/cookies, proxy rotation or other anti-bot evasion is implemented.

## 16. Testing the review workflow

The review workflow is tested with synthetic records and fake Apify clients only. Automated tests must not call Shopee or Apify, use a real token or spend credits. The Live-provider tests verify the Actor input and charge cap with a fake client, plus response mapping, product attribution, redaction and remote-storage deletion attempts. The test suite isolates export/cache output in temporary directories so running tests does not create files in the project’s `data/exports/`.
