# Đề xuất bộ benchmark đánh giá hỏi đáp số liệu trên kho thời tiết

**Ngày:** 19/11/2026. **Trạng thái:** đề xuất, chưa triển khai. **Phạm vi:** luồng `ask_data` (MCP và `AskService`), nhánh nhiều bảng `find_fields` → `plan_join` → `query_dataset`, route chat `POST /api/v1/text2sql/chat`.

## 1. Vì sao cần

- Bộ thử nghiệm hiện có (bán lẻ, vận chuyển, mỗi bộ 10 câu) đã dùng để chỉnh prompt nên không còn độc lập ([ask-flow](../handbook/modules/text2sql/ask-flow.md#kiểm-thử)). `tests/test_text2sql_ask.py` dùng LLM giả nên chỉ kiểm tra code, không đo chất lượng.
- Thử thật ngày 19/11 trên connection "Weather warehouse" đã lộ ra các lỗi mà unit test không bắt được:
  - Bộ lọc dùng `ten_thanh_pho = 'Hà Nội'` trong khi dữ liệu lưu `Ha Noi`, nên trả `NULL` dù chọn đúng metric, quy tắc và ngày.
  - Bước viết lại tự đổi "Ha Noi" thành "Hà Nội", nên người dùng không thể vòng qua lỗi.
  - Cùng một câu hỏi, lúc trả `answered`, lúc trả `needs_clarification`.
- Kế hoạch đo retrieval (`Recall@30`, `MRR@5`, so sánh dense/BM25/hybrid, có hoặc không `rerank`) đã ghi ở [embed-retrieve §5](../handbook/modules/text2sql/embed-retrieve.md) nhưng chưa có tập dữ liệu để chạy.

Mục tiêu: một bộ câu hỏi có đáp án kiểm chứng được trên dữ liệu thật của `data_wh`. Bộ này chạy lặp lại được, chấm tự động từng tầng của luồng, và so được hai lần chạy (trước và sau khi đổi prompt, model, ngưỡng hoặc ranking).

## 2. Dữ liệu nền

Connection `01a1d33a-0ef9-728f-b911-3dec9f4ffbf7` (PostgreSQL `data_wh`), do DAG Airflow `weather_warehouse_ingest` nạp mỗi giờ từ Open-Meteo:

| Thành phần | Hiện có |
|---|---|
| Bảng | `fact_tong_hop_thoi_tiet`, `fact_chi_tiet_thoi_tiet`, 5 bảng `dim_*`, 5 bảng `dm_*`, 3 bảng `tb_*` |
| Loại bản ghi | `HIEN_TAI` (324 dòng, từ 13/11), `DU_BAO_NGAY` (240 dòng, 06/11 đến 25/11), `DU_BAO_GIO` (5.760 dòng) |
| Thành phố | 12, tên lưu không dấu: Ha Noi, Ho Chi Minh, Da Nang, Hue, Can Tho, Hai Phong, Ha Long, Nha Trang, Phu Quoc, Vinh, Thai Binh, Buon Ma Thuot |
| Tri thức | 16 metric, 21 thuật ngữ, 8 quy tắc chuyên gia, 21 điều kiện thời tiết |

Các quy tắc chuyên gia (ngày có mưa, thời tiết hiện tại lấy bản ghi mới nhất, cuối tuần, thời tiết xấu, chỉ tính thành phố đang theo dõi, chỉ số ngày và chỉ số trung bình dùng loại bản ghi khác nhau, lần nạp thất bại) chính là chỗ mô hình dễ sai nhất. Benchmark phải phủ đủ cả 8 quy tắc.

## 3. Hai vấn đề phải giải trước

### 3.1. Dữ liệu thay đổi mỗi giờ

DAG ghi lại 7 ngày đã qua và 7 ngày tới ở mỗi lượt nạp, nên số liệu của cùng một ngày có thể thay đổi giữa hai lần chạy. Hai cách xử lý:

- **Snapshot (khuyến nghị).** Dump `data_wh` một lần thành `evals/text2sql/snapshots/weather-2026-11-19.sql` rồi khôi phục vào database `data_wh_bench` trong container `warehouse-db`. Runner chạy trong tiến trình thay URL nguồn của connection bằng URL snapshot. Cách này giữ nguyên `connection_id`, ID cột, metric, thuật ngữ và quy tắc, nên không phải ingest lại. Mỗi phiên bản bộ đề gắn với đúng một snapshot.
- **Chạy trên dữ liệu sống.** Đáp án vẫn tính bằng SQL gốc ngay lúc chạy, nhưng một câu có thể đúng hoặc sai tùy giờ chạy (ví dụ "nóng nhất" đổi thành phố). Chỉ nên dùng cho bài smoke.

Trong cả hai cách, **đáp án không lưu dưới dạng số**. Mỗi câu có một `gold_sql` do người viết và duyệt; runner chạy nó trên cùng dữ liệu mà hệ thống được hỏi.

### 3.2. Thời gian tương đối

`AskService` và `ChatPipeline` đã nhận tham số `today` (`backend/modules/text2sql/chat/service.py`, `pipeline.py`). Mỗi câu khai báo `today` cố định (mặc định là ngày chụp snapshot) để "hôm qua", "3 ngày tới", "cuối tuần này" luôn có cùng một đáp án.

## 4. Bộ câu hỏi

> **Đã thay thế.** Taxonomy chi tiết (21 loại, khoảng 520 câu, mỗi loại 20 đến 30 câu kèm loại con, dạng gold và nguồn tham khảo) nằm ở [taxonomy câu hỏi](2026-11-19-taxonomy-cau-hoi-benchmark.md). Phần dưới đây giữ lại làm lịch sử của bản đề xuất đầu.

Khoảng **120 câu**, chia hai phần tách biệt:
- **`dev` (40 câu):** được xem và được dùng để chỉnh prompt.
- **`test` (80 câu):** chỉ xem điểm tổng và nhãn lỗi, không xem nội dung khi chỉnh prompt. Nếu buộc phải mở để sửa thì chuyển câu đó sang `dev` và viết câu thay thế.

| Nhóm | Ví dụ | Kiểm tra gì | Số câu |
|---|---|---|---|
| A. Một chỉ số, một nơi, một ngày | "Nhiệt độ cao nhất ở Hà Nội hôm qua?" | Chọn đúng metric, quy tắc chỉ số ngày, giá trị lọc khớp dữ liệu (`Ha Noi`) | 15 |
| B. Thời gian tương đối | "Tổng lượng mưa ở Huế 3 ngày qua", "7 ngày tới Đà Nẵng có mưa mấy ngày" | Quy đổi khoảng thời gian, phân biệt quá khứ và dự báo | 15 |
| C. Nhóm, xếp hạng | "Top 3 thành phố mưa nhiều nhất tuần qua", "theo vùng khí hậu" | `group_by`, `order_by`, `limit` | 12 |
| D. Nhiều chỉ số trong một câu | "Cao nhất, thấp nhất và lượng mưa ở Vinh hôm qua" | Mỗi metric có quy tắc riêng, không áp quy tắc của metric này sang metric khác (lỗi đã gặp) | 10 |
| E. Quy tắc chuyên gia | ngày có mưa, thời tiết hiện tại, cuối tuần, thời tiết xấu, thành phố đang theo dõi | Điều kiện quy tắc có trong SQL; câu hỏi tự lọc cùng cột thì quy tắc nhường (`overridden`) | 16 (mỗi quy tắc 2) |
| F. Vận hành ETL | "Tỷ lệ nạp thành công hôm qua", "thời gian nạp trung bình" | Metric ngoài miền thời tiết, bảng `tb_lan_nap_du_lieu` | 6 |
| G. Nhiều bảng, `no_metric` | "Điều kiện thời tiết xuất hiện nhiều nhất ở Đà Nẵng tuần này" | Nhánh `find_fields` → `plan_join` → `query_dataset`, đường nối đã khai báo | 10 |
| H. Biến thể cách viết | "HN", "Sài Gòn", "TP.HCM", không dấu, sai chính tả, tiếng Anh | Chuẩn hóa tên riêng về giá trị thật trong dữ liệu | 14 |
| I. Mơ hồ | "Thời tiết Hà Nội thế nào?", "Mai có nóng không?" | Được hỏi lại hoặc trả một tập chỉ số mặc định hợp lý; không chấp nhận số sai | 8 |
| J. Ngoài phạm vi, không có dữ liệu | "Giá vàng hôm nay", "Nhiệt độ Bangkok", "Lượng mưa năm 2020" | `no_metric` hoặc báo rõ không có dữ liệu; không bịa số | 8 |
| K. Cặp dễ nhầm | hiện tại / trung bình / cao nhất; tổng lượng mưa / xác suất mưa; số thành phố có dữ liệu / đang theo dõi | Chọn đúng metric trong cặp | 6 |

Cách tạo:
- Nhóm A, B, C, H sinh bán tự động từ mẫu câu × tham số (thành phố, chỉ số, cách nói thời gian). Generator sinh luôn `gold_sql`.
- Các nhóm D, E, G, I, J, K viết tay.
- Mọi câu đều được người duyệt trước khi vào bộ đề. Generator cố định seed để lần sinh sau ra đúng như lần trước.

### Định dạng một câu (YAML)

```yaml
id: wx-a-007
split: test
category: A
tags: [quy_tac_chi_so_ngay, ten_khong_dau]
question: "Nhiệt độ cao nhất ở Hà Nội hôm qua là bao nhiêu?"
today: 2026-11-19
accept_status: [answered]
expect:
  metrics: [nhiet_do_cao_nhat]
  rules: ["Chỉ số theo ngày dùng bản ghi dự báo ngày"]
  glossary: ["Nhiệt độ"]          # tùy chọn, dùng để chấm truy hồi
  filter_values: {ten_thanh_pho: "Ha Noi"}
gold_sql: |
  SELECT MAX(nhiet_do_cao_nhat_c) FROM fact_tong_hop_thoi_tiet f
  JOIN dim_thanh_pho t USING (thanh_pho_key)
  WHERE t.ten_thanh_pho = 'Ha Noi' AND f.loai_quan_sat = 'DU_BAO_NGAY' AND f.ngay_key = DATE '2026-11-18'
compare: {mode: scalar, abs_tol: 0.05}
```

`compare.mode`:
- `scalar`: một giá trị.
- `set`: so tập dòng, không xét thứ tự.
- `ordered`: so cả thứ tự, dùng khi câu hỏi yêu cầu xếp hạng.
- `columns_subset`: chấp nhận kết quả có thêm cột.

Số so theo sai số tuyệt đối hoặc tương đối; chuỗi so sau khi bỏ dấu và chuẩn hóa chữ hoa, chữ thường.

## 5. Cách chấm

Chấm theo từng tầng để biết sai ở bước nào, không chỉ đúng hay sai ở đầu ra. Mọi chỉ số chính là **chấm bằng code, không dùng LLM làm giám khảo**.

| Tầng | Chỉ số | Lấy từ |
|---|---|---|
| 1. Truy hồi | Recall của thuật ngữ và quy tắc kỳ vọng; `Recall@5`, `MRR@5` của metric ứng viên | `rewrite.glossary_terms`, `rewrite.rules`, `AskService.candidates()` |
| 2. Viết lại | Giữ đủ thực thể: thành phố, mốc thời gian, chỉ số (kiểm tra bằng từ khóa và bỏ dấu) | `rewrite.rewritten_question` |
| 3. Lập plan | Đúng metric (khớp tập); đúng khoảng thời gian; giá trị lọc tồn tại trong dữ liệu; đúng `group_by` | `queries[].plan` |
| 4. Quy tắc | Điều kiện quy tắc có trong SQL; không áp quy tắc sang metric khác | `queries[].rules`, `queries[].sql` |
| 5. Kết quả | **Execution accuracy**: kết quả khớp kết quả của `gold_sql` | `queries[].result.rows` |
| 6. Hành vi | Trạng thái nằm trong `accept_status`; với nhóm I và J, không có số bịa | `status` |

Điểm chính của một câu là **đúng hoàn toàn**: trạng thái hợp lệ, và nếu `answered` thì kết quả khớp đáp án. Các tầng 1 đến 4 dùng để chẩn đoán.

Một câu được tính là **lỗi hạ tầng**, không tính vào điểm chất lượng, khi gặp:
- OpenRouter trả 402 hoặc 5xx;
- `Không thể tạo embedding`;
- mất kết nối database.

Báo cáo ghi riêng tỷ lệ lỗi hạ tầng. Nếu tỷ lệ này trên 5% thì lần chạy bị đánh dấu không hợp lệ.

**Độ ổn định:** mỗi câu chạy `--repeat 3`. Báo cáo ghi:
- `pass@1`: trung bình số lượt đúng;
- `pass^3`: đúng cả 3 lượt;
- tỷ lệ câu cho trạng thái khác nhau giữa các lượt.

Đây là cách đo trực tiếp hiện tượng lúc `answered`, lúc `needs_clarification`.

**Vận hành:** latency p50 và p95 của từng bước (embed, rewrite, plan, query), số lần gọi LLM, và token nếu OpenRouter trả về.

## 6. Kiến trúc runner

```text
evals/text2sql/
├── cases/weather/{dev,test}/*.yaml
├── generators/weather.py      # sinh nhóm A, B, C, H kèm gold_sql
├── snapshots/                 # dump data_wh, script khôi phục data_wh_bench
├── runner.py                  # gọi AskService/dataset flow trong tiến trình, today cố định, nguồn = snapshot
├── scoring.py                 # chấm từng tầng, so kết quả
└── report.py                  # JSONL từng câu → báo cáo Markdown, so sánh hai lần chạy
```

- **Cách gọi:** `uv run python -m evals.text2sql run --suite weather --split test --repeat 3 --concurrency 4`. Mỗi lần chạy ghi:
  - `runs/<thời-điểm>/results.jsonl`: đầu vào, đầu ra từng tầng, điểm, latency;
  - `summary.md`: điểm theo nhóm, theo tag và theo tầng, cùng danh sách câu sai kèm tầng sai đầu tiên.
- **So sánh:** `... compare runs/A runs/B` liệt kê câu từ đúng sang sai và từ sai sang đúng. Đây là công cụ chính khi chỉnh prompt.
- **Mức MCP:** thêm một tập smoke khoảng 10 câu gọi qua stdio bằng `docker exec ... superset-ai-mcp` để kiểm tra đường đi thật (đây chính là chỗ đã hỏng hôm nay). Tập này không dùng để chấm chất lượng.
- **Unit test cho `scoring.py`** nằm trong `tests/`, chạy cùng bộ test hiện có. Bản thân benchmark không chạy trong `unittest` vì gọi LLM thật.

**Ước tính:** 80 câu × 3 lượt × 2 lần gọi LLM ≈ 480 lần gọi, cộng embedding và Jev rerank. Mỗi câu mất 9 đến 16 giây, nên chạy 4 luồng mất khoảng 15 đến 20 phút. Chi phí tính theo giá model đang dùng trên OpenRouter. Cần kiểm tra số dư trước khi chạy, vì hôm nay đã hết credit giữa chừng.

## 7. Lộ trình

| Giai đoạn | Nội dung | Kết quả |
|---|---|---|
| 1. MVP | Snapshot, định dạng YAML, runner `ask_data`, chấm tầng 5 và 6, 40 câu (nhóm A, B, D, J, K) | Điểm baseline đầu tiên và danh sách lỗi thật |
| 2. Đầy đủ | 120 câu, chấm tầng 1 đến 4, `--repeat`, nhánh dataset (G), `compare` | Báo cáo theo tầng, đo độ ổn định |
| 3. Mở rộng | Smoke qua MCP, route chat, so sánh model và rerank theo [embed-retrieve §5](../handbook/modules/text2sql/embed-retrieve.md), chạy định kỳ | Theo dõi hồi quy |

Baseline nên chạy **trước** khi sửa lỗi "Hà Nội" / "Ha Noi", để benchmark chứng minh được mức cải thiện của bản sửa.

## 8. Cần quyết định

1. **Snapshot hay dữ liệu sống.** Khuyến nghị snapshot `data_wh_bench`.
2. **Vị trí code.** Khuyến nghị thư mục `evals/` ở gốc repo, tách khỏi `backend/` và `tests/`.
3. **Quy mô và tách tập.** 120 câu, `dev` 40 / `test` 80, hay bắt đầu nhỏ hơn.
4. **Câu mơ hồ (nhóm I).** Chỉ chấp nhận `needs_clarification`, hay chấp nhận cả câu trả lời mặc định nếu số liệu đúng.
5. **Model so sánh.** Chỉ `OPENROUTER_MODEL` hiện tại, hay thêm một hoặc hai model để so.

## 9. Giới hạn

- Một miền dữ liệu (thời tiết) với 16 metric chưa đại diện cho kho nghiệp vụ lớn. Định dạng câu hỏi và runner không phụ thuộc miền, nên có thể thêm bộ khác sau.
- `gold_sql` do người viết vẫn có thể sai. Mỗi câu cần hai người duyệt, hoặc ít nhất một lần đối chiếu với kết quả của hệ thống khi hai bên khác nhau.
- Snapshot cũ dần so với dữ liệu thật. Khi schema hoặc tri thức (metric, quy tắc) đổi thì phải làm snapshot và phiên bản bộ đề mới.
