# MCP server

**Trạng thái: đã triển khai.** `backend/mcp_server/` tạo MCP server bằng Python SDK chính thức (`mcp` 2.x, lớp `MCPServer`). Có 15 tool: 10 tool tìm và xem tri thức dữ liệu, `find_fields` và `plan_join` ([tìm trường và nối bảng](modules/text2sql/find-fields-join.md)), `query_dataset` chạy truy vấn nhiều bảng, `query_metric` chạy metric trên database nguồn, và `ask_data` chạy luồng hỏi đáp cố định ([ask-flow](modules/text2sql/ask-flow.md)); chưa có resource và prompt.

## Cấu trúc

Thư mục chia theo khái niệm của MCP; mỗi thư mục có một hàm `register_*` được `server.py` gọi khi tạo server.

```text
backend/mcp_server/
├── __main__.py        dòng lệnh: stdio hoặc streamable-http
├── server.py          tạo MCPServer, nạp mọi model, gọi register_tools / register_resources / register_prompts
├── tools/
│   ├── __init__.py    register_tools: gọi hàm đăng ký của từng file
│   ├── common.py      kiểu tham số dùng chung, dựng dịch vụ, ánh xạ lỗi, SearchHit/SearchOut
│   ├── table.py       search_tables
│   ├── column.py      search_columns
│   ├── metric.py      search_metrics, get_metric
│   ├── glossary.py    search_glossary_terms, get_glossary_term
│   ├── expert_rule.py search_expert_rules, get_expert_rule
│   ├── own_knowledge.py  search_own_knowledge, get_own_knowledge
│   ├── query.py       query_metric
│   ├── ask.py         ask_data
│   ├── join.py        find_fields, plan_join
│   └── dataset.py     query_dataset
├── resources/         register_resources (chưa có resource)
└── prompts/           register_prompts (chưa có prompt)
```

Thêm một khả năng mới: tạo một file trong thư mục tương ứng, định nghĩa hàm đăng ký và gọi nó từ `register_*` của thư mục đó. Đặt tên file theo nghiệp vụ, không trùng tên hàm tool (để `patch` trong test không bị che). Tool chỉ kiểm tra tham số và gọi dịch vụ của module `text2sql`; logic nằm ở đó, không nằm trong tool.

## Chạy

Khi stack chạy bằng `compose.yaml`, cho MCP host khởi động server bằng stdio bên trong container `backend`:

```powershell
docker exec -i ai-agent-superset-standalone-backend-1 superset-ai-mcp
```

Cấu hình MCP host với lệnh `docker` và các tham số `exec`, `-i`, `ai-agent-superset-standalone-backend-1`, `superset-ai-mcp`; không cần truyền biến môi trường vì container đã có đủ cấu hình. Không chạy `uv run superset-ai-mcp` trên máy host cho stack này: connection nguồn đăng ký trong container dùng tên dịch vụ Docker (ví dụ `warehouse-db:5432`), máy host không phân giải được nên mọi truy vấn báo "Không thể thực hiện truy vấn trên database nguồn"; `.env` ở host cũng thiếu các biến mô hình (`OPENROUTER_MODEL`, `TEXT2SQL_EMBEDDING_MODEL`, `QDRANT_URL`...) mà compose cấp cho container.

Chỉ dùng `uv run superset-ai-mcp` từ gốc repository khi backend và database nguồn đều chạy trực tiếp trên máy. Không ghi thông tin thường ra stdout vì stdout là luồng giao thức.

Để thử Streamable HTTP trên cùng máy:

```powershell
uv run superset-ai-mcp --transport streamable-http --host 127.0.0.1 --port 8001
```

Endpoint là `http://127.0.0.1:8001/mcp`. Chế độ HTTP chỉ chấp nhận địa chỉ loopback vì chưa có xác thực cho MCP. Không mở cổng ra mạng ngoài.

Server chạy độc lập với FastAPI nhưng dùng cùng cấu hình `.env`. Bắt tay giao thức và `tools/list` không cần dịch vụ nào; gọi tool cần `DATABASE_URL` (metadata database), `QDRANT_URL` và `OPENROUTER_API_KEY` (embedding, và Jev khi `rerank=true`). Chỉ mục Qdrant được `ingestion-worker` giữ cập nhật, xem [worker và hàng đợi](modules/text2sql/worker-ingestion.md).

## Luồng dùng

```text
search_*  →  AI chọn một mục  →  get_*  (metric, thuật ngữ, quy tắc, tri thức riêng)
search_tables / search_columns  →  kết quả đã gồm mô tả có cấu trúc, không cần get_*
ask_data trả no_metric  →  find_fields  →  plan_join  →  query_dataset
```

Mọi tool đều nhận `connection_id`, và chỉ trả mục thuộc đúng connection đó: ID của connection khác cho kết quả "không tìm thấy" thay vì lộ dữ liệu.

## Tool tìm kiếm

Mỗi tool tìm trong một loại, bằng truy hồi hybrid dense + BM25 (khớp không dấu) trên đúng topic của [chỉ mục](modules/text2sql/embed-retrieve.md).

| Tool | Tìm | Trả về mỗi kết quả | `k` mặc định, tối đa |
| --- | --- | --- | --- |
| `search_tables` | Bảng | Mô tả bảng và cột rút gọn (xem dưới) | 3, 5 |
| `search_columns` | Cột | **Toàn bộ mô tả có cấu trúc** của cột và bảng chứa nó | 5, 10 |
| `search_metrics` | Metric (kết hợp tín hiệu bảng, cột) | Tên, nhãn, mô tả, bảng, điểm | 5, 10 |
| `search_glossary_terms` | Thuật ngữ đã duyệt | `id`, tên, văn bản tóm tắt, điểm | 5, 10 |
| `search_expert_rules` | Quy tắc đang áp dụng | `id`, tên, văn bản tóm tắt, điểm | 5, 10 |
| `search_own_knowledge` | Cách hiểu riêng của một người dùng | `id`, tên, văn bản tóm tắt, điểm | 5, 10 |

Tham số chung: `connection_id` (UUID, bắt buộc), `question` (1 đến 2000 ký tự, bắt buộc, rỗng thì lỗi), `k`, `rerank` (boolean, mặc định `false`). `search_own_knowledge` bắt buộc thêm `user_id`.

**Kết quả `search_tables`** là bản rút gọn của `TableDictionaryOut`. Mỗi bảng gồm `table_id`, tên kỹ thuật (`schema.bảng`), tên hiển thị, mô tả, grain, loại bảng, cờ PII, điểm và danh sách cột. Mỗi cột chỉ giữ `column_id`, tên, tên hiển thị, kiểu, vai trò ngữ nghĩa, và (khi có) mô tả, đơn vị, từ đồng nghĩa, cột tham chiếu dạng `bảng.cột`, cờ PII; trường rỗng bị lược bỏ. Bỏ hẳn các trường ghi sổ (thời gian cập nhật, cờ đã lưu, vị trí cột, nullable, giá trị mặc định, phép tổng hợp, vai trò cột, độ chi tiết thời gian của bảng). Muốn xem đủ thì dùng API data dictionary. `search_columns` vẫn trả `ColumnDictionaryOut` kèm tham chiếu bảng.

**Tín hiệu mức khớp.** Mọi tool `search_*` trả thêm `match` và `note`: `none` (không có kết quả nào), `weak` (điểm xếp hạng lại của kết quả đầu dưới 0,2, nhiều khả năng không có mục nào khớp), `ok`, hoặc `unverified` (không rerank nên không đánh giá được; kết quả luôn là top-k gần nhất). Ngưỡng 0,2 là heuristic chưa hiệu chỉnh trên dữ liệu thật. Muốn có tín hiệu `weak`/`ok` thì gọi với `rerank=true`.

**Kết quả của ba tool còn lại** (`SearchOut`) là danh sách `{id, name, summary, table_id, score, rerank_score}`, kèm `reranked`, `rerank_warning`, `match` và `note`. `summary` là văn bản đã lập chỉ mục (đủ để chọn mục); `id` dùng cho tool `get_*` tương ứng. Chỉ mục cập nhật gần thời gian thực nhưng không tức thì, nên `get_*` mới là nguồn chính xác cuối cùng.

Tool tìm kiếm luôn trả đủ `k` kết quả gần nhất có thể, kể cả khi không có mục nào thật sự phù hợp; chưa có ngưỡng điểm. Khi cần phân biệt, đặt `rerank=true` và dùng `rerank_score` (0 đến 1).

## Tool xem chi tiết

Chỉ có cho metric, thuật ngữ, quy tắc và tri thức riêng. Mọi tool nhận `connection_id` và ID của mục; không có `rerank`.

| Tool | Tham số thêm | Trả về |
| --- | --- | --- |
| `get_metric` | `metric_id` | Biểu thức, định dạng, tiền tệ, loại, cảnh báo khi dùng, nguồn, bảng, các cột mà biểu thức tham chiếu |
| `get_glossary_term` | `term_id` | Tên, nhóm, định nghĩa của bản đang phục vụ, từ đồng nghĩa, liên kết tới bảng, cột, metric (có tên) |
| `get_expert_rule` | `rule_id` | Bảng áp dụng, mô tả, điều kiện có cấu trúc kèm câu đọc được, ngoại lệ, câu hỏi ví dụ, thuật ngữ và metric liên quan |
| `get_own_knowledge` | `user_id`, `entry_id` | Tên, loại, định nghĩa, bảng ngữ cảnh, trạng thái duyệt, phiên bản |

Chỉ mục "còn khả dụng" được kiểm lại khi xem chi tiết: thuật ngữ chưa duyệt hoặc đã thu hồi, quy tắc không còn hiệu lực, metric đã tắt hoặc thuộc dataset ảo, và tri thức riêng đã có bản hệ thống thay thế đều trả "không tìm thấy mục này hoặc mục không còn khả dụng".

## Tool chạy metric (`query_metric`)

Chạy một metric đã chọn trên database nguồn và trả số liệu. **AI không viết SQL**: gửi plan (`metric_id`, `group_by`, `time`, `filters`, `order_by`, `limit`), server tự dựng đúng một câu `SELECT` tổng hợp trên bảng của metric, bind mọi giá trị, rồi chạy trong transaction chỉ đọc có timeout và giới hạn số dòng.

| Tham số | Bắt buộc | Ý nghĩa |
| --- | --- | --- |
| `connection_id`, `metric_id` | có | Connection và metric (từ `search_metrics`). |
| `group_by` | không | Tối đa 5 ID cột (từ `search_tables`, `search_columns`). |
| `time` | không | `{column_id, start, end, granularity}`; khoảng `[start, end)` và/hoặc nhóm theo ngày, tuần, tháng, quý, năm. |
| `filters` | không | Tối đa 10 điều kiện `{column_id, operator, value}` nối bằng AND. |
| `order_by` | không | `"metric"`, `"time"` hoặc cột trong `group_by`. |
| `limit` | không | Mặc định 100, bị cắt bởi `TEXT2SQL_QUERY_MAX_ROWS`. |

Quy trình gợi ý: `search_metrics`, `get_metric`, `search_columns` hoặc `search_tables` để lấy ID cột, rồi `query_metric`.

Kết quả: `metric` (tên, nhãn, định dạng, cảnh báo khi dùng), `columns` (tên, vai trò chiều, thời gian hoặc metric), `rows`, `row_count`, `truncated`, `limit`, `sql` và `parameters` đã chạy, `pii` và `elapsed_ms`. `Decimal` trả dạng chuỗi; `null` nghĩa là không có dữ liệu, không phải 0.

**Dữ liệu cá nhân** được xử lý trước khi trả về: giá trị trong cột đánh dấu PII, và số điện thoại, email, CCCD/CMND, thẻ, IP phát hiện được ở mọi cột chiều, được thay bằng placeholder nhất quán (`<PII_1>`, `<VN_PHONE_NUMBER_1>`...). Không lọc được theo cột PII. Nhóm theo cột PII sẽ **hỏi xác nhận người dùng** (MCP elicitation, qua cơ chế `Resolve` của SDK nên chạy cả với HTTP không trạng thái): từ chối hoặc hủy thì truy vấn không chạy; client không hỗ trợ elicitation vẫn nhận dữ liệu đã che, với `pii.confirmation = "not_supported"`. Đây là sự đồng ý của người dùng, còn rào chắn thật là việc che dữ liệu luôn chạy.

Chi tiết cách biên dịch, kiểm tra biểu thức, bảo đảm chỉ đọc và transaction, danh sách loại PII và giới hạn (như không nhận dạng tên người trong văn bản tự do): [Chạy metric trên database nguồn](modules/text2sql/query-metric.md).

## Tool truy vấn nhiều bảng (`query_dataset`)

Dùng khi `ask_data` trả `no_metric`, theo quy trình `find_fields` → `plan_join` → `query_dataset`. **AI không viết SQL hay `FROM`**: server tự tính phương án nối từ quan hệ khai báo trong data dictionary, lưu thành dataset dùng lại, dựng một câu `SELECT` và chạy chỉ đọc.

| Tham số | Bắt buộc | Ý nghĩa |
| --- | --- | --- |
| `connection_id` | có | Connection nguồn. |
| `table_ids` | có | 1 đến 8 ID bảng cần nối. |
| `plan` | có | `DatasetQueryPlan`: `select` (`column_id` kèm `aggregation`, hoặc `expression` viết cột dạng `ten_bang.ten_cot`), `group_by`, `time`, `filters` (`placement` `where` hoặc `join`), `order_by`, `limit`. Không có `from_sql`. |
| `root_table_id` | không | Bảng gốc theo câu hỏi: "doanh thu theo khách" gốc là đơn hàng, "khách chưa có đơn" gốc là khách hàng. Bỏ trống thì chọn bảng ít làm nhân dòng nhất. |
| `edge_ids` | không | Phương án đã chọn khi lần gọi trước trả `ambiguous`. |

Kết quả `DatasetQueryOut`: `status` (`ok`, `ambiguous`, `not_declared`), `join`, `options`, `dataset` (`dataset_id`, `created`, `selected_column_ids`, `added_column_ids`), `result` (`DatasetResult`, có `sql`, `warnings` nhân dòng và `pii`) và `message`. `ambiguous` và `not_declared` là kết quả có cấu trúc, không phải lỗi; với `not_declared`, agent báo người dùng bổ sung khai báo quan hệ trong data dictionary, không tự nối. Dữ liệu cá nhân xử lý như `query_metric` (che, hỏi xác nhận khi chọn cột PII). Chi tiết: [tìm trường, nối bảng và `query_dataset`](modules/text2sql/find-fields-join.md), [dựng truy vấn nhiều bảng](modules/text2sql/build-query.md), [dataset truy vấn](modules/text2sql/query-datasets.md).

## Xếp hạng lại (`rerank`)

Mọi tool tìm kiếm có tham số `rerank` (mặc định `false`). Khi `true`, các ứng viên được chấm lại bằng Jev qua OpenRouter, với cách hỏi riêng cho từng loại (bảng, cột, metric, thuật ngữ, quy tắc, tri thức riêng). Nếu Jev lỗi hoặc quá thời gian, tool **không thất bại**: trả thứ tự gốc với `reranked=false` và `rerank_warning` ghi mã lỗi. Client nên xem `rerank_warning` thay vì giả định đã rerank. Chi tiết cách chấm, chi phí và cấu hình `TEXT2SQL_RERANK_*` ở [embed và retrieve](modules/text2sql/embed-retrieve.md).

## Lỗi

- Lỗi nghiệp vụ (connection không tồn tại, mục không tìm thấy, chưa đồng bộ index, Qdrant, OpenRouter hoặc database nguồn không dùng được, truy vấn quá giờ, plan không hợp lệ) trả kết quả lỗi của MCP kèm thông điệp an toàn của lỗi đó (dùng `ToolError`, server chỉ ghi INFO).
- Lỗi bất ngờ chỉ trả thông điệp chung, không lộ chi tiết.
- Tham số sai (UUID hỏng, `k` ngoài khoảng, `rerank` không phải boolean, thiếu `user_id`) bị từ chối trước khi truy hồi.

## Giới hạn hiện tại về định danh

`connection_id` và `user_id` đều do client truyền vào; server **chưa xác thực** ai đang gọi. Hệ quả:

- Ai gọi được tool đều đọc được mọi connection khi biết ID, và với `query_metric`, `query_dataset` là **chạy được truy vấn trên database nguồn** của connection đó (truy vấn chỉ đọc, giới hạn tài nguyên, dữ liệu cá nhân đã che).
- `user_id` là ranh giới riêng tư duy nhất của tri thức riêng. Nó chỉ có ý nghĩa khi runtime tin cậy của agent tự gắn `user_id` từ phiên đã đăng nhập, không để mô hình tự điền. Một client không tin cậy có thể đọc tri thức riêng của người dùng khác bằng cách truyền `user_id` khác.

Vì vậy chỉ chạy MCP trên máy tin cậy (HTTP bị giới hạn loopback). Việc lấy connection và người dùng từ danh tính đã xác thực, thay vì từ tham số, là việc cần làm trước khi dùng cho nhiều người dùng.

## Kiểm tra

- `tests/test_mcp_dataset_tool.py`: `query_dataset` trên catalog SQLite: `ambiguous`/`not_declared` có cấu trúc, tạo rồi dùng lại dataset và chỉ thêm cột mới, cột lọc không ghi vào dataset, hỏi xác nhận PII, không nhận `from_sql`.
- `tests/test_mcp_server.py`: bắt tay trong bộ nhớ và qua stdio, đủ 15 tool, lược đồ tham số (giới hạn `k`, `rerank` mặc định `false`, `user_id` chỉ ở tool tri thức riêng), truyền tham số xuống đúng hàm, ghép kết quả tìm kiếm với mô tả bảng/cột, xử lý lỗi và từ chối tham số sai.
- `tests/test_text2sql_topics.py`: tìm theo topic (lọc `user_id`, rerank, đường lui) và các hàm chi tiết (đúng connection, đúng người dùng, mục không còn khả dụng).
- `tests/test_text2sql_rerank.py`, `tests/test_text2sql_qdrant.py`: client Jev và tìm kiếm Qdrant, trong đó các test tích hợp cần `QDRANT_TEST_URL`.
- `tests/test_text2sql_query.py`, `tests/test_text2sql_pii.py`, `tests/test_text2sql_query_pg.py`: biên dịch và kiểm tra biểu thức, che PII, và chạy thật trên PostgreSQL (cần `POSTGRES_TEST_URL`); xem [chạy metric](modules/text2sql/query-metric.md).
- `tests/test_entrypoints.py`: tiến trình MCP và worker tự nạp đủ model khi chạy riêng.

Các test này không gọi dịch vụ ngoài trừ các test tích hợp Qdrant khi được bật.
