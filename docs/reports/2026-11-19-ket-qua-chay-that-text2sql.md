# Kết quả chạy thật route chat text2sql (database nguồn và LLM thật)

**Ngày chạy:** 2026-11-19 đến rạng sáng 2026-11-20 (giờ Việt Nam). **Phiên bản:** working tree chưa commit, gồm route chat LangGraph và agent `Text2SqlAgentService` mới. **Model:** `openai/gpt-6-luna` qua OpenRouter (cấu hình mặc định), embedding `openai/text-embedding-3-small`.

## 1. Thiết lập

- **Connection:** `Weather warehouse` (PostgreSQL, database `data_wh` trong container `warehouse-db`), 16 bảng, 16 metric, 8 quy tắc chuyên gia. Dữ liệu là kho thời tiết mô phỏng: 12 thành phố, bản ghi `HIEN_TAI` (13/11 đến hiện tại, nạp mỗi giờ), `DU_BAO_GIO` và `DU_BAO_NGAY` (6/11 đến 25/11, gồm cả ngày tương lai), nhật ký nạp `tb_lan_nap_du_lieu`.
- **Chỉ mục Qdrant:** collection `text2sql_semantics_v1` đã có 213 point cho connection này, không cần đồng bộ lại.
- **Kết nối từ máy host:** `DATABASE_URL` trong `.env` trỏ cổng 5432 không có trên host; URI nguồn đã lưu dùng host `warehouse-db` (tên service Compose). Harness đổi host:port trong tiến trình (`--app-db 127.0.0.1:15432`, `--source-host-map warehouse-db=127.0.0.1:15433`), không sửa dữ liệu đã lưu và không in URI.
- **Harness:** `scripts/text2sql_eval/run_eval.py`, bộ câu hỏi `scripts/text2sql_eval/questions.json`, kết quả JSON trong `scripts/text2sql_eval/results/` (gitignore). Cách dùng và cách chấm: [chạy đánh giá thật](../handbook/modules/text2sql/danh-gia-chay-that.md).
- Không ghi lượt hội thoại (không gửi `user_id`), chỉ đọc database nguồn.

## 2. Bộ câu hỏi

40 câu tiếng Việt, dựa trên metric, bảng và quy tắc thật của connection:

| Nhóm | Số câu | Ví dụ |
| --- | --- | --- |
| T1 tra cứu | 3 | "Bây giờ ở Đà Nẵng bao nhiêu độ?", "Ngày mai Hải Phòng nhiệt độ thấp nhất bao nhiêu?" |
| T2 tổng hợp | 2 | "Độ ẩm trung bình ở Hà Nội tuần trước là bao nhiêu?" |
| T3 đếm | 2 | "Tuần trước Đà Nẵng có mấy ngày mưa?" |
| T4 có/không | 2 | "Hôm qua TP.HCM có nóng trên 33 độ không?" |
| T5 liệt kê | 2 | "Thành phố miền Bắc nào không có mưa hôm qua?" (gold rỗng) |
| T6 phân nhóm | 2 | "Nhiệt độ trung bình hôm qua theo vùng khí hậu?" (cần nối bảng danh mục) |
| T7 cực trị | 2 | "3 thành phố mưa nhiều nhất 7 ngày qua là những nơi nào?" |
| T8 so sánh | 2 | "Hôm qua Hà Nội hay TP.HCM nóng hơn, chênh bao nhiêu độ?" |
| T9 dẫn xuất | 2 | "Biên độ nhiệt ở Hà Nội hôm qua?", "Tỷ lệ nạp dữ liệu thành công là bao nhiêu phần trăm?" |
| T10 xu hướng | 2 | "Dự báo tổng lượng mưa từng ngày trong 5 ngày tới ở Đà Nẵng?" |
| T11 phân bố | 2 | "Loại thời tiết nào xuất hiện nhiều nhất ở Phú Quốc tuần trước?" |
| T12 bất thường | 2 | "Thành phố nào có thời tiết xấu cần cảnh báo trong 7 ngày qua?" |
| T13 tương quan | 2 | "Độ ẩm và xác suất mưa theo giờ ở Huế tuần trước tương quan thế nào?" |
| T15 vận hành | 3 | "Ngày 17/11 hệ thống nạp dữ liệu mấy lần, có lần nào lỗi không?" |
| T22 định nghĩa | 2 | "Thế nào thì được tính là ngày có mưa?" |
| Tách câu | 3 | "Ngày có mưa là gì, tuần trước Huế có mấy ngày như vậy?" |
| Phụ thuộc (`<kết quả câu N>`) | 2 | "Thành phố nào nóng nhất hôm qua, độ ẩm trung bình ở đó hôm qua bao nhiêu?" |
| Thiếu thông tin | 3 | "Thành phố nào mưa nhiều nhất?", "Nhiệt độ hôm qua là bao nhiêu?", "Ở đó dạo này thế nào?" |

Đáp án gold là SQL chỉ đọc do người viết, chạy lại trên database nguồn ngay sau mỗi câu với đúng ngày `today` mà agent đã dùng (lần chạy đi qua nửa đêm 19/11 sang 20/11 nên số liệu giữa các lần chạy khác nhau). Câu có nhiều cách hiểu hợp lý (ví dụ "dao động" theo bản ghi ngày hay giờ) có nhiều gold; khớp một là đạt.

## 3. Tỷ lệ đạt

| Nhóm | Trước sửa | Sau sửa (1 lượt) | Sau sửa (2 lượt mỗi câu) |
| --- | --- | --- | --- |
| T1 | 3/3 | 3/3 | 6/6 |
| T2 | 2/2 | 2/2 | 4/4 |
| T3 | 1/2 | 2/2 | 4/4 |
| T4 | 2/2 | 2/2 | 4/4 |
| T5 | 2/2 | 2/2 | 4/4 |
| T6 | 1/2 | 1/2 | 3/4 |
| T7 | 2/2 | 2/2 | 4/4 |
| T8 | 2/2 | 2/2 | 4/4 |
| T9 | 2/2 | 2/2 | 4/4 |
| T10 | 2/2 | 2/2 | 4/4 |
| T11 | 2/2 | 2/2 | 4/4 |
| T12 | 2/2 | 2/2 | 4/4 |
| T13 | 2/2 | 2/2 | 4/4 |
| T15 | 2/3 | 3/3 | 6/6 |
| T22 | 2/2 | 2/2 | 4/4 |
| Tách câu | 2/3 | 3/3 | 6/6 |
| Phụ thuộc | 2/2 | 2/2 | 4/4 |
| Thiếu thông tin | 1/3 | 3/3 | 6/6 |
| **Tổng** | **34/40** | **39/40** | **79/80** |

Ghi chú:
- Cột "Trước sửa" là file `baseline.json`. Lúc đó câu T15-1 là "Hôm qua hệ thống nạp dữ liệu mấy lần…"; sau đó đổi thành ngày 17/11 để kiểm tra múi giờ (mục 4.4). Ở nhóm thiếu thông tin, M-1 và M-2 trượt vì gộp toàn bộ dữ liệu hoặc gộp mọi thành phố thành một số; bộ chấm sau này nhận thêm cách nói "chưa nêu", nhưng đọc lại thì hai câu trả lời đó vẫn không hợp lý nên giữ là trượt.
- Cột "1 lượt" là `after-4.json`, "2 lượt" là `final-x2.json`. Thêm một lần đo ổn định (`stability-1.json`, 5 lượt mỗi câu): T6-2 5/5, D-2 5/5, M-1 5/5, M-2 4/5.
- Không câu nào hết lượt gọi công cụ (`exhausted`), không có lời gọi lỗi bị lặp lại y nguyên.

Thời gian (một lượt, 4 câu chạy song song): trung vị 16,3 giây/câu trước sửa, 13,6 giây sau sửa; bước hiểu câu hỏi (rewrite, phân loại, truy hồi) trung vị khoảng 6 giây; một câu con trung vị 8,6 giây trước sửa và 4,8 giây sau sửa. Số bước công cụ cho 40 câu giảm từ 75 xuống 57, số lần gọi `get_column_values` từ 29 xuống 8.

## 4. Lỗi đáng chú ý và cách sửa

### 4.1. Lọc theo tên có dấu trả về rỗng hoặc 0 và bị báo là kết quả thật

Dữ liệu ghi tên thành phố không dấu (`Da Nang`). Agent lọc `ten_thanh_pho = 'Đà Nẵng'`, nhận `0` và trả lời "Tuần trước Đà Nẵng có **0 ngày mưa**" trong khi gold là 7 (T3-1). Ở nhiều câu khác agent tự sửa nhưng tốn thêm 1 đến 2 lượt `get_column_values` (29 lượt cho 40 câu), vì `ILIKE '%Huế%'` không khớp `Hue`.

**Sửa** (`agent_tools.py`): `query_metric` đối chiếu giá trị lọc văn bản (`equals`, `not_equals`, `in`, `not_in`, `contains`, `not_contains`) với các giá trị thực của cột, không phân biệt dấu và hoa thường; khớp duy nhất thì tự đổi và ghi chú, không khớp thì báo lỗi kèm giá trị gần giống để model sửa. `get_column_values` không tìm thấy bằng `ILIKE` thì so khớp lại không phân biệt dấu. Sau sửa T3-1 trả đúng 7 ngày; câu "TP.HCM" nhận lỗi kèm danh sách và sửa được ngay ở lượt sau.

### 4.2. Quy tắc chuyên gia bị áp chồng lên metric dạng tỷ lệ

Quy tắc "Lần nạp thất bại" (`trang_thai = 'THAT_BAI'`) được gắn với metric `ty_le_nap_thanh_cong`. `query_metric` thêm điều kiện này vào `WHERE` nên tỷ lệ thành công thành `0` (T9-2, SQL: `... FROM tb_lan_nap_du_lieu WHERE "trang_thai" = 'THAT_BAI'` trả `[[0]]`). Agent phát hiện và viết lại bằng `run_sql`, tốn thêm một lượt. Quy tắc "Ngày có mưa" gắn với `ty_le_ngay_co_mua` có cùng nguy cơ (lọc `tong_luong_mua_mm > 0` làm tỷ lệ luôn 100%).

**Sửa** (`sql_builder.py`): điều kiện quy tắc trên cột đã nằm trong phần điều kiện của biểu thức metric (`CASE WHEN`, `FILTER (WHERE …)`) thì không lọc thêm, kèm ghi chú. Sau sửa T9-2 gọi `query_metric` một lần và trả đúng 97,0%. Việc gắn quy tắc với metric vẫn nên được người quản trị xem lại.

### 4.3. Bước tổng hợp lỗi khi model trả văn bản thường

Hai câu tách (T15-1, S-2) đã trả lời xong cả hai câu con nhưng route báo 503 `Text2SqlAgentUnavailable`: model trả `“Ngày có mưa” là ngày có tổng lượng mưa lớn hơn 0 mm… Huế có 7 ngày mưa.` thay vì JSON, `PydanticOutputParser` báo `OutputParserException`.

**Sửa** (`prompt_synthesize.py`): `SynthesizeParser` dùng văn bản thường làm `answer` khi không parse được JSON (văn bản bắt đầu bằng `{` hoặc ` ``` ` vẫn báo lỗi). Prompt nhắc viết xuống dòng là `\n`. Sau sửa nhóm tách câu đạt 6/6 qua hai lượt.

### 4.4. Mốc thời gian của cột `timestamptz` bị tính theo UTC

`tb_lan_nap_du_lieu.bat_dau_luc` là `timestamp with time zone` (data dictionary ghi `TIMESTAMP`), còn kết nối nguồn đặt `TimeZone=UTC`. Lọc `bat_dau_luc >= '2026-11-17' AND < '2026-11-18'` vì vậy theo ngày UTC: ngày 17/11 giờ Việt Nam có 2 lần nạp, ngày 17/11 UTC chỉ có 1 (một lần chạy lúc 23 giờ ngày 16/11 UTC thuộc ngày 17/11 giờ Việt Nam).

**Sửa** (`source_query_repository.py`): kết nối nguồn đặt `TimeZone` bằng `TEXT2SQL_TIMEZONE`. Cột `timestamp without time zone` (như `thoi_diem_quan_sat`) không bị ảnh hưởng. Sau sửa T15-1 trả đúng 2 lần nạp.

### 4.5. Thay chiều được hỏi bằng cột gần nghĩa

"Nhiệt độ trung bình hôm qua theo vùng khí hậu?" (T6-2): bảng của metric chỉ có cột `vung` (7 vùng địa lý), còn `vung_khi_hau` (4 miền) nằm ở `dm_thanh_pho`/`dim_thanh_pho` và có trong `knowledge.columns`. Agent phân nhóm theo `vung` và gọi đó là vùng khí hậu.

**Sửa** (prompt agent và mô tả công cụ `query_metric`): đối chiếu từng chiều và điều kiện với `knowledge.columns`; cột đúng nghĩa ở bảng khác thì nối bảng bằng `run_sql`, không thay bằng cột khác tên. Sau sửa đạt 5/5 trong lần đo ổn định nhưng vẫn trượt 1/2 ở lần chạy cuối: lỗi giảm nhưng chưa hết (mục 5).

### 4.6. Câu thiếu thông tin được trả lời bằng giả định không hợp lý

- "Thành phố nào mưa nhiều nhất?": agent cộng toàn bộ dữ liệu, gồm cả ngày dự báo tương lai, và trả "Đà Nẵng 469,9 mm".
- "Nhiệt độ hôm qua là bao nhiêu?": agent trả một số trung bình gộp 12 thành phố.

**Sửa:** prompt quy định không gộp toàn bộ dữ liệu khi bảng trộn số liệu đã xảy ra với dự báo (hỏi lại khoảng thời gian), còn bảng chỉ có số liệu đã xảy ra như nhật ký nạp thì tính trên toàn bộ và nói rõ; thiếu đối tượng thì trả theo từng đối tượng. Để model biết bảng có số liệu tương lai, `query_metric` không lọc thời gian sẽ ghi chú khoảng dữ liệu đã gộp (ví dụ `ngay_key từ 2026-11-06 đến 2026-11-25`). Bản sửa đầu chỉ có quy tắc trong prompt nên làm hai câu T9-2 và T15-2 (tỷ lệ, thời gian nạp trung bình) bị hỏi lại thừa; bản sau phân biệt theo loại bảng nên hai câu này trả lời thẳng lại.

### 4.7. Câu con đầu tiên trả lời luôn cả câu sau

Ở câu phụ thuộc D-2, câu con 1 ("Thành phố nào nóng nhất hôm qua?") cũng truy vấn độ ẩm vì agent nhận `full_question`, làm câu 1 chậm thêm khoảng 10 giây và chạy SQL thừa. Câu con sau bước tách đã tự đủ ngữ cảnh, câu không tách thì `full_question` trùng `question`.

**Sửa** (`text2sql_agent_service.py`, prompt agent): bỏ `full_question` khỏi đầu vào agent. Sau sửa D-2 mỗi câu con một truy vấn, tổng 20 giây (trước 28,6 giây).

### 4.8. Các cải thiện nhỏ khác

- Metric `thoi_gian_nap_trung_binh` dùng `EXTRACT(EPOCH FROM …)` bị từ chối nên agent phải tự viết SQL; nay `sql_builder.py` cho phép `EXTRACT`.
- Gom theo ngày trên cột kiểu `date` trả `DATE_TRUNC` dạng timestamp kèm múi giờ (`2026-11-12T00:00:00+00:00`); nay ép về `date`.

## 5. Vấn đề còn lại

- **T6-2 chưa ổn định:** agent đôi khi vẫn phân nhóm theo `vung` thay vì nối sang `vung_khi_hau` (6/7 lần đạt sau sửa). Muốn chắc chắn hơn cần cho `query_metric` nối bảng chiều theo quan hệ đã khai báo, hoặc bổ sung `vung_khi_hau` vào bảng tổng hợp.
- **M-2 chưa ổn định:** 1/5 lần vẫn trả một số trung bình gộp mọi thành phố mà không nói rõ. Việc hỏi lại hiện chỉ là văn bản trong câu trả lời; `status` vẫn là `answered`. Khi có bước hỏi lại người dùng bằng pause/resume của LangGraph, nên để agent gọi một công cụ hỏi lại thay vì viết câu hỏi vào câu trả lời.
- **Cấu hình quy tắc:** quy tắc "Lần nạp thất bại" gắn với `ty_le_nap_thanh_cong`, "Ngày có mưa" gắn với `ty_le_ngay_co_mua`. Builder đã tránh được lỗi, nhưng nên xem lại cách gắn này trong quản lý quy tắc chuyên gia.
- **Data dictionary ghi sai kiểu:** `bat_dau_luc`, `ket_thuc_luc`, `lay_luc` là `timestamptz` nhưng catalog ghi `TIMESTAMP`.
- **Bộ chấm còn dễ dãi:** chỉ kiểm tra con số và tên có mặt trong câu trả lời, không kiểm tra giả định hay bước thừa. Các nhận định trong báo cáo này có đọc lại từng câu trả lời của lần chạy trước sửa và các câu trượt. Mỗi loại mới có 2 đến 3 câu, chưa đủ để đo độ chính xác theo loại như đề xuất benchmark.
- **Chi phí bước hiểu câu hỏi:** rewrite và phân loại chiếm khoảng 6 giây mỗi câu, gần một nửa thời gian của câu đơn.
- **Chưa kiểm tra:** câu SQL chạy quá `TEXT2SQL_QUERY_TIMEOUT_SECONDS`, hội thoại nhiều lượt có `chat_history`, câu ngoài phạm vi dữ liệu (T20), và dữ liệu chứa PII.

## 6. Sau khi hoàn thiện (chạy lại ngày 2026-11-20)

Chạy lại sau khi đã có đủ stream SSE, hỏi lại bằng `interrupt()`/`Command(resume=...)` của LangGraph và ghi lượt vào `conversation`. Cùng connection, cùng model; working tree vẫn chưa commit.

### 6.1. Cách chạy

- **Qua HTTP thật:** `scripts/text2sql_eval/serve.py` chạy backend từ code của working tree trên máy host (cổng 18100, uvicorn, đổi địa chỉ database trong tiến trình như lần trước); `run_eval.py` gửi từng câu tới `POST /api/v1/text2sql/chat/stream`, đọc từng event SSE và dựng lại kết quả từ các event `preprocess`, `question_started`, `tool`, `question_waiting`, `question_answered`, `answer`, `clarification`, `done`, `error`. Container `backend` (code cũ) không được dùng. Cách dùng: [chạy đánh giá thật](../handbook/modules/text2sql/danh-gia-chay-that.md).
- **Có ghi hội thoại:** mọi câu gửi `user_id = text2sql-eval`. Sau mỗi câu, harness đọc `GET /api/v1/conversations/{id}/turns` và so số lượt, `turn_id`, `status`, `answer`, `resume_id`, `continued_from` với stream, rồi xóa hội thoại đó.
- **Bộ câu hỏi:** 40 câu cũ cộng 9 kịch bản mới (49 mục, mỗi mục chạy 2 lần: 112 lần gửi, trong đó 6 lần là ca lỗi):
  - 3 hội thoại nhiều lượt dựa vào lịch sử đã lưu: "Nhiệt độ cao nhất ở Hà Nội hôm qua" → "Còn ở Hải Phòng thì sao?" → "Hôm kia thì sao?"; "Thành phố nào nóng nhất hôm qua?" → "Độ ẩm trung bình ở đó hôm qua"; "Tổng lượng mưa ở Huế 7 ngày qua" → "Trong đó có mấy ngày mưa?".
  - 3 câu hỏi lại rồi chạy tiếp bằng `resume_id`: "Cho tôi xem số liệu tháng này" (bắt buộc phải dừng), "Thành phố nào mưa nhiều nhất?" (trả lời "Trong 7 ngày qua"), "Lượng mưa dự báo ở Huế là bao nhiêu?" (trả lời "Ngày mai"). Mỗi câu có gold cho câu trả lời sau khi chạy tiếp.
  - 3 ca lỗi: connection không tồn tại, connection tạm dừng (harness tạo tạm một connection `is_active = false` với URI giả rồi xóa), `resume_id` không tồn tại.

### 6.2. Tỷ lệ đạt theo loại

Các cột là bốn lần chạy toàn bộ, mỗi câu 2 lần, theo thứ tự thời gian. Lần 1 là code của các bước trước; các sửa ở mục 6.4 được thêm dần (lần 2: khoảng ngày tính sẵn; lần 3: ghi chú số gộp; lần 4: gợi ý cột gần tên).

| Nhóm | Lần 1 | Lần 2 | Lần 3 | Lần 4 |
| --- | --- | --- | --- | --- |
| T1 | 6/6 | 6/6 | 6/6 | 6/6 |
| T2 | 3/4 | 4/4 | 4/4 | 4/4 |
| T3, T4, T5, T7, T8, T9, T10, T11, T13 (mỗi nhóm) | 4/4 | 4/4 | 4/4 | 4/4 |
| T6 | 4/4 | 4/4 | 3/4 | 4/4 |
| T12 | 4/4 | 4/4 | 4/4 | 3/4 (\*) |
| T15 | 6/6 | 6/6 | 6/6 | 6/6 |
| T22 | 3/4 (\*) | 4/4 | 4/4 | 4/4 |
| Tách câu | 6/6 | 6/6 | 6/6 | 6/6 |
| Phụ thuộc | 4/4 | 4/4 | 4/4 | 4/4 |
| Thiếu thông tin | 6/6 | 6/6 | 5/6 (\*) | 6/6 |
| Hội thoại nhiều lượt | 5/6 | 6/6 | 6/6 | 6/6 |
| Hỏi lại và chạy tiếp | 6/6 | 6/6 | 6/6 | 6/6 |
| Lỗi | 6/6 | 6/6 | 6/6 | 6/6 |
| **Tổng** | **95/98** | **98/98** | **96/98** | **97/98** |

(\*) Chấm sai, câu trả lời đúng khi đọc lại; bộ chấm đã sửa sau lần đó và chấm lại cho kết quả đạt:
- T22-1 lần 1: câu trả lời viết `lớn hơn **0 mm**`, dấu `*` của markdown làm hỏng từ khóa.
- M-2 lần 3: trả theo từng thành phố (12 con số) mà không dùng từ "giả định".
- T12-2 lần 4: viết "TP.HCM" thay vì "Hồ Chí Minh".

Ba lần trượt thật trong các lần chạy này là:
- T2-1 và lượt 1 của C-3 ở lần 1: lệch một ngày, xem mục 6.4.1.
- T6-2 ở lần 3: phân nhóm theo `vung`, xem mục 6.4.3.

Đo độ ổn định riêng:

| Lần đo | Kết quả |
| --- | --- |
| Sau sửa 6.4.1 | T2-1 5/5, C-3 5/5, T7-2 5/5, T6-2 4/5, M-2 0/5 (gộp thành một số, không nói rõ) |
| Sau sửa 6.4.2 | M-2 5/5 (4 lần trả theo từng thành phố, 1 lần một số gộp có nói rõ), T9-2 5/5, T15-2 5/5, T3-2 5/5, T6-2 5/5, T12-1 5/5 |
| Sau sửa 6.4.3 | T6-2 6/6, T6-1 6/6, T11-2 6/6, M-2 6/6 |

Không câu nào hết lượt gọi công cụ (`exhausted`).

### 6.3. Stream, hỏi lại, hội thoại

- **Stream:** ở lần chạy cuối, cả 106 lần gửi thành công đều kết thúc bằng `done`; không có event `error` nào. Thứ tự event luôn là `turn` → `preprocess` (không có khi chạy tiếp) → `question_started` → `tool`... → `question_answered` hoặc `question_waiting` → `answer` hoặc `clarification` → `done`. Ở lần chạy cuối có 273 event `tool`, khớp đúng số bước trong kết quả. Event đầu tiên (`turn`) đến sau trung vị 0,7 giây.
- **Hỏi lại:**
  - Có 10 lần dừng mỗi lần chạy: R-1, R-2, R-3, M-1, M-3, mỗi câu 2 lần, tất cả qua `ask_user` với `status = needs_clarification`.
  - Không có lần nào hỏi lại bằng văn bản trong câu trả lời.
  - Chạy tiếp bằng `resume_id` luôn trả lời đúng gold. Lượt chạy tiếp không chạy lại bước hiểu câu hỏi nên mất 3,9 đến 6 giây (lượt dừng mất 9 đến 16 giây).
- **Hội thoại:**
  - Câu nối tiếp được viết lại đúng nhờ lịch sử đã lưu: "Còn ở Hải Phòng thì sao?" thành nhiệt độ cao nhất ở Hải Phòng hôm qua; "Hôm kia thì sao?" giữ Hải Phòng; "ở đó" thành TP. Hồ Chí Minh.
  - Kiểm tra lưu hội thoại không phát hiện sai lệch nào ở cả bốn lần chạy:
    - Mỗi lần gửi có đúng một lượt lưu, cùng `turn_id`, `status`, `answer` với stream.
    - Lượt dừng lưu đúng `resume_id`.
    - Lượt chạy tiếp có `continued_from` trỏ về lượt dừng.
- **Ngắt kết nối:** client đóng stream ngay sau `preprocess`, lượt được lưu `status = error`, `error_code = client_disconnected`.
- **Lỗi:**
  - Connection không tồn tại trả 404.
  - Connection tạm dừng trả 400 ("Connection đang tạm dừng nên chưa thể truy vấn.").
  - `resume_id` lạ trả 404.
  - Cả ba lỗi đều trả về trước khi stream bắt đầu, trong khoảng 0,9 giây.

### 6.4. Lỗi tìm thấy và cách sửa

#### 6.4.1. Lệch một ngày ở "7 ngày qua"

T2-1 và lượt 1 của C-3: agent lọc `ngay_key >= '2026-11-12' AND < '2026-11-20'` (8 ngày) nhưng câu trả lời ghi "từ 13 đến 19/11", trả 58,7 mm thay vì 8,6 mm. Lỗi xảy ra ở 2/16 truy vấn "7 ngày qua" trong lần 1. Model tự cộng trừ ngày nên đôi khi sai.

**Sửa** (`text2sql_agent_service.py`, `prompt_text2sql_agent.py`):
- Đầu vào agent có thêm `dates`, các khoảng tính sẵn từ `today` dạng `{from, before}` nửa mở: `yesterday`, `last_7_days`, `last_week`, `this_week`, `this_month`, `last_month`.
- Prompt yêu cầu dùng đúng các khoảng này và nêu đúng khoảng đã lọc.

Sau sửa, mọi truy vấn lọc mốc đầu của "7 ngày qua" ở lần 2 và 4 (16 và 17 truy vấn) đều bắt đầu từ 13/11, và T2-1, C-3 đạt 5/5 trong lần đo ổn định.

#### 6.4.2. Câu không nêu đối tượng bị gộp thành một số

M-2 ("Nhiệt độ hôm qua là bao nhiêu?") đạt ở các lần chạy toàn bộ, nhưng một lần đo riêng cho 0/5: agent trả "24,5 °C" gộp 12 thành phố mà không nói rõ. Quy tắc trong prompt có, nhưng model không làm theo ổn định.

**Sửa** (`agent_tools.py`): `query_metric` không có `group_by` và không lọc theo cột văn bản nào thì thêm ghi chú: kết quả là một số gộp mọi dòng của bảng, câu hỏi không nêu đối tượng thì trả theo từng đối tượng hoặc nói rõ là số gộp. Cách làm giống ghi chú khoảng thời gian đã sửa M-1. Sau sửa M-2 đạt 11/11 qua hai lần đo; T9-2 và T15-2, hai câu tổng hợp hợp lệ trên toàn bảng, vẫn trả lời thẳng (5/5).

#### 6.4.3. T6-2 vẫn thay vùng khí hậu bằng vùng địa lý

Lần 3 và một lần đo riêng (1/5) vẫn phân nhóm theo `vung`. Không làm được cách chắc chắn là cho `query_metric` tự nối bảng, vì catalog hiện không có quan hệ giữa các bảng (module join cũ đã gỡ).

**Sửa** (`agent_tools.py`): khi `query_metric` phân nhóm theo một cột, công cụ liệt kê các cột ở bảng khác có tên hoặc nhãn mở rộng từ tên cột đó (ví dụ `vung` thì gợi ý `dm_thanh_pho.vung_khi_hau (Vùng khí hậu)`; không liệt kê cột trùng tên, vốn là khóa nối) và nhắc nối bảng bằng `run_sql` nếu câu hỏi hỏi đúng chiều đó. Lần đo sau sửa: 6/6, trong đó 2 lần agent gọi `query_metric` theo `vung`, đọc ghi chú và tự chuyển sang `run_sql` nối `vung_khi_hau`. T6-1 (phân nhóm theo `ten_thanh_pho`) không nhận ghi chú này.

#### 6.4.4. Lượt đang chờ mở lại từ lịch sử không chạy tiếp được

Đây là lỗi hợp đồng API, do bước SSE ghi nhận lại. API hội thoại không trả `resume_id`, nên sau khi tải lại trang, lựa chọn của lượt đang chờ bị gửi như câu hỏi mới.

**Sửa:**
- Backend (`conversation_service.py`, `schema_conversation.py`): lượt trả thêm `resume_id`, `resume_expires_at`, lấy từ `continuation` của lượt `needs_clarification` còn hạn. Bản thân `continuation` vẫn không trả ra.
- Frontend (`types.ts`, `use-chat.ts`): dựng lại lượt từ lịch sử dùng `resume_id` này.
- Harness kiểm tra `resume_id` lưu khớp với stream. Riêng giao diện chưa được thử trong trình duyệt.

#### 6.4.5. Bộ chấm

- Bỏ dấu `*` của markdown khi so từ khóa.
- `clarify_or_assume` chấp nhận câu trả lời theo từng đối tượng (trường `breakdown`).
- Thêm tên viết tắt (`TP.HCM`) cho "Ho Chi Minh".
- Thêm các cụm như "số gộp", "gộp chung" vào danh sách cách nói rõ giả định.

### 6.5. Thời gian

Lần chạy cuối, 4 câu song song, 106 lần gửi thành công:

| Chỉ số | Trung vị | p90 | Lớn nhất |
| --- | --- | --- | --- |
| Tổng một lần gửi | 12,2 s | 21,4 s | 27,9 s |
| Đến event đầu tiên (`turn`) | 0,7 s | 0,9 s | 2,1 s |
| Đến event `preprocess` | 6,0 s | 7,6 s | 8,7 s |
| Một câu đơn (`question_started` tới `question_answered`/`question_waiting`) | 5,5 s | 11,5 s | 22,8 s |

So với lần chạy trong tiến trình (mục 3: trung vị 13,6 s/câu), đi qua HTTP và SSE không làm chậm thêm. Lần chạy cuối có 273 bước công cụ: 97 `query_metric`, 73 `get_metric`, 42 `get_table`, 28 `get_column_values`, 24 `run_sql`, 9 `get_expert_rule`.

### 6.6. Vấn đề còn lại

- **Bước hiểu câu hỏi vẫn khoảng 6 giây**, gần một nửa thời gian. Người dùng thấy event đầu sau 0,7 giây nhưng phải chờ khoảng 6 giây mới có `preprocess`. Chưa xử lý (prompt rewrite và phân loại không đổi).
- **T6-2 dựa vào gợi ý, chưa chắc chắn:** cần khai báo quan hệ bảng trong data dictionary để `query_metric` tự nối bảng chiều.
- **Câu không nêu đối tượng:** M-2 đôi khi vẫn trả một số gộp, dù có nói rõ là gộp. Agent chọn giả định thay vì hỏi lại, đúng quy tắc "ưu tiên giả định hợp lý".
- **Giao diện:** frontend chạy trong container là bản build cũ. Việc chạy tiếp lượt đang chờ sau khi tải lại trang mới kiểm tra qua API, chưa thử trong trình duyệt.
- **Chưa kiểm tra:**
  - Nhiều worker uvicorn hoặc reverse proxy.
  - Khởi động lại backend giữa lúc dừng và lúc chạy tiếp.
  - Câu SQL quá thời gian chờ, câu ngoài phạm vi (T20), dữ liệu có PII.
  - Câu tách chạy song song mà nhiều câu đơn cùng hỏi lại.
- **Bộ chấm:** vẫn chỉ so con số và tên. Các nhận định ở trên có đọc lại câu trả lời của mọi câu trượt và các câu thiếu thông tin. Mỗi loại vẫn chỉ có 2 đến 3 câu.
- **Từ trước, chưa đổi:**
  - Quy tắc "Lần nạp thất bại" và "Ngày có mưa" gắn với metric tỷ lệ.
  - Data dictionary ghi `TIMESTAMP` cho cột thực tế là `timestamptz`.
  - Prompt rewrite và phân loại dùng ví dụ cùng miền thời tiết.
