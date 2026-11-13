# API đồng bộ schema, bảng và cột

**Trạng thái:** đã triển khai đồng bộ trực tiếp trong request; chưa có tác vụ nền. **Endpoint:** `POST /api/v1/database-connections/{id}/sync`.

## Mục đích

Lấy metadata từ database nguồn đã đăng ký và cập nhật snapshot `database_schemas → database_tables → database_columns` trong metadata database của ứng dụng. Không chạy DDL và không sửa dữ liệu của nguồn.

## Luồng xử lý hiện tại

1. Kiểm tra connection tồn tại và đang hoạt động, rồi giải mã URI trong service; route chưa có xác thực/phân quyền.
2. Mở kết nối nguồn, đọc schema, table/view và column bằng dialect/driver tương ứng; đóng tài nguyên nguồn sau khi đọc.
3. Đối chiếu theo khóa tự nhiên `(connection_id, schema_name)`, `(schema_id, table_name)`, `(table_id, column_name)` để cập nhật bản ghi hiện có và thêm bản ghi mới. Giữ ID của bản ghi còn tồn tại.
4. Cập nhật `last_synced_at` của schema và table đã quan sát. Caller commit metadata một lần khi toàn bộ snapshot hợp lệ; lỗi thì rollback.
5. Trả `status: "completed"`, `last_synced_at`, `schema_count`, `table_count`, `column_count`.

## Lưu ý thiết kế

Chưa có cột đánh dấu metadata đã biến mất khỏi nguồn; đồng bộ không xóa bản ghi cũ. Service bỏ qua schema hệ thống `information_schema` và các schema bắt đầu bằng `pg_`, đọc bảng, view và materialized view. Với nguồn lớn, cần bổ sung giới hạn số bảng, timeout toàn thao tác và tác vụ nền.
