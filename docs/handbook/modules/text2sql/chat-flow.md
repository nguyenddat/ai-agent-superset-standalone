# Luồng chat phía server (`POST /api/v1/text2sql/chat`)

**Trạng thái: đã triển khai** (2026-11-16; cập nhật cùng ngày: thông tin cột trong `data`, giả định và thông điệp trong `done`; lưu lượt vào hội thoại, hỏi nối tiếp, chọn cách nối ở lượt sau, lựa chọn trả lời khi hỏi lại). Mã: `backend/modules/text2sql/chat/pipeline.py` (`ChatPipeline`), `chat/turns.py` (ghi lượt, kiểm tra request tiếp tục), `chat/events.py`, `chat/reasoning.py`, `chat/dataset_flow.py`, `chat/analysis_context.py`, `chat/columns.py`, route `backend/modules/text2sql/routes/chat.py`. Các agent ở [gói agent dùng chung](../agent_package.md); lưu trữ ở [module conversation](../conversation/README.md).

Giao diện gọi route này là tab `Hỏi dữ liệu` của frontend (xem [handbook frontend](../../frontend/README.md#hỏi-dữ-liệu)). Câu hỏi gợi ý cho màn hình trống lấy từ [`GET /api/v1/text2sql/suggestions`](suggestions.md).

Một request là **một lượt hỏi**: server tự chạy toàn bộ chuỗi (viết lại câu hỏi, tìm metric, hoặc tìm trường và truy vấn nhiều bảng, rồi phân tích) và trả kết quả dạng Server-Sent Events. Khi có `user_id`, lượt được lưu vào một hội thoại và câu hỏi được hiểu theo các lượt trước của hội thoại đó (xem [Hội thoại và lịch sử](#hội-thoại-và-lịch-sử)); không có `user_id` thì mỗi request độc lập và không lưu gì. MCP tool [`ask_data`](ask-flow.md) vẫn tồn tại độc lập và không đổi hành vi (không có lịch sử).

## Request

```json
{"connection_id": "<UUID>", "question": "Doanh thu theo vùng năm 2025?", "user_id": "alice"}
```

| Trường | Ràng buộc |
| --- | --- |
| `connection_id` | UUID, connection phải tồn tại và đang hoạt động. |
| `question` | Chuỗi 1 đến 2000 ký tự sau khi bỏ khoảng trắng đầu cuối. Bắt buộc, trừ khi tiếp tục một lượt (`previous_turn_id`): khi đó có thể bỏ, lượt mới lấy câu hỏi của lượt trước. |
| `user_id` | Tùy chọn, tối đa 255 ký tự; chuỗi rỗng coi như không có. Dùng để lọc tri thức riêng (`own_knowledge`) và làm chủ hội thoại. |
| `conversation_id` | Tùy chọn, UUID. Có thì bắt buộc có `user_id`; hội thoại phải thuộc `user_id` và cùng `connection_id`. Không gửi (mà có `user_id`) thì server tạo hội thoại mới, tiêu đề lấy từ câu hỏi. |
| `previous_turn_id`, `join_signature` | Tùy chọn, phải đi cùng nhau và cùng `conversation_id`, `user_id`: chọn một cách nối cho lượt trước đang `join_ambiguous` (xem [Chọn cách nối](#chọn-cách-nối-ở-lượt-sau)). `join_signature` 1 đến 64 ký tự. |

Body không nhận trường khác (`extra="forbid"`), nên client không thể gửi SQL hay plan. Lỗi đầu vào, lỗi connection và lỗi hội thoại được trả **trước** khi stream bắt đầu, dạng JSON `{"detail": "..."}` như mọi API khác:

| Lỗi | HTTP |
| --- | ---: |
| Body sai: thiếu `question` khi không tiếp tục, `conversation_id` không có `user_id`, `previous_turn_id`/`join_signature` thiếu một hoặc thiếu `conversation_id` | 422 |
| Connection không tồn tại | 404 |
| Connection đang tạm dừng | 400 |
| Hội thoại không tồn tại hoặc thuộc người khác (`Không tìm thấy hội thoại.`) | 404 |
| Hội thoại thuộc connection khác; `join_signature` không thuộc các phương án đã lưu của lượt trước | 422 |
| `previous_turn_id` không thuộc hội thoại (`Không tìm thấy lượt hỏi đáp.`) | 404 |
| Lượt trước không ở trạng thái `join_ambiguous` hoặc không có trạng thái tiếp tục | 409 |
| Cách nối đã chọn không còn trong các phương án hiện tại của đồ thị quan hệ | 409 |

## Response

`200`, `Content-Type: text/event-stream`, header `Cache-Control: no-cache` và `X-Accel-Buffering: no` (tắt buffer của nginx). Mỗi event có dạng:

```text
event: <tên>
data: <JSON một dòng, UTF-8, không escape tiếng Việt>

```

Lỗi xảy ra sau khi stream đã bắt đầu không đổi được HTTP status nữa, nên được gửi thành event `error` rồi kết thúc stream.

### Các event

| Event | Payload | Khi nào |
| --- | --- | --- |
| `turn` | `{conversation_id, turn_id}` | Event **đầu tiên** khi request có `user_id`, ngay sau khi lượt được ghi (`running`); client giữ id dù stream bị ngắt. Không có khi không có `user_id`. |
| `step` | `{step, status, detail}`; `status` là `started`, `done` hoặc `skipped` | Bắt đầu, kết thúc hoặc bỏ qua một bước. |
| `reasoning` | `{step, source, index, delta}` (xem [Event `reasoning`](#event-reasoning)) | Từng đoạn quá trình suy luận của một bước, giữa `step started` và `step done`/`skipped` của bước đó. |
| `data` | Kết quả một truy vấn (xem dưới) | Sau khi một truy vấn chạy xong, trước phần phân tích. |
| `token` | `{text}` | Từng đoạn câu trả lời của `AnalysisAgent`. |
| `done` | `{status, flow, dataset_id?, assumptions, message, clarification_question?, clarification_options?, conversation_id?, turn_id?}` (xem [Event `done`](#event-done)) | Kết thúc bình thường. |
| `error` | `{code, message}` | Chỉ khi chính bước phân tích hỏng, không khởi tạo được tài nguyên, hoặc không mở được lượt hội thoại; stream kết thúc, không có `done`. |

`step` thuộc: `rewrite`, `metric_search`, `metric_query`, `field_search`, `dataset_plan`, `join_plan`, `dataset_query`, `analysis`.

Ví dụ:

```text
event: step
data: {"step":"rewrite","status":"done","detail":{"original_question":"Doanh thu theo vùng?","rewritten_question":"Doanh thu theo vùng?","glossary_terms":["Doanh thu"],"rules":[],"own_knowledge":[],"changes":[]}}

event: step
data: {"step":"metric_search","status":"done","detail":{"candidates":[{"name":"revenue","label":"Doanh thu","source":"glossary_link"}]}}

event: step
data: {"step":"metric_query","status":"skipped","detail":{"reason":"Không có metric tách theo vùng."}}

event: step
data: {"step":"field_search","status":"done","detail":{"match":"ok","note":null,"tables":[{"name":"public.orders","display_name":"Đơn hàng","fields":["Tổng tiền"]}]}}

event: step
data: {"step":"join_plan","status":"done","detail":{"status":"ok","description":"Bắt đầu từ Đơn hàng: Đơn hàng (cột Mã khách) nối tới Khách hàng (cột Mã)","root_table":"Đơn hàng","tables":["Đơn hàng","Khách hàng"],"joins":["Đơn hàng (cột Mã khách) nối tới Khách hàng (cột Mã)"]}}

event: data
data: {"kind":"dataset","sql":"WITH \"base\" AS (...) SELECT ...","parameters":{"p1":201},"columns":[{"name":"customers_region","column_id":"<UUID>","label":"Vùng","role":"dimension","data_type":"text","format":null,"unit":null,"contains_pii":false},{"name":"revenue","column_id":"<UUID>","label":"Tổng tiền (tổng)","role":"metric","data_type":"decimal","format":"#,##0","unit":"VND","contains_pii":false}],"rows":[["Bắc","350.00"],["Nam","100.00"]],"row_count":2,"truncated":false,"warnings":[],"rules_applied":[],"filters_overridden":[],"pii":{"confirmation":"not_supported","masked_columns":[],"detected":{},"warning":null}}

event: token
data: {"text":"Miền Bắc có doanh thu cao nhất "}

event: done
data: {"status":"answered","flow":"dataset","dataset_id":"<UUID>","assumptions":["Tính trên mọi trạng thái đơn"],"message":"Doanh thu theo vùng."}
```

### Event `reasoning`

**Đã triển khai** (2026-11-16). Stream quá trình suy luận của các bước trước phần phân tích cuối, để giao diện hiển thị "đang nghĩ gì".

| Trường | Ý nghĩa |
| --- | --- |
| `step` | Tên bước, cùng tập tên với event `step` (`rewrite`, `metric_search`, `metric_query`, `field_search`, `dataset_plan`, `join_plan`, `dataset_query`). Bước `analysis` không có `reasoning` (câu trả lời đã là `token`). |
| `source` | `model`: suy luận của mô hình (trường `analysis` B1..Bn của `QuestionRewriteAgent`, `QueryPlanAgent`, `DatasetPlanAgent`), stream dần khi mô hình đang sinh. `server`: lời giải thích bằng tiếng Việt thường của các bước không dùng LLM. |
| `index` | Số thứ tự mục suy luận trong bước, bắt đầu từ 0, **đếm chung cho cả hai nguồn** trong cùng bước (mục của server đứng sau mục của mô hình). |
| `delta` | Phần chữ mới. Client **nối** `delta` vào mục `index` của bước `step`. Mục `model` có thể đến qua nhiều event; mỗi mục `server` đến trọn trong một event. |

Thứ tự trong một bước: `step started` → các `reasoning` của bước đó → (`data` nếu bước chạy truy vấn) → `step done` hoặc `step skipped`. Mọi `reasoning` của một bước nằm trước event kết thúc bước đó; client cũ bỏ qua event lạ vẫn chạy đúng vì các event `step`, `data`, `token`, `done`, `error` giữ nguyên. Khi `metric_search` không có ứng viên, lời giải thích chuyển sang luồng dataset nằm ở bước `metric_search` (vì `metric_query` chỉ có `skipped`, không có `started`).

```text
event: step
data: {"step":"rewrite","status":"started","detail":{}}

event: reasoning
data: {"step":"rewrite","source":"model","index":0,"delta":"B1. Câu hỏi "}

event: reasoning
data: {"step":"rewrite","source":"model","index":0,"delta":"hỏi doanh thu theo vùng"}

event: reasoning
data: {"step":"rewrite","source":"model","index":1,"delta":"B2. Thuật ngữ 'Doanh thu' khớp"}

event: step
data: {"step":"rewrite","status":"done","detail":{...}}

event: step
data: {"step":"metric_search","status":"started","detail":{}}

event: reasoning
data: {"step":"metric_search","source":"server","index":0,"delta":"Loại metric 'Số đơn hàng': điểm Jev 0.20 dưới ngưỡng 0.60."}

event: reasoning
data: {"step":"metric_search","source":"server","index":1,"delta":"Không có metric nào đủ liên quan tới câu hỏi. Chuyển sang luồng dataset: ..."}

event: step
data: {"step":"metric_search","status":"done","detail":{"candidates":[]}}
```

Suy luận của server theo bước (`chat/reasoning.py`, chỉ dùng tên hiển thị của bảng, cột, metric, quy tắc; không có UUID, URI, mật khẩu, lỗi nội bộ hay giá trị dữ liệu):

| Bước | Nội dung |
| --- | --- |
| `metric_search` | Mỗi ứng viên giữ vì liên kết thuật ngữ hoặc quy tắc; giữ hoặc loại theo điểm Jev so với `TEXT2SQL_ASK_METRIC_MIN_SCORE` (hoặc "chưa chấm được điểm Jev" khi Jev không bật/lỗi); cắt còn 6 ứng viên; không còn ứng viên thì chuyển sang luồng dataset và vì sao. |
| `metric_query` | Sau suy luận của mô hình: quy tắc chuyên gia được áp dụng hoặc nhường cho bộ lọc của câu hỏi; mỗi truy vấn chạy xong (số dòng, bị cắt, cột PII đã che); `no_metric` thì lý do và chuyển sang luồng dataset; plan sai thì thông báo (đã đổi UUID thành tên); `needs_clarification`. |
| `field_search` | Số cột và bảng tìm được, từng bảng với tối đa 6 tên cột hiển thị, mức khớp (`ok`: đã lọc theo Jev; `unverified`: chỉ tham khảo); không có cột thì dừng. |
| `dataset_plan` | Sau suy luận của mô hình: ánh xạ thành công (bảng gốc, các bảng dùng), bảng tự thêm, hoặc lỗi tên (một thông báo, không retry); `cannot_answer`/`needs_clarification`. |
| `join_plan` | `ok`: bảng gốc, từng bước `LEFT JOIN` (bảng, cột nối), cảnh báo nhân dòng; một bảng thì không cần nối; `ambiguous`: số cách nối, từng cách, cách nào đã dùng trước đây; `not_declared`: các nhóm bảng chưa có quan hệ khai báo. |
| `dataset_query` | Bộ dựng từ chối (thông báo đã làm sạch); truy vấn chạy xong (số dòng, bị cắt, cột PII đã che); dùng lại dataset cũ hay tạo mới, số cột thêm, hoặc lưu thất bại. |

`rewrite` chỉ có suy luận của mô hình. Nội dung suy luận của mô hình là văn bản tự do do mô hình viết từ ngữ cảnh đã gửi (câu hỏi, thuật ngữ, quy tắc, tên cột; không có dòng dữ liệu), server không lọc lại.

**Giới hạn:** suy luận của mô hình chỉ đến dần khi nhà cung cấp stream đối số tool call từng phần (`tool_call_chunks`). Nếu nhà cung cấp hoặc model trả toàn bộ đối số trong một chunk cuối thì mọi mục `analysis` đến một lần ngay trước `step done`; nội dung vẫn đúng. Chưa kiểm với OpenRouter/`openai/gpt-6-luna` thật xem đối số có được stream từng phần không. Nếu mô hình lỗi giữa chừng, các `reasoning` đã gửi vẫn ở client, bước đó không có `step done` và lượt hỏi đi tiếp vào `analysis` với trạng thái `error` như trước.

Payload `data`: `kind` (`metric` hoặc `dataset`), `metric` (chỉ với `kind=metric`: `name`, `label`, `format`, `currency`), `sql` và `parameters` (để kiểm tra; do server dựng), `columns` (xem [Thông tin cột](#thông-tin-cột-trong-data)), `rows` (đã che PII, đủ số dòng theo `limit` của truy vấn, trần `TEXT2SQL_QUERY_MAX_ROWS`), `row_count`, `truncated`, `warnings` (cảnh báo của metric, nhân dòng, trần cột dataset), `rules_applied` và `filters_overridden` (quy tắc chuyên gia tự áp dụng cho metric, xem [ask-flow.md](ask-flow.md)), `pii` (`confirmation` luôn là `not_supported`, `masked_columns`, `detected`, `warning`). Luồng metric có thể có tối đa ba event `data` (câu hỏi nhiều đại lượng).

### Thông tin cột trong `data`

**Đã triển khai** (2026-11-16). Mỗi mục của `columns` theo đúng thứ tự giá trị trong mỗi dòng của `rows`:

| Trường | Ý nghĩa |
| --- | --- |
| `name` | Tên cột kết quả như trước: luồng dataset là alias kỹ thuật (`customers_region`, `revenue`, `time_bucket`); luồng metric đã là nhãn (`Trạng thái`, `Ngày đặt (month)`, tên hiển thị của metric). Tên trong `pii.masked_columns` khớp với trường này. |
| `column_id` | UUID (chuỗi) của cột nguồn trong catalog, hoặc `null` (cột giá trị của luồng metric, biểu thức của luồng dataset). Cột tổng hợp từ một cột (`sum`, `count`...) mang `column_id` của cột đó. |
| `label` | Tên để hiển thị. Cột thường: `display_name` trong data dictionary, không có thì `name`. Cột tổng hợp ở luồng dataset: `display_name` kèm phép tổng hợp, ví dụ `Tổng tiền (tổng)`, `Mã đơn (số lượng)`; không có dictionary thì `name`. Cột kỳ thời gian: tên hiển thị của cột thời gian kèm kỳ, ví dụ `Ngày đặt (theo tháng)`. Cột giá trị metric: `label` của metric. Biểu thức: `name`. |
| `role` | `dimension`, `time` hoặc `metric` như trước. |
| `data_type` | Một trong `integer`, `decimal`, `float`, `date`, `datetime`, `boolean`, `text`, hoặc `null` khi không suy được. Cột thường suy từ kiểu Postgres của cột (`int*`, `serial` → `integer`; `numeric`, `decimal`, `money` → `decimal`; `real`, `double precision` → `float`; `date`; `timestamp*` → `datetime`; `bool*` → `boolean`; còn lại, kể cả `uuid`, `time`, `interval`, `json` → `text`). Cột kỳ thời gian: `date` nếu cột nguồn là `date`, `datetime` nếu là `timestamp` (giá trị vẫn có phần giờ `T00:00:00`). Cột giá trị metric và cột tổng hợp suy theo kiểu giá trị Python mà driver trả về **trước** khi định dạng (`Decimal` → `decimal`, `int` → `integer`...; trộn số nguyên và `Decimal` là `decimal`). Khi không dòng nào có giá trị: `count`, `count_distinct` là `integer`; metric có biểu thức chỉ là một `COUNT(...)` là `integer`; cột tổng hợp khác dùng kiểu của cột nguồn; còn lại `null`. |
| `format`, `unit` | Cột thường và cột tổng hợp (trừ `count`, `count_distinct`): `format`, `unit` của data dictionary. Cột giá trị metric: `format` và `currency` của metric (`currency` đặt vào `unit`). Cột kỳ thời gian: `null` (định dạng của cột ngày không còn đúng sau khi gom theo kỳ). Không có thì `null`. |
| `contains_pii` | Như trước. |

**Số thập phân vẫn gửi dạng chuỗi** trong `rows` (ví dụ `"350.00"`) để giữ độ chính xác; client dựa vào `data_type` (`decimal`, `integer`, `float`) để biết cột số và tự chuyển khi vẽ hoặc định dạng. `format_cell` không đổi.

Metadata lấy từ catalog đã nạp ở bước viết lại câu hỏi (`load_context`: cột, data dictionary, metric của connection), nên không có truy vấn thêm. Kiểu giá trị Python được ghi trong `QueryResult.value_types`/`DatasetResult.value_types` và phép tổng hợp trong `ResultColumn.aggregation`; cả hai là trường ẩn (`exclude=True`) nên đầu ra của MCP `query_metric`, `query_dataset`, `ask_data` không đổi. Metadata cột không chứa giá trị dòng; cơ chế che PII giữ nguyên.

`AnalysisAgent` nhận `columns` rút gọn: `name`, `label`, `role`, `data_type`, `unit` (bỏ trường `null`, không gửi `column_id`).

Ví dụ một cột giá trị của luồng metric:

```json
{"name":"Số đơn hàng","column_id":null,"label":"Số đơn hàng","role":"metric","data_type":"decimal","format":",.2f","unit":"VND","contains_pii":false}
```

### Event `done`

**Đã triển khai** (2026-11-16). Ngoài `status`, `flow` và `dataset_id` (chỉ khi có dataset được lưu hoặc dùng lại):

| Trường | Ý nghĩa |
| --- | --- |
| `assumptions` | Danh sách giả định của bước lập kế hoạch (metric hoặc dataset); luôn có, có thể rỗng. |
| `message` | Chuỗi, luôn có, có thể rỗng: lý do của kế hoạch khi `answered`; lý do dừng khi `cannot_answer`, `join_*`, `needs_clarification`; thông điệp an toàn khi `error` (thông điệp của lỗi nghiệp vụ, hoặc thông điệp chung khi lỗi không mong đợi). |
| `clarification_question` | Chỉ có khi có câu hỏi làm rõ (thường với `needs_clarification`). |
| `clarification_options` | Chỉ có khi bước lập kế hoạch đưa ra lựa chọn trả lời cho câu hỏi làm rõ: tối đa 4 chuỗi ngắn. Client hiển thị thành nút; bấm thì gửi chuỗi đó làm `question` mới trong **cùng hội thoại** (bước viết lại tự ghép với câu hỏi gốc). |
| `conversation_id`, `turn_id` | Chỉ có khi request có `user_id`; trùng với event `turn`. |

`assumptions`, `message`, `clarification_question`, `clarification_options` được làm sạch UUID như các thông báo hiện có (`sanitize_message`: UUID của cột, bảng, metric đổi thành tên; UUID lạ thành `(mục nội bộ)`). Không có mã lỗi, stack trace hay nguyên nhân nội bộ. Hàm `done()` trong `chat/events.py` nhận thêm trường tùy chọn bằng tham số từ khóa và bỏ trường có giá trị `None`, để thêm trường mới (ví dụ `conversation_id`, `turn_id`) mà không đổi chữ ký.

```text
event: done
data: {"status":"needs_clarification","flow":"dataset","assumptions":["Tính theo ngày đặt"],"message":"Chưa rõ kỳ báo cáo.","clarification_question":"Bạn muốn xem năm nào?","clarification_options":["Năm 2025","Năm 2026"],"conversation_id":"<UUID>","turn_id":"<UUID>"}
```

### Trạng thái cuối (`done.status`)

| `status` | `flow` | Ý nghĩa |
| --- | --- | --- |
| `answered` | `metric` hoặc `dataset` | Có số liệu. |
| `needs_clarification` | `metric` hoặc `dataset` | Câu hỏi mơ hồ; phần phân tích đặt câu hỏi làm rõ. Không truy vấn gì. |
| `cannot_answer` | `metric` hoặc `dataset` | Không tìm thấy trường liên quan, agent kết luận không đủ trường, kế hoạch tham chiếu tên không tồn tại, hoặc bộ dựng truy vấn từ chối (kể cả nhân dòng). |
| `join_ambiguous` | `dataset` | Có nhiều cách nối; liệt kê để người dùng chọn. |
| `join_not_declared` | `dataset` | Các bảng chưa khai báo quan hệ; cần bổ sung trong data dictionary. |
| `error` | bất kỳ (`none` khi lỗi trước khi biết luồng) | Lỗi trong một bước (LLM của bước lập kế hoạch, Qdrant, database nguồn...). Vẫn có phần phân tích xin lỗi ngắn gọn. |

`dataset_id` chỉ có khi một dataset được lưu hoặc dùng lại.

## Luồng

```text
rewrite → metric_search ─┬─ có ứng viên → metric_query (QueryPlanAgent)
                         │     ready → chạy metric → data
                         │     needs_clarification → dừng
                         │     no_metric ─┐
                         └─ không có ─────┴→ field_search → dataset_plan (DatasetPlanAgent)
                                              → ánh xạ tên → join_plan → dataset_query → data
mọi trạng thái cuối → analysis (AnalysisAgent, stream token) → done
```

1. **Viết lại câu hỏi** (`rewrite`): như [ask-flow.md](ask-flow.md): truy hồi thuật ngữ, quy tắc chuyên gia, tri thức riêng theo câu hỏi gốc rồi một lượt `QuestionRewriteAgent` (route chat gọi `stream` để phát `reasoning`; MCP `ask_data` vẫn gọi `run`). Detail của `done` gồm câu viết lại và các mục đã dùng.
2. **Tìm metric** (`metric_search`): metric liên kết với thuật ngữ, quy tắc đã chọn cộng top 5 tìm theo câu viết lại, lọc bằng Jev theo `TEXT2SQL_ASK_METRIC_MIN_SCORE`.
3. **Truy vấn metric** (`metric_query`): một lượt `QueryPlanAgent`. `ready` thì dựng truy vấn bằng code (quy tắc chuyên gia áp tự động), chạy chỉ đọc, che PII. Tên cột sai trong plan thì `cannot_answer`, không retry. `no_metric` hoặc không có ứng viên thì sang luồng dataset (`metric_query` là `skipped`).
4. **Tìm trường** (`field_search`): `FieldService.find(câu viết lại)` (Jev, ngưỡng `TEXT2SQL_FIELD_MIN_SCORE`). `match=none` thì `cannot_answer`. `match=unverified` (Jev lỗi) vẫn tiếp tục, `note` ghi trong detail.
5. **Lập kế hoạch dataset** (`dataset_plan`): một lượt `DatasetPlanAgent` với `tables` là đầu ra `find_fields` rút gọn (`name` dạng `schema.bảng`, `short_name`, `description`, `grain`, `fields`), `expert_rules` (thuật ngữ và quy tắc đã truy hồi, dạng văn bản thường) và `own_knowledge`. `cannot_answer`/`needs_clarification` thì dừng.
6. **Ánh xạ tên về ID** (`chat/dataset_flow.py`): chỉ trong các bảng mà `find_fields` trả, nhưng chấp nhận mọi cột có trong catalog của các bảng đó (ví dụ cột khóa để đếm). Bảng viết `schema.bảng` (hoặc tên ngắn nếu duy nhất), cột viết `bảng.cột` (hoặc `schema.bảng.cột`), không phân biệt hoa thường. Tên bảng ngắn trùng giữa nhiều schema là lỗi rõ ràng. Mọi tên sai được gom thành **một** thông báo kèm danh sách tên hợp lệ (không lộ UUID), trạng thái `cannot_answer`, **không retry**. Kiểm tra `select` 1 đến 20 mục, mỗi mục đúng một trong `column` hoặc `expression`, `aggregation` chỉ với `column`, tối đa 8 bảng, có bảng gốc. Bảng gốc và bảng chứa cột được dùng mà agent quên liệt kê trong `tables` được tự thêm (vẫn chỉ trong các bảng tìm được), ghi ở `dataset_plan.detail.added_tables`. `order_by` dạng `bảng.cột` được đổi sang ID khi cột nằm trong `group_by`; alias giữ nguyên.
7. **Tính cách nối** (`join_plan`): `JoinService.plan(table_ids, root=bảng gốc)`; đồ thị quan hệ hiện tại là nguồn sự thật. Xem quy tắc dưới.
8. **Chạy dataset** (`dataset_query`): `DatasetQueryService.prepare` biên dịch; lỗi từ chối của bộ dựng (kể cả từ chối nhân dòng) thành `cannot_answer` với thông báo tiếng Việt của bộ dựng đã đổi UUID thành tên. Sau đó chạy chỉ đọc, che PII. **Chỉ sau khi chạy thành công** mới `DatasetStore.get_or_create` + `add_columns` + commit (giống tool `query_dataset`). Lưu thất bại không làm hỏng câu trả lời: thêm cảnh báo vào `warnings`. Cảnh báo trần 200 cột của dataset cũng đi vào `warnings`.
9. **Phân tích** (`analysis`): `AnalysisAgent.stream` với ngữ cảnh đúng schema của prompt `prompt_text2sql_analysis.py`: `question`, `rewritten_question`, `today`, `flow`, `status`, `rewrite` (tên thuật ngữ, quy tắc, tri thức riêng đã dùng, các thay đổi), `queries` (mỗi truy vấn với `rows` cắt tối đa `TEXT2SQL_CHAT_MAX_ROWS_TO_LLM` dòng, `row_count` là số dòng thật để mô hình biết bị cắt), `assumptions`, `pii` (`masked_columns`, `note`), `message`, `join`, `clarification_question`. Mọi trạng thái cuối, kể cả khi không chạy truy vấn nào hoặc một bước lỗi, đều qua bước này để người dùng nhận câu trả lời bằng lời.

## Quy tắc nối bảng và dataset đã lưu

- `ok`: dùng đúng phương án đồ thị trả. `get_or_create` theo `(connection, signature, bảng gốc)`: cùng cách nối và cùng gốc thì dùng lại dataset cũ (`created=false`) và chỉ thêm cột mới (`dataset_query.detail.added_columns`).
- `ambiguous`: **không tự chọn**, dừng với `join_ambiguous`. `join_plan.detail.options` liệt kê từng phương án bằng lời thường (`number`, `signature`, `description`, `root_table`, `tables`, `joins` dạng "Đơn hàng (cột Nơi giao) nối tới Địa điểm (cột Mã)") và `previously_used=true` khi phương án trùng signature với một dataset đã lưu cùng gốc và cùng bộ bảng (cờ chỉ để gợi ý hiển thị). Người dùng chọn bằng `signature` ở request sau (xem [Chọn cách nối](#chọn-cách-nối-ở-lượt-sau)); `number` chỉ để hiển thị.
- `not_declared`: dừng với `join_not_declared`, thông báo cần bổ sung khai báo quan hệ (cột tham chiếu) trong data dictionary; không bao giờ tự nối theo tên cột.

## Hội thoại và lịch sử

**Đã triển khai** (2026-11-16). Mã: `chat/turns.py` (`prepare_turn`, `TurnRecorder`), `ChatPipeline.prepare_turn`/`run(..., turn_request=...)`; lưu trữ qua `ConversationService` của [module conversation](../conversation/ghi-luot-tu-pipeline.md).

### Quy tắc

| Request | Hành vi |
| --- | --- |
| Không có `user_id` | Như trước: một lượt độc lập, không lưu, không có event `turn`, `done` không có id. |
| `user_id`, không có `conversation_id` | Tạo hội thoại mới (`start`, tiêu đề từ câu hỏi) rồi lượt 1. |
| `user_id` + `conversation_id` | Kiểm tra sở hữu và connection trước khi stream; lượt kế tiếp của hội thoại, có lịch sử. |
| `user_id` + `conversation_id` + `previous_turn_id` + `join_signature` | Tiếp tục lượt `join_ambiguous` với cách nối đã chọn; tạo lượt mới có `continued_from`. |

Route kiểm tra hội thoại bằng một session ngắn trước khi stream (`prepare_turn`, chỉ đọc). Generator mở **session riêng** cho việc ghi lượt (không dùng session truy vấn của pipeline vì session đó rollback khi một bước lỗi); tầng pipeline là nơi commit, service không commit:

1. `start` (nếu cần) → `recent_history` (6 lượt) → `begin_turn` (khóa hội thoại, lượt `running`) → **commit** → event `turn`.
2. Mỗi event đi qua `TurnRecorder.observe`: gom `step` và `reasoning`, `data`, `token`; `done` được thêm `conversation_id`, `turn_id`.
3. Gặp `done` hoặc `error`: `complete_turn` → **commit**, **trước** khi gửi event đó cho client (client nhận `done` rồi gọi API hội thoại là thấy lượt đã xong).
4. Client ngắt kết nối (generator bị đóng) trước khi kết thúc: lượt được đóng với `status=error`, `error_code=client_disconnected` cùng phần đã thu được (bước, token, kết quả), không kẹt `running`. Lượt chỉ còn `running` khi tiến trình chết giữa chừng.
5. Ghi kết quả lượt hỏng (lỗi database) chỉ được ghi log và rollback session ghi lượt; stream không đổi.

### Dữ liệu một lượt

| Trường | Nguồn |
| --- | --- |
| `status`, `flow` | `done`; không có `done` mà có `error` thì `error`. |
| `answer` | Nối các `token`. |
| `rewritten_question`, `rewrite` | Kết quả bước viết lại (`rewrite`: tên thuật ngữ, quy tắc, tri thức riêng đã dùng và `changes`, không có UUID). |
| `steps` | Mỗi bước một mục theo thứ tự xuất hiện: `{step, status, detail, reasoning}`; `status`, `detail` là của event `step` cuối cùng của bước (`detail` của `started` rỗng nên giữ detail của `done`/`skipped`); `reasoning` là danh sách `{source, text}` theo `index`, đã nối `delta`. Đủ để dựng lại khung suy luận như khi stream. |
| `results` | Payload của từng event `data` (đã che PII, giữ `kind`, `metric.name`/`label`, `columns`, `rows`...), service cắt `rows` theo `CONVERSATION_MAX_STORED_ROWS` và thêm `stored_truncated`. |
| `assumptions`, `clarification_question`, `clarification_options` | Bản đã làm sạch UUID trong `done`. |
| `pii` | Gộp `pii` của các `data`: `confirmation`, `masked_columns`, `detected` (cộng số đếm), `warnings`. |
| `dataset_id`, `duration_ms`, `model` | Dataset đã lưu hoặc dùng lại; thời gian từ lúc mở lượt; `OPENROUTER_MODEL`. |
| `error_code`, `error_message` | Khi `status=error`: mã lỗi nghiệp vụ (`agent_unavailable`, `text2sql_query_failed`, `internal_error`, `client_disconnected`...) và nguyên nhân nội bộ (tên lớp lỗi và thông điệp, tối đa 2000 ký tự). API hội thoại **không** trả `error_message`. |
| `continuation` | Chỉ với `join_ambiguous`, xem dưới; API không trả. |

### Hỏi nối tiếp

Trước bước viết lại, server lấy `recent_history(limit=6)`: các lượt gần nhất có trạng thái `answered`, `needs_clarification`, `cannot_answer`, `join_ambiguous`, `join_not_declared` (bỏ `running`, `error`). Mỗi mục gửi cho `QuestionRewriteAgent` chỉ gồm `question`, `rewritten_question`, `status`, `answer` (rút gọn tối đa 500 ký tự) và `clarification_question`; **không** có dòng dữ liệu, SQL hay kết quả. Lượt đầu (không có lịch sử) không có khóa `history`. Prompt dùng lịch sử để biến câu nối tiếp thành câu hỏi độc lập, ghép câu trả lời làm rõ với câu hỏi gốc, và bỏ qua lịch sử khi câu hỏi mới không liên quan ([gói agent](../agent_package.md#questionrewriteagent-với-lịch-sử-hội-thoại)). Các bước sau (metric, dataset, phân tích) chỉ dùng câu đã viết lại như trước.

Truy hồi thuật ngữ, quy tắc, tri thức riêng cho bước viết lại dùng câu đã viết lại của lượt gần nhất nối với câu hỏi hiện tại (khi có lịch sử), để câu ngắn như "chia theo khu vực" vẫn kéo được thuật ngữ của chủ đề đang hỏi.

Trả lời câu hỏi làm rõ: client gửi câu trả lời (hoặc một mục của `clarification_options`) làm `question` mới cùng `conversation_id`; không có trường riêng.

### Chọn cách nối ở lượt sau

Khi lượt kết thúc `join_ambiguous`, server lưu vào cột nội bộ `conversation_turns.continuation`: `version`, `rewritten_question`, `rewrite` (thông tin viết lại, không có suy luận), `root_table_id`, `table_ids`, `plan` (kế hoạch dataset đã ánh xạ về ID, dạng JSON của `DatasetQueryPlan`), `assumptions`, `reason`, `signatures` (signature của các phương án lúc đó).

Request chọn cách nối:

```json
{"connection_id": "<UUID>", "user_id": "alice", "conversation_id": "<UUID>",
 "previous_turn_id": "<UUID lượt join_ambiguous>", "join_signature": "<signature trong join_plan.detail.options>"}
```

Server (trước khi stream) kiểm tra lượt trước thuộc hội thoại, `status=join_ambiguous`, có `continuation`; `join_signature` nằm trong `signatures` đã lưu; tính lại `JoinService.plan(table_ids, root)` trên đồ thị hiện tại và chỉ chấp nhận khi signature còn trong các phương án (đồ thị là nguồn sự thật; quan hệ đã đổi thì 409). Sau đó stream **không** chạy lại viết lại câu hỏi, tìm metric, tìm trường hay lập kế hoạch (không gọi LLM nào ngoài phân tích) và không mở Qdrant/embedding/Jev:

```text
event: turn
data: {"conversation_id":"<UUID>","turn_id":"<UUID lượt mới>"}

event: step
data: {"step":"join_plan","status":"started","detail":{}}

event: reasoning
data: {"step":"join_plan","source":"server","index":0,"delta":"Dùng cách nối người dùng đã chọn ở lượt trước; không viết lại câu hỏi hay lập lại kế hoạch."}

event: step
data: {"step":"join_plan","status":"done","detail":{"status":"ok","chosen":true,"signature":"<signature>","description":"Bắt đầu từ Đơn hàng: ...","root_table":"Đơn hàng","tables":["Đơn hàng","Địa điểm"],"joins":["..."]}}

event: step
data: {"step":"dataset_query","status":"started","detail":{}}
...
event: done
data: {"status":"answered","flow":"dataset","dataset_id":"<UUID>","assumptions":["..."],"message":"<reason của kế hoạch>","conversation_id":"<UUID>","turn_id":"<UUID lượt mới>"}
```

`dataset_query` chạy như luồng thường (biên dịch, chạy chỉ đọc, che PII, lưu dataset theo signature đã chọn, rồi phân tích). Lượt mới có `continued_from` trỏ tới lượt `join_ambiguous`, `question` là câu hỏi gửi kèm hoặc câu hỏi của lượt trước, `rewritten_question`/`rewrite`/`assumptions` lấy từ trạng thái đã lưu. Lượt trước giữ nguyên, có thể chọn lại cách khác bằng request mới.

## PII

- Route HTTP không có bước hỏi đồng ý, nên PII **luôn bị che** (`confirmation=not_supported`): cột đánh dấu `contains_pii` và giá trị nhận diện được (email, số điện thoại, CCCD...) thành placeholder `<PII_n>` trước khi rời server.
- **Các dòng đã che (tối đa `TEXT2SQL_CHAT_MAX_ROWS_TO_LLM` mỗi truy vấn) được gửi tới nhà cung cấp LLM (OpenRouter) để phân tích**, cùng câu hỏi, SQL và tên cột. Giá trị gốc của cột PII không bao giờ được gửi; giá trị không được đánh dấu PII và không bị bộ nhận diện bắt thì vẫn được gửi.
- Bộ dựng truy vấn từ chối lọc, tính toán hay dùng cột PII làm thời gian.

## Nguyên tắc

- Mỗi agent gọi mô hình **một lượt**, không retry, không vòng lặp; chỉ dùng model cấu hình (`OPENROUTER_MODEL`, mặc định `openai/gpt-6-luna`).
- Pipeline dùng `AskService` theo từng phần để chèn stream của agent: `start` (kiểm tra câu hỏi, truy hồi ngữ cảnh) → `rewriter.stream(request.payload())` → `rewritten`; `search_candidates` (trả cả ứng viên giữ, loại và điểm Jev); `plan_context` → `planner.stream` → `planned`. `rewrite`, `candidates`, `plan`, `prepare` giữ nguyên hành vi (gọi `run`) cho MCP `ask_data`.
- Client và LLM không bao giờ đưa SQL thô vào: SQL do server dựng từ plan đã ánh xạ về ID và đã kiểm tra; truy vấn chạy trong transaction chỉ đọc có timeout.
- Session và client (Qdrant, embedding, Jev) được tạo **bên trong** generator của stream bằng `get_session_factory()` (không dùng dependency `get_database` vì vòng đời không khớp với stream) và đóng trong `finally`, kể cả khi client ngắt kết nối giữa chừng. Generator đồng bộ, Starlette chạy từng bước trong threadpool. Kiểm tra connection và hội thoại dùng một session ngắn riêng trước khi stream. Lượt tiếp tục chọn cách nối không mở Qdrant, embedding hay Jev.
- Chỉ tầng pipeline commit: session truy vấn chỉ commit dataset sau khi truy vấn chạy thành công; session ghi lượt (riêng) commit khi mở lượt và khi kết thúc lượt.
- Thông báo lỗi gửi người dùng không chứa chi tiết nội bộ (UUID, stack trace); lỗi không mong đợi được ghi log và trả thông điệp chung.

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `TEXT2SQL_CHAT_MAX_ROWS_TO_LLM` | 50 | Số dòng (đã che) tối đa mỗi truy vấn gửi cho `AnalysisAgent`. Event `data` vẫn gửi đủ dòng cho client. |
| `TEXT2SQL_QUERY_MAX_ROWS`, `TEXT2SQL_QUERY_TIMEOUT_SECONDS` | 200, 15 | Trần dòng và timeout của truy vấn ([query-metric.md](query-metric.md)). |
| `TEXT2SQL_ASK_METRIC_MIN_SCORE`, `TEXT2SQL_FIELD_MIN_SCORE` | 0,6 | Ngưỡng Jev cho metric và trường. |

## Kiểm thử

- `tests/test_text2sql_chat_pipeline.py`: agent giả có `stream` phát `ReasoningDelta` rồi trả draft, embedding, index, Jev giả và database nguồn giả (không gọi LLM, OpenRouter hay Qdrant thật): thứ tự event luồng metric, luồng dataset thành công, `no_metric` chuyển sang dataset, `find_fields` không có kết quả, `cannot_answer`/`needs_clarification`, tên sai không retry và không lộ UUID, tên bảng ngắn trùng schema, `join_ambiguous` kèm `previously_used`, `join_not_declared`, bộ dựng từ chối nhân dòng, PII luôn che và cắt dòng cho LLM, lưu dataset chỉ sau khi chạy thành công và dùng lại ở lần hai, không lưu khi truy vấn lỗi, phân tích stream nhiều `token`, phân tích hỏng thì `error`, ngắt giữa chừng đóng client và session; `reasoning` luôn nằm giữa `step started` và `step done`/`skipped` của bước, nguồn `model` và `server`, nội dung server cho từng nhánh (Jev giữ/loại, chuyển sang dataset, tìm trường, ánh xạ và lỗi tên, nối `ok`/`ambiguous`/`not_declared`, nhân dòng, dùng lại hay tạo dataset, PII), không chứa UUID hay giá trị PII; agent lỗi giữa lúc suy luận và ngắt kết nối khi mô hình đang suy luận thì đóng stream của agent.
- `tests/test_text2sql_chat_pipeline.py` (thông tin cột và `done`): cột metric có `column_id`, nhãn, `data_type` chuẩn hóa, `format`/`unit` từ metric, cột kỳ thời gian `datetime`/`date`; cột dataset có và không có dictionary, `count` là `integer`, số thập phân vẫn là chuỗi; payload cho `AnalysisAgent` không có UUID; `done` mang giả định và thông điệp đã làm sạch UUID, câu hỏi làm rõ, lỗi không mong đợi chỉ có thông điệp chung; chuẩn hóa kiểu Postgres và kiểu giá trị Python; trường ẩn không đổi đầu ra MCP.
- `tests/test_text2sql_chat_route.py`: `TestClient` với pipeline giả: header, cú pháp SSE (kể cả `reasoning` có xuống dòng và dấu nháy, ghép `delta` theo `step`/`index`), lỗi đầu vào 422 và connection không tồn tại 404, connection tạm dừng 400 trước khi stream.
- `tests/test_text2sql_chat_conversation.py` (hội thoại, agent giả, SQLite): tạo hội thoại mới và ghi đủ dữ liệu lượt (bước kèm suy luận đã ghép, kết quả cắt theo `max_stored_rows`, `metric.name`/`kind`, `pii`, model, thời gian), event `turn` đầu stream và id trong `done`; không có `user_id` thì không lưu; lịch sử gọn được đưa vào context viết lại (đúng năm khóa, không có dòng dữ liệu, tối đa 6 lượt, câu trả lời ≤ 500 ký tự); `clarification_options` (chuẩn hóa, tối đa 4) trong `done`, lượt và lịch sử; lưu `join_not_declared`, `cannot_answer`, lỗi ở bước đầu và lỗi phân tích (`error_code`, `error_message` không ra API); ngắt kết nối đóng lượt `client_disconnected`; sai chủ sở hữu, khác connection, lượt trước sai trạng thái; chọn cách nối thành công không gọi viết lại/lập kế hoạch, signature lạ (422) và signature không còn trong đồ thị (409); câu hỏi gợi ý `history` và `metric_usage` có dữ liệu sau khi lượt được lưu; route kiểm tra các trường hội thoại trước khi stream (422/404/409) và chuyển `TurnRequest` cho pipeline.
- Đã chạy đầu-cuối trên PostgreSQL tạm (metadata migrate bằng Alembic, database nguồn tổng hợp `customers`/`orders`/`items`/`locations`/`weather`, URI mã hóa Fernet) với agent giả có kịch bản, gọi qua route và đọc stream: số liệu khớp tính tay cho luồng metric (doanh thu theo trạng thái), dataset (doanh thu, số đơn theo vùng, giữ đơn không có khách), khử trùng khi nối xuống `items`, PII che, từ chối nhân dòng, `not_declared`, `ambiguous`, dùng lại dataset.

## Giới hạn

- Lịch sử chỉ đi vào bước viết lại câu hỏi (dạng chữ, không có số liệu); câu nối tiếp mà câu viết lại không đủ ý thì các bước sau cũng không biết ngữ cảnh. Chất lượng ghép ngữ cảnh phụ thuộc mô hình; chưa kiểm với `openai/gpt-6-luna` thật.
- Chỉ tiếp tục được lượt `join_ambiguous`; trả lời làm rõ đi qua câu hỏi mới, không có trạng thái tiếp tục riêng. Chưa có "thử lại" (`retry_of`) từ route chat.
- `connection_id` và `user_id` do client gửi, **chưa xác thực**; `user_id` lọc tri thức riêng và làm chủ hội thoại. Như mọi API hiện tại, chỉ chạy trong môi trường tin cậy.
- Không có Text2SQL tự do: câu hỏi chỉ trả lời được bằng metric có sẵn hoặc dataset dựng từ trường đã mô tả và quan hệ đã khai báo.
- Độ trễ: tối đa bốn lần gọi LLM nối tiếp (viết lại, lập plan metric, lập plan dataset, phân tích) cộng truy hồi Qdrant, Jev và truy vấn nguồn; thường vài chục giây trước khi có token đầu tiên của phần phân tích.
- Giá trị lọc phải suy ra được từ mô tả cột; không có NER cho tên riêng.
