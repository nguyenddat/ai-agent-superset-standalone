# Dataset truy vấn (lưu định nghĩa join dùng lại)

**Trạng thái:** lớp lưu trữ **đã triển khai** (model `QueryDataset`, migration `7e4c1a9b5d32`, `DatasetStore` ở `backend/modules/text2sql/dataset/store.py`). MCP tool `query_dataset` dùng lớp này sau khi truy vấn chạy thành công (tạo hoặc dùng lại dataset, thêm cột được chọn, rồi commit; lỗi biên dịch, connection tạm dừng, timeout hay lỗi SQL thì không ghi gì); quy tắc chọn cột ghi vào dataset nằm ở [find-fields-join.md](find-fields-join.md#chạy-truy-vấn-nhiều-bảng-query_dataset). Chưa có API HTTP.

## Mục đích

Sau khi [`plan_join`](find-fields-join.md) trả một `JoinOption`, server lưu **định nghĩa join** (không kèm cột select) thành một dataset, theo cách của dataset Superset. Gặp lại cùng cách nối thì dùng lại dataset cũ và chỉ thêm cột vào danh sách select, thay vì tạo dataset mới cho mỗi câu hỏi. Không tạo view hay bảng nào ở database nguồn; định nghĩa chỉ nằm trong metadata DB của ứng dụng.

## Bảng `technical.text2sql_query_datasets`

| Cột | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id`, `created_at`, `updated_at` | UUID, timestamptz | Kế thừa `BaseModel`. |
| `connection_id` | UUID, FK `database_connections` `ON DELETE CASCADE`, có index | Connection sở hữu dataset. |
| `signature` | varchar(64) | `JoinOption.signature`: băm tập cạnh, không phụ thuộc thứ tự bảng. |
| `root_table_id` | UUID, FK `database_tables` `ON DELETE CASCADE` | Bảng gốc của cây `LEFT JOIN`. |
| `table_ids` | JSON, danh sách UUID dạng chuỗi | Các bảng trong join. |
| `edge_ids` | JSON, danh sách UUID dạng chuỗi | Các cạnh (ID cột khóa ngoại) đã dùng. |
| `from_sql` | text | `FROM ... LEFT JOIN ... ON ...` do `plan_join` dựng, không có cột select. |
| `selected_column_ids` | JSON, danh sách UUID dạng chuỗi, có thứ tự | Cột đã chọn cho dataset; chỉ thêm, không bớt. |

**Khóa duy nhất:** `(connection_id, signature, root_table_id)`, tên `uq_text2sql_query_datasets_connection_id`. Cùng tập cạnh nhưng gốc khác thì `LEFT JOIN` cho kết quả khác nghĩa (giữ dòng của bảng khác), nên là hai dataset riêng.

Xóa connection hoặc xóa bảng gốc khỏi metadata thì dataset bị xóa theo (cascade ở database). Bảng không phải gốc hay cột đã chọn bị xóa sau đó không tự cập nhật `table_ids`/`selected_column_ids`; bước dựng SQL phải đối chiếu lại metadata trước khi dùng.

## `DatasetStore(session)`

Service nhận session và **không commit**; caller quyết định commit (cùng quy ước repository).

- `get_or_create(connection_id, option) -> (QueryDataset, created)`: tìm theo khóa duy nhất; chưa có thì thêm trong savepoint (`begin_nested`). Nếu tiến trình khác vừa tạo cùng khóa, `IntegrityError` được bắt, savepoint rollback và dataset đã có được đọc lại, trả `created=False`.
- `add_columns(dataset, column_ids) -> ColumnAddition`: khóa dòng dataset (`SELECT ... FOR UPDATE`, đọc lại giá trị mới nhất) rồi thêm cột. `added` là đúng các cột thực sự được thêm; `warning` khác `None` khi chạm trần cột.
- `get(connection_id, dataset_id)`: không thấy hoặc thuộc connection khác thì lỗi `text2sql_entity_not_found`.
- `list(connection_id, limit=50)`: dataset của connection, mới cập nhật trước; `limit` bị kẹp trong khoảng 1–200.

## Quy tắc append-only của cột

- Chỉ thêm, không xóa hay đổi thứ tự cột đã có; cột mới nối vào cuối theo thứ tự yêu cầu.
- Khử trùng: cột đã có trong dataset hoặc lặp lại trong cùng yêu cầu bị bỏ qua (không lỗi).
- Mỗi cột mới phải tồn tại và thuộc một trong `table_ids` của dataset; nếu không, cả yêu cầu bị từ chối với `text2sql_invalid_request`, nêu ID cột không hợp lệ, không cột nào được thêm.
- Trần **200 cột** mỗi dataset. Yêu cầu làm vượt trần không ghi thêm cột nào và trả cảnh báo thay vì lỗi; `query_dataset` vẫn chạy truy vấn và đưa cảnh báo vào `message` của kết quả (dataset chỉ là bản ghi để dùng lại, không giới hạn cột được truy vấn).
- Danh sách mới được gán lại vào thuộc tính (không sửa tại chỗ) để SQLAlchemy ghi nhận thay đổi của cột JSON.

## Giới hạn hiện tại

- Không có API xóa dataset hay bỏ cột; dataset chỉ mất khi connection hoặc bảng gốc bị xóa.
- `from_sql` là bản chụp lúc tạo; đổi quan hệ trong data dictionary không sửa dataset cũ mà sinh `signature` mới, tức dataset mới.
- Trên SQLite (dùng cho test), khóa ngoại sang bảng ở schema chính không được tạo vì schema `technical` là database đính kèm; cascade chỉ có hiệu lực trên PostgreSQL.
