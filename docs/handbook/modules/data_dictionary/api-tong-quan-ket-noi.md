# API tổng quan từ điển của một kết nối

**Trạng thái:** đã triển khai. **Endpoint:** `GET /api/v1/database-connections/{connection_id}/dictionary-summary`.

## Mục đích

Liệt kê mọi bảng và view đã đồng bộ của một kết nối kèm trạng thái mô tả, để giao diện hiển thị danh sách bảng trong màn hình Từ điển mà không phải đọc từ điển từng bảng.

## Luồng xử lý hiện tại

1. Đọc kết nối theo `connection_id`; không có thì trả 404 `Không tìm thấy kết nối database được yêu cầu.`. Route đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng.
2. Đọc schema của kết nối, rồi đọc toàn bộ bảng của các schema đó, sắp theo tên, trong một truy vấn.
3. Đọc từ điển mức bảng theo danh sách bảng, cặp `(id cột, id bảng)` của mọi cột và danh sách cột đã có từ điển. Mỗi loại một truy vấn, không truy vấn theo từng bảng.
4. Không ghi gì vào database.

## Kết quả

| Trường | Ý nghĩa |
| --- | --- |
| `connection_id` | ID kết nối được yêu cầu. |
| `table_count`, `described_table_count` | Tổng số bảng và số bảng đã có từ điển mức bảng. |
| `schemas[]` | `schema_id`, `schema_name`, `tables[]`; schema theo thứ tự của module `database_connection`. |
| `tables[]` | `table_id`, `table_name`, `table_type`, `is_saved`, `display_name` (tên bảng khi chưa lưu), `layout` (`wide` khi chưa lưu), `column_count`, `described_column_count` (số cột đã có từ điển). |
