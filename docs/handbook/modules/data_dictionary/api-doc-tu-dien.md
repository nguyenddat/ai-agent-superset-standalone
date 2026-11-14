# API đọc từ điển của bảng

**Trạng thái:** đã triển khai. **Endpoint:** `GET /api/v1/tables/{table_id}/dictionary`.

## Mục đích

Trả về toàn bộ từ điển của một bảng đã đồng bộ: phần mô tả mức bảng, vai trò cột, grain thời gian, ánh xạ tổng hợp chỉ số và từ điển của mọi cột. Bảng hoặc cột chưa được lưu vẫn có kết quả, dùng giá trị mặc định suy ra từ metadata. Hai API lưu cũng trả về đúng cấu trúc này.

## Luồng xử lý hiện tại

1. Đọc `database_tables` theo `table_id`; không có thì trả 404 `Không tìm thấy bảng được yêu cầu.`. Route chưa có xác thực/phân quyền.
2. Đọc schema để lấy `connection_id`, `schema_name`; đọc các cột của bảng theo `ordinal_position`.
3. Đọc `table_dictionaries` theo `table_id` và các bản ghi con theo `table_dictionary_id`; đọc `column_dictionaries` theo danh sách cột cùng aggregation, synonym của chúng. Mỗi loại bản ghi đọc một truy vấn, không truy vấn theo từng cột.
4. Ghép kết quả: trường đã lưu lấy từ bản ghi từ điển, trường chưa lưu lấy mặc định ở dưới. `is_saved` cho biết bảng hoặc cột đã có bản ghi.
5. Không ghi gì vào database.

## Giá trị mặc định

| Trường | Bảng chưa lưu | Cột chưa lưu |
| --- | --- | --- |
| `display_name` | Tên bảng | Tên cột |
| `description` | Comment của bảng ở nguồn | Comment của cột ở nguồn |
| `layout` | `wide` | — |
| `temporal_kind` | — | `timestamp` nếu kiểu chứa `TIMESTAMP`/`DATETIME`; `date` nếu kiểu là `DATE` |
| `semantic_role` | — | Suy theo thứ tự bên dưới |
| Danh sách con, cờ | Rỗng, `false` | Rỗng, `false`; `is_primary_key` null |

`semantic_role` đã lưu khác null thì dùng giá trị đó. Nếu null (cột chưa lưu hoặc người dùng để trống), service suy theo thứ tự:

1. `key` nếu cột là khóa: `is_primary_key` đã lưu là `true`, hoặc có `referenced_column_id`. Khi `is_primary_key` chưa khai báo (null), cột cũng là khóa nếu là khóa chính ở nguồn hoặc tên có dạng `id`, `..._id`, `key`, `..._key` (không phân biệt hoa thường).
2. `row_kind` nếu cột được gán vai trò `row_kind` ở mức bảng.
3. `time` nếu `temporal_kind` khác null.
4. `measure` nếu kiểu dữ liệu là số (`INT`, `SMALLINT`, `BIGINT`, `NUMERIC`, `DECIMAL`, `REAL`, `FLOAT`, `DOUBLE`, `MONEY`).
5. `dimension` cho các trường hợp còn lại.

Quy tắc theo tên chỉ là gợi ý: đặt `is_primary_key = false` để bỏ suy luận khóa cho cột, hoặc khai báo `semantic_role` trực tiếp.

## Kết quả

`TableDictionaryOut` gồm thông tin bảng (`table_id`, `connection_id`, `schema_name`, `table_name`, `table_type`), các trường mô tả, `indicator_catalog` (bảng danh mục chỉ số đã liên kết, có `table_id`, tên và `display_name`), `column_roles` (kèm `column_name`), `time_grains`, `indicator_aggregations` và `columns`. `semantic_role` là vai trò đang áp dụng; `semantic_role_is_default` là `true` khi vai trò được suy mặc định (chưa lưu hoặc lưu null), để giao diện gửi lại null thay vì cố định giá trị suy ra. Mỗi cột có thông tin vật lý (`name`, `data_type`, `is_nullable`, `source_is_primary_key`, `default_value`) cùng các trường từ điển; `referenced_column` trả về schema, bảng và tên cột được tham chiếu.
