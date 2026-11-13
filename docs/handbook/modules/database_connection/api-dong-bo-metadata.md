# API đồng bộ schema, bảng và cột

**Trạng thái:** dự kiến, chưa có route hay tác vụ nền. **Method dự kiến:** `POST`. Đường dẫn và schema JSON chưa chốt.

## Mục đích

Lấy metadata từ database nguồn đã đăng ký và cập nhật snapshot `database_schemas → database_tables → database_columns` trong metadata database của ứng dụng. Không chạy DDL và không sửa dữ liệu của nguồn.

## Luồng xử lý dự kiến

1. Kiểm tra quyền, trạng thái connection và giải mã URI trong service; không ghi URI rõ vào log.
2. Mở kết nối nguồn, đọc schema, table/view và column bằng dialect/driver tương ứng; đóng tài nguyên nguồn sau khi đọc.
3. Đối chiếu theo khóa tự nhiên `(connection_id, schema_name)`, `(schema_id, table_name)`, `(table_id, column_name)` để cập nhật bản ghi hiện có và thêm bản ghi mới. Giữ ID của bản ghi còn tồn tại.
4. Cập nhật `last_synced_at` của schema và table đã quan sát. Caller commit metadata một lần khi toàn bộ snapshot hợp lệ; lỗi thì rollback.
5. Trả số schema, table/view và column đã quan sát cùng thời điểm đồng bộ.

## Lưu ý thiết kế

Chưa có cột đánh dấu metadata đã biến mất khỏi nguồn. Bản đồng bộ đầu tiên không được tự xóa bản ghi cũ cho đến khi chốt quy tắc phụ thuộc dataset và lịch sử; muốn xóa hoặc đánh dấu stale cần migration/thiết kế bổ sung. Với nguồn lớn, cần chốt giới hạn số bảng, timeout và việc chạy tác vụ nền trước khi triển khai.
