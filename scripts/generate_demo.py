"""Generate data/demo_products.json  (500 RAW records, deterministic: fixed seed).

The records imitate the structure of the real Apify/Shopee VN output (item_id, title,
price, price_before_discount, sold, rating_star, images, categories, nested shop, ...).
They are SYNTHETIC. All brands/shops are fictional and all URLs use the reserved
`demo.invalid` domain, so nothing here can be mistaken for real Shopee data.

Deliberate data-quality problems (so the cleaning step has visible work):
  * 14 duplicate item_id           * 4 records without item_id (2 are copies of others)
  * 4 malformed records            * null sold / rating_star / rating_count / total_ratings
  * missing shop name / location   * some numeric fields stored as text ("₫199.000", "1,5K", "4,8")
  * url present in only ~15% of records (like the real fetchDetail output)

Run:  python scripts/generate_demo.py
"""
import copy
import json
import random
from pathlib import Path

SEED = 20261007
OUT = Path(__file__).resolve().parent.parent / "data" / "demo_products.json"
rng = random.Random(SEED)

LOCATIONS = ["TP. Hồ Chí Minh", "Hà Nội", "Đà Nẵng", "Bình Dương", "Hải Phòng", "Cần Thơ", "Đồng Nai"]
BRANDS = ["NovaStep", "UrbanFit", "Kicksy", "VietStride", "HanoiStreet", "LuxWalk", "Sài Gòn Basic", "TechNest", "PixelGear"]
COLORS = ["Trắng", "Đen", "Xám", "Kem", "Xanh Navy", "Nâu", "Đỏ Đô"]

# group key -> (count, category tree, title builder parts, price range, shop name pool, variants)
GROUPS = {
    "sneaker_nam": dict(
        n=200, cats=["Thời Trang Nam", "Giày Dép Nam", "Giày Sneaker"],
        head="Giày Sneaker Nam",
        styles=["Basic", "Trắng Cổ Thấp", "Đế Cao", "Phong Cách Hàn Quốc", "Unisex", "Da PU", "Vải Canvas", "Chunky", "Đế Êm Siêu Nhẹ", "Thể Thao Năng Động"],
        extras=["Chống Trượt", "Thoáng Khí", "Full Box", "Bảo Hành 6 Tháng", "Hot Trend", ""],
        price=(149_000, 899_000), tiers=("Size", ["39", "40", "41", "42", "43"]),
        shops=["Sneaker House VN", "Kho Giày Sài Gòn", "Urban Street Store", "Giày Nam Official", "Footwear Mall", "Sneaker Hub 24h", "Phố Giày Hà Nội", "Step Up Store"]),
    "thethao_nam": dict(
        n=60, cats=["Thời Trang Nam", "Giày Dép Nam", "Giày Thể Thao"],
        head="Giày Thể Thao Nam",
        styles=["Đế Cao", "Chạy Bộ", "Tập Gym", "Đế Êm", "Siêu Nhẹ", "Đi Bộ", "Training"],
        extras=["Thoáng Khí", "Chống Trượt", "Full Box", ""],
        price=(199_000, 1_200_000), tiers=("Size", ["39", "40", "41", "42", "43"]),
        shops=["Mall Thể Thao", "Run Club Store", "Sport Zone VN", "Gym Gear Shop"]),
    "sneaker_nu": dict(
        n=40, cats=["Thời Trang Nữ", "Giày Dép Nữ", "Giày Sneaker"],
        head="Giày Sneaker Nữ",
        styles=["Trắng Basic", "Đế Bánh Mì", "Ulzzang", "Cổ Cao", "Vải Canvas"],
        extras=["Siêu Nhẹ", "Hot Trend", ""],
        price=(129_000, 599_000), tiers=("Size", ["35", "36", "37", "38", "39"]),
        shops=["Giày Xinh Official", "Candy Shoes", "Nàng Sneaker", "Style Girl Store"]),
    "ao_thun": dict(
        n=50, cats=["Thời Trang Nam", "Áo Thun"],
        head="Áo Thun Nam Cotton",
        styles=["Cổ Tròn", "Oversize", "Form Rộng", "Basic", "Tay Lỡ", "Co Giãn 4 Chiều"],
        extras=["Thoáng Mát", "Không Xù Lông", ""],
        price=(59_000, 299_000), tiers=("Size", ["S", "M", "L", "XL"]),
        shops=["Áo Thun Gốc", "Local Brand VN", "Cotton House", "Shop Đồ Nam 99"]),
    "balo": dict(
        n=40, cats=["Túi Ví Nam", "Balo"],
        head="Balo Laptop Chống Nước",
        styles=["15.6 Inch", "14 Inch", "Chống Sốc", "Có Cổng USB", "Đa Năng", "Đi Học Đi Làm"],
        extras=["Bảo Hành 12 Tháng", "Siêu Bền", ""],
        price=(129_000, 549_000), tiers=("Màu sắc", COLORS[:4]),
        shops=["Balo & Túi 24h", "Travel Gear VN", "Bag Station", "Văn Phòng Phẩm Plus"]),
    "tai_nghe": dict(
        n=40, cats=["Thiết Bị Điện Tử", "Tai Nghe"],
        head="Tai Nghe Bluetooth",
        styles=["Không Dây", "Chống Ồn", "True Wireless", "Gaming", "Pin 30 Giờ", "Mini"],
        extras=["Bảo Hành 12 Tháng", "Bass Mạnh", ""],
        price=(89_000, 1_490_000), tiers=("Màu sắc", COLORS[:3]),
        shops=["Phụ Kiện Công Nghệ HCM", "Audio Land", "TechNest Official", "Gadget 360"]),
    "chuot": dict(
        n=30, cats=["Máy Tính & Laptop", "Chuột Không Dây"],
        head="Chuột Không Dây",
        styles=["Silent Click", "Gaming RGB", "Văn Phòng", "Sạc Pin", "Bluetooth 5.0"],
        extras=["Tiết Kiệm Pin", "Bảo Hành 12 Tháng", ""],
        price=(39_000, 459_000), tiers=("Màu sắc", COLORS[:3]),
        shops=["Phụ Kiện Công Nghệ HCM", "PixelGear Store", "Office Tech VN"]),
    "ban_phim": dict(
        n=20, cats=["Máy Tính & Laptop", "Bàn Phím"],
        head="Bàn Phím Cơ",
        styles=["Blue Switch", "Red Switch", "Không Dây", "LED RGB", "Layout 75%"],
        extras=["Hotswap", "Bảo Hành 12 Tháng", ""],
        price=(299_000, 1_890_000), tiers=("Switch", ["Blue", "Red", "Brown"]),
        shops=["PixelGear Store", "Gadget 360", "Keyboard Lab VN"]),
}

used_ids: set[int] = set()


def unique_id(digits: int) -> int:
    while True:
        value = rng.randint(10 ** (digits - 1), 10 ** digits - 1)
        if value not in used_ids:
            used_ids.add(value)
            return value


def make_shops(names):
    return [{
        "shopid": unique_id(9),
        "name": name,
        "username": name.lower().replace(" ", ".").replace("&", "and")[:24],
        "location": rng.choice(LOCATIONS),
        "rating_star": round(rng.uniform(4.3, 4.9), 2),
        "item_count": rng.randint(20, 900),
        "follower_count": rng.randint(100, 90_000),
        "response_rate": rng.randint(80, 100),
        "response_time": rng.choice([300, 600, 3600, 7200]),
        "is_official_shop": rng.random() < 0.2,
        "is_shopee_verified": rng.random() < 0.45,
    } for name in names]


def round_price(value: float) -> int:
    return int(round(value / 100) * 100)       # e.g. 219000, 183200


def make_product(group_key: str, spec: dict, shops: list, serial: int) -> dict:
    shop = copy.deepcopy(rng.choice(shops))
    brand = rng.choice(BRANDS)
    code = f"{spec['head'].split()[0][:2].upper()}-{serial:03d}"
    parts = [spec["head"], rng.choice(spec["styles"]), rng.choice(spec["extras"]), brand, f"Mã {code}"]
    title = " ".join(p for p in parts if p)

    lo, hi = spec["price"]
    price = round_price(rng.triangular(lo, hi, lo + (hi - lo) * 0.3))
    has_variants = rng.random() < 0.3
    price_max = round_price(price * rng.uniform(1.05, 1.4)) if has_variants else price
    discounted = rng.random() < 0.75
    before = round_price(price * rng.uniform(1.1, 1.8)) if discounted else None
    discount = round((1 - price / before) * 100) if before else None

    sold = None if rng.random() < 0.2 else int(rng.paretovariate(1.2) * 20) % 60_000
    rating = None if rng.random() < 0.08 else round(rng.uniform(3.6, 5.0), 2)
    rating_count = rng.randint(5, 3000) if rng.random() < 0.15 else None
    item_id = unique_id(11)
    n_images = rng.randint(1, 5)
    tier_name, tier_options = spec["tiers"]
    cat_ids = [rng.randint(11_000_000, 11_099_999) for _ in spec["cats"]]

    record = {
        "shop_id": shop["shopid"],
        "item_id": item_id,
        "title": title,
        "currency": "VND",
        "description": f"Sản phẩm demo: {title}. Dữ liệu mẫu, không phải dữ liệu thật từ Shopee.",
        "brand": brand,
        "brand_id": rng.randint(1_000_000, 9_999_999),
        "condition": 1,
        "shop_location": shop["location"],
        "cat_id": cat_ids[-1],
        "price": price,
        "price_min": price,
        "price_max": price_max,
        "price_before_discount": before,
        "price_min_before_discount": before,
        "price_max_before_discount": round_price(before * (price_max / price)) if before else None,
        "discount_pct": discount,
        "availability": "IN_STOCK",
        "liked_count": rng.randint(0, 5000),
        "stock": rng.randint(0, 2000),
        "is_hide_stock": False,
        "sold": sold,
        "historical_sold": (sold or 0) + rng.randint(0, 500),
        "view_count": rng.randint(0, 20_000),
        "is_pre_order": False,
        "has_model_with_available_shopee_stock": True,
        "rating_star": rating,
        "rating_count": rating_count,
        "total_ratings": rating_count,
        "images": [f"https://demo.invalid/images/{item_id}_{i}.jpg" for i in range(1, n_images + 1)],
        "categories": [{"name": n, "catid": c, "url": f"https://demo.invalid/cat/{c}"}
                       for n, c in zip(spec["cats"], cat_ids)],
        "attributes": [{"name": "Thương hiệu", "value": brand}, {"name": "Xuất xứ", "value": "Việt Nam"}],
        "models": [{"name": opt, "price": price, "stock": rng.randint(0, 200)} for opt in tier_options[:3]],
        "tier_variations": [{"name": tier_name, "options": tier_options}],
        "breadcrumb": spec["cats"],
        "label_ids": [],
        "item_has_video": rng.random() < 0.3,
        "shop": shop,
    }
    if rng.random() < 0.15:           # url is only sometimes present (as in the real data)
        record["url"] = f"https://demo.invalid/product/{shop['shopid']}/{item_id}"
    return record


def inject_quality_problems(rec: dict) -> None:
    """Randomly damage a few records in realistic ways (text-formatted numbers, missing fields)."""
    r = rng.random()
    if r < 0.05 and isinstance(rec.get("price"), int):
        v = rec["price"]
        rec["price"] = rng.choice([f"₫{v:,}".replace(",", "."), f"{v:,}", f"{v:,}".replace(",", ".") + "đ"])
    if 0.05 <= r < 0.10 and isinstance(rec.get("sold"), int):
        v = rec["sold"]
        rec["sold"] = rng.choice([f"{v / 1000:.1f}K".replace(".", ","), f"{v / 1000:.1f}K", f"Đã bán {v}"]) if v >= 1000 else str(v)
    if 0.10 <= r < 0.14 and isinstance(rec.get("rating_star"), float):
        rec["rating_star"] = str(rec["rating_star"]).replace(".", ",")
    if 0.14 <= r < 0.17 and isinstance(rec.get("discount_pct"), int):
        rec["discount_pct"] = f"{rec['discount_pct']}%"
    if 0.17 <= r < 0.20:
        rec["shop"]["name"] = None
    if 0.20 <= r < 0.23:
        rec["shop"]["location"] = None
        rec["shop_location"] = None
    if 0.23 <= r < 0.25:
        rec["categories"] = []


def build() -> list:
    base, serial = [], 0
    for key, spec in GROUPS.items():
        shops = make_shops(spec["shops"])
        for _ in range(spec["n"]):
            serial += 1
            rec = make_product(key, spec, shops, serial)
            inject_quality_problems(rec)
            base.append((key, rec))
    rng.shuffle(base)
    records = [rec for _, rec in base]
    assert len(records) == 480

    # 2 unique records lose their item_id (cannot be de-duplicated by ID)
    for rec in rng.sample(records, 2):
        rec["item_id"] = None

    sneaker_idx = [i for i, (k, _) in enumerate(base) if k == "sneaker_nam" and records[i]["item_id"]]
    other_idx = [i for i, (k, _) in enumerate(base) if k != "sneaker_nam" and records[i]["item_id"]]
    originals = rng.sample(sneaker_idx, 12) + rng.sample(other_idx, 2)

    extras = []
    for i in originals:                       # 14 duplicates: same item_id, slightly different counters
        dup = copy.deepcopy(records[i])
        if isinstance(dup.get("sold"), int):
            dup["sold"] += rng.randint(1, 30)
        extras.append((i, dup))
    for i in rng.sample(sneaker_idx, 2):      # 2 copies that lost their item_id (fallback dedupe)
        copy_rec = copy.deepcopy(records[i])
        copy_rec["item_id"] = None
        extras.append((i, copy_rec))

    malformed = [None, "corrupted-record", {}, {"item_id": unique_id(11), "title": "   ", "price": 100000}]
    for item in malformed:
        extras.append((rng.randrange(len(records)), item))

    out = list(records)
    # insert every extra AFTER its original so "keep first" keeps the original
    for i, item in sorted(extras, key=lambda t: -t[0]):
        pos = rng.randint(i + 1, len(out))
        out.insert(pos, item)
    assert len(out) == 500, len(out)
    return out


if __name__ == "__main__":
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {len(data)} raw records -> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
