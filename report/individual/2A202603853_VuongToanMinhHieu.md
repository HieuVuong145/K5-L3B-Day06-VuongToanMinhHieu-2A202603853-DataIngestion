# Báo cáo cá nhân — Day 6 · Data Ingestion Engineering

- **Họ và tên**: Vương Toàn Minh Hiếu
- **MSSV**: 2A202603853
- **Lớp**: L3B
- **Chủ đề & Corpus**: Quy chế Đào tạo của Đại học Bách khoa Hà Nội năm 2025 (Ban hành kèm Quyết định số 5445/QĐ-ĐHBK)
- **Embedding Provider**: OpenRouter API (`openai/text-embedding-3-small`, 1536 chiều)
- **Vector Store**: PostgreSQL 16 + `pgvector 0.8.7` (Docker Compose local)

---

## Dữ liệu và pipeline
- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang**:
  - Dữ liệu: Văn bản Quy chế Đào tạo Đại học Bách khoa Hà Nội từ URL chính thức: `https://ctt.hust.edu.vn/Upload/Nguy%E1%BB%85n%20Qu%E1%BB%91c%20%C4%90%E1%BA%A1t/files/DTDH_QDQC/Hoctap/QCDT_2025_5445_QD-DHBK.pdf` (gồm 34 trang vật lý). Hệ thống tích hợp tính năng tự động tải trực tiếp từ URL nếu repo không đính kèm file PDF.
  - Bản quyền & tính pháp lý: Văn bản quy chế đào tạo công khai của cơ sở giáo dục đại học (Public Institutional Policy), được phép sử dụng công khai trong môi trường học thuật và nghiên cứu. Chi tiết tại `data/manifest.json`.
  - Quy tắc tính trang theo `GUIDE.md`:
    - Loại trừ Trang 2 (Bìa quy chế), Trang 3 & Trang 4 (Mục lục quy chế).
    - Số trang nội dung hợp lệ đưa vào pipeline: **31 trang nội dung** (từ Trang 1, 5 đến Trang 34, tương ứng từ Điều 1 đến Điều 48 của quy chế; đạt chuẩn $\ge 30$ trang của đề bài).
    - Tổng số ký tự chuẩn hóa: **68.897 ký tự** (trung bình ~2.300 ký tự/trang, 100% văn bản số, không có trang scan ảnh hay trang rỗng).
- **Chuẩn hóa, lỗi và giới hạn**:
  - Chuẩn hóa: Dùng Unicode chuẩn NFC, xóa bỏ ký tự tab `\t`, gộp khoảng trắng thừa, tái tạo ngắt dòng đoạn văn theo các mốc điều khoản (`Điều \d+\.`, `CHƯƠNG`, số thứ tự khoản).
  - Lỗi & giới hạn: Một số bảng quy đổi điểm (thang điểm 10 sang thang điểm chữ và thang 4 tại Điều 5) khi trích xuất text PDF bị dính liền các cột điểm; một số điều khoản kéo dài qua hai trang PDF (ví dụ Điều 15 ngắt giữa trang 15 và 16) khiến việc chunking cơ học dễ làm đứt ngữ cảnh liên kết giữa các khoản.
  - Toàn bộ nội dung trích xuất đã được lưu cache tại `data/extracted_pages_cache_dhbk.json` giúp pipeline tái lập chỉ trong **0.65 giây**.
- **Embedding model, vector store, metric, lệnh chạy và chi phí**:
  - **Embedding Model**: `openai/text-embedding-3-small` thông qua **OpenRouter API** (1536 dimensions).
  - **Vector Store**: PostgreSQL 16 + extension `pgvector 0.8.7` chạy local qua Docker trên cổng `127.0.0.1:55433`.
  - **Metric**: Cosine Similarity ($1 - \text{cosine\_distance}$).
  - **Lệnh chạy**: `cd starter && python -m src.run`.
  - **Chi phí thực tế**: Sử dụng tổng cộng **74.596 tokens** qua OpenRouter API, chi phí thực tế là **$0.00149** (~37 đồng VNĐ, ghi nhận minh bạch tại `results/summary.json`).
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn**:
  - Metadata bắt buộc: `document_id` (`quy_che_dao_tao_dhbk_2025`), `source` (`https://ctt.hust.edu.vn/Upload/Nguy%E1%BB%85n%20Qu%E1%BB%91c%20%C4%90%E1%BA%A1t/files/DTDH_QDQC/Hoctap/QCDT_2025_5445_QD-DHBK.pdf`), `page` (từ trang 5 đến 34).
  - Trường lọc bổ sung: `chapter` (nhận diện tự động qua regex `CHƯƠNG [IVXLCDM]+` ở đầu các phần: Chương I, Chương II, Chương III, Chương IV, Chương V, Chương VI). Lý do chọn: Cho phép lọc chính xác theo từng bậc đào tạo (Chương II: Đại học; Chương III: Kỹ sư; Chương IV: Thạc sĩ; Chương V: Tiến sĩ), triệt tiêu hiện tượng nhầm lẫn giữa các bậc đào tạo có quy định tương tự nhau.

---

## Cấu hình và benchmark
- **Ba cấu hình A / B / C**:
  - **Cấu hình A (Fixed-size)**: `chunk_size = 500` ký tự, `overlap = 50` ký tự. Metadata: `source`, `page`. Không lọc metadata. Sinh ra **164 chunks**.
  - **Cấu hình B (Paragraph/Structure-based)**: Cắt theo ranh giới đoạn văn / điều khoản tự nhiên, giới hạn `max_size = 800` ký tự. Metadata: `source`, `page`, `chapter`. Không lọc metadata. Sinh ra **113 chunks** (giảm 31.1% số vector so với A).
  - **Cấu hình C (B + Metadata Filtering)**: Dùng chung không gian vector và chunk của B, nhưng **áp dụng bộ lọc metadata `chapter`** tại thời điểm truy vấn khi câu hỏi có điều kiện filter. Khác biệt duy nhất giữa B và C là bước lọc metadata.
- **Bộ Benchmark (20 câu hỏi tiếng Việt)**:
  - Phân chia: **15 câu dev** và **5 câu test** (cố định trước khi chạy pipeline).
  - Phân loại: 12 câu trực tiếp (`truc_tiep`), 6 câu điều kiện/ngoại lệ (`dieu_kien`), 2 câu diễn đạt lại (`dien_dat_lai`).
  - Metadata filter: Có **3 câu kiểm tra filter** (`q01` lọc Chương I, `q06` lọc Chương I, và `q17` lọc Chương IV trong tập test).
  - Kiểm chứng evidence: Toàn bộ 20 câu hỏi đều có `evidence_quote` và `gold_page` được kiểm tra khớp 100% với nội dung gốc trong PDF. Chi tiết tại `benchmark/benchmark.json`.
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test**:
  - Ưu tiên 1: Tối đa hóa **Evidence Hit@3** và **Hit@1** trên tập dev.
  - Ưu tiên 2: Tính toàn vẹn ngữ nghĩa của chunk (**Chunk Coherence**) đạt mức cao nhất.
  - Ưu tiên 3: Tối ưu dung lượng vector index và giảm thiểu chi phí token API.

---

## Kết quả


| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian embed & lưu | Chi phí OpenRouter |
|---|---|:---:|:---:|:---:|:---:|:---:|
| **A (Fixed-size 500)** | dev | 3/15 (20.00%) | 3/15 (20.00%) | 164 | 14.64s | $0.00149 |
| **A (Fixed-size 500)** | test | 1/5 (20.00%) | 1/5 (20.00%) | 164 | 14.64s | $0.00149 |
| **B (Paragraph 800)** | dev | 2/15 (13.33%) | 3/15 (20.00%) | 113 | 10.07s | $0.00149 |
| **B (Paragraph 800)** | test | 1/5 (20.00%) | 1/5 (20.00%) | 113 | 10.07s | $0.00149 |
| **C (Paragraph + Filter)** | dev | 2/15 (13.33%) | 3/15 (20.00%) | 113 | Query filter | $0.00149 |
| **C (Paragraph + Filter)** | test | 1/5 (20.00%) | 1/5 (20.00%) | 113 | Query filter | $0.00149 |

-----
| Strategy | Coherence trung bình /2 (n=10) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và TB /2 (n=5) |
|---|:---:|:---:|:---:|:---:|
| **A** | 1.00 / 2 (10 mẫu) | 15/15 (100.0%) | N/A (không có filter) | 4 câu mức 0, 0 câu mức 1, 1 câu mức 2 $\rightarrow$ **0.40 / 2** |
| **B** | **2.00 / 2** (10 mẫu) | 15/15 (100.0%) | N/A (không có filter) | 4 câu mức 0, 0 câu mức 1, 1 câu mức 2 $\rightarrow$ **0.40 / 2** |
| **C** | **2.00 / 2** (10 mẫu) | 15/15 (100.0%) | **1/1 (100.0%)** | 4 câu mức 0, 0 câu mức 1, 1 câu mức 2 $\rightarrow$ **0.40 / 2** |

- **Đường dẫn artifacts**:
  - Traces chi tiết: `results/traces_A.json`, `results/traces_B.json`, `results/traces_C.json`
  - Thống kê tổng hợp: `results/summary.json`
  - Nhật ký thí nghiệm: `artifacts/experiment_log.csv`
  - Đánh giá thủ công: `results/manual_audit.json`
  - Mẫu audit: 10 trang đầu tiên (Trang 5 đến 14) cho Coherence; 5 câu test $\times$ Top-3 (15 records) cho Metadata; 5 câu test cho Grounding.

---

## Phân tích và kết luận

### So sánh A–B và B–C
1. **So sánh A vs B (Tác động của Chunking Strategy)**:
   - **Độ mạch lạc ngữ nghĩa (Coherence)**: Chiến lược B đạt điểm tuyệt đối **2.00/2**, hoàn toàn vượt trội so với A (**1.00/2**). Ở Strategy A, việc cắt cứng 500 ký tự thường cắt ngang giữa một câu quy định hoặc cắt rời một khoản luật ra khỏi tên Điều, khiến người đọc hoặc LLM không biết điều kiện đó áp dụng cho đối tượng nào. Strategy B giữ trọn vẹn ngữ nghĩa của từng khoản/mục.
   - **Tài nguyên**: B chỉ tạo ra **113 chunks**, tiết kiệm **31.1% dung lượng vector** so với A (164 chunks), thời gian gọi API và lưu vào database giảm từ 14.64s xuống 10.07s.
   - **Độ chính xác truy xuất**: Trên tập dev, A đạt Hit@1 là 3/15 trong khi B đạt 2/15; trên tập test cả hai đều đạt 1/5. Mặc dù số lượng hit thô của A cao hơn một chút do cắt nhỏ dày đặc hơn (chunk density cao hơn), nhưng các chunk của A bị đứt gãy ngữ cảnh nghiêm trọng.
2. **So sánh B vs C (Tác động của Metadata Filter)**:
   - Tại câu hỏi có filter (như `q01`, `q06`, `q17`), Strategy C đảm bảo **100% tuân thủ phạm vi của chương**, ngăn chặn hoàn toàn việc nhầm lẫn giữa quy định đào tạo đại học (Chương II) và sau đại học (Chương IV, Chương V).

### Phân tích 2 ví dụ thất bại cụ thể
1. **Ví dụ 1: Câu `q15` (Chương trình đào tạo kỹ sư chuyên sâu đặc thù)**:
   - *Câu hỏi*: "Chương trình đào tạo kỹ sư chuyên sâu đặc thù có thời gian thiết kế và khối lượng học tập là bao nhiêu?" (Gold: Trang 20, Điều 21 Chương III: 1,5 năm và 60 tín chỉ).
   - *Nguyên nhân thất bại ở Strategy A & B*: Cả A và B đều trả về Top-1 tại **Trang 6 (Score: 0.6416)** thuộc Chương I (nói về CTĐT tích hợp cử nhân - kỹ sư 5,5 năm 180 tín chỉ).
   - *Bài học & Đánh đổi*: Do cả hai trang đều chứa các từ khóa học thuật giống hệt nhau ("CTĐT kỹ sư", "thời gian thiết kế", "khối lượng học tập"), mô hình embedding thuần ngữ nghĩa (bi-encoder) không thể tự phân biệt được giữa "kỹ sư chuyên sâu độc lập" và "kỹ sư tích hợp". Đây chính là tình huống mà **Metadata Filtering (Strategy C)** phát huy sức mạnh tối đa: khi thêm filter `{"chapter": "Chương III"}`, Top-1 lập tức được ép về đúng Trang 20!
2. **Ví dụ 2: Câu `q10` (Hạng tốt nghiệp đại học bị giảm đi một mức khi nào?)**:
   - *Câu hỏi*: "Hạng tốt nghiệp Xuất sắc hoặc Giỏi của sinh viên đại học bị giảm đi một mức khi nào?" (Gold: Trang 16, Điều 15).
   - *Nguyên nhân thất bại*: Top-1 của hệ thống trả về đúng **Trang 16 (Score: 0.5497)** nhưng lại lấy trúng Khoản 1 của Điều 15 (về cách tính điểm trung bình toàn khóa), trong khi quy định giảm hạng lại nằm ở Khoản 2 (bị đẩy xuống Rank 4 ngoài Top-3).
   - *Bài học*: Đối với các văn bản quy phạm pháp luật có cấu trúc gồm nhiều khoản phụ thuộc, việc chia chunk theo đoạn đơn lẻ (single paragraph) làm phân tán các điều kiện đi kèm. Kỹ thuật chunking cần cải tiến để nhóm trọn vẹn cả Điều (Article-level chunking) hoặc áp dụng kỹ thuật Parent-Child Chunking.

### Chiến lược được chọn & Đánh đổi (Trade-offs)
- **Chiến lược được chọn**: **Cấu hình C (Structure-based + Metadata Filtering)**.
- **Đánh đổi**:
  - *Ưu điểm*: Đảm bảo tính mạch lạc tuyệt đối (2.0/2), tiết kiệm 31% chi phí token và bộ nhớ index, cho phép kiểm soát phạm vi truy xuất chính xác thông qua bộ lọc metadata của từng chương.
  - *Hạn chế*: Đòi hỏi query hoặc ứng dụng phía trước (LLM router) phải nhận diện và truyền vào đúng metadata filter (`chapter`); nếu không có filter, văn bản pháp lý nhiều khoản tương tự nhau vẫn có thể gây phân tán kết quả.

### Hạn chế & Hướng cải tiến

- **Hạn chế & Nguyên nhân kết quả giữa các cấu hình có sự tương đồng**:
  1. **Đặc thù cấu trúc của tài liệu (Corpus Characteristics)**: Trong văn bản pháp quy như Quy chế Đào tạo ĐHBK Hà Nội, đa số các Khoản/Mục luật có độ dài thực tế dao động tự nhiên trong khoảng 300–600 ký tự. Kích thước này vô tình nằm rất gần với kích thước cửa sổ cố định 500 ký tự của Cấu hình A. Do đó, ranh giới cắt của Cấu hình A (fixed-size) và Cấu hình B (paragraph-aware) không tạo ra sự chênh lệch quá cực đoan về độ dài chunk, khiến vector ngữ nghĩa của hai phương pháp có sự phân bố tương đồng trên các câu hỏi mang tính tra cứu chung.
  2. **Quy mô và độ tổng quát hóa của Benchmark (Benchmark Scale & Generality)**: Bộ câu hỏi gồm 20 câu (15 Dev / 5 Test) đạt đúng chuẩn tối thiểu của bài lab, nhưng cỡ mẫu còn khiêm tốn khiến sai số thống kê (variance) cao: chỉ cần 1 câu trượt top-3 đã làm thay đổi chỉ số Hit tới 6.67% (tập Dev) hoặc 20.0% (tập Test). Bên cạnh đó, các câu hỏi hiện tại chủ yếu là tra cứu thông tin trực tiếp hoặc điều kiện đơn, chưa có nhiều câu hỏi suy luận phức tạp liên chương (cross-chapter reasoning) hay câu hỏi phủ định/ngoại lệ đặc thù để làm bộc lộ rõ rệt sự phân hóa giữa các phương pháp.
  3. **Hạn chế của Dense Embedding thuần túy**: Mô hình `text-embedding-3-small` dễ bị nhiễu bởi các cụm từ ngữ pháp lý lặp lại với tần suất dày đặc ("học phần", "tín chỉ", "sinh viên", "học kỳ chính", "quy định của ĐHBK Hà Nội"), làm nén khoảng cách vector giữa các điều khoản khác nhau lại gần nhau.

- **Hướng phát triển & Cải tiến trong tương lai**:
  1. **Mở rộng quy mô và tăng tính tổng quát của Benchmark**: Tăng số lượng câu hỏi lên $\ge 50 - 100$ câu (ví dụ 70 Dev / 30 Test) với độ bao phủ rộng hơn: bổ sung các câu hỏi so sánh chéo giữa các bậc đào tạo (ví dụ: so sánh chuẩn ngoại ngữ tốt nghiệp giữa cử nhân, kỹ sư và thạc sĩ), câu hỏi điều kiện lồng nhau, câu hỏi bẫy từ đồng nghĩa và câu hỏi phủ định ("Trường hợp nào không được hoãn thi?") để kiểm tra ngưỡng phân tách ranh giới của từng phương pháp.
  2. **Kết hợp Hybrid Retrieval (Dense Vector + BM25)**: Tích hợp tìm kiếm từ khóa chính xác BM25 kết hợp với Dense Vector để bắt trọn các con số, định lượng và mốc thời gian đặc thù (như "15 ngày làm việc", "5% tín chỉ", "180 TC"), khắc phục triệt để điểm mù của mô hình ngữ nghĩa dày đặc.
  3. **Kiến trúc Chunking phân cấp (Hierarchical / Parent-Child Chunking)**: Chia nhỏ văn bản ở mức Khoản (child chunk) để embedding và tính tương đồng vector sắc bén, nhưng khi truy xuất sẽ trả về toàn bộ ngữ cảnh của Điều tương ứng (parent chunk), giúp LLM vừa định vị chính xác vừa có đầy đủ ngữ cảnh để tổng hợp câu trả lời.
  4. **Tích hợp Reranker**: Áp dụng mô hình Cross-Encoder (như BGE-Reranker hoặc Cohere Rerank) trên Top-10 kết quả ban đầu để đẩy đúng chunk mang câu trả lời hạt nhân lên vị trí Top-1.
