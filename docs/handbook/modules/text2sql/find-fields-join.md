# Tìm trường và nối bảng (`find_fields`, `plan_join`)

**Trạng thái:** `find_fields`, `plan_join` và `query_dataset` **đã triển khai** (MCP tool, mã ở `backend/modules/text2sql/dataset/`: `field_service.py`, `join_graph.py`, `join_service.py`, `join_schemas.py` và phần dataset). Cập nhật 2026-11-16.

Mục đích: khi chưa có metric phù hợp, agent xác định các trường thông tin nằm ở bảng nào, chọn bảng cần nối, rồi để server tính cách nối. Server không suy đoán quan hệ.

## `find_fields(connection_id, question)`

- Tìm cột bằng hybrid dense + BM25, xếp hạng lại bằng Jev, chỉ giữ cột có điểm từ `TEXT2SQL_FIELD_MIN_SCORE` (mặc định 0,6, do người dùng chọn, chưa hiệu chỉnh bằng dữ liệu thật).
- Kết quả nhóm theo bảng (bảng có cột điểm cao nhất đứng trước): `table_id`, tên, mô tả, grain, và các cột (`column_id`, kiểu, vai trò ngữ nghĩa, mô tả, đơn vị, cờ PII, điểm).
- Không cột nào qua ngưỡng thì `match=none` kèm `note` yêu cầu hỏi lại người dùng. Nếu Jev lỗi, trả cột chưa lọc với `match=unverified`.

## `plan_join(connection_id, table_ids, edge_ids?, root_table_id?)`

Đồ thị: nút là bảng, cạnh là quan hệ **đã khai báo** trong data dictionary (`referenced_column` của cột). Không nối theo tên cột giống nhau. Cạnh được định danh bằng ID cột khóa ngoại (`edge_id`). Cột được tham chiếu là khóa chính hoặc duy nhất thì quan hệ là nhiều-một.

- **Thuật toán:** bảng đầu tiên là gốc của cây; mỗi bảng còn lại nối vào cây bằng đường ngắn nhất (BFS) qua các bảng trung gian (xấp xỉ cây Steiner). Mọi đường ngắn nhất ngang nhau đều được giữ, tối đa 4 phương án.
- **Bảng gốc:** tham số `root_table_id` (agent chọn theo grain của câu hỏi: "doanh thu theo khách" gốc là đơn hàng, "khách chưa có đơn" gốc là khách hàng); bỏ trống thì chọn bảng ít làm nhân dòng nhất. Mọi bảng còn lại `LEFT JOIN` từ gốc ra ngoài; không có RIGHT JOIN vì chỉ là đổi gốc.
- **`ok`:** một phương án. Kết quả có `from_sql` (`FROM ... LEFT JOIN ... ON ...`, không có cột select, định danh được trích dẫn), `signature` (băm tập cạnh, không phụ thuộc thứ tự bảng), các bước nối và `warnings`.
- **`ambiguous`:** nhiều cách nối (ví dụ hai cột cùng tham chiếu một bảng như nơi đi và nơi đến). Agent chọn một phương án và gọi lại với `edge_ids` của phương án đó.
- **`not_declared`:** thiếu quan hệ khai báo. `message` nêu các nhóm bảng chưa nối được và yêu cầu bổ sung data dictionary; agent phải báo lại người dùng, không tự nối.
- **Cảnh báo nhân dòng:** gốc được chọn để ít nhân dòng nhất; bước nối đi từ phía "một" sang phía "nhiều" (hoặc qua cột không duy nhất) bị đánh dấu `multiplies_rows` và có cảnh báo vì SUM hoặc COUNT có thể cộng trùng.

## Chạy truy vấn nhiều bảng (`query_dataset`)

**Đã triển khai** (`backend/mcp_server/tools/dataset.py`). Quy trình của agent khi `ask_data` trả `no_metric`: `find_fields` → `plan_join` → `query_dataset`.

- **Tham số:** `connection_id`, `table_ids` (1 đến 8), `root_table_id` (tùy chọn), `edge_ids` (tùy chọn, chọn phương án khi `ambiguous`) và `plan` (`DatasetQueryPlan`, xem [dựng truy vấn nhiều bảng](build-query.md)). Client **không bao giờ** gửi `from_sql`: server tự gọi `JoinService.plan` với cùng tham số; `plan` có `extra="forbid"` nên `plan.from_sql` bị từ chối, còn tham số thừa ở cấp ngoài bị bỏ qua.
- **`ambiguous` / `not_declared`:** trả kết quả có cấu trúc (không phải lỗi) với `status`, `options` (khi `ambiguous`) và `message` tiếng Việt; `not_declared` nói rõ cần bổ sung khai báo quan hệ trong data dictionary và agent không được tự nối bảng. Không ghi dataset, không chạy truy vấn.
- **`ok`:** biên dịch bằng `DatasetQueryService.prepare` (lỗi plan trả `ToolError`, chưa ghi gì), rồi chạy chỉ đọc, và chỉ khi truy vấn thành công mới `DatasetStore.get_or_create`, `add_columns` và commit (truy vấn lỗi, timeout hoặc connection tạm dừng thì không ghi gì). Cùng cách nối (cùng `signature` và bảng gốc) thì dùng lại dataset cũ, `created=false`, và chỉ thêm cột mới; xem [dataset truy vấn](query-datasets.md).
- **PII:** giống `query_metric`: kết quả có cột PII thì hỏi xác nhận bằng elicitation trước khi chạy (từ chối hoặc hủy thì không ghi dataset, không chạy); client không hỗ trợ elicitation vẫn nhận dữ liệu đã che với `pii.confirmation = "not_supported"`.
- **Kết quả `DatasetQueryOut`:** `status` (`ok`, `ambiguous`, `not_declared`), `join` (`JoinOption` đã dùng khi `ok`), `options`, `dataset` (`dataset_id`, `created`, `selected_column_ids` là toàn bộ cột của dataset sau lần gọi, `added_column_ids` là cột vừa thêm), `result` (`DatasetResult`) và `message`.

**Cột nào được ghi vào dataset** (`dataset/selection.py`): cột thực sự xuất hiện trong kết quả, theo thứ tự: `column_id` của mục `select`, các cột tham chiếu trong `expression` (đọc bằng cùng bộ phân tích `parse_dataset_expression`, ánh xạ `bang.cot` về ID cột trong các bảng của phương án nối), các cột `group_by` (luôn được trả về) và cột `time` khi có `granularity` (cột kỳ). Cột chỉ dùng để lọc (`filters`) hoặc chỉ làm khoảng thời gian không được ghi, vì dataset mô tả các trường người dùng xem, còn điều kiện lọc thuộc từng câu hỏi.

## Giới hạn

- Quan hệ chưa khai báo thì không nối được, kể cả khi hai cột trùng tên.
- Tối đa 8 bảng mỗi lần. Chỉ nối bằng `LEFT JOIN` từ gốc ra ngoài.
- Chưa kiểm tra bản số của quan hệ nhiều-nhiều; cạnh không có khóa duy nhất ở phía được tham chiếu luôn bị coi là nhân dòng.
