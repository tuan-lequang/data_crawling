# 🛒 Shopee Product Data Crawler

A small Streamlit app that demonstrates a complete data pipeline:

```
keyword → collect product data → parse → clean → remove duplicates → DataFrame → CSV
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
Pandas DataFrame → Streamlit table → CSV download (UTF-8-SIG)
```

Live architecture in one line:
`Streamlit → Apify API → xtracto/shopee-scraper → Shopee Vietnam → Raw JSON → Parser → Cleaning → Pandas → CSV`

Everything after the provider is identical for live and demo data. That is why the demo is a faithful way to show the processing and export steps.

## 2. Folder structure

```
shopee-crawler/
├── app.py               Streamlit UI only (no data logic)
├── pipeline.py          the whole flow in one readable place
├── config.py            every constant (columns, limits, Actor settings)
├── crawler/
│   ├── base.py          provider interface + error types
│   ├── apify_shopee.py  LIVE provider
│   ├── demo_provider.py DEMO provider
│   └── parser.py        raw JSON → standard record
├── utils/
│   ├── cleaning.py      value cleaning + de-duplication
│   ├── csv_exporter.py  UTF-8-SIG export + read-back verification
│   └── validators.py    keyword / count / sort checks
├── data/demo_products.json   500 raw demo records (synthetic)
├── scripts/
│   ├── generate_demo.py      rebuilds the demo file (fixed seed → identical output)
│   └── live_smoke.py         one small REAL Apify run to check your token
├── tests/               pytest suite (+ fixtures with the real record structure)
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

It runs the real pipeline for 10 products, prints counts and a few rows, and saves a CSV to `data/exports/`.

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

## 9. CSV export

- Encoding **UTF-8 with BOM (`utf-8-sig`)** so Excel on Windows shows Vietnamese correctly.
- File name: `shopee_products_<YYYYMMDD_HHMMSS>.csv`, e.g. `shopee_products_20261007_135500.csv`.
- The app reads the CSV back before offering the download and shows `CSV verified: N rows, 20 columns, UTF-8-SIG`.
- Excel tip: long ID numbers (`product_id`, `shop_id`) may appear as `2.2E+10`. The file is correct; format those columns as **Text** in Excel.

## 10. Testing

```bash
python -m pytest
```

The suite uses mocks, so it needs no token, no internet and costs nothing. It covers the parser (with the real record structure as fixture), all cleaning rules, de-duplication, CSV encoding, the demo pipeline, the Apify provider (missing/invalid token, 401/403/429/5xx, network error, timeout + abort, failed run, empty result), and the Streamlit UI (headless).

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
3. Show the table, then **Download CSV** and open it in Excel (Vietnamese is intact).
4. Switch to **Live Shopee via Apify** with a small request (10–20 products) and show the real elapsed-time status.
5. Keep a CSV from an earlier live run as a backup in case the network fails.

Why Demo exists: *"Live scraping depends on an external service, so the Demo Dataset guarantees the processing and export pipeline can still be demonstrated."*
