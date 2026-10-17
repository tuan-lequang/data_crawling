# Shopee Crawler — Thu thập và xử lý dữ liệu sản phẩm

Shopee Crawler là ứng dụng Python có giao diện Streamlit, hỗ trợ thu thập dữ liệu sản phẩm theo từ khóa, chuẩn hóa dữ liệu, loại bản ghi trùng, hiển thị kết quả và xuất CSV/Excel. Dự án có thêm trang **Review Explorer** để minh họa luồng xem và xuất dữ liệu đánh giá.



## 1. Chức năng chính

- **Hai nguồn dữ liệu sản phẩm:**
  - **Demo Dataset:** 500 bản ghi tổng hợp nằm tại `data/demo_products.json`; đây không phải dữ liệu sản phẩm thật đang được lấy trực tiếp từ Shopee.
  - **Live Shopee via Apify:** gọi Actor bên thứ ba `xtracto/shopee-scraper`; cần cấu hình token Apify, kết nối mạng và có thể sử dụng credit.
- **Hai chế độ lấy sản phẩm Live:**
  - **Fast:** ưu tiên tốc độ và giảm yêu cầu lấy thông tin chi tiết; một số trường có thể trống.
  - **Enriched:** yêu cầu thêm thông tin chi tiết, thường chậm hơn; nên thử với số lượng nhỏ (khoảng 20 sản phẩm trở xuống).
- **Pipeline xử lý dữ liệu:** kiểm tra đầu vào, lấy dữ liệu, parse về cấu trúc thống nhất, làm sạch, loại trùng, sắp xếp và giới hạn số bản ghi.
- **Tùy chỉnh trường xuất:** chọn toàn bộ 20 trường, dùng bộ trường của bảng cũ hoặc tự chọn từng trường.
- **Xuất dữ liệu:** tải CSV, Excel (.xlsx), hoặc cả hai. File được lưu vào `data/exports/` và đồng thời có nút tải xuống trên giao diện.
- **Review Explorer:** dữ liệu review Demo là dữ liệu tổng hợp; review Live sử dụng Actor bên thứ ba `memo23/shopee-reviews-scraper` khi người dùng chủ động xác nhận và bấm Fetch. Yêu cầu Live có thể phát sinh chi phí và kết quả có thể không đầy đủ.
- **Xử lý review:** chuẩn hóa, loại trùng, cache cục bộ và thử che một số mẫu thông tin nhạy cảm trong nội dung văn bản trước khi lưu/hiển thị/xuất. Cơ chế che dữ liệu là biện pháp giảm rủi ro, không bảo đảm ẩn danh tuyệt đối.

## 2. Kiến trúc và luồng xử lý

```text
Người dùng nhập từ khóa, số lượng, kiểu sắp xếp và nguồn dữ liệu
                         │
                         ▼
                 Giao diện Streamlit
                         │
                         ▼
          Provider: Demo Dataset hoặc Live/Apify
                         │
                         ▼
                   Dữ liệu thô
                         │
                         ▼
         Parser → Cleaning → Loại bản ghi trùng
                         │
                         ▼
               Sắp xếp và giới hạn số dòng
                         │
                         ▼
                  Pandas DataFrame
                         │
                ┌────────┴────────┐
                ▼                 ▼
          Bảng kết quả        CSV / Excel
```

Điểm quan trọng của thiết kế là hai nguồn sản phẩm dùng chung các bước xử lý sau khi lấy dữ liệu. Vì vậy, Demo có thể dùng để trình bày và kiểm thử pipeline mà không phải gọi dịch vụ bên ngoài.

## 3. Công nghệ và cấu trúc thư mục

**Công nghệ chính:** Python, Streamlit, Pandas, python-dotenv, Apify Client, openpyxl và pytest.

```text
shopee-crawler/
├── app.py                    # Giao diện Streamlit
├── config.py                 # Hằng số, giới hạn và schema
├── pipeline.py               # Pipeline xử lý sản phẩm
├── review_pipeline.py        # Pipeline xử lý review
├── crawler/                  # Provider, parser và tích hợp Apify
├── utils/                    # Làm sạch, validate, cache và xuất file
├── data/
│   ├── demo_products.json    # 500 bản ghi Demo tổng hợp
│   └── exports/              # CSV/XLSX được sinh ra khi chạy
├── scripts/                  # Tiện ích tạo Demo và smoke test Live
├── tests/                    # Kiểm thử tự động
├── .env.example              # Mẫu cấu hình token, không chứa token thật
├── requirements.txt          # Thư viện phụ thuộc
└── README.md
```

## 4. Yêu cầu trước khi cài đặt

- Python **3.10 trở lên**.
- Máy có quyền cài thư viện Python.
- Trình duyệt web hiện đại để mở giao diện Streamlit.
- **Chỉ cần Apify token nếu có nhu cầu thử chế độ Live.** Chạy Demo không yêu cầu token hoặc Internet.

## 5. Cài đặt và chạy trên Windows

### Bước 1 — Mở đúng thư mục dự án

Mở VS Code/Terminal tại thư mục chứa trực tiếp `app.py` và `requirements.txt`.

### Bước 2 — Tạo môi trường Python riêng

```powershell
python -m venv .venv
```

### Bước 3 — Cài thư viện

Có thể gọi Python trong môi trường ảo trực tiếp, không cần kích hoạt môi trường trước:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Bước 4 — Chạy kiểm thử (khuyến nghị)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Lệnh này chạy bộ test tự động. Kết quả cần được ghi nhận theo lần chạy thực tế trên máy sử dụng; không nên dùng lại số liệu từ một lần chạy trước đó.

### Bước 5 — Khởi động ứng dụng

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Mở địa chỉ được Streamlit hiển thị trong Terminal, thường là `http://localhost:8501`. Để dừng ứng dụng, nhấn `Ctrl+C` trong Terminal.

## 6. Chạy trên macOS/Linux

Trong Terminal ở thư mục chứa `app.py`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app.py
```

Sau khi chạy, mở địa chỉ Streamlit thông báo trên Terminal, thường là `http://localhost:8501`.

## 7. Chạy thử Demo Dataset (không cần token)

1. Khởi động ứng dụng theo hướng dẫn ở trên.
2. Trong **Data Source**, chọn **Demo Dataset**.
3. Nhập thử một từ khóa, ví dụ `giày sneaker nam`, rồi chọn số lượng sản phẩm.
4. Có thể thử chế độ sắp xếp, phần **Product output fields**, và chọn CSV, Excel hoặc cả hai.
5. Bấm nút bắt đầu crawl. Quan sát các bước xử lý và các chỉ số như số bản ghi nhận được, số bản ghi hợp lệ, số bản ghi trùng bị loại và số bản ghi cuối cùng.
6. Tải file qua nút Download hoặc mở thư mục `data/exports/` trong dự án.
7. Nếu bật **Review settings**, mở trang review của một sản phẩm Demo để xem ví dụ review tổng hợp. Những review này không phải lời nhận xét thật từ khách hàng Shopee.

Có thể thử thêm: `áo thun nam`, `balo laptop`, `tai nghe bluetooth`, `chuột không dây` hoặc `bàn phím cơ`. Dữ liệu Demo có chủ đích chứa một số giá trị thiếu, định dạng số khác nhau và bản ghi trùng để minh họa chức năng làm sạch.

## 8. Cấu hình chế độ Live (tùy chọn)

Chỉ thực hiện phần này khi đã xác nhận mình có quyền sử dụng nguồn dữ liệu đó và chấp nhận việc gọi dịch vụ bên thứ ba có thể phát sinh chi phí.

1. Sao chép `.env.example` thành `.env` ngay cạnh `app.py`.
   - PowerShell: `Copy-Item .env.example .env`
   - macOS/Linux: `cp .env.example .env`
2. Mở `.env` và điền token Apify do chính bạn quản lý:

   ```dotenv
   APIFY_API_TOKEN=YOUR_APIFY_API_TOKEN
   ```

3. Lưu file và khởi động lại ứng dụng. Token được đọc từ biến môi trường; ứng dụng không nên hiển thị chính giá trị token trên giao diện.
4. Chọn **Live Shopee via Apify** nếu cần thử crawl sản phẩm. Fast phù hợp hơn khi ưu tiên tốc độ; Enriched dùng nhiều thao tác lấy chi tiết hơn và có thể mất nhiều thời gian.
5. Với Live reviews, đọc phần thông báo chi phí và phạm vi dữ liệu trên giao diện trước khi xác nhận. Chỉ bấm Fetch khi đã kiểm tra giá hiện hành của Actor và chấp nhận giới hạn chi phí hiển thị.

**Bảo mật token:** không đưa `.env` vào GitHub, không gửi token trong ảnh chụp màn hình, video demo, báo cáo hoặc tin nhắn. `.env` đã được liệt kê trong `.gitignore`; chỉ chia sẻ `.env.example` đã bỏ trống token.

> **Lưu ý về quyền sử dụng dữ liệu:** Apify và các Actor nêu trên là dịch vụ bên thứ ba, không phải API chính thức của Shopee. Việc sử dụng Actor không tự tạo ra quyền thu thập dữ liệu. Trước khi chạy Live, hãy kiểm tra điều khoản nền tảng đang áp dụng và bảo đảm đã có cơ sở/ủy quyền phù hợp. Nếu không chắc chắn, hãy dùng Demo Dataset để nộp bài và trình diễn.

### Chi phí và giới hạn Live

- Chạy Demo không gọi Actor và không phát sinh phí Apify.
- Crawl sản phẩm Live và lấy review Live có thể sử dụng credit; giá, thời gian chạy và số bản ghi thực tế phụ thuộc dịch vụ/Actor và thời điểm sử dụng.
- Ước tính trong ứng dụng không phải báo giá đảm bảo. Hãy đọc trang Pricing hiện hành của Actor và kiểm tra tài khoản trước khi xác nhận.
- Review Live đọc nguồn review ở cấp shop rồi lọc theo sản phẩm, vì vậy mức độ bao phủ có thể một phần và thứ tự không được bảo đảm là mới nhất.
- Trường không có trong nguồn sẽ để trống; ứng dụng không tự bịa dữ liệu để đủ số lượng yêu cầu.

## 9. Dữ liệu đầu ra

### Sản phẩm — 20 trường chuẩn

`product_id`, `product_name`, `shop_id`, `shop_name`, `shop_location`, `price`, `price_min`, `price_max`, `original_price`, `discount_pct`, `sold`, `rating`, `image_url`, `product_url`, `category`, `is_official_shop`, `is_shopee_verified`, `keyword`, `crawl_time`, `data_source`.

Tất cả dữ liệu sản phẩm được chuẩn hóa theo schema chung. Giá được lưu theo đơn vị VND; ID được giữ dưới dạng văn bản khi xuất Excel để giảm nguy cơ bị đổi thành dạng khoa học. `product_url` hoặc các trường khác có thể để trống nếu nguồn không trả về.

### Review — 13 trường chuẩn

`review_id`, `product_id`, `shop_id`, `rating`, `comment`, `created_at`, `purchased_variant`, `like_count`, `seller_reply`, `review_image_count`, `review_images`, `data_source`, `scraped_at`.

Review được xuất riêng với file sản phẩm. URL ảnh review không được bật mặc định trong danh sách trường xuất. Che thông tin nhạy cảm trong văn bản là **best-effort**, không phải bảo đảm ẩn danh hoàn toàn.

### Vị trí file

- CSV sản phẩm: `data/exports/shopee_products_<thời-điểm>.csv`
- Excel sản phẩm: `data/exports/shopee_products_<thời-điểm>.xlsx`
- CSV/Excel review: `data/exports/shopee_reviews_<product_id>_<thời-điểm>.<csv|xlsx>`
- Cache review cục bộ: `data/cache/reviews/` (được tạo khi cần và nằm ngoài nội dung cần commit).

CSV dùng mã hóa UTF-8 có BOM để tăng khả năng hiển thị tiếng Việt trong Excel. File Excel có sheet dữ liệu, tiêu đề cố định và bộ lọc; các ID dài được ghi dưới dạng text.

## 10. Kiểm thử tự động

Chạy:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Bộ test bao gồm parser, làm sạch, loại trùng, pipeline Demo, xuất CSV/Excel, provider Apify qua fake/mock client và các luồng giao diện. Kiểm thử tự động không phải là bằng chứng rằng dịch vụ Live hoạt động trong tài khoản hiện tại; không cần chạy Actor thật để thực hiện bộ test.





---

**Ghi chú:** README mô tả hành vi được triển khai trong mã nguồn. Khả năng lấy dữ liệu Live cần được xác minh riêng trong môi trường và tài khoản cụ thể; không nên tuyên bố Live đã chạy thành công nếu chưa thực sự kiểm tra.
