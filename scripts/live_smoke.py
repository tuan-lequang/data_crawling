"""ONE small real Apify run, to check your token and the live pipeline before the demo.

    python scripts/live_smoke.py                        # 10 products, keyword "giày sneaker nam"
    python scripts/live_smoke.py "áo thun nam" 10

This spends a little Apify credit (it is a real scraper run). It prints only counts and a
few product names; the token is never printed. The CSV is saved to the project-root exports/ folder.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from config import EXPORT_DIR  # noqa: E402
from crawler.apify_shopee import ApifyShopeeProvider  # noqa: E402
from crawler.base import ProviderError  # noqa: E402
from pipeline import run_pipeline  # noqa: E402
from utils.csv_exporter import export_csv  # noqa: E402


def main() -> int:
    load_dotenv()
    keyword = sys.argv[1] if len(sys.argv) > 1 else "giày sneaker nam"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    try:
        result = run_pipeline(ApifyShopeeProvider(), keyword, limit, "relevancy",
                              on_progress=lambda stage, msg: print(msg))
    except (ValueError, ProviderError) as exc:
        print(f"\n❌ {exc}")
        return 1
    print("\nStats:", result.stats_dict())
    for warning in result.warnings:
        print("⚠", warning)
    cols = ["product_name", "price", "sold", "rating", "shop_name", "product_url"]
    print(result.df[cols].head(5).to_string())
    print("\nColumns with data (non-null counts):")
    print(result.df.notna().sum().to_string())
    print("\nSaved:", export_csv(result.df, EXPORT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
