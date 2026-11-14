# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**



---

## Hướng dẫn Triển khai & Tái lập Thí nghiệm (Implementation Guide)

### 1. Dữ liệu và Nguồn gốc (Data Source & Paths)
- **Tài liệu**: Quy chế Đào tạo của Đại học Bách khoa Hà Nội năm 2025.
- **Đường dẫn URL chính thức**: [QCDT_2025_5445_QD-DHBK.pdf](https://ctt.hust.edu.vn/Upload/Nguy%E1%BB%85n%20Qu%E1%BB%91c%20%C4%90%E1%BA%A1t/files/DTDH_QDQC/Hoctap/QCDT_2025_5445_QD-DHBK.pdf)
- **Hồ sơ dữ liệu chi tiết**: [data/manifest.json](data/manifest.json)
- **Quy mô dữ liệu**: 34 trang vật lý, 31 trang nội dung hữu ích (từ trang 1, 5 đến 34), loại trừ trang bìa (trang 2) và mục lục (trang 3–4) theo chuẩn `GUIDE.md`. Tổng số ký tự chuẩn hóa NFC: **68.897 ký tự**.
- **Cơ chế tự động tải**: Hệ thống tự động kết nối và tải file PDF từ URL chính thức nếu môi trường chạy chưa có file cục bộ.

### 2. Yêu cầu Môi trường & Thiết lập (Prerequisites & Setup)
1. **Docker**: Cần bật Docker Desktop để khởi chạy PostgreSQL 16 + `pgvector`.
2. **Python**: Phiên bản khuyến nghị Python 3.10 – 3.14.
3. **Cấu hình file môi trường (`starter/.env`)**:
   Sao chép từ file mẫu:
   ```bash
   cp starter/.env.example starter/.env
   ```
   Cấu hình thông số trong `starter/.env`:
   ```env
   DATABASE_URL=postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab
   OPENROUTER_API_KEY=api_key
   EMBEDDING_MODEL=openai/text-embedding-3-small
   ```

### 3. Quy trình Chạy Thí nghiệm (Step-by-step Execution)

#### Bước 1: Khởi động Cơ sở dữ liệu Vector
```bash
cd starter
docker compose up -d
```
Kiểm tra kết nối và extension `pgvector`:
```bash
python scripts/check_setup.py
```

#### Bước 2: Kích hoạt Virtualenv & Cài đặt Dependencies
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

#### Bước 3: Thực thi Toàn bộ Pipeline & Đánh giá Benchmark
```bash
python -m src.run
```
Lệnh trên thực hiện tuần tự:
1. Đọc bộ 20 câu hỏi benchmark (15 Dev, 5 Test) từ [benchmark/benchmark.json](benchmark/benchmark.json).
2. Tải/đọc PDF và chuẩn hóa NFC 30 trang nội dung từ trang 5 đến 34.
3. Sinh chunks: Cấu hình A (164 chunks, fixed 500 ký tự) và Cấu hình B (113 chunks, theo điều khoản max 800 ký tự).
4. Gọi OpenRouter API sinh vector embedding 1536 chiều và nạp idempotent (`ON CONFLICT DO UPDATE`) vào database.
5. Đánh giá Top-3 cho 3 cấu hình A, B, C; tính toán Hit@1, Hit@3, token và chi phí API ($0.00149).
6. Tự động lưu toàn bộ trace, summary, log và nhật ký thí nghiệm.

### 4. Cấu trúc Kết quả & Báo cáo (Results & Reports)
- **Thống kê tổng hợp**: [results/summary.json](results/summary.json)
- **Vết truy xuất Top-3**: [results/traces_A.json](results/traces_A.json), [results/traces_B.json](results/traces_B.json), [results/traces_C.json](results/traces_C.json)
- **Kiểm toán thủ công 5 khía cạnh**: [results/manual_audit.json](results/manual_audit.json)
- **Log thực thi Pipeline**: [results/pipeline.log](results/pipeline.log)
- **Nhật ký thí nghiệm**: [artifacts/experiment_log.csv](artifacts/experiment_log.csv)
- **Báo cáo cá nhân hoàn chỉnh**: [report/individual/2A202603853_VuongToanMinhHieu.md](report/individual/2A202603853_VuongToanMinhHieu.md)

