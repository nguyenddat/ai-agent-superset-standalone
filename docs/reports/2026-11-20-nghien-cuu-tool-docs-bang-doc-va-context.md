# Nghiên cứu: tài liệu công cụ, giải mã lỗi, bảng dọc và mở rộng context cho agent text2sql

Ngày 20/11/2026. Báo cáo tổng hợp từ bốn nhánh nghiên cứu chạy song song: khai thác lỗi từ dữ liệu đã lưu, thực nghiệm
lỗi công cụ, bảng thiết kế dạng dọc, mở rộng context ở bước tiền xử lý. Mọi thực nghiệm chạy trên **bản chụp** của
`backend/` và `scripts/text2sql_eval/`, với catalog thật của connection `01a1d33a-…`, database nguồn chỉ đọc và LLM
thật (`openai/gpt-6-luna` qua OpenRouter). Không sửa code trong repo; báo cáo này là file duy nhất được ghi vào repo.

Dữ liệu gốc, script và số liệu chi tiết nằm trong thư mục nháp của phiên:
`C:\Users\dat\AppData\Local\Temp\claude\d--Code-Superset-AI\3428e385-9db2-46b6-835b-611b745f0661\scratchpad\` với bốn
thư mục con `error-mining\`, `error-experiments\`, `long-tables\`, `preprocess-context\` (danh sách file ở Phụ lục A).

## 0. Tóm tắt cho người quyết định

**Hai vấn đề anh/chị nêu:**

- **P1, bảng dọc:** ý nghĩa một ô phải đọc từ cột khác (mã chỉ số, loại dòng).
- **P2, "đệ quy vô hạn":** agent thử lại lỗi của lỗi trước.

**Kết luận:**

1. **P1 hỏng theo kiểu im lặng, không sinh lỗi.**
   - Data dictionary đã khai báo đủ cách đọc bảng dọc: layout, vai trò cột, grain theo loại dòng, cách tổng hợp theo
     chỉ số. Nhưng `catalog_context`, `agent_catalog`, `index_documents`, `get_table`, `sql_builder` và prompt đều bỏ
     qua các khai báo này.
   - Hậu quả quan sát được:
     - `COUNT(*)` trên bảng dọc đếm 816 thay vì 68 (phình 12 lần);
     - `SUM(gia_tri_so)` không lọc chỉ số ra 6,7 triệu;
     - chọn nhầm chỉ số "ban ngày" (sai 2/2 lần);
     - loại dòng dao động giữa các lần chạy;
     - nối lẫn khóa `*_id` với `*_key`, ra đúng chỉ vì trùng giá trị.
   - Bộ chấm hiện tại (49 câu, 97/98) **không có câu nào bắt buộc đọc bảng dọc và không kiểm cách đọc**, nên chưa
     đo được P1. Agent vẫn tự chọn bảng dọc ở T11-2 (11 câu SQL trên `fact_chi_tiet_thoi_tiet`), có lần dùng
     `COUNT(*)` phình số mà vẫn được chấm đạt vì chỉ so loại đứng đầu.
2. **P2 không tái hiện trên benchmark hiện tại, nhưng thấy rõ trên bộ câu khó.**
   - Trên 910 lượt agent đã lưu: 1,0% lời gọi lỗi, chuỗi lỗi dài nhất là 2, 0 lượt hết số bước.
   - Trên 26 câu khó × 2 lần: chuỗi 3 lỗi, tối đa 6 lỗi trong một lượt. 17/21 lỗi là `get_table` đoán tên bảng
     (`tb_chi_so` → `tb_chi_so_thoi_tiet` → `tb_thanh_pho` → `Chiều thành phố` → …).
   - Gốc của chuỗi lỗi là **thiếu thông tin cấu trúc**, chủ yếu không phải thông báo khó đọc. Agent không có danh sách
     bảng, còn thông báo "không tìm thấy bảng" không liệt kê bảng có thật.
   - Thông báo viết lại (A/B 78 lượt) giảm 20% số lời gọi sau lỗi và đưa lỗi phát sinh tiếp từ 9 về 0, nhưng độ đúng
     không đổi (39/39 so với 38/39). 23/31 lời gọi giảm được nằm ở hai kịch bản E01, E05, và thông báo "viết lại" là
     văn bản viết tay cho từng kịch bản, giàu hơn thông báo code sẽ tự sinh. Vì vậy con số này là **mức trần**.
3. **Đòn bẩy lớn nhất là mở rộng context ở preprocess.**
   - Bản context đầy đủ (metric đầy đủ, điều kiện quy tắc, thẻ bảng kèm cách đọc bảng dọc, đường nối, chuẩn hóa thực
     thể và thời gian, đoạn prompt khoảng 260 token) cho kết quả:
     - độ đúng giữ 34/34;
     - lời gọi tra cứu từ 2,38 xuống 0,12 mỗi câu;
     - số vòng LLM từ 4,0 xuống 2,29;
     - thời gian từ 10,06 s xuống 6,74 s;
     - token đầu vào từ 35,6 nghìn xuống 21,3 nghìn;
     - lỗi công cụ từ 2 xuống 0.
   - Riêng trên bảng dọc, **danh sách 25 chỉ số trong `knowledge.indicators`** (mã, đơn vị, cột giá trị, phép tổng
     hợp, loại dòng) cộng đoạn prompt giảm số bước từ 7,2 xuống 3,6 và sửa được câu "ban ngày" (A 10/12, B 11/12;
     B còn một lượt trả lời rỗng). `reading_guide` trong `get_table` không được đọc lần nào.
   - Mẫu 17 câu được chọn nghiêng về câu tốn nhiều tra cứu. Trên phân bố 49 câu thật, ước lượng token giảm ít hơn
     nhiều (0–15%); lợi ích chắc chắn hơn là bớt khoảng 0,85 vòng LLM (~2 s) mỗi câu con (xem "Kiểm tra lại").
4. **Tool docs vẫn cần**, nhưng vai trò khác với kỳ vọng ban đầu:
   - Chặn lỗi dùng sai công cụ và tham số (get_metric nhận mô tả, get_column_values cho cột DATE, order_by null, alias
     có `-`).
   - Dạy quy tắc đọc bảng dọc trước khi viết SQL.
   - Dạy khi nào **không** hỏi lại.
   - Không thay được context: trong cả hai điều kiện của thực nghiệm bảng dọc, agent gọi `get_table` 0 lần. Hướng dẫn
     chỉ đặt trong kết quả công cụ sẽ không được đọc.

**Đề xuất làm theo thứ tự** (chi tiết ở mục 7):

1. Lỗi có cấu trúc + gom lỗi + chẩn đoán kết quả rỗng + kiểm soát vòng lặp theo lớp lỗi.
2. Tool docs.
3. Catalog đọc metadata bảng dọc.
4. Context preprocess mở rộng + bước [2b].
5. `query_indicator` và cảnh báo bảng dọc trong `run_sql`.
6. Bộ đo mới.

Tất cả bắt đầu **sau** khi workflow `wf_e2bc0d7e-1ef` (văn phong, stream, biểu đồ) xong, vì workflow đó đang sửa đúng
các file này.

### Số liệu chính

| Chỉ số | Giá trị | Nguồn |
|---|---|---|
| Lượt agent đã lưu (bỏ trùng) | 910 lượt, 2.111 lời gọi, 2.782 lần gọi LLM, 21,2 triệu token, 6.554 s | error-mining |
| Lỗi cứng | 21 (1,0%); rỗng 31; NULL 3; chuỗi dài nhất 2; hết bước 0 | error-mining |
| Vòng chỉ tra cứu (get_metric/get_table/get_expert_rule) | 806/1.872 vòng, 24,5% token, ~29% thời gian | error-mining |
| Lượt có lỗi hoặc rỗng so với lượt sạch (34 cặp) | +1,96 vòng, +5,1 s, +18.200 token mỗi câu | error-mining |
| Fuzz 136 ca | 77 lỗi, 16 "thành công sai nghĩa", 24 thông báo chấm 0–1/3 | error-experiments |
| Stress 26 câu × 2 | 45/52 đạt; 21 lỗi; 7 lượt hỏng **không có lỗi công cụ nào** | error-experiments |
| A/B thông báo viết lại (13 kịch bản × 2 × 3) | 152 → 121 lời gọi sau lỗi; 9 → 0 lỗi tiếp theo; đúng 39/39 → 38/39 | error-experiments |
| Bảng dọc, A (công cụ, prompt hiện tại) so với B (danh sách chỉ số trong knowledge + đoạn prompt) | 10/12 → 11/12; 7,2 → 3,6 bước; 19,4 → 12,9 s | long-tables |
| Context đầy đủ so với hiện tại (17 câu × 2) | tra cứu 2,38 → 0,12; vòng 4,0 → 2,29; 10,06 → 6,74 s; token vào −40% | preprocess-context |

## 1. Bằng chứng

### 1.1 Nguồn dữ liệu và cách đếm

| Nguồn | Phạm vi | Ghi chú |
|---|---|---|
| `results/*.json` (14 file) + `a2-trace*.jsonl` (4 file) | 910 lượt agent sau khi bỏ trùng, 2.111 lời gọi | Error-mining dùng cả hai nguồn. Error-experiments và preprocess-context chỉ dùng trace (561 lượt, 1.324 lời gọi), nên số đếm hơi khác nhau. |
| Fuzz trực tiếp | 136 ca tham số sai, gọi thẳng công cụ | Thông báo nguyên văn và điểm "giải mã được" 0–3 |
| Stress | 26 câu khó (bảng dọc, nối bảng chiều, dẫn xuất, mơ hồ, grain) × 2 = 52 lượt | Gold do người viết SQL |
| A/B tiêm lỗi | 13 kịch bản × 2 biến thể thông báo × 3 lần = 78 lượt | Chạy vòng `tool_agent_graph` thật sau lời gọi lỗi tiêm vào |
| Thực nghiệm bảng dọc | 6 câu × 2 lần × 2 điều kiện, ẩn bảng ngang `fact_tong_hop_thoi_tiet` | Gold trong `long-tables/gold.json`. `knowledge` dựng tay (5 bảng, 7 cột chọn sẵn), không qua preprocess thật |
| Thực nghiệm context | 17 câu (18 câu con) × 4 biến thể × 2 lần | Preprocess thật lưu một lần, chỉ chạy lại bước agent |

Bảng `conversation_turns` trong app DB đang trống, nên không có lịch sử dùng thật.

### 1.2 Phân loại lỗi theo công cụ

Số lần lấy từ 910 lượt đã lưu (L) và fuzz (F). "Sửa ngay" là lời gọi kế tiếp thành công.

| Công cụ | Lớp lỗi (mã đề xuất) | L | F | Thông báo hiện tại | Sửa ngay | Gốc rễ |
|---|---|---:|---:|---|---|---|
| query_metric | `QM_FILTER_VALUE_NOT_FOUND` | 15 | có | `Cột ten_thanh_pho không có giá trị 'TP.HCM'. Một số giá trị có: [8 giá trị đầu ABC]` | 15/15 | Bí danh/viết tắt (TP.HCM 12, "TP. Hồ Chí Minh" 2, "Thành phố Hồ Chí Minh" 1). Sửa được chỉ vì `Ho Chi Minh` tình cờ nằm trong 8 giá trị đầu theo ABC |
| query_metric | `QM_ARG_SCHEMA` (null/kiểu/enum) | 2 | 5 | `Tham số không hợp lệ: order_by: Input should be a valid list` | 1/2 | Pydantic không nhận null; thông báo tiếng Anh, không có ví dụ |
| query_metric | `QM_COLUMN_NOT_IN_TABLE` | 0 | 4 | `Cột 'vung_khi_hau' không thuộc bảng … Các cột hợp lệ: <35 cột>` | (A/B E03: 4,7 → 3,7 lời gọi) | Không nói cột nằm ở bảng nào, không nói phải chuyển sang run_sql |
| query_metric | `QM_GRAIN_UNSUPPORTED` | 0 | 2 | `time_grain.grain: Input should be 'day',…` | tự sửa | Không nói cách lấy số theo giờ |
| query_metric | `QM_EXPR_NOT_BUILDABLE` | 1 | – | `Biểu thức … không dựng tự động được; hãy dùng get_metric…` | 1/1 | Thông báo tốt |
| query_metric | rỗng/NULL không báo (`QM_EMPTY_FILTER`) | 4 | có | Hàm gộp trên 0 dòng trả NULL | 4/4 nhưng "bắn rải" | Không phân biệt "không khớp" với "giá trị NULL". Nhánh `partial` (>500 giá trị) lọc thẳng nên rỗng im lặng |
| query_metric | tham số lạ bị bỏ qua (`QM_UNKNOWN_ARG`) | – | 1 | (không có, `date_range` bị bỏ qua) | – | Pydantic mặc định `extra="ignore"`: agent tưởng đã lọc |
| query_metric | lọc row_kind mâu thuẫn CASE của metric | – | 1 | (không có, ra toàn NULL, ghi chú còn nói "không áp quy tắc vì đã lọc") | – | Không kiểm tra |
| get_column_values | `GCV_EMPTY` | 12 | có | `rows: []` | 10/12 | Trước đây thiếu so khớp không dấu (đã sửa, 57 lần tự khớp); vẫn thiếu bí danh; `_` không coi là khoảng trắng (`dự báo` không khớp `DU_BAO_GIO`) |
| get_column_values | `GCV_NON_TEXT_COLUMN` | 1 | 2 | `Chỉ liệt kê giá trị cho cột văn bản; 'chi_so_key' có kiểu BIGINT.` | 1/1 | Không trỏ sang danh mục chỉ số (bảng dọc) hay MIN/MAX (cột ngày). A/B E05: 9,0 → 5,0 lời gọi |
| get_metric | `METRIC_NOT_FOUND` | 1 | 8 | `Không tìm thấy metric 'gio giat toi da 40 km/h theo ngay thanh pho'.` | 1/1 | Coi get_metric như công cụ tìm kiếm; khi không có ứng viên gần thì không gợi ý gì. So khớp quá chặt: `Nhiệt độ trung bình` trượt vì nhãn có thêm `(°C)` |
| get_table | `TABLE_NOT_FOUND` | 0 | 5 | `Không tìm thấy bảng 'weather'.` | stress: chuỗi 3, 17 lỗi | Không có danh sách bảng; gợi ý "Gần giống" chỉ so chuỗi con nên `tb_chi_so` không có gợi ý nào. **Nguồn chuỗi lỗi số 1** |
| get_expert_rule | `RULE_NOT_FOUND` | 0 | 2 | `Không tìm thấy quy tắc '…'.` | – | Như get_metric |
| run_sql | `SQL_PARSE` | 1 | 6 | `Không đọc được cú pháp SQL (PostgreSQL): Invalid expression / Unexpected token. Line 1, Col: 163.` | đúng cú pháp, **sai nghĩa** | Không trích đoạn SQL; model đổi hẳn bài toán (T12-2#2, câu duy nhất trượt ở a2-final3) |
| run_sql | `SQL_TABLE_NOT_IN_CONNECTION` | 0 | 3 | `Bảng 'weather' không có trong connection này. Ghi đủ schema.bảng.` | – | "Ghi đủ schema.bảng" gây hiểu sai khi bảng không tồn tại. Khi đã ghi schema, `sql_guard` gợi ý "Dùng get_table để xem bảng có sẵn", nhưng `get_table` không liệt kê được bảng: chính gợi ý này mời agent vào chuỗi đoán tên bảng |
| run_sql | `SQL_FOREIGN_DIALECT` | 0 | 4 | `column "day" does not exist` (cho DATEADD) | tự sửa | Thông báo sai bản chất |
| run_sql | `DB_42703_*` (chuỗi trong nháy kép, bí danh trong HAVING) | 0 | 2 | `column "Ha Noi" does not exist` / `column "tb" does not exist` | tự sửa | Không nói là chuỗi/bí danh |
| run_sql | `DB_42725/42883` toán tử/hàm | 0 | 1 | `operator is not unique: unknown + unknown` | – | Không gợi ý `||`/ép kiểu |
| run_sql | `SQL_EMPTY_LITERAL` (literal có dấu) | 3 | có | `rows: []` | 3/3 | run_sql không tự khớp giá trị như query_metric |
| run_sql | `SQL_EMPTY_TRUE` (rỗng đúng nghĩa) | 15 | – | `rows: []` | 14/15, thêm 1–2 vòng | Không có chẩn đoán nên model không tin và truy vấn lại |
| ask_user | `ASK_LIMIT` | 0 | 2 | `Đã hỏi lại người dùng đủ số lần…` | – | Thông báo tốt |

Ngoài bảng trên còn có các lỗi có trong code nhưng chưa gặp trong dữ liệu:
- tham chiếu khớp nhiều đối tượng;
- `statement_timeout` (57014);
- mất kết nối (`Text2SqlQueryFailed`);
- `Database báo lỗi <sqlstate>: …` chung chung.

**Điểm giải mã được trung bình** (fuzz, thang 0–3):

| Công cụ | Điểm |
|---|---:|
| get_column_values | 1,20 |
| get_expert_rule | 1,50 |
| get_table | 1,60 |
| get_metric | 1,62 |
| query_metric | 1,78 |
| run_sql | 1,78 |

**Các cơ chế tự sửa trong công cụ đã có hiệu quả:**
- đổi giá trị lọc về đúng dạng dữ liệu (`Hà Nội` → `Ha Noi`): 256 lần;
- so khớp không dấu: 57 lần;
- ghi chú phạm vi thời gian: 59 lần;
- ghi chú quy tắc đã áp: 61 lần.

Sửa ở tầng công cụ là cách rẻ và hiệu quả, nên tiếp tục theo hướng này.

### 1.3 Chuỗi lỗi và vòng lặp

| Tập dữ liệu | Lỗi | Chuỗi ≥ 2 | Chuỗi dài nhất | Lặp cùng lớp lỗi | Hết bước |
|---|---:|---:|---:|---:|---:|
| 910 lượt đã lưu | 21 cứng + 34 rỗng/NULL | 3 (chuỗi kết quả không ổn) | 2 | 0 | 0 |
| Stress 52 lượt (65 lượt agent) | 21 ở 9 lượt | 4 | 3 | 4 | 0 |
| A/B, thông báo hiện tại | 9 lỗi tiếp theo | – | – | E01: 8 lỗi/3 lượt | 0 |

**Ba mẫu "lỗi của lỗi" quan sát được** (mầm của P2):

1. **Lỗi lộ ra lần lượt** (`49e9a64f97b6`): `order_by: null` bị chặn → bỏ `order_by` → lộ lỗi `'TP.HCM'` → sửa thành
   `'Ho Chi Minh'`. Công cụ chỉ báo một lỗi mỗi lần nên mỗi lần sửa lại gặp lỗi mới.
2. **Né lỗi bằng cách đổi bài toán** (`9e288f9637a2`): alias `ngay-vuot-nguong` lỗi cú pháp. Thông báo chỉ có
   `Col: 163`, nên model chuyển từ gộp theo thành phố sang liệt kê dòng. 31 dòng bị cắt, câu trả lời thiếu
   "Ho Chi Minh".
3. **Bắn rải khi rỗng không có chẩn đoán** (`61776f5b418a`): `contains 'TP.HCM'` ra NULL → model gọi song song 3 lần
   `get_column_values`, một lần cho cột DATE nên bị lỗi kiểu.
4. **Đoán tên bảng** (stress L5, cả 3 câu con lặp lại): 6 lần `get_table` với tên đoán. Cơ chế `failed_calls` chỉ
   chặn lời gọi **giống hệt** nên không thấy được chuỗi này (0 lần kích hoạt trong toàn bộ dữ liệu).

**Diễn giải.** Mô hình hiện tại tự gỡ gần như mọi lỗi đơn lẻ trong 1 bước. "Đệ quy" xuất hiện khi:
- thông tin cần để sửa không có trong thông báo lẫn context (tên bảng, cách đọc bảng dọc); hoặc
- công cụ báo lỗi từng cái một.

Vì chỉ thử một mô hình mạnh, với mô hình yếu hơn hoặc lược đồ lớn hơn, P2 có thể nặng hơn nhiều (xem mục 8).

### 1.4 Chi phí lãng phí

| Loại | Vòng | Token | Thời gian |
|---|---:|---:|---:|
| Vòng chỉ tra cứu | 806/1.872 (43%) | 5,18 triệu / 21,17 triệu (24,5%) | ~1.923 / 6.554 s (~29%) |
| Vòng lỗi cứng | 20 | 139 nghìn (0,66%) | ~40 s |
| Vòng rỗng/NULL/lặp | 31 | 301 nghìn (1,4%) | ~89 s |

- 643/910 lượt mở đầu bằng một vòng tra cứu.
- Các mục bị tra nhiều nhất: `get_table fact_tong_hop_thoi_tiet` 186 lần, `get_metric tong_luong_mua` 174 lần,
  `get_column_values ten_thanh_pho` 97 lần. Đây đều là thông tin ổn định, có thể đưa sẵn vào context.

### 1.5 Lỗi bảng dọc và bảng trộn loại dòng (P1)

**Kho dữ liệu có 7 bảng mà một ô phải đọc kèm cột khác mới hiểu được.**

| Bảng | Dạng | Ô phụ thuộc vào |
|---|---|---|
| `fact_chi_tiet_thoi_tiet` (79.932 dòng) | `indicator_values` | `chi_so_key` → `dim_chi_so_thoi_tiet.ma_chi_so` (chỉ số, đơn vị); kiểu chỉ số (SO → `gia_tri_so`, DUNG_SAI → `gia_tri_dung_sai`); `loai_quan_sat` |
| `tb_gia_tri_quan_sat` (79.932 dòng, 5 cột) | `indicator_values` | `chi_so_id` → `dm_chi_so_thoi_tiet`; thời gian, thành phố và loại dòng phải nối qua `quan_sat_id` sang `tb_quan_sat_thoi_tiet` |
| `dim_chi_so_thoi_tiet`, `dm_chi_so_thoi_tiet` (25 chỉ số) | `indicator_catalog` | Mỗi chỉ số có đơn vị, kiểu giá trị, cách tổng hợp riêng. TONG 9, TRUNG_BINH 8, LON_NHAT 5, NHO_NHAT 2, BAT_KY 1; kiểu SO 24, DUNG_SAI 1 (không có chỉ số văn bản) |
| `fact_tong_hop_thoi_tiet` (6.708 dòng, 35 cột), `tb_quan_sat_thoi_tiet` | ngang, trộn 3 loại dòng | Số dòng có giá trị theo HIEN_TAI/DU_BAO_NGAY/DU_BAO_GIO: `nhiet_do_c` 408/0/6.048; `nhiet_do_cao_nhat_c` 0/252/0; `mua_mm` 0/0/6.048 |
| `dim_dieu_kien_thoi_tiet` | bảng mã | `ma_thoi_tiet` là mã WMO |

Các điểm cần lưu ý khi đọc những bảng này:
- 12 chỉ số theo giờ: 10 có ở cả HIEN_TAI và DU_BAO_GIO, 2 (`mua_mm`, `xac_suat_mua_pct`) chỉ có ở DU_BAO_GIO.
  13 chỉ số theo ngày chỉ có ở DU_BAO_NGAY. Vì vậy quy tắc "chỉ số giờ ở HIEN_TAI/DU_BAO_GIO" phải lấy từ ma trận
  chỉ số × loại dòng, không viết cứng.
- Chỉ số boolean `la_ban_ngay` nằm ở `gia_tri_dung_sai`.
- Tên trong danh mục ghi không dấu (`Nhiet do`, `Mien Trung`).
- Đơn vị lẫn nhau: °C, %, mm, hPa, km/h, m, cm, giờ, Đúng/Sai.

**Lỗi quan sát được:**

| Hiện tượng | Ở đâu | Hậu quả |
|---|---|---|
| `COUNT(*)` trên bảng dọc | trace a2-full-x2 T11-2#2; gold Q5 | 816 thay vì 68 (×12); 310 thay vì 31. Vẫn chấm đạt vì thứ hạng không đổi |
| Loại dòng dao động | T11-2 qua các lần chạy | Đáp án "Dong" và "Nhieu may" |
| Chọn nhầm chỉ số | Bảng dọc Q4 "bao nhiêu giờ là ban ngày", A sai 2/2 | Ra 11,6 (thoi_luong_ban_ngay_gio) thay vì 12 (đếm la_ban_ngay=true trên DU_BAO_GIO) |
| `SUM(gia_tri_so)` không lọc chỉ số | fuzz S24 | 6,7 triệu (cộng hPa với mm) |
| Lọc bằng tên có dấu hoặc tên làm mã | S25/S26/S42/S46/S51 | 0 dòng hoặc NULL, không gợi ý |
| Trộn loại quan sát | S27; gold Q1 | 24,17 thay vì 24,52; 20,02 thay vì 20,15 |
| "Hiện tại" không lọc HIEN_TAI | gold Q6; A/B E01 | Lấy dự báo 26/11 (17,4 °C) thay vì quan sát hiện tại (16,7 °C) |
| Chỉ số boolean đọc ở `gia_tri_so` | S29 | NULL |
| Thiếu chỉ số theo giờ | stress L2#1 | 4/7 chỉ số nhóm Mưa |
| "Chỉ số nào lớn nhất" so khác đơn vị | stress L8 × 2 | "Độ ẩm 70,1% lớn nhất" |
| Nối `dm_*.…_id = fact.…_key` | trace và lite | Đúng nhờ trùng giá trị (lỗi tiềm ẩn) |
| Không lọc `loai_quan_sat` trên bảng trộn | 2/186 SQL | Trộn hiện tại với dự báo |

**Metadata hiện có và chỗ bị bỏ qua.**

- Data dictionary hỗ trợ 3 layout: `wide`, `indicator_values`, `indicator_catalog`.
- Các vai trò cột được khai báo:
  - `time`, `created_at`, `row_kind`;
  - `indicator_key`, `value` (qualifier number/boolean/text);
  - `catalog_key`/`code`/`name`/`unit`/`value_kind`/`aggregation`.
- Ngoài ra có `table_time_grains` (HIEN_TAI → instant, DU_BAO_GIO → hour, DU_BAO_NGAY → day) và
  `indicator_aggregations` (TONG → SUM, TRUNG_BINH → AVG, LON_NHAT → MAX, NHO_NHAT → MIN, BAT_KY/CUOI_CUNG → NONE).
- Text2sql bỏ qua toàn bộ các khai báo này, cùng với `unit`, `semantic_role` và `referenced_column_id` (khóa ngoại).

**`indicator_catalog_id`: đã khai báo (đã kiểm lại trên app DB, chỉ đọc).**
- Trường này trỏ đúng:
  - `fact_chi_tiet_thoi_tiet` → `dim_chi_so_thoi_tiet`;
  - `tb_gia_tri_quan_sat` → `dm_chi_so_thoi_tiet`.
- Nhánh error-experiments ghi NULL là do script `dd_layout2.py` so `indicator_catalog_id` với `database_tables.id`.
  Thực ra khóa ngoại này trỏ tới `table_dictionaries.id` (xem `models/table_dictionary.py`).
- **Khóa ngoại cũng đã khai báo đủ:** 22 cặp `referenced_column_id`, gồm `fact_chi_tiet_thoi_tiet.quan_sat_id` và
  `tb_gia_tri_quan_sat.quan_sat_id` → `tb_quan_sat_thoi_tiet.quan_sat_id`. Đường nối `dim_*.*_id` → `dm_*.*_id`
  cũng có, ví dụ `dim_thanh_pho.nguon_thanh_pho_id` → `dm_thanh_pho.thanh_pho_id`.

**Metadata sai cần sửa:**
- `gia_tri_so` khai báo `column_aggregations` SUM/AVG/MIN/MAX ở mức cột. Khai báo này sai bản chất, vì phép tổng hợp
  phụ thuộc chỉ số.
- `dm_chi_so_thoi_tiet` gán vai trò `time` cho `tao_luc`.

**Lỗi không sinh thông báo.** 7/7 lượt stress hỏng không có lỗi công cụ nào: L2#1, L8 × 2, A4#2, A3 × 2, L1#2. Ba
lượt cuối là hỏi lại thừa hoặc hiểu sai "được dự báo". Những lỗi này chỉ chặn được bằng tool docs, context và cảnh báo
do code sinh.

### 1.6 Khoảng trống context

Preprocess hiện đưa trung bình **3.965 token** (expert_rules 1.184, glossary 800, tables 626, columns 589, metrics 455),
cộng 1.462 token system prompt. Các khoảng trống:

- `knowledge_context` bỏ `table_id` và `score` của mọi hit. Với metric, agent không biết bảng, biểu thức hay quy tắc tự
  áp, nên 330/561 lượt mở đầu bằng `get_metric`.
- Không có danh sách bảng đầy đủ, nên agent đoán tên bảng (stress L5).
- Không có cách đọc bảng dọc, loại dòng, đơn vị hay đường nối (P1).
- Không chuẩn hóa thực thể: 9/13 lỗi trong trace là `TP.HCM`. Bước [2b] đã lên kế hoạch nhưng chưa xây.
- `json.dumps(indent=2)` tốn thêm khoảng 9% token.

## 2. Tài liệu công cụ (tool docs)

### 2.1 Định dạng, vị trí và cách nạp

**Vị trí:** `backend/agent_package/tool_docs/`. Mỗi công cụ một file Markdown `<tên_công_cụ>.md`, viết tiếng Việt cho
người đọc là LLM. Mỗi file có hai phần, phân tách bằng tiêu đề cố định:

```markdown
# query_metric
## Tóm tắt
<≤ 60 từ: dùng để làm gì, khi nào dùng, khi nào không. Đi vào description của tool schema.>
## Hướng dẫn
<Tham số kèm ví dụ hợp lệ, kết quả trả về, bảng dọc, lỗi thường gặp: mã → nghĩa → cách sửa.>
```

**Loader** `backend/agent_package/tool_docs/__init__.py`, chỉ dùng thư viện chuẩn (`importlib.resources`). Không
import `backend.modules`:

```python
@dataclass(frozen=True)
class ToolDoc:
    name: str
    summary: str   # phần "Tóm tắt"
    guide: str     # phần "Hướng dẫn"
    sections: dict[str, str]  # tiêu đề cấp 3 trong Hướng dẫn, ví dụ "Lỗi QM_FILTER_VALUE_NOT_FOUND"

def tool_doc(name: str) -> ToolDoc: ...          # đọc 1 lần, lru_cache
def tools_guide(names: Sequence[str]) -> str: ... # ghép các phần Hướng dẫn cho system prompt
def error_help(tool: str, code: str) -> str | None: ...  # trích mục lỗi tương ứng
```

**Nạp vào ba chỗ** (chi phí đã cân nhắc):

1. **Mô tả công cụ** (`StructuredTool.from_function(description=tool_doc(name).summary)` trong
   `agent_tools.Text2SqlToolkit.tools()`): ngắn, được gửi ở mọi vòng.
2. **System prompt**: `text2sql_agent_service` ghép `text2sql_agent_prompt + "\n# TÀI LIỆU CÔNG CỤ\n" +
   tools_guide(enabled_tools)` một lần cho mỗi lượt.
   - Đếm thật (o200k) trên bản nháp ở mục 2.2: phần Hướng dẫn của 8 file là **khoảng 3.170 token** (thân 2.160,
     các mục lỗi 1.000), chưa kể make_chart. Bỏ `query_indicator` (chưa có công cụ) còn khoảng 2.800. Prompt agent
     hiện tại khoảng 1.470 token, nên nạp nguyên văn sẽ làm system prompt lớn gấp ba. Phải rút gọn về ≤ 1.500 token
     (chỉ giữ thân, đưa mục lỗi sang kênh (3)), hoặc chấp nhận và đo.
   - Bù lại: context mở rộng bớt vòng. Nhưng mức −40% chỉ đo trên bộ 17 câu nhiều tra cứu; trên 49 câu ước lượng
     chỉ khoảng −5% (mục 6.2), không đủ bù cho khoảng 3.000 token docs. Prompt caching qua OpenRouter cho mô hình
     này **chưa được kiểm**.
   - Nếu đo thấy quá đắt, chỉ đưa phần "Lỗi thường gặp" vào kênh (3).
3. **Trong lỗi khi leo thang** (mục 4): lần thứ hai gặp cùng `(tool, code)` thì `tool_agent` gắn `error_help(tool,
   code)` vào thông báo lỗi. Không thêm công cụ `get_tool_doc`, vì mỗi lần gọi tốn thêm một vòng.

**Ranh giới module:**
- `agent_package` chỉ chứa văn bản và loader.
- Danh sách công cụ được bật và nội dung động (tên bảng, loại biểu đồ được bật) do `backend/modules/text2sql` chèn vào
  qua placeholder `{tables}`/`{chart_types}` bằng `str.format_map`, đúng như cách đề xuất cho `make_chart`.

**Kiểm thử** (`backend/tests/agent_package/test_tool_docs.py`):
- mỗi công cụ trong `Text2SqlToolkit.tools()` đều có file;
- `summary` ≤ 400 ký tự;
- mỗi mã lỗi trong `tool_errors.CODES` có mục tương ứng trong docs;
- tổng `tools_guide` ≤ 1.500 token (đếm bằng o200k; bản nháp hiện tại vượt, xem trên);
- docs chỉ nhắc tới trường context và công cụ **đã có** ở đợt đó. Ví dụ `knowledge.indicators`, `entities`,
  `join_paths`, `reading_guide`, `query_indicator` chỉ được vào docs từ đợt cài chúng. Docs mô tả tính năng chưa có
  sẽ tự sinh lỗi mới: agent đi tìm danh sách bảng không có trong context.

### 2.2 Bản nháp tool docs

Các bản nháp dưới đây là nội dung đề xuất cho các file `.md`. Ví dụ lấy từ kho thời tiết. Khi viết thật, đặt các
ví dụ phụ thuộc dữ liệu dưới dạng mẫu chung hoặc sinh từ catalog, để docs không gắn chặt với một connection.

**Lưu ý khi đọc bản nháp:** bản nháp mô tả hành vi **sau** Đ1–Đ6, chưa phải hành vi hiện tại. Đối chiếu với code
ngày 20/11, các điểm sau chưa đúng:
- `get_column_values` hiện escape `_` trong `search` và `normalized` không đổi `_` thành khoảng trắng;
- công cụ này chưa trả danh mục cho cột khóa chỉ số;
- `query_metric` chưa từ chối trường lạ (`extra` đang là ignore) và chưa có `QM_EMPTY_FILTER`;
- `get_table` chưa có `layout`, `reading_guide`, `join_paths`;
- `run_sql` chưa có cảnh báo `LONG_TABLE_*`;
- các mã lỗi chưa tồn tại.

Ngược lại, `get_table` hiện đã nhận cả nhãn hiển thị chính xác ("Fact - Tổng hợp thời tiết"); chỉ nhãn tự đặt mới
lỗi. Quy tắc "dim_* nối bằng *_key, dm_*/tb_* bằng *_id" trong `run_sql.md` là quy ước riêng của kho này: khi viết
thật thì thay bằng `join_paths` sinh từ khóa ngoại.

#### get_metric.md

```markdown
# get_metric
## Tóm tắt
Xem định nghĩa một metric: bảng, biểu thức, cột của bảng, quy tắc chuyên gia tự áp. Nhận TÊN hoặc ID metric (lấy
từ knowledge.metrics), không nhận mô tả hay câu hỏi. Thông tin đã có trong knowledge.metrics thì không cần gọi.
## Hướng dẫn
- Tham số: {"metric": "tong_luong_mua"} hoặc {"metric": "<uuid>"}. Nhãn hiển thị cũng được ("Tổng lượng mưa").
- Không dùng để tìm kiếm: {"metric": "gió giật tối đa 40 km/h theo ngày"} sẽ lỗi. Không có metric hợp → dùng
  run_sql trên bảng phù hợp trong knowledge.tables.
- Trả về: name, label, expression, table, columns, expert_rules (điều kiện đã viết theo tên cột).
### Lỗi METRIC_NOT_FOUND
Tên không khớp metric nào. Chọn một tên trong valid_options của lỗi; nếu không có metric phù hợp thì viết SQL bằng
run_sql. Không thử thêm biến thể tên.
### Lỗi METRIC_AMBIGUOUS
Tên khớp nhiều metric. Gọi lại với id trong valid_options.
```

#### get_table.md

```markdown
# get_table
## Tóm tắt
Xem một bảng: mô tả, một dòng là gì, các cột (kiểu, nhãn, đơn vị, khóa nối), metric của bảng, và với bảng dọc hoặc
bảng trộn loại dòng thì có reading_guide. Chỉ gọi với tên có trong knowledge.tables hoặc danh sách bảng của context;
không đoán tên.
## Hướng dẫn
- Tham số: {"table": "public.fact_tong_hop_thoi_tiet"} hoặc tên ngắn "fact_tong_hop_thoi_tiet" hoặc id.
- Không gọi với nhãn tiếng Việt tự đặt ("Chiều thành phố"). Không biết bảng nào: xem danh sách bảng trong context.
- Trả về: table, label, layout (wide | indicator_values | indicator_catalog), grain, columns[{name, type, label,
  unit, references, row_kinds}], metrics, reading_guide (nếu có), join_paths.
- Thẻ bảng trong context đã có cùng nội dung: không gọi lại cho bảng đã có thẻ.
### Lỗi TABLE_NOT_FOUND
Tên bảng không tồn tại. valid_options là danh sách bảng có thật (tên + nhãn + layout). Chọn từ đó, không đoán tên mới.
```

#### get_expert_rule.md

```markdown
# get_expert_rule
## Tóm tắt
Xem đầy đủ một quy tắc chuyên gia (điều kiện theo tên cột, ngoại lệ, ví dụ). Dùng khi tự viết SQL cho run_sql và
knowledge.expert_rules chưa có điều kiện "where". query_metric tự áp quy tắc gắn với metric, không cần gọi.
## Hướng dẫn
- Tham số: {"rule": "<tên quy tắc>"} hoặc id, lấy từ knowledge.expert_rules.
- Khi tự viết SQL: chép điều kiện where của quy tắc vào WHERE và nêu quy tắc trong câu trả lời.
### Lỗi RULE_NOT_FOUND
Chọn tên trong valid_options (toàn bộ quy tắc của connection khi ít). Không có quy tắc phù hợp thì làm tiếp không cần quy tắc.
```

#### get_column_values.md

```markdown
# get_column_values
## Tóm tắt
Xem giá trị thực của một cột VĂN BẢN hoặc boolean để viết điều kiện lọc đúng cách ghi trong dữ liệu (thường không
dấu, ví dụ 'Ho Chi Minh', 'Mien Bac', mã 'DU_BAO_GIO'). Không dùng cho cột số, ngày; không cần khi context đã có
entities/value_dictionary.
## Hướng dẫn
- Tham số: {"table": "dim_thanh_pho", "column": "ten_thanh_pho", "search": "chi minh"}. search ngắn, một hai từ,
  không phân biệt dấu và hoa thường; '_' trong mã được coi như khoảng trắng.
- Bí danh, viết tắt (TP.HCM, HN, Sài Gòn) có thể không khớp: tìm bằng một từ đặc trưng ("minh", "noi").
- Cột khóa chỉ số của bảng dọc (role indicator_key, ví dụ chi_so_key): công cụ trả cặp (khóa, ma_chi_so, tên, đơn vị)
  từ bảng danh mục.
- Cột ngày/số: muốn biết khoảng giá trị thì dùng run_sql SELECT MIN(cot), MAX(cot).
- Trả về: rows (giá trị), row_count, notes (ví dụ "Không phân biệt dấu").
### Lỗi GCV_NON_TEXT_COLUMN
Cột không phải văn bản. Làm theo fix trong lỗi: MIN/MAX bằng run_sql, hoặc dùng danh mục chỉ số nếu là cột khóa chỉ số.
### Lỗi GCV_PII_COLUMN
Cột chứa dữ liệu cá nhân, không liệt kê được. Không thử cột khác cùng nghĩa.
### Kết quả rỗng
search không khớp. Thử một từ ngắn hơn một lần; vẫn rỗng thì giá trị không có trong dữ liệu: nói rõ với người dùng.
```

#### query_metric.md

```markdown
# query_metric
## Tóm tắt
Tính một metric bằng SQL do hệ thống dựng: lọc, phân nhóm, gom theo ngày/tuần/tháng/quý/năm, sắp xếp, giới hạn; tự
áp quy tắc gắn với metric và tự khớp giá trị văn bản với dữ liệu. Ưu tiên khi có metric đúng ý. Không nối bảng,
không gom theo giờ: các trường hợp đó dùng run_sql.
## Hướng dẫn
- Ví dụ: {"metric": "tong_luong_mua",
  "filters": [{"column": "ten_thanh_pho", "operator": "equals", "value": "Ho Chi Minh"},
              {"column": "ngay_key", "operator": "greater_than_or_equal", "value": "2026-11-13"},
              {"column": "ngay_key", "operator": "less_than", "value": "2026-11-20"}],
  "group_by": ["ten_thanh_pho"], "order_by": [{"field": "value", "direction": "desc"}], "limit": 5}
- Trường không dùng thì BỎ HẲN, không truyền null. Chỉ các trường: metric, filters, group_by, time_grain, order_by,
  limit, skip_rules (và các trường hệ thống bổ sung). Trường lạ bị từ chối.
- operator: equals, not_equals, contains, not_contains, greater_than(_or_equal), less_than(_or_equal), in, not_in
  (value là danh sách), is_null, is_not_null (không có value). Ngày dạng YYYY-MM-DD.
- filters/group_by chỉ dùng cột của bảng chứa metric (xem knowledge.metrics[].table và thẻ bảng). Cột ở bảng khác
  (ví dụ vùng của thành phố ở dim_thanh_pho) thì dùng run_sql với JOIN theo join_paths.
- order_by.field là "value" hoặc một cột có trong group_by/time_grain.
- Bảng trộn loại dòng: metric thường đã tự chọn loại dòng bằng CASE. Không tự lọc loai_quan_sat khác loại mà metric
  dùng (sẽ ra NULL).
- Trả về: sql, columns, rows, row_count, truncated, notes. Đọc notes: giá trị lọc đã đổi, quy tắc đã áp, phạm vi thời
  gian đã gộp, cảnh báo.
### Lỗi QM_ARG_SCHEMA
Sai kiểu hoặc thiếu trường. Lỗi liệt kê MỌI trường sai cùng lúc, mỗi trường có fix và ví dụ JSON đúng: sửa tất cả
trong một lần gọi.
### Lỗi QM_FILTER_VALUE_NOT_FOUND
Giá trị lọc không có trong cột. Chọn giá trị trong valid_options (xếp theo độ gần). Không tự đặt biến thể khác.
### Lỗi QM_COLUMN_NOT_IN_TABLE
Cột không thuộc bảng của metric. Lỗi chỉ ra bảng có cột đó và đường nối: chuyển sang run_sql.
### Lỗi QM_GRAIN_UNSUPPORTED
Không gom theo giờ: dòng DU_BAO_GIO đã là một giờ; lọc theo khoảng thời gian bằng run_sql.
### Lỗi QM_EXPR_NOT_BUILDABLE
Biểu thức metric không dựng tự động: dùng expression và table có trong lỗi để viết run_sql.
### Ghi chú QM_EMPTY_FILTER (không phải lỗi)
Kết quả rỗng/NULL; notes cho biết bộ lọc nào loại hết dòng và giá trị gần nhất. Sửa đúng bộ lọc đó; nếu notes nói
"mọi giá trị lọc đều tồn tại" thì rỗng là kết quả thật: trả lời là không có.
```

#### run_sql.md

```markdown
# run_sql
## Tóm tắt
Chạy MỘT câu SELECT PostgreSQL chỉ đọc do bạn viết, khi query_metric không diễn đạt được (nối bảng, so sánh kỳ, dẫn
xuất, tương quan, bảng dọc, theo giờ). Chỉ dùng bảng trong danh sách bảng của context. Cú pháp PostgreSQL, không
phải SQL Server/MySQL.
## Hướng dẫn
- Tham số: {"sql": "SELECT ...", "purpose": "<phần câu hỏi được trả lời>"}.
- Viết đúng PostgreSQL: chuỗi trong nháy đơn 'Ha Noi'; tên cột/alias snake_case không dấu, không '-' hay dấu cách;
  nối chuỗi bằng ||; ngày: DATE '2026-11-19', cột + INTERVAL '1 day', date_trunc('week', cot); không DATEADD,
  GETDATE, DATE_FORMAT, IFNULL, TOP, backtick. Không dùng alias của SELECT trong WHERE/HAVING (lặp lại biểu thức).
  Chia: x / NULLIF(y, 0). Sắp giảm dần cột có NULL: ORDER BY cot DESC NULLS LAST.
- Lọc văn bản: dùng giá trị đúng cách ghi trong dữ liệu (entities hoặc value_dictionary của context, hoặc
  get_column_values). Dữ liệu thường không dấu.
- Nối bảng theo join_paths của context. Bảng dim_* nối bằng *_key, bảng dm_*/tb_* nối bằng *_id; không trộn.
- Bảng trộn loại dòng (có cột loại dòng, ví dụ loai_quan_sat): luôn lọc đúng một loại dòng mà cột cần đọc có giá
  trị (columns[].row_kinds). "Hiện tại" = dòng HIEN_TAI mới nhất.
- BẢNG DỌC (layout indicator_values): một ô chỉ có nghĩa khi biết (chỉ số, loại dòng).
  1. Luôn lọc chỉ số qua bảng danh mục: JOIN dim_chi_so_thoi_tiet c ON c.chi_so_key = f.chi_so_key
     WHERE c.ma_chi_so = 'nhiet_do_c'. Lọc theo ma_chi_so (mã), không theo tên có dấu.
  2. Lọc một loại dòng có trong indicators[].row_kinds của chỉ số (thường: chỉ số giờ ở HIEN_TAI/DU_BAO_GIO, chỉ số
     ngày ở DU_BAO_NGAY; có chỉ số giờ chỉ ở DU_BAO_GIO như mua_mm).
  3. Đọc đúng cột giá trị theo kiểu chỉ số (value_column): số ở gia_tri_so, đúng/sai ở gia_tri_dung_sai.
  4. Tổng hợp theo aggregation của chỉ số (SUM/AVG/MAX/MIN). Không SUM/AVG qua nhiều chỉ số; không so sánh giá trị
     khác đơn vị.
  5. Đếm lần quan sát bằng COUNT(DISTINCT quan_sat_id), không COUNT(*) (mỗi lần quan sát có nhiều dòng).
  Sai: SELECT SUM(gia_tri_so) FROM fact_chi_tiet_thoi_tiet           -- cộng mm với hPa
  Đúng: SELECT SUM(f.gia_tri_so) FROM fact_chi_tiet_thoi_tiet f JOIN dim_chi_so_thoi_tiet c ON c.chi_so_key=f.chi_so_key
        WHERE c.ma_chi_so='tong_luong_mua_mm' AND f.loai_quan_sat='DU_BAO_NGAY' AND ...
  Đếm giờ ban ngày: COUNT(*) FILTER (WHERE f.gia_tri_dung_sai) với ma_chi_so='la_ban_ngay', loai_quan_sat='DU_BAO_GIO'.
- Trả về: sql (đã chuẩn hóa), columns, rows (tối đa N dòng gửi bạn), row_count, truncated, notes (cảnh báo).
  truncated=true: viết lại câu gộp hơn thay vì đọc từng dòng.
### Lỗi SQL_PARSE
Cú pháp sai. Lỗi có excerpt quanh vị trí sai và fix theo mẫu. Sửa ĐÚNG chỗ đó, giữ nguyên ý truy vấn; không đổi bài toán.
### Lỗi SQL_FOREIGN_DIALECT
Dùng hàm/cú pháp của hệ khác. Thay bằng dạng PostgreSQL trong fix.
### Lỗi SQL_TABLE_NOT_IN_CONNECTION
Bảng không có. Chọn trong valid_options; không đoán tên.
### Lỗi SQL_NOT_SELECT / SQL_FORBIDDEN
Chỉ đọc được bằng một câu SELECT; không gọi hàm hệ thống.
### Lỗi DB_<sqlstate>
Database báo lỗi; mục 3.3 của tài liệu thiết kế giải nghĩa từng mã. Làm theo fix.
### Lỗi DB_TIMEOUT
Quá thời gian. Thu hẹp thời gian, lọc trước khi nối, gộp trước khi sắp xếp. Không chạy lại y nguyên.
### Ghi chú SQL_EMPTY (không phải lỗi)
0 dòng: notes đối chiếu từng chuỗi trong WHERE với dữ liệu. Có literal không tồn tại → sửa theo gợi ý. Mọi literal
tồn tại → kết quả rỗng là thật, trả lời "không có", không truy vấn lại để xác minh.
### Cảnh báo LONG_TABLE_* / ROW_KIND_MISSING (không phải lỗi)
Câu SQL đọc bảng dọc hoặc bảng trộn loại dòng sai cách. Sửa theo cảnh báo trước khi dùng kết quả.
```

#### ask_user.md

```markdown
# ask_user
## Tóm tắt
Dừng và hỏi lại người dùng khi thiếu thông tin bắt buộc và không có cách hiểu hợp lý. Tối đa 2 lần mỗi câu. Ưu tiên
giả định hợp lý và nói rõ giả định hơn là hỏi lại.
## Hướng dẫn
- Tham số: {"question": "Bạn muốn xem khoảng thời gian nào?", "options": ["7 ngày qua", "Tháng này"]}. options lấy
  từ dữ liệu hoặc knowledge.
- KHÔNG hỏi lại khi:
  - câu có "trong dữ liệu", "từng", "đã bao giờ": phạm vi là toàn bộ dữ liệu;
  - các cách hiểu cho cùng kết quả: chạy thử các cách hiểu trước (ví dụ hai chỉ số cùng 252,6) rồi trả lời và nêu cả hai;
  - "được dự báo": gồm cả dự báo đã lưu trong quá khứ, không chỉ từ hôm nay;
  - đã có giá trị mặc định khai báo (loại dòng mặc định, chỉ số ưu tiên).
- Nên hỏi lại khi: các cách hiểu cho kết quả khác hẳn và không có mặc định (ví dụ không có mốc thời gian trên bảng
  trộn số liệu thực tế và dự báo, trừ câu về hiện tại).
- Hệ thống tự gọi thay bạn khi một lỗi lặp lại nhiều lần (xem mục kiểm soát vòng lặp); khi đó đừng thử thêm.
### Lỗi ASK_LIMIT
Đã hỏi đủ số lần: chọn cách hiểu hợp lý nhất, nói rõ giả định, trả lời.
```

#### make_chart.md (công cụ do workflow `wf_e2bc0d7e-1ef` thêm)

Nội dung mô tả đã có trong `docs/reports/2026-11-20-thiet-ke-tra-loi-stream-bieu-do.md` mục 4.6. Khi workflow đó xong,
chuyển chuỗi mô tả sang `tool_docs/make_chart.md`: phần Tóm tắt là một câu; phần Hướng dẫn chứa cấu trúc `chart` và
danh sách loại `{chart_types}` được bật. Các lỗi của validator mang mã `CHART_*` theo định dạng ở mục 3.

#### query_indicator.md (công cụ mới đề xuất ở mục 5)

```markdown
# query_indicator
## Tóm tắt
Tính một hoặc nhiều chỉ số của BẢNG DỌC bằng SQL do hệ thống dựng: tự nối danh mục, lọc mã chỉ số và loại dòng,
chọn cột giá trị và phép tổng hợp đúng theo chỉ số, ghi đơn vị. Dùng thay run_sql cho mọi câu đọc bảng dọc.
## Hướng dẫn
- Ví dụ: {"table": "fact_chi_tiet_thoi_tiet", "indicator": "gio_giat_kmh", "row_kind": "DU_BAO_GIO",
  "filters": [{"column": "ten_thanh_pho", "operator": "equals", "value": "Ha Noi"},
              {"column": "ngay_key", "operator": "equals", "value": "2026-11-19"}]}
- Nhiều chỉ số cùng lúc dạng cột: {"indicators": ["nhiet_do_c", "do_am_pct"], "row_kind": "HIEN_TAI", "pivot": true,
  "latest_per": ["ten_thanh_pho"]} (giá trị mới nhất của mỗi thành phố).
- indicator là ma_chi_so (xem knowledge.indicators hoặc reading_guide.indicators). Bỏ row_kind thì dùng loại dòng mặc
  định của chỉ số. aggregation bỏ trống thì dùng cách tổng hợp của danh mục; chỉ số đúng/sai dùng COUNT_TRUE.
- Trả về như query_metric, thêm unit cho từng chỉ số và notes về chỉ số tương đương ở grain khác.
### Lỗi IND_NOT_FOUND
Mã chỉ số không có. Chọn trong valid_options (mã + tên + đơn vị).
### Lỗi IND_ROW_KIND_MISMATCH
Chỉ số không có ở loại dòng đã chọn. Dùng một loại dòng trong valid_options.
### Lỗi IND_AGG_INVALID
Phép tổng hợp không hợp với kiểu chỉ số (ví dụ SUM trên đúng/sai). Dùng phép trong valid_options.
### Lỗi IND_GRAIN_TOO_FINE
time_grain chi tiết hơn grain của loại dòng (ví dụ theo giờ trên DU_BAO_NGAY). Đổi loại dòng hoặc grain.
```

### 2.3 Thay đổi prompt đi kèm

Prompt agent (`prompt_text2sql_agent.py`, sau khi workflow hiện tại ghi bản mới):

- Thêm mục **"TRƯỜNG MỚI TRONG CONTEXT"**, khoảng 260 token, đã thử trong biến thể `full`:
  - mô tả `tables[]` (thẻ bảng), `join_paths`, `entities`, `time_ranges`, `indicators`;
  - quy tắc "chỉ gọi get_* cho thông tin chưa có trong context".

  Thiếu đoạn này thì mô hình vẫn tra lại khoảng 40% (ctx_only 1,00 lời gọi tra cứu mỗi câu, full 0,12).
- Thêm mục **"BẢNG DỌC"**, 4–5 dòng, đã thử trong điều kiện B của thực nghiệm bảng dọc. Nội dung tóm tắt 5 quy tắc của
  `run_sql.md`. Không viết dạng "phải gọi get_table trước": ở B câu này bị bỏ qua 12/12 lượt.
- Sửa mục **"KHI CÔNG CỤ BÁO LỖI"**:
  - "Lỗi có `code`, `fix`, `valid_options`: sửa mọi mục trong `errors` trong một lần gọi";
  - "khi hệ thống báo `escalation` thì làm đúng hành động được chỉ";
  - "kết quả rỗng có chẩn đoán thì tin chẩn đoán".
- Thu hẹp quy tắc "bảng trộn dự báo thì hỏi lại khoảng thời gian" để không áp vào câu "trong dữ liệu" hoặc "từng"
  (stress A3 × 2).

## 3. Giải mã lỗi

### 3.1 Định dạng lỗi có cấu trúc

Giữ khóa `error` ở mức trên cùng, để `tool_agent._call_tools` vẫn đặt `status="error"` và dữ liệu cũ vẫn đọc được.
Giá trị của khóa đổi từ chuỗi sang đối tượng; nhiều lỗi thì dùng `errors`:

```json
{
  "error": {
    "code": "QM_FILTER_VALUE_NOT_FOUND",
    "message": "Cột ten_thanh_pho không có giá trị 'TP.HCM'.",
    "field": "filters[0].value",
    "why": "Dữ liệu ghi tên thành phố không dấu, không viết tắt.",
    "fix": "Dùng một giá trị trong valid_options, ví dụ \"Ho Chi Minh\".",
    "valid_options": ["Ho Chi Minh", "Ha Noi", "Hai Phong"],
    "retry": "change_args",
    "next_tool": null
  },
  "errors": []
}
```

| Trường | Ý nghĩa |
|---|---|
| `code` | Mã ổn định, dạng `<CÔNG_CỤ>_<LỚP>` hoặc `DB_<sqlstate>`. Dùng để đếm vòng lặp, thống kê và tra docs |
| `message` | Một câu: sai gì, viết bằng tên tham số và giá trị thật |
| `field` | Đường dẫn tham số (`filters[0].column`, `sql@163`) |
| `why` | Vì sao sai, ngắn gọn; có thể bỏ khi hiển nhiên |
| `fix` | Hành động cụ thể, kèm ví dụ JSON hoặc SQL khi có |
| `valid_options` | Cột hoặc danh sách có ≤ 30 giá trị thì **liệt kê hết**. Nhiều hơn thì lấy 10–30 giá trị, xếp theo thứ tự: bí danh khai báo → khớp viết tắt (chữ cái đầu, bỏ tiền tố "TP."/"Thành phố") → không dấu → trigram. **Không xếp chỉ bằng trigram**: đo trên 12 thành phố, trigram xếp `TP.HCM` gần `Thai Binh` nhất (không có Ho Chi Minh trong top 3), `HN` gần `Hue` nhất, `Sài Gòn` không gần giá trị nào. Thứ tự đó còn tệ hơn danh sách ABC hiện tại |
| `retry` | `change_args` (đổi tham số sẽ được) / `switch_tool` (phải đổi công cụ, xem `next_tool`) / `ask_user` / `no` (không thử lại, trả lời với phần đã có) |
| `next_tool` | Công cụ nên dùng tiếp, nếu có |
| `errors` | Các lỗi khác tìm thấy **cùng lúc** (gom lỗi), cùng cấu trúc |

**Cài đặt:**

- `ToolError` (trong `backend/agent_package/tool_agent.py`) thêm các thuộc tính tùy chọn `code, field, why, fix,
  valid_options, retry, next_tool, extra: list[ToolError]` và `to_payload()`.
  - `str(error)` vẫn là `message`, để `AgentStepOut.error` và log không đổi kiểu.
  - `AgentStepOut` thêm `error_code: str | None = None`, có mặc định để đọc được snapshot cũ.
- `_validation_message` đổi thành `_validation_errors`: mỗi mục pydantic thành một `ToolError(code="<TOOL>_ARG_SCHEMA",
  field=…, fix=<ví dụ đúng theo kiểu trường>)`, câu chữ tiếng Việt và gom tất cả trong một lần.
- File mới `backend/modules/text2sql/services/tool_errors.py`:
  - hằng mã lỗi (`CODES`);
  - hàm dựng lỗi;
  - xếp hạng `valid_options` theo độ gần (tái dùng `normalized`; thêm khớp viết tắt như hàm `acronym` trong
    `preprocess-context/snapshot/expand.py`, bí danh khai báo, cuối cùng mới đến trigram);
  - `decode_db_error(sqlstate, message, position, sql, catalog)` (mục 3.3).
- **Gom lỗi:**
  - `query_metric` kiểm tra toàn bộ tham số (schema → cột → toán tử → giá trị) và thu thập lỗi thay vì ném ở lỗi đầu
    tiên. Giới hạn: khi pydantic từ chối một trường thì không kiểm được ngữ nghĩa của chính trường đó. Chỉ gom được
    lỗi schema với lỗi ngữ nghĩa của **các trường khác**, bằng cách kiểm từng filter trên dict thô. Sau khi
    null → `[]` thì trường hợp ở `49e9a64f97b6` hết hẳn, không cần gom;
  - `run_sql` gom các bảng không có trong một lần.
- **Pydantic:**
  - `QueryMetricArgs`, `FilterArg`, `OrderArg` dùng `model_config = ConfigDict(extra="forbid")`;
  - các trường danh sách nhận `None` thành `[]` qua `field_validator(mode="before")`;
  - `limit: None` đã hợp lệ sẵn (`int | None`), không cần sửa.
  - `extra="forbid"` đổi JSON schema gửi cho model (`additionalProperties: false`). Trước khi bật, kiểm lại các
    trường mà workflow `wf_e2bc0d7e-1ef` thêm vào tham số công cụ.
- **Ghi mọi lỗi vào `steps`:** hiện chỉ `query_metric`, `run_sql` và `_execute` gọi `_record` khi lỗi. Lỗi của
  `get_metric`, `get_table`, `get_expert_rule`, `ask_user`, lỗi pydantic, công cụ lạ và lời gọi lặp **không có trong
  `AgentStepOut`**. Trong stress, 17/21 lỗi (`get_table`) vì vậy không thấy được từ `answers[].steps`. Đ1 phải ghi
  các lỗi này, ví dụ qua `on_tool` hoặc trong `tool_agent`, thì các chỉ số ở 7.3 mới đếm đúng.

### 3.2 Bảng chuyển đổi thông báo cũ → mới

| Mã | Công cụ | Thông báo cũ | Thông báo mới (message → fix / valid_options / retry) |
|---|---|---|---|
| `METRIC_NOT_FOUND` | get_metric, query_metric | `Không tìm thấy metric 'X'.` (gợi ý "Gần giống" thường rỗng) | "Không có metric 'X'. get_metric nhận tên hoặc id, không nhận mô tả." → valid_options = 10 metric gần nhất theo nhãn không dấu, bỏ đơn vị trong ngoặc; nếu connection có ≤ 30 metric thì liệt kê hết. retry=change_args; nếu không metric nào hợp: next_tool=run_sql |
| `METRIC_AMBIGUOUS` | get_metric | `'X' khớp nhiều metric: a, b. Dùng id.` | Giữ ý, valid_options = [{id, name, label, table}]. retry=change_args |
| `TABLE_NOT_FOUND` | get_table | `Không tìm thấy bảng 'X'.` | "Không có bảng 'X' trong connection." → valid_options = mọi bảng `{name, label, layout}` (≤ 30, xếp theo độ gần); fix "chọn một tên trong danh sách, không đoán". retry=change_args |
| `SQL_TABLE_NOT_IN_CONNECTION` | run_sql | `Bảng 'X' không có trong connection này. Ghi đủ schema.bảng.` / `… Dùng get_table để xem bảng có sẵn.` | Như trên. Chỉ nói "ghi đủ schema.bảng" khi tên ngắn có thật ở nhiều schema. Bỏ gợi ý "Dùng get_table để xem bảng có sẵn", vì get_table không liệt kê được bảng |
| `RULE_NOT_FOUND` | get_expert_rule | `Không tìm thấy quy tắc 'X'.` | valid_options = toàn bộ quy tắc (thường ít) hoặc 10 gần nhất. retry=change_args |
| `COLUMN_NOT_IN_TABLE` | query_metric, get_column_values | `Cột 'X' không thuộc bảng T. Các cột hợp lệ: <35 cột>` | "Cột 'X' không thuộc bảng T." why: "Cột này ở bảng U (nối qua `T.k = U.k`)" nếu tìm được; valid_options = 5 cột gần tên trong T; fix: "query_metric không nối bảng: dùng run_sql với JOIN" → retry=switch_tool, next_tool=run_sql. Không tìm được bảng nào thì retry=change_args |
| `QM_ARG_SCHEMA` | query_metric | `Tham số không hợp lệ: order_by: Input should be a valid list` | "order_by phải là danh sách." fix: `"order_by": [{"field": "value", "direction": "desc"}]` hoặc bỏ trường. Mọi trường sai liệt kê cùng lúc. (Sau khi null → [] thì lỗi này gần như hết) |
| `QM_UNKNOWN_ARG` | query_metric | (không báo, bỏ qua lặng lẽ) | "Không có tham số 'date_range'." fix: "lọc thời gian bằng filters trên cột ngày: …ví dụ…". retry=change_args |
| `QM_GRAIN_UNSUPPORTED` | query_metric | `time_grain.grain: Input should be 'day',…` | "query_metric không gom theo giờ." fix: "dòng DU_BAO_GIO đã là một giờ: dùng run_sql (hoặc query_indicator) lọc theo khoảng giờ". retry=switch_tool |
| `QM_FILTER_VALUE_NOT_FOUND` | query_metric | `Cột c không có giá trị 'TP.HCM'. Một số giá trị có: [8 giá trị đầu ABC]` | Giữ message. Cột ≤ 30 giá trị: liệt kê hết (như bản viết lại E04). Nhiều hơn: xếp theo bí danh khai báo → viết tắt → không dấu (xem 3.1; trigram một mình làm `TP.HCM` mất Ho Chi Minh). Khi khớp bí danh hoặc viết tắt **duy nhất** thì **tự đổi và ghi chú** như với dấu. `Sài Gòn` chỉ giải được bằng bí danh khai báo. retry=change_args |
| `QM_FILTER_OP_TYPE` | query_metric | `Toán tử contains chỉ dùng cho cột văn bản ('ngay_key').` | Giữ, thêm fix: "cột ngày dùng greater_than_or_equal + less_than với YYYY-MM-DD" kèm ví dụ |
| `QM_ORDER_FIELD` | query_metric | `Chỉ sắp xếp được theo 'value' hoặc cột có trong group_by/time_grain…` | Giữ, valid_options = ["value", …group_by] |
| `QM_EXPR_NOT_BUILDABLE` | query_metric | `Biểu thức … không dựng tự động được; hãy dùng get_metric…` | Đưa luôn `expression` và `table` vào lỗi; retry=switch_tool, next_tool=run_sql (bỏ được một vòng get_metric) |
| `QM_ROW_KIND_CONFLICT` | query_metric | (không báo, toàn NULL) | "Metric tự lấy loại dòng DU_BAO_GIO (CASE) nhưng filters lọc HIEN_TAI: kết quả sẽ NULL." fix: bỏ filter loại dòng hoặc chọn metric khác. retry=change_args |
| `QM_SKIP_RULE_UNKNOWN` | query_metric | (bỏ qua lặng lẽ) | valid_options = quy tắc gắn với metric |
| `QM_EMPTY_FILTER` (notes) | query_metric | (NULL không ghi chú) | notes: "0 dòng khớp. Bộ lọc `ten_thanh_pho contains 'TP.HCM'` khớp 0 giá trị; gần nhất: 'Ho Chi Minh'." hoặc "Mọi giá trị lọc đều tồn tại; 0 dòng trong khoảng 13/11–19/11: kết quả rỗng là thật." |
| `GCV_NON_TEXT_COLUMN` | get_column_values | `Chỉ liệt kê giá trị cho cột văn bản; 'X' có kiểu BIGINT.` | Theo vai trò cột: indicator_key → "Đây là khóa chỉ số của bảng dọc; danh sách chỉ số: dim_chi_so_thoi_tiet (ma_chi_so, ten_chi_so, don_vi), nối c.chi_so_key = f.chi_so_key" (hoặc trả luôn danh sách sau khi hỗ trợ). Cột ngày/số → fix `SELECT MIN(X), MAX(X)` bằng run_sql. retry=switch_tool |
| `GCV_EMPTY` (notes) | get_column_values | `rows: []` | notes: "Không có giá trị chứa 'TP.HCM'; giá trị gần nhất: …" (trigram trên toàn bộ giá trị nếu ≤ 500) |
| `SQL_PARSE` | run_sql | `Không đọc được cú pháp SQL (PostgreSQL): Invalid expression / Unexpected token. Line 1, Col: 163.` | "Lỗi cú pháp ở ký tự 163: `…AS ngay-vuot-nguong, …`" (±30 ký tự, đánh dấu vị trí) + fix theo mẫu nhận diện: alias có `-`/dấu cách → `"ngay_vuot_nguong"`; backtick → nháy kép; `TOP n` → `LIMIT n`. retry=change_args, kèm câu "giữ nguyên ý truy vấn" |
| `SQL_FOREIGN_DIALECT` | run_sql | `column "day" does not exist` (từ database) | Chặn trước khi chạy bằng sqlglot: "DATEADD không có trong PostgreSQL: dùng `cot + INTERVAL '1 day'`." Bảng ánh xạ: DATEADD, DATEDIFF, GETDATE/NOW, DATE_FORMAT/FORMAT, IFNULL/ISNULL, TOP, backtick, `+` nối chuỗi |
| `SQL_NOT_SELECT`, `SQL_FORBIDDEN_FUNC`, `SQL_MULTI_STATEMENT` | run_sql | như hiện tại | Giữ, retry=change_args; nếu gặp lần 2 → retry=no |
| `DB_<sqlstate>` | run_sql, query_metric | `Database báo lỗi 42703: column "tb" does not exist` | Xem 3.3 |
| `DB_TIMEOUT` (57014) | run_sql, query_metric | `Truy vấn vượt quá N giây. Hãy thu hẹp…` | Giữ, thêm `retry=change_args` và chặn chạy lại y nguyên; lần 2 → retry=no |
| `ASK_LIMIT` | ask_user | `Đã hỏi lại người dùng đủ số lần…` | Giữ, retry=no |
| `TOOL_UNKNOWN` | (vòng agent) | `Không có công cụ 'X'. Các công cụ hợp lệ: …` | Giữ (điểm 3/3) |
| `REPEATED_CALL` | (vòng agent) | `Lời gọi này đã lỗi trước đó với đúng các tham số này…` | Giữ cho lời gọi giống hệt, thêm lại `fix` của lỗi gốc |

### 3.3 Giải mã lỗi PostgreSQL (SQLSTATE)

**Đầu vào cần có.** `source_query_repository.run_read_only` hiện chỉ giữ `sqlstate` và `message_primary`/`hint`.
Cần đưa thêm `diag.statement_position`, `diag.column_name` và `diag.table_name` vào `ToolError`, tức một trường
`db: {sqlstate, message, position, hint}`. Sau đó `tool_errors.decode_db_error` kết hợp ba nguồn:

- mã SQLSTATE;
- regex trên message;
- phân tích sqlglot của chính câu SQL (danh sách alias trong SELECT, literal, bảng, cột của catalog).

| SQLSTATE | Tình huống nhận diện | Thông báo mới (fix) | retry |
|---|---|---|---|
| 42P01 undefined_table | — (thường đã bắt ở guard) | như `SQL_TABLE_NOT_IN_CONNECTION` | change_args |
| 42703 undefined_column | Tên trùng alias trong SELECT | "`tb` là bí danh của SELECT; PostgreSQL không dùng bí danh trong WHERE/HAVING/GROUP BY biểu thức: lặp lại biểu thức hoặc bọc bằng subquery/CTE." | change_args |
| 42703 | Tên có dấu cách, có dấu, hoặc trùng một giá trị dữ liệu | "`\"Ha Noi\"` trong nháy kép là tên cột; chuỗi phải dùng nháy đơn: `'Ha Noi'`." | change_args |
| 42703 | Cột có ở bảng khác trong catalog | "Cột `vung_mien` không ở bảng `f`; có ở `dim_thanh_pho` (nối `f.thanh_pho_key = t.thanh_pho_key`)." + 5 cột gần tên trong bảng đang dùng | change_args |
| 42703 | Còn lại | valid_options = cột gần tên của các bảng trong FROM | change_args |
| 42702 ambiguous_column | — | "Cột `ngay_key` có ở nhiều bảng trong FROM: ghi rõ bí danh `f.ngay_key`." | change_args |
| 42803 grouping_error | — | "Cột `X` phải nằm trong GROUP BY hoặc trong hàm gộp." | change_args |
| 42883 undefined_function | Tên hàm thuộc hệ khác | như `SQL_FOREIGN_DIALECT` | change_args |
| 42883 | `operator does not exist: date = text`, `text > integer` | "So sánh khác kiểu: ép kiểu `cot::date` hoặc dùng `DATE '2026-11-19'`." | change_args |
| 42725 ambiguous_function | `unknown + unknown` | "Nối chuỗi bằng `||`; phép tính trên literal cần ép kiểu." | change_args |
| 22P02 invalid_text_representation | — | "Giá trị 'abc' không đúng kiểu của cột `X` (kiểu Y)." | change_args |
| 22007/22008 datetime | — | "Ngày viết `DATE 'YYYY-MM-DD'`, khoảng `INTERVAL '7 days'`." | change_args |
| 22012 division_by_zero | — | "Chia cho 0: dùng `x / NULLIF(y, 0)`." | change_args |
| 21000 cardinality_violation | — | "Subquery trả nhiều dòng: dùng `IN (…)` hoặc thêm điều kiện, `LIMIT 1`." | change_args |
| 42601 syntax_error (từ DB) | — | như `SQL_PARSE`, dùng `position` của diag để trích đoạn | change_args |
| 57014 query_canceled | — | `DB_TIMEOUT` | change_args, lần 2: no |
| 53xxx, 54xxx (tài nguyên, quá phức tạp) | — | "Truy vấn quá nặng: gộp trước khi nối, bớt cột." | change_args, lần 2: no |
| 25006, 42501 (chỉ đọc, quyền) | — | "Không có quyền đọc hoặc ghi: chỉ dùng bảng trong danh sách." | no |
| 08xxx, mất kết nối | — | Giữ `Text2SqlQueryFailed`: dừng cả câu, không trả cho model | — |
| Khác | — | `DB_<sqlstate>`: message gốc + hint của Postgres | change_args |

Có 3 mã đáng chặn trước khi chạy (rẻ hơn một lần gọi database và cho thông báo đúng bản chất):
- `SQL_FOREIGN_DIALECT`;
- chuỗi trong nháy kép (so tên định danh với tập cột của catalog);
- alias trong HAVING/WHERE.

## 4. Kiểm soát vòng lặp ngoài lời gọi giống hệt

### 4.1 Cơ chế

Đặt trong `backend/agent_package/tool_agent.py`, chỉ dựa vào `code` của lỗi nên không phụ thuộc module.
`ToolAgentContext` thêm:

```python
error_counts: Counter[tuple[str, str]]    # (tool, code)
consecutive_failures: int                  # số vòng liên tiếp có lời gọi thất bại (lỗi hoặc rỗng-nghi-ngờ)
total_failures: int
loop_policy: LoopPolicy                    # ngưỡng, có mặc định
doc_lookup: Callable[[str, str], str|None] # = tool_docs.error_help
```

Các bước leo thang khi một lời gọi thất bại:

| Bậc | Điều kiện kích hoạt | Hành động của code | Lý do theo dữ liệu |
|---|---|---|---|
| 0 | Lỗi lần đầu | Trả lỗi có cấu trúc (mục 3) | 49/52 chuỗi dài 1; 15/15 lỗi giá trị sửa được ngay |
| 1 | Cùng `(tool, code)` lần thứ **2** trong một lượt, **hoặc** 2 vòng liên tiếp thất bại | Gắn `escalation`: `{"level": 1, "doc": error_help(tool, code), "hint": "Đã gặp lỗi này 2 lần. Đổi cách làm: <next_tool hoặc gợi ý>", "valid_options": <đầy đủ hơn>}`. Với `TABLE_NOT_FOUND` là danh sách bảng đầy đủ; với `COLUMN_NOT_IN_TABLE` là thẻ bảng | Trên 910 lượt đã lưu, điều kiện cặp tool+code kích hoạt **0 lần**. Điều kiện "2 vòng liên tiếp thất bại" kích hoạt **1 lần** (`49e9a64f97b6`: QM_ARG_SCHEMA rồi QM_FILTER_VALUE_NOT_FOUND) và vô hại, vì bậc 1 chỉ gắn thêm tài liệu. Trên stress, bậc này bắt được cả 4 lượt lặp cùng lớp (get_table đoán bảng) ngay ở lần lặp đầu |
| 2 | Cùng `(tool, code)` lần thứ **3**, **hoặc** 3 vòng liên tiếp thất bại | **Chặn công cụ cho lớp lỗi đó**: các lời gọi `(tool)` kế tiếp mà lỗi lại cùng `code` bị thay bằng `{"error": {"code": "LOOP_BLOCKED", "retry": "switch_tool" or "ask_user"}}`. Gửi kèm HumanMessage hệ thống: "Dừng thử biến thể. Hoặc dùng <next_tool>, hoặc gọi ask_user với các lựa chọn: …, hoặc trả lời với phần đã có." | Chuỗi dài nhất quan sát: 3 (stress), đều là đoán tên bảng. Với thông báo mới (A/B E01), lỗi tiếp theo về 0, nên bậc 2 chỉ còn bắt trường hợp bất thường |
| 3 | Tổng lỗi trong lượt ≥ **5**, **hoặc** `rounds ≥ max_steps − 2` mà vòng cuối vẫn thất bại | Kết thúc sớm: gửi `PARTIAL_NOTICE` ("Trả lời ngay bằng kết quả đã có; nêu phần chưa trả lời được, lỗi gặp phải ở dạng dễ hiểu, và gợi ý người dùng cách hỏi lại"), không cho gọi công cụ nữa (như `EXHAUSTED_NOTICE` hiện tại) | Tối đa quan sát: 6 lỗi/lượt (stress L5), vẫn ra đúng. **Với thông báo hiện tại, ngưỡng 5 sẽ biến lượt đúng này thành câu trả lời dở dang**, nên chỉ bật ngưỡng này cùng lúc với thông báo mới (bậc 1–2 đã chặn chuỗi trước lỗi thứ 5). 910 lượt đã lưu có tối đa 2 lỗi/lượt |
| Tự hỏi lại | Bậc 2 với `retry=ask_user` (ví dụ giá trị thực thể không tồn tại và có ≥ 2 ứng viên gần) | Code gọi `AgentPause` thay model với câu hỏi dựng từ `valid_options` (tôn trọng `MAX_CLARIFICATIONS`) | Tránh model đoán tiếp; chỉ khi có lựa chọn cụ thể. **Mặc định tắt**: 3/7 lượt stress hỏng (A3 × 2, L1#2) là hỏi lại thừa hoặc hiểu sai "được dự báo", và chưa có dữ liệu nào cho thấy cần code tự hỏi thay model |

**Các quy ước đi kèm:**

- **"Thất bại"** gồm lỗi cứng và **kết quả rỗng/NULL có chẩn đoán "literal không tồn tại"**. Rỗng thật không tính, vì
  15 lượt "miền Bắc không mưa" là rỗng đúng nghĩa.
- **Khóa đếm** là `(tool, code)`, không phải `(tool, code, field)`. Lý do: chuỗi đoán bảng đổi tham số mỗi lần nhưng
  `code` giữ nguyên. Trường `field` chỉ dùng để viết `hint`.
- **`failed_calls`** (chặn giống hệt) giữ nguyên, kèm lại `fix` của lỗi gốc.
- **Ghi log:** mỗi bước leo thang ghi vào `AgentStepOut` (`escalation_level`) và log, để bộ đo đếm được `loop_count`.
- **Song song:** nhiều lời gọi trong một vòng (bắn rải) được đếm theo vòng, không theo từng lời gọi, cho
  `consecutive_failures`. **`error_counts` cũng chỉ tăng tối đa 1 lần cho mỗi `(tool, code)` trong một vòng.** Nếu
  đếm theo từng lời gọi, một câu so sánh 3 thành phố viết tắt (TP.HCM, HN, ĐN) gọi song song 3 `query_metric` sẽ bị
  chặn (bậc 2) ngay ở vòng đầu, dù mỗi lỗi đều sửa được trong 1 bước.
- **Bậc 2 nên có thêm điều kiện "bỏ qua danh sách":** chỉ chặn khi lời gọi lỗi mới dùng giá trị **nằm ngoài**
  `valid_options` đã đưa ở lần trước. Điều kiện này đúng với chuỗi L5 (đoán tên mới thay vì chọn trong danh sách) và
  không chặn nhầm khi agent sửa lần lượt các giá trị khác nhau.
- **Ngưỡng là cấu hình** (`TEXT2SQL_LOOP_REPEAT_ESCALATE=2`, `TEXT2SQL_LOOP_REPEAT_BLOCK=3`,
  `TEXT2SQL_LOOP_MAX_FAILURES=5`), để điều chỉnh khi đo trên mô hình yếu hơn.

### 4.2 Vì sao không chỉ tăng hay giảm `max_steps`

- Không lượt nào chạm `max_steps=12` (tối đa 7 vòng trong dữ liệu đã lưu).
- Giảm `max_steps` không cắt được chuỗi đoán mò sớm hơn bậc 1–2, mà lại cắt mất các câu nhiều bước hợp lệ.
- Tăng `max_steps` chỉ kéo dài vòng lặp.

## 5. Thiết kế hỗ trợ bảng dọc

### 5.1 Catalog (`catalog_context.py`, `agent_catalog.py`)

**`TableInfo` thêm các trường:**

- `layout`: `wide` | `indicator_values` | `indicator_catalog`.
- `roles`: `{time, row_kind, indicator_key, value: {number, boolean, text}, catalog_key/code/name/unit/value_kind/aggregation, entity_key}`.
- `row_kinds`: `[{value, label, time_grain}]`, từ `table_time_grains`.
- `indicator_catalog`: `{table, join: "c.chi_so_key = f.chi_so_key", code_column, name_column, unit_column}`.
- `indicators`: `[{code, name, name_ascii, unit, value_kind, value_column, aggregation, row_kinds, equivalent}]`.
  - Đọc từ dữ liệu bảng danh mục khi dựng catalog, theo cách của `srv_indicators.read_indicators` bên extension.
  - Cache theo `content_hash` của dictionary cộng lần nạp dữ liệu mới nhất.
  - Tối đa khoảng 500 chỉ số; vượt quá thì `too_many=true` và chỉ đưa vào index.
- `join_paths` từ `referenced_column_id`.

**`ColumnInfo` thêm:** `unit`, `semantic_role`, `aggregations`, `references`, `row_kinds` (loại dòng mà cột có giá
trị, lấy từ profile).

**Ánh xạ `catalog_value_kind` → qualifier** (SO → number, DUNG_SAI → boolean, CHU → text): đọc từ metadata mới (mục
5.6). Trong lúc metadata chưa có, suy ra từ dữ liệu: chỉ số nào chỉ có giá trị ở `gia_tri_dung_sai` thì là boolean.
Danh mục hiện chỉ có SO (24) và DUNG_SAI (1).

**Bảng dọc không tự mang loại dòng hoặc thực thể** (`tb_gia_tri_quan_sat` chỉ có `chi_so_id`, `quan_sat_id`, các cột
value): catalog phải **kế thừa** `row_kind`, `time`, thành phố của bảng cha qua khóa ngoại đã khai báo
`quan_sat_id → tb_quan_sat_thoi_tiet`. Metadata hiện có đủ để làm việc này. Cũng từ khóa ngoại đó suy được khóa thực
thể dùng để đếm lần quan sát (`quan_sat_id`, có ở cả hai bảng dọc). Vì vậy `entity_key_column_id` ở mục 5.6 chỉ cần
khi bảng dọc không có khóa ngoại tới bảng "lần quan sát".

### 5.2 Index và truy hồi (`index_documents.py`)

- Thêm topic `indicator`: mỗi chỉ số của mỗi bảng dọc là một tài liệu. Ví dụ trong
  `long-tables/proposed_payloads.json` mục 2. Nội dung:
  - tên có dấu và không dấu, mã;
  - bảng và điều kiện lọc;
  - đơn vị, phép tổng hợp, cột giá trị, loại dòng;
  - chỉ số tương đương ở grain khác.
- Tài liệu bảng dọc ghi "dạng dọc", cột chỉ số, loại dòng và vài tên chỉ số.
- Tài liệu cột của bảng trộn loại dòng ghi "Chỉ có ở: DU_BAO_NGAY".
- `ChatService.preprocess` lấy thêm top-k `indicators` và đưa vào knowledge.

Đây là cách duy nhất để tên chỉ số (nằm trong *dữ liệu* của bảng danh mục) được truy hồi.

### 5.3 Công cụ

| Công cụ | Thay đổi |
|---|---|
| `get_table` | Trả `layout`, `reading_guide` do code sinh từ metadata. Mẫu sinh tự động: `long-tables/tools/guide.py` → `guide_fact_chi_tiet.json`. Nội dung: `how_to_read`, `indicator_column`, `catalog` (cách nối), `value_columns`, `row_kind` kèm grain, `count_entities_by`, `indicators[]`, `example_sql`. Cùng nội dung với thẻ bảng của context (một hàm dựng chung) |
| `get_column_values` | Cột vai trò `indicator_key`: tự nối danh mục, trả `(khóa, mã, tên, đơn vị)`. Coi `_` như khoảng trắng khi tìm |
| `query_indicator` (mới) | Tham số `{table, indicator \| indicators[], row_kind?, filters, group_by, time_grain?, aggregation?, pivot?, latest_per?}`. Code tự làm: nối danh mục, lọc `ma_chi_so` và `loai_quan_sat`, chọn cột giá trị theo kiểu, phép tổng hợp mặc định từ `indicator_aggregations` (NONE → giá trị tại thời điểm, boolean → COUNT_TRUE). `pivot` sinh `MAX(value) FILTER (WHERE code=…)`; `latest_per` lấy dòng mới nhất theo thực thể. Notes ghi đơn vị và chỉ số tương đương. Lỗi kiểm tra trước: `IND_NOT_FOUND`, `IND_ROW_KIND_MISMATCH`, `IND_AGG_INVALID`, `IND_GRAIN_TOO_FINE`, `ROW_KIND_MISSING` (theo tiền lệ `grain_problems` của extension). Cài đặt ở file mới `services/indicator_builder.py`, tái dùng `FilterArg`, `_literal`, phần dựng bộ lọc của `sql_builder` |
| `run_sql` (`sql_guard.py` + phân tích sau parse) | **Chặn** (ToolError `LONG_TABLE_UNFILTERED_AGG`): SUM/AVG/MIN/MAX trên cột value của bảng dọc mà WHERE không có điều kiện `=`/`IN` trên cột chỉ số hoặc mã chỉ số, và GROUP BY cũng không có cột chỉ số. **Cảnh báo** (notes, không chặn): `LONG_TABLE_COUNT_STAR` (COUNT(*) trên bảng dọc → COUNT(DISTINCT entity_key)); `ROW_KIND_MISSING` (đọc bảng có row_kind mà không lọc hoặc nhóm theo row_kind); `ROW_KIND_COLUMN_MISMATCH` (đọc cột chỉ có ở loại X nhưng lọc loại Y); `BOOLEAN_VALUE_COLUMN` (đọc `gia_tri_so` cho chỉ số boolean); `JOIN_KEY_MIX` (nối `*_id` với `*_key` khi không có khóa ngoại khai báo) |
| `query_metric` | `QM_ROW_KIND_CONFLICT`; `ORDER BY … NULLS LAST` khi dựng |

**Phương án thay thế cho `query_indicator`:** sinh tự động "metric ảo" cho mỗi chỉ số để `query_metric` dùng lại
`sql_builder`. Cách này rẻ hơn về số công cụ, nhưng thêm 25 metric cho mỗi bảng dọc và khó diễn đạt `pivot`/
`latest_per`. Khuyến nghị dùng công cụ riêng (xem quyết định D3).

### 5.4 Prompt và tool docs

Xem mục 2.2 (`run_sql.md`, `query_indicator.md`) và 2.3 (mục "BẢNG DỌC" trong prompt).

Điểm quan trọng từ thực nghiệm: trong cả hai điều kiện A và B, agent gọi `get_table` **0 lần**. Riêng ở B, đoạn prompt
còn ghi rõ "trước khi viết SQL trên bảng này phải gọi get_table và làm theo how_to_read", nhưng agent bỏ qua cả 12/12
lượt. Phần cải thiện của B đến từ `knowledge.indicators` có sẵn trong context. Vì vậy hướng dẫn đọc bảng phải đi qua
ba kênh: context (thẻ bảng hoặc danh sách chỉ số), prompt hoặc tool docs, và cảnh báo của `run_sql`. Không thể chỉ đặt
trong `get_table`, và không dựa vào câu lệnh "hãy gọi công cụ X trước" trong prompt. Thẻ `reading` dạng `must[]` ở mục
5.5 **chưa được thử trực tiếp**.

### 5.5 Thẻ đọc bảng trong context

Khi top-k truy hồi trúng một bảng dọc, một chỉ số, hoặc một cột của bảng trộn loại dòng, code gắn thẻ `reading` vào
`knowledge.tables[]`. Thẻ gồm:
- `must[]`: lọc mã chỉ số, lọc một loại dòng, `COUNT(DISTINCT quan_sat_id)`;
- `matched_indicators[]`: chỉ số khớp câu hỏi, kèm cột giá trị, đơn vị, phép tổng hợp, loại dòng, gợi ý;
- một câu SQL mẫu.

Ví dụ ở `long-tables/proposed_payloads.json` mục 4. Với bảng dọc có danh mục, thẻ là phần lớn nhất (phần tables lên
tới 3.549 token), nên chỉ đưa danh mục rút gọn của các chỉ số khớp cộng với tên các chỉ số còn lại.

### 5.6 Metadata cần có trong data dictionary

| Mục | Hiện có | Cần thêm | Cách lấy |
|---|---|---|---|
| layout, vai trò cột, row_kind → grain, mã tổng hợp → hàm | Có | — | Đã khai báo |
| `indicator_catalog_id` | Có (đã kiểm trên app DB) | — | Đã khai báo |
| Khóa ngoại (`referenced_column_id`) | Có, 22 cặp | — | Đã khai báo |
| Khóa thực thể của bảng dọc (đếm lần quan sát) | Suy được từ khóa ngoại `quan_sat_id` | `table_dictionaries.entity_key_column_id` (tùy chọn, chỉ khi không suy được) | Khóa ngoại; nếu không có thì profiling: cột mà (cột, chỉ số) là duy nhất; admin xác nhận |
| `catalog_value_kind` → qualifier | Không | `catalog_value_kind_map` (lưu cùng kiểu bảng với `indicator_aggregations`) | Admin; suy từ dữ liệu khi thiếu |
| Chỉ số × loại dòng có dữ liệu; cột × loại dòng có giá trị | Không | Bảng sinh tự động `indicator_profiles`, `column_row_kinds` | Profiling khi đồng bộ hoặc nạp |
| Loại dòng mặc định | Không | `default_row_kind` (tùy chọn) | Admin |
| Chỉ số tương đương ở hai grain, chỉ số ưu tiên | Không | `indicator_equivalences` (tùy chọn) | Admin (gợi ý bằng so khớp tên) |
| Ký hiệu đơn vị chuẩn (°C, km/h) | Tên không dấu ("Do C") và mã đơn vị (`ma_don_vi` = `DEG_C`…) | Bảng ánh xạ mã đơn vị → ký hiệu (từ điển chuẩn, không cần admin) | Từ điển chuẩn |
| Bí danh giá trị thực thể (TP.HCM, Sài Gòn, HN) | Không | `value_aliases` theo cột | Admin; gợi ý từ log lỗi `QM_FILTER_VALUE_NOT_FOUND` |
| Expert rule cho bảng dọc ("hiện tại = HIEN_TAI mới nhất", "chỉ số ngày lấy từ DU_BAO_NGAY") | Chỉ có cho bảng ngang | Thêm 2 quy tắc | Admin |
| Sửa sai | `column_aggregations` của `gia_tri_so`; vai trò `time` = `tao_luc` của `dm_chi_so_thoi_tiet` | Bỏ | Admin |

**Khi metadata thiếu**, xử lý theo thứ tự:

1. **Heuristic kèm độ tin cậy:**
   - Đoán bảng dọc: ít cột, có một cột khóa hoặc mã có lực lượng ≤ 500 nối sang bảng có `ma_`/`ten_`/`don_vi`, và 1–3
     cột value cùng tiền tố.
   - Đoán cột loại dòng: cột văn bản ít giá trị làm các cột khác null theo từng giá trị, như ma trận 408/0/6.048.
   - Đoán phép tổng hợp từ đơn vị.
2. **Đưa kết quả cho agent** dạng `inferred=true` kèm cảnh báo.
3. **Ghi đề xuất vào hàng chờ duyệt** (như `own_knowledge_proposals`).
4. **Chỉ chặn và hỏi người dùng** khi không suy ra được cột chỉ số.

## 6. Mở rộng context ở bước preprocess

### 6.1 Những gì thêm vào

| Mã | Nội dung | Token thêm | Hiệu quả đo được |
|---|---|---:|---|
| A | Metric đầy đủ: `table`, `expression`, cảnh báo, `auto_rules` | ~+200 | get_metric 25 → 4 (lite) |
| B | Thẻ bảng: cột dạng `tên kiểu \| nhãn \| đơn vị \| → FK \| giá trị`; grain; `data_range`; `row_kind` (giá trị, grain, cột có ở loại nào); `long_table` (cách đọc, nối danh mục, chỉ số + đơn vị + tổng hợp) | ~+1.700 (phần tables 1.656–3.549, TB 2.340) | get_table 33 → 1 (baseline → full); không còn nối sai khóa. Ở full, agent không dùng bảng dọc lần nào, nên phần `long_table` của thẻ **chưa được kiểm** |
| B' | Danh sách **mọi** bảng (tên, nhãn, layout), một dòng mỗi bảng | ~+250 (15 bảng) | **Chưa thử trong context** (biến thể full không có danh sách này). Bằng chứng gián tiếp: thông báo lỗi kèm danh sách bảng ở A/B E01 giảm 11,0 → 7,3 lời gọi, 8 → 0 lỗi |
| C | `join_paths` từ khóa ngoại khai báo | +30–130 | Không nối sai khóa |
| D | Điều kiện `where` của expert rule | ~+180 | get_expert_rule 12 → 5 (lite), 0 (full) |
| E | [2b] Chuẩn hóa thực thể: từ điển giá trị (cột văn bản ≤ 40 giá trị), không dấu, viết tắt, bí danh; chỉ xét từ viết hoa (tên riêng) | +45–130 | Lỗi TP.HCM 2/2 → 0; get_column_values 11 → 0 |
| F | [2b] Quy đổi thời gian thành `[from, before)` kèm thứ | +45–80 | Bớt tự tính ngày |
| I | Chỉ số khớp câu hỏi (topic `indicator`) + thẻ đọc bảng dọc | +200–600 | Gần nhất đã đo: đưa **cả 25 chỉ số** dựng tay vào knowledge (chưa có truy hồi top-k, chưa có thẻ `must[]`). Bảng dọc 7,2 → 3,6 bước, 10/12 → 11/12 |
| — | Bỏ `indent=2` khi `json.dumps` context | −9% | — |

**Kết quả đo** (17 câu, 18 câu con, mỗi biến thể chạy 2 lần):

| Biến thể | Đúng | Tra cứu/câu | Vòng LLM | Lỗi | Thời gian TB | Token vào TB |
|---|---|---:|---:|---:|---:|---:|
| baseline | 34/34 | 2,38 | 4,00 | 2 | 10,06 s | 35.636 |
| ctx_only (A–F, prompt cũ) | 34/34 | 1,00 | 2,88 | 2 | 7,91 s | 30.282 |
| lite (A, D, E, F) | 34/34 | 1,26 | 3,03 | 1 | 8,79 s | 28.263 |
| **full (A–F + đoạn prompt)** | **34/34** | **0,12** | **2,29** | **0** | **6,74 s** | **21.285** |

**Giới hạn của thực nghiệm:**
- Mẫu nhỏ; độ đúng đã chạm trần nên chỉ chứng minh được là "không giảm".
- Bộ câu nghiêng về câu tốn nhiều lượt tra cứu: lịch sử trên đủ 49 câu chỉ có 1,26 lượt tra cứu mỗi câu, nên mức giảm
  thực tế sẽ nhỏ hơn.
- Phương án H (đưa SQL thành công trong lịch sử) chưa thử, và không khuyến nghị lúc này vì rủi ro lặp lại SQL sai đã
  được chấp nhận.

### 6.2 Ngân sách token và độ trễ

- **Context ban đầu:**
  - từ khoảng 3.965 token lên khoảng 6.300 token khi có thẻ bảng ngang;
  - tối đa khoảng 7.500 token khi có thẻ bảng dọc kèm danh mục.

  Trên bộ 17 câu, tổng token mỗi câu vẫn **giảm** (−40%), vì số vòng giảm từ 4,0 xuống 2,29. Trên phân bố thật (49
  câu, 0,89 vòng chỉ tra cứu mỗi lượt, khoảng 7.500 token đầu vào mỗi lần gọi LLM), ước lượng thô như sau:
  - bỏ khoảng 0,85 vòng tiết kiệm khoảng 6.400 token;
  - context dài thêm khoảng 2.300 token, gửi lại ở khoảng 2,2 lần gọi còn lại, tốn thêm khoảng 5.100;
  - còn lại giảm khoảng 1.300 trên khoảng 23.900 token mỗi lượt, tức chỉ khoảng −5%.

  Nếu thêm tool docs nguyên văn (mục 2.1, khoảng +2.800–3.200 token mỗi lần gọi), tổng token sẽ **tăng**. Lợi ích
  chắc chắn là độ trễ: 0,85 vòng × khoảng 2,4 s mỗi lần gọi LLM ≈ −2 s mỗi câu con.
- **Trần đề xuất:**
  - tối đa 4 thẻ bảng, theo thứ tự: bảng của metric → bảng của cột truy hồi → bảng của quy tắc → bảng truy hồi;
  - thẻ bảng dọc tối đa 1.200 token (danh mục rút gọn);
  - cả khối `knowledge` tối đa 8.000 token, vượt thì cắt glossary và own_knowledge trước.
- **Độ trễ:**
  - profile mỗi connection: 57 truy vấn chỉ đọc, 1,4–1,64 s, chạy một lần rồi cache;
  - dựng thẻ theo từng câu là code thuần, chạy trong luồng truy hồi song song với phân loại intent (truy hồi thường
    xong sớm hơn 1–3 s), nên gần như không thêm độ trễ.

### 6.3 Cache

- `ConnectionProfile` (file mới `services/connection_profile.py`) cache theo `(connection_id, dictionary content_hash)`.
  Nội dung gồm:
  - thẻ bảng;
  - từ điển giá trị;
  - danh mục chỉ số;
  - ma trận cột hoặc chỉ số × loại dòng;
  - `join_paths`.
- Xóa cache khi:
  - có lần nạp dữ liệu thành công mới (`tb_lan_nap_du_lieu` hoặc ingestion job);
  - sửa dictionary;
  - xây lại index.
- `data_range` dùng TTL khoảng 1 giờ, vì dữ liệu dự báo được nạp mỗi giờ.
- Lưu trong bộ nhớ tiến trình (LRU theo connection). Chỉ khi có nhiều worker mới cân nhắc lưu vào app DB.

### 6.4 Thứ tự triển khai context

1. **Bước 1** (rẻ, rủi ro thấp): A + D + danh sách mọi bảng (B') + bỏ `indent=2` + đoạn prompt.
2. **Bước 2:** E + F ([2b]).
   - Kèm bảng bí danh giá trị.
   - Cờ "giá trị không có trong dữ liệu" và "ngoài vùng dữ liệu" đưa vào context.
3. **Bước 3:** `ConnectionProfile` + thẻ bảng B + C. `get_table` dùng chung hàm dựng thẻ.
4. **Bước 4:** topic `indicator` + thẻ đọc bảng dọc (I). Làm cùng đợt hỗ trợ bảng dọc ở mục 5.

## 7. Kế hoạch triển khai

### 7.1 Điều kiện bắt đầu

Workflow `wf_e2bc0d7e-1ef` đang sửa `prompt_text2sql_agent.py`, `prompt_synthesize.py`, `tool_agent.py`,
`agent_tools.py`, `agent_catalog.py`, `sql_builder.py`, `chat_service.py`, `chat_graph.py`, `chat_events.py`,
`schema_text2sql.py`, `router_chat.py` và frontend. Kế hoạch này chỉ bắt đầu khi workflow đó đã xong. Cụ thể:

- toàn bộ test xanh;
- chạy thật lại đạt ít nhất 97/98;
- anh/chị đã duyệt.

Mỗi đợt dưới đây đọc lại các file trên ở trạng thái mới trước khi sửa. Đặc biệt:
- `_execute` sẽ trả thêm `result_id`, `fields`, `chart`;
- `tool_agent` sẽ có thêm `on_text`/`on_tool_start`;
- prompt sẽ có mục BIỂU ĐỒ.

### 7.2 Các đợt

| Đợt | Nội dung | File (chủ sở hữu duy nhất trong đợt) | Test |
|---|---|---|---|
| **Đ0. Bộ đo** (làm trước để có baseline) | Thêm bộ câu: 26 câu stress (`error-experiments/stress_questions.json` + `gold_values.json`), 6 câu bảng dọc (`long-tables/gold.json`), câu bí danh thực thể (Sài Gòn, HN, TP.HCM), câu ngoài vùng dữ liệu. Cờ `--hide-tables` trong `run_eval` để buộc dùng bảng dọc. Chỉ số mới (7.3) | `scripts/text2sql_eval/run_eval.py`, `questions*.json`, `serve.py` (tăng giới hạn 400 ký tự của trace) | Chạy baseline trên commit sau workflow hiện tại |
| **Đ1. Lỗi có cấu trúc + vòng lặp** | `ToolError` mở rộng, `_validation_errors`, `LoopPolicy` và leo thang, `AgentStepOut.error_code`/`escalation_level`; `tool_errors.py`; gom lỗi trong `query_metric`; `extra="forbid"`, null → `[]`; `NULLS LAST`; chẩn đoán rỗng/NULL; trích đoạn `SQL_PARSE`; chặn dialect ngoài; `decode_db_error` (truyền `diag` từ repository); valid_options xếp theo độ gần; so khớp bỏ đơn vị trong ngoặc, `_` = khoảng trắng | `agent_package/tool_agent.py`; `services/tool_errors.py` (mới); `services/agent_tools.py`; `services/sql_builder.py`; `services/sql_guard.py`; `services/agent_catalog.py` (chỉ hàm `_find`); `repositories/source_query_repository.py`; `schemas/schema_text2sql.py` (2 trường) | Mỗi mã lỗi một test (dữ liệu vào → payload mong đợi); test vòng lặp với model giả lặp 3 lần cùng lỗi → bậc 1, 2, 3; test snapshot cũ (step không có `error_code`) vẫn đọc được; chạy lại fuzz 136 ca: không còn thông báo điểm 0–1 |
| **Đ2. Tool docs** | `tool_docs/*.md` (8 file) + loader; `tools()` lấy `summary`; prompt thêm `# TÀI LIỆU CÔNG CỤ`; sửa mục "KHI CÔNG CỤ BÁO LỖI", thu hẹp quy tắc hỏi lại | `agent_package/tool_docs/`; `agent_package/prompts/prompt_text2sql_agent.py`; `services/agent_tools.py` (chỉ `tools()`); `services/text2sql_agent_service.py` (ghép prompt) | Test của loader (mục 2.1); token budget; eval: stress A3, L1 không còn hỏi lại thừa |
| **Đ3. Context bước 1–2** | A, D, B', bỏ indent, đoạn prompt; [2b] thực thể + thời gian + bí danh | `services/text2sql_agent_service.py` (`knowledge_context`); `services/chat_service.py` (preprocess); `services/entity_normalizer.py` (mới); `agent_package/get_chat_models.py` (indent); prompt | Unit: chuẩn hóa TP.HCM/Sài Gòn/HN → `Ho Chi Minh`/`Ha Noi`; không khớp nhầm "mưa" → `Mua`; quy đổi thời gian; eval 49×2 |
| **Đ4. Catalog + metadata bảng dọc** | Mở rộng `TableInfo`/`ColumnInfo`; `ConnectionProfile` + cache + invalidation; thẻ bảng B + C; `get_table.reading_guide`; `get_column_values` cho indicator_key; data dictionary: migration `entity_key_column_id`, `default_row_kind`, `catalog_value_kind_map`, `value_aliases`, `indicator_profiles`, `column_row_kinds`; sửa 2 metadata sai | `services/catalog_context.py`, `services/agent_catalog.py`, `services/connection_profile.py` (mới), `services/agent_tools.py` (get_table, get_column_values); `modules/data_dictionary/models`, `schemas`, `services`, migration Alembic; `docs/handbook/modules/data_dictionary/` | Fixture bảng dọc trong test; profile dựng đúng ma trận 408/0/6.048; cache bị xóa khi nạp; test migration lên/xuống |
| **Đ5. Index + context bảng dọc** | Topic `indicator`, tài liệu bảng dọc, cột "chỉ có ở"; thẻ đọc bảng (I) | `services/index_documents.py`, `services/retrieval_service.py`/`topic_search_service.py`, `services/chat_service.py`, `services/text2sql_agent_service.py` | Truy hồi "ban ngày", "gió giật", "mưa" ra đúng chỉ số; eval bảng dọc |
| **Đ6. query_indicator + cảnh báo run_sql** | `indicator_builder.py`; công cụ mới; cảnh báo và chặn của bảng dọc trong `run_sql` | `services/indicator_builder.py` (mới), `services/agent_tools.py`, `services/sql_guard.py` (hoặc `services/sql_lint.py` mới), `tool_docs/query_indicator.md`, `tool_docs/run_sql.md` | Test SQL dựng ra so với `expected_sql` trong `proposed_payloads.json`; COUNT(*) → cảnh báo; SUM không lọc → chặn; eval bảng dọc 6×2 |
| **Đ7. Chạy thật và rà soát độc lập** | 49×2 + stress 26×2 + bảng dọc 6×2 (ẩn bảng ngang) + A/B tiêm lỗi 13×3 | — | Ngưỡng ở 7.3 |

**Lý do của thứ tự này:**
- Đ1 và Đ2 nhỏ, đứng độc lập, sửa đúng P2.
- Đ3 cho hiệu quả lớn nhất về chi phí.
- Đ4 đến Đ6 là P1, phụ thuộc metadata và cần anh/chị quyết (mục 8).

Mỗi đợt một commit, đẩy thẳng lên `main` theo quy ước của repo.

### 7.3 Đo thành công bằng eval harness

**`run_eval.py` thêm các chỉ số** (tính từ `answers[].steps` và trace). Điều kiện: Đ1 đã ghi lỗi của mọi công cụ vào
`steps` (xem 3.1). Hiện lỗi của `get_table`/`get_metric`/`get_expert_rule`, lỗi pydantic và lỗi lặp không có trong
`steps`, và trace chỉ giữ 400 ký tự.

| Chỉ số | Định nghĩa |
|---|---|
| `error_rate_by_tool` | Lỗi cứng / lời gọi, theo công cụ và theo `error_code` |
| `silent_failure_rate` | Kết quả rỗng/NULL có chẩn đoán "literal không tồn tại" / lời gọi dữ liệu |
| `chain_len_max`, `chain_len_p95` | Độ dài chuỗi lời gọi thất bại liên tiếp trong một lượt |
| `loop_count` | Số lần kích hoạt leo thang bậc 1/2/3 (từ `escalation_level`) |
| `repeat_class_runs` | Số lượt có cùng `(tool, code)` ≥ 2 |
| `lookup_calls_per_question` | get_metric + get_table + get_expert_rule + get_column_values |
| `rounds`, `seconds`, `input_tokens` | Trung bình và trung vị cho mỗi câu |
| `long_table_sql_ok` | Tỷ lệ SQL trên bảng dọc có lọc chỉ số và loại dòng, và không dùng COUNT(*) |
| `join_key_ok` | Tỷ lệ SQL nối đúng cặp khóa đã khai báo |
| `needless_clarification` | Số lần ask_user ở các câu gold không cần hỏi lại |

**Ngưỡng nghiệm thu đề xuất:**

| Bộ | Hiện tại | Mục tiêu |
|---|---|---|
| 49 câu × 2 | 97/98 | ≥ 97/98 (không giảm) |
| Stress 26 × 2 | 45/52 | ≥ 49/52 |
| Bảng dọc 6 × 2 (ẩn bảng ngang) | 10/12 (A) | ≥ 11/12, `long_table_sql_ok` = 100% |
| Lỗi cứng / lời gọi | 1,0% | ≤ 0,5% |
| `chain_len_max` (stress) | 3 | ≤ 2 |
| `repeat_class_runs` (stress) | 4 | 0 |
| `lookup_calls_per_question` (49 câu) | ~1,26 | ≤ 0,3 |
| Thời gian agent TB | đo ở Đ0 | −20% (ước lượng −2 s/câu con trên ~7 s) |
| Token vào mỗi câu | đo ở Đ0 | không tăng (ước lượng ở 6.2 chỉ khoảng −5% trên 49 câu; −40% chỉ đạt trên bộ 17 câu nhiều tra cứu) |
| Fuzz 136 ca, điểm giải mã | TB 1,2–1,8; 24 thông báo 0–1 | TB ≥ 2,5; không còn 0–1 |
| A/B tiêm lỗi | 152 lời gọi sau lỗi; 9 lỗi tiếp | ≤ 121; 0 |

## 8. Các quyết định cần anh/chị

| # | Câu hỏi | Đề xuất mặc định |
|---|---|---|
| D1 | "Đệ quy vô hạn" anh/chị gặp ở đâu (mô hình khác, lược đồ lớn hơn, bản MCP cũ)? Có trace hay hội thoại cụ thể không? Dữ liệu hiện có (910 + 65 + 78 lượt) chưa lượt nào chạm `max_steps` | Gửi trace nếu có. Đồng thời chạy lại A/B tiêm lỗi với 1–2 mô hình rẻ hơn để đo độ nhạy với thông báo lỗi |
| D2 | Nạp tool docs vào system prompt (bản nháp hiện tại khoảng +2.800–3.200 token mỗi lần gọi LLM; rút gọn được về khoảng 1.500) hay chỉ nạp phần lỗi khi leo thang? | Nạp phần thân đã rút gọn (≤ 1.500 token) vào system prompt; mục lỗi chỉ đưa ra khi leo thang. Đo token ở Đ7 |
| D3 | Bảng dọc dùng công cụ riêng `query_indicator` hay sinh metric ảo cho `query_metric`? | Dùng công cụ riêng |
| D4 | Câu không nói rõ grain (gió giật mạnh nhất hôm qua, tổng mưa tuần trước): ưu tiên chỉ số ngày (DU_BAO_NGAY) hay giờ? Khi hai cách cho cùng kết quả, agent có tự chọn mà không hỏi lại không? | Ưu tiên chỉ số ngày; cùng kết quả thì không hỏi, nêu cả hai |
| D5 | Ẩn bảng trùng vai trò (dm_* và dim_*, tb_* và fact_*) khỏi agent, hay đánh dấu bảng chuẩn trong catalog? | Đánh dấu `preferred` trong dictionary; agent chỉ thấy bảng chuẩn, trừ khi câu hỏi nêu "dữ liệu gốc" |
| D6 | Bí danh thực thể (Sài Gòn, HN, thủ đô) khai báo tay trong data dictionary hay để code tự suy? | Cả hai: code suy (không dấu, viết tắt); bí danh khai báo tay để ghi đè; gợi ý bí danh từ log lỗi |
| D7 | Metadata do heuristic suy ra (chỉ số × loại dòng, khóa thực thể, tổng hợp theo đơn vị) do ai duyệt, ở đâu? | Hàng chờ đề xuất kiểu `own_knowledge_proposals`, duyệt trên màn data dictionary; số liệu profiling (ma trận có dữ liệu) dùng ngay không cần duyệt |
| D8 | Đo P1: thêm cờ ẩn bảng trong `run_eval` hay tạo connection hoặc schema chỉ có bảng dọc? | Cờ `--hide-tables` (rẻ, không đụng warehouse) |
| D9 | Quy ước "N ngày tới": tính từ ngày mai hay gồm hôm nay? "Được dự báo" có gồm dự báo đã lưu trong quá khứ không? | Từ ngày mai; có gồm |
| D10 | Benchmark bảng dọc có cần snapshot dữ liệu cố định không? Dự báo nạp mỗi giờ nên số gold trôi nhẹ | Gold tính lại bằng SQL ở mỗi lần chạy, như bộ hiện tại |
| D11 | Giữ lịch sử phiên bản dự báo (theo `lay_luc`)? Hiện mỗi bộ (thành phố, thời điểm, loại dòng) chỉ có 1 dòng | Chưa cần. Khi cần thì thêm vai trò "phiên bản" và quy tắc lấy bản mới nhất |

## 9. Kiểm tra lại

Đã đối chiếu báo cáo với dữ liệu trong thư mục nháp và với code ngày 20/11 (chỉ đọc). Script và số liệu kiểm ở
`scratchpad\critic\` (`check_dd.py`, truy vấn app DB chỉ đọc).

### 9.1 Số liệu đã tính lại và khớp

- **Lượt agent đã lưu:** 910 lượt, 2.111 lời gọi, 2.782 lần gọi LLM, 21,17 triệu token, 6.554 s.
  - 21 lỗi cứng: query_metric 18, get_metric 1, get_column_values 1, run_sql 1.
  - Rỗng 31, NULL 3. Chuỗi lỗi: 52 chuỗi, 49 dài 1, 3 dài 2. Hết bước 0.
  - Vòng chỉ tra cứu: 806/1.872 vòng, 24,5% token. Cặp câu: +1,96 vòng, +5,06 s, +18.198 token.
  - `REPEATED_FAILURE`: 0 lần trong mọi results, trace và stress.
- **Fuzz:** 136 ca; 77 lỗi, 16 `silent_harm`, 24 thông báo điểm ≤ 1. Điểm trung bình theo công cụ khớp. Lưu ý mẫu
  nhỏ: get_table 5 ca, get_column_values 5 ca, get_expert_rule 2 ca.
- **Stress:** 65 lượt agent, 262 lời gọi, 21 lỗi ở 9 lượt. 4 lượt có chuỗi ≥ 2, 2 lượt có chuỗi 3, 4 lượt lặp cùng
  lớp, tối đa 6 lỗi một lượt. 17/21 lỗi là get_table.
- **A/B tiêm lỗi:** 152 → 121 lời gọi sau lỗi; 9 → 0 lỗi tiếp theo (8/9 ở E01); đúng 39 → 38. E01 11,0 → 7,3;
  E05 9,0 → 5,0; E03 4,7 → 3,7.
- **Bảng dọc:** chấm lại bằng `score_exp.py`: A 10/12, 7,2 bước, 19,4 s; B 11/12, 3,6 bước, 12,9 s; 0 lỗi; get_table
  0 lần.
- **Context:** 136 bản ghi (17 × 4 × 2). Đúng 34/34 ở cả bốn biến thể.
  - Tra cứu mỗi câu: baseline 2,38, ctx_only 1,00, lite 1,26, full 0,12.
  - Vòng: 4,00 → 2,29. Thời gian: 10,06 → 6,74 s. Token vào: 35.636 → 21.285.
  - Context TB 3.965 → 6.269 token. Profile 57 truy vấn, 1,64 s.

### 9.2 Đã sửa trong báo cáo

| Chỗ | Trước | Sau | Bằng chứng |
|---|---|---|---|
| `indicator_catalog_id` | Hai nhánh mâu thuẫn, cần kiểm lại | Đã khai báo đúng cho cả hai bảng dọc. Nhánh báo NULL so khóa với nhầm bảng | `models/table_dictionary.py` (FK `table_dictionaries.id`); truy vấn app DB |
| Khóa ngoại | Không nói rõ có hay không | 22 cặp đã khai báo, gồm `quan_sat_id` của cả hai bảng dọc | app DB |
| Đếm phép tổng hợp | TONG 10, LON_NHAT 4 | TONG 9, LON_NHAT 5 (TRUNG_BINH 8, NHO_NHAT 2, BAT_KY 1) | `warehouse_profile.json` |
| Chỉ số theo giờ | 12 chỉ số đều có ở HIEN_TAI và DU_BAO_GIO | 10 ở cả hai, 2 chỉ ở DU_BAO_GIO | `guide_fact_chi_tiet.json` |
| "49 câu không có câu nào đọc bảng dọc" | Như vậy | Không câu nào *bắt buộc* đọc; agent vẫn tự đọc ở T11-2 | `error_summary.json` (`p1_vertical_table_observations`) |
| Điều kiện B của thực nghiệm bảng dọc | "Thẻ đọc bảng" | Danh sách 25 chỉ số dựng tay trong knowledge + đoạn prompt. reading_guide không được đọc; câu lệnh "phải gọi get_table" bị bỏ qua 12/12 | `long-tables/tools/experiment.py` |
| B' (danh sách mọi bảng) | Có hiệu quả đo được | Chưa thử trong context; chỉ có bằng chứng gián tiếp từ thông báo lỗi E01 | `preprocess-context/snapshot/expand.py` |
| get_table, get_expert_rule giảm | 34 → 1; 12 → 0 | 33 → 1; 12 → 5 (lite) / 0 (full) | `analysis/exp_summary.txt` |
| Token tool docs | 1.400–1.800, test ≤ 2.000 | Bản nháp đo được khoảng 3.170 (o200k); đặt trần 1.500 và rút gọn | đếm tiktoken trên mục 2.2 |
| Lợi ích token của context | −40% | −40% chỉ trên bộ 17 câu; trên 49 câu ước lượng khoảng −5%; có tool docs thì có thể tăng | 6.2 |
| Xếp `valid_options` | Theo trigram | Viết tắt và bí danh trước, liệt kê hết khi ≤ 30. Trigram một mình làm lỗi phổ biến nhất (TP.HCM) tệ hơn | mô phỏng trên 12 thành phố |
| Bậc 1 trên 910 lượt | Kích hoạt 0 lần | 0 lần theo cặp tool+code, 1 lần theo "2 vòng liên tiếp" (vô hại) | `chains.len_ge_2` |
| Bậc 3 (tổng ≥ 5) | Chỉ cắt lượt bệnh lý | Với thông báo hiện tại sẽ cắt lượt stress L5 vốn ra đúng; chỉ bật cùng thông báo mới | stress |
| Đếm khi gọi song song | Đếm từng lời gọi | Tối đa 1 lần cho mỗi (tool, code) trong một vòng; bậc 2 thêm điều kiện "dùng giá trị ngoài valid_options" | lập luận, câu so sánh 3 thành phố |
| Tự hỏi lại | Bật | Mặc định tắt | 3/7 lượt stress hỏng liên quan hỏi lại |
| Đo bằng `steps` | Ngầm định đủ | Lỗi lookup, pydantic, lặp không được ghi vào `steps`; Đ1 phải ghi | `agent_tools.py` (`_record` chỉ ở 3 chỗ) |
| Gợi ý của sql_guard | Không nhắc | "Dùng get_table để xem bảng có sẵn" trỏ tới công cụ không liệt kê được bảng | `sql_guard.py` |
| Bản nháp tool docs | Không nói rõ thời điểm | Mô tả hành vi sau Đ1–Đ6; docs phải đi theo từng đợt | đối chiếu `agent_tools.py`, `sql_builder.py` |

### 9.3 Thông báo mới có chặn được "lỗi của lỗi" không: mô phỏng trên chuỗi thật

| Chuỗi thật | Lời gọi kế tiếp hiện tại | Với đề xuất | Đánh giá |
|---|---|---|---|
| `49e9a64f97b6`: `order_by: null` → bỏ order_by → `'TP.HCM'` → `'Ho Chi Minh'` | 3 lời gọi, 2 lỗi | null → `[]` nên lỗi 1 biến mất. `TP.HCM` khớp viết tắt duy nhất nên tự đổi và ghi chú | 2 lỗi → 0. Chắc chắn, vì là logic code, không phụ thuộc model |
| `9e288f9637a2`: alias `ngay-vuot-nguong` → `Col: 163` → model đổi sang liệt kê dòng, 31 dòng bị cắt, thiếu Ho Chi Minh | Đổi bài toán | Lỗi trích `…AS ngay-vuot-nguong FROM…` + fix "đổi thành ngay_vuot_nguong" + "giữ nguyên ý truy vấn" | Rất có thể sửa đúng trong 1 bước, nhưng chưa đo. Nguyên nhân sai cuối cùng là `truncated` (31 dòng), nên quy tắc "truncated thì gộp lại" trong run_sql.md cũng cần |
| `61776f5b418a`: `contains 'TP.HCM'` ra NULL → 3 `get_column_values` song song, 1 lỗi cột DATE | Bắn rải | [2b] đưa `entities` (Ho Chi Minh) trước khi gọi. Nếu vẫn lọt thì `QM_EMPTY_FILTER` chỉ đúng bộ lọc và giá trị gần | Bỏ được chuỗi nếu khớp viết tắt hoạt động. Chẩn đoán rỗng chưa được thử với model |
| Stress L5 (6 lỗi): `tb_chi_so` → `tb_chi_so_thoi_tiet` → `tb_thanh_pho` → `Chiều thành phố` → `Chiều chỉ số` → `dim_chi_so` | Đoán tên mới, chỉ một số lỗi có gợi ý "Gần giống" | Lỗi đầu đã kèm 15 bảng có layout. Nếu agent vẫn đoán thì bậc 1 ở lỗi thứ 2, bậc 2 chặn ở lỗi thứ 3 | E01 (cùng câu) cho 8 → 0 lỗi với thông báo viết tay. Đây là bằng chứng mạnh nhất cho P2 |

**Kết luận:** chuỗi lỗi có thật đều ngắn và có nguyên nhân rõ. Đề xuất chặn được chuỗi chủ yếu nhờ **thông tin**
(danh sách bảng, viết tắt, chỉ số), sau đó mới đến định dạng `code/fix/retry`. Định dạng có cấu trúc và kiểm soát vòng
lặp là lưới an toàn cho model yếu hơn hoặc lược đồ lớn hơn. Hiện chưa có trace nào cho thấy model đi vào vòng lặp
thật (D1).

### 9.4 Ngưỡng có đủ căn cứ không

- **Ngưỡng 2 (bậc 1):** có căn cứ: rẻ, chỉ thêm văn bản, và bắt được 4/4 lượt lặp trong stress.
- **Ngưỡng 3 (bậc 2):** căn cứ yếu. Chỉ có 2 lượt đạt chuỗi 3, đều cùng một câu hỏi. Cần thêm điều kiện "bỏ qua
  danh sách" và đếm theo vòng để không chặn nhầm.
- **Ngưỡng 5 (bậc 3):** chưa có căn cứ. Lượt duy nhất vượt ngưỡng lại ra đúng.
- **Việc cần làm trước khi chốt:** ở Đ0, mô phỏng cả ba ngưỡng offline trên trace stress và A/B. Chỉ cần phát lại
  chuỗi `error_seq` với `LoopPolicy`, không cần gọi LLM. Báo số lần mỗi bậc kích hoạt trên lượt đúng và lượt sai.

### 9.5 Thiết kế bảng dọc có làm được với metadata hiện có không

**Làm được phần lớn.** Metadata hiện có đã đủ:
- layout, vai trò cột, row_kind → grain, mã tổng hợp → hàm;
- `indicator_catalog_id`;
- 22 khóa ngoại;
- mã đơn vị.

Từ đó dựng được, không cần migration:
- `reading_guide`;
- topic `indicator`;
- cảnh báo `LONG_TABLE_UNFILTERED_AGG`, `COUNT_STAR`, `JOIN_KEY_MIX`.

**Còn thiếu:**
- ánh xạ `catalog_value_kind` → qualifier: suy được từ dữ liệu (DUNG_SAI chỉ có ở `gia_tri_dung_sai`);
- ma trận chỉ số × loại dòng: profiling;
- loại dòng mặc định và bí danh giá trị: khai báo tay.

`tb_gia_tri_quan_sat` cần kế thừa loại dòng và thời gian qua khóa ngoại `quan_sat_id`. Thiết kế cũ chưa nói điều này
(đã bổ sung ở 5.1). `entity_key_column_id` thành tùy chọn.

### 9.6 Mở rộng context có đáng không

- **Đáng, nếu làm theo bước 1–2 của 6.4:**
  - A + D + danh sách bảng + [2b] tốn ít (+700–850 token);
  - nhắm đúng hai nguồn lỗi lớn nhất: đoán tên bảng và viết tắt thực thể;
  - bớt vòng tra cứu.
- **Thẻ bảng đầy đủ (B, +1.700 đến +3.500 token): đáng về độ trễ, nhưng gần như hòa về token trên phân bố thật**
  (ước lượng khoảng −5%). Không nên vừa thêm thẻ đầy đủ vừa nạp tool docs khoảng 3.000 token mà không đo lại.
- **Thẻ đọc bảng dọc (I): chưa thử ở dạng đề xuất.** Bằng chứng duy nhất là danh sách 25 chỉ số dựng tay trên 6 câu
  (10/12 → 11/12, lượt hỏng mới ở B là trả lời rỗng). Cần thử lại sau Đ5 với truy hồi top-k thật.

## Phụ lục A. File bằng chứng

Gốc thư mục: `C:\Users\dat\AppData\Local\Temp\claude\d--Code-Superset-AI\3428e385-9db2-46b6-835b-611b745f0661\scratchpad\`

| Thư mục | File chính |
|---|---|
| `error-mining\` | `ghi-chu-khai-thac-loi.md`, `runs_dataset.json` (910 lượt), `error_summary.json` (phân loại, chuỗi, lãng phí, danh mục 21 thông báo lỗi), `noncases.txt`, `mine.py`, `analyze.py` |
| `error-experiments\` | `bao-cao-thuc-nghiem-loi-tool.md`, `out\fuzz_results.json`, `out\fuzz_rated.json`, `out\historic_trace_errors.json`, `stress_questions.json`, `out\gold_values.json`, `out\stress-run1.json`, `out\stress-trace.jsonl`, `out\stress_trace_errors.json`, `out\replay_results_merged.json`, `scripts\*.py` |
| `long-tables\` | `app_dictionary.json`, `warehouse_profile.json`, `wide_nonnull_by_kind.json`, `guide_fact_chi_tiet.json`, `proposed_payloads.json`, `gold.json`, `exp_AB.json`, `analysis\scan_results.json`, `tools\guide.py`, `tools\experiment.py` |
| `preprocess-context\` | `bao-cao-mo-rong-context-preprocess.md`, `snapshot\expand.py`, `snapshot\agent_exp.py`, `profile_cards.json`, `catalog_dump.json`, `sizes.json`, `exp_results.json`, `analysis\*.txt` |

## Phụ lục B. Giới hạn chung

- **Một mô hình:** chỉ thử `openai/gpt-6-luna`, vốn tự sửa lỗi tốt. Mô hình yếu hơn có thể nhạy với thông báo lỗi hơn
  nhiều. Lợi ích của mục 3–4 có thể bị đánh giá thấp.
- **Một bộ dữ liệu:** chỉ có kho thời tiết, 15 bảng, khoảng 15 metric. Lược đồ lớn hơn sẽ làm danh sách bảng và thẻ
  bảng đắt hơn; khi đó cần truy hồi thẻ theo top-k thay vì đưa toàn bộ.
- **Trace bị cắt:** trace chỉ giữ 400 ký tự đầu của kết quả công cụ; 125 lời gọi không khớp được với kết quả đầy đủ.
- **`indicator_catalog_id`:** đã kiểm lại trên app DB, trường này đã khai báo. Báo NULL trước đây là do lỗi truy vấn
  (xem 1.5).
- **Thông báo "viết lại" trong A/B là văn bản viết tay** cho từng kịch bản. Thông báo do code sinh theo mục 3 sẽ
  nghèo hơn, nên lợi ích đo được là mức trần.
