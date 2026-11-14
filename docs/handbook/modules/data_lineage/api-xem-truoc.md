# Xem trước SQL và đọc SQL view

**Trạng thái:** đã triển khai. Các đường dẫn có tiền tố `/api/v1/data-lineage/connections/{connection_id}`.

`POST /preview` nhận `target_table_id`, `sql_text`; trả `source_table_ids`, `dependencies[]` (`source_column_id`, `target_column_id`, `role`), `warnings[]` và `complete`. Đây là đề xuất chưa ghi database. Chỉ nhận một câu `SELECT` PostgreSQL; không thực thi SQL. Nguồn có thể là nhiều bảng trực tiếp trong `FROM`/`JOIN`; tên bảng không có schema phải xác định duy nhất trong phạm vi kết nối. Cột không có tên bảng phải xác định duy nhất giữa các nguồn.

Parser đề xuất `value` từ biểu thức SELECT, `group` từ GROUP BY, `join` từ điều kiện JOIN, `filter` từ WHERE/HAVING. `SELECT *`, nguồn/cột mơ hồ, `JOIN USING`, CTE, subquery, UNION và hàm cửa sổ được cảnh báo hoặc yêu cầu khai báo thủ công. `complete=true` chỉ có nghĩa là bộ phân tích đơn giản không phát hiện trường hợp chưa xử lý; người dùng vẫn cần xác nhận SQL đúng là phép biến đổi tạo bảng đích.

`GET /tables/{table_id}/view-sql` đọc định nghĩa của view/materialized view trong database nguồn, bằng role trong URI đã lưu. Truy vấn kiểm tra `USAGE` trên schema và `SELECT` trên view; bảng thường trả 422, không đọc được view trả 404 hoặc lỗi nguồn 503. API không tự tạo phép biến đổi từ SQL này; frontend có thể đưa SQL sang `/preview` rồi gửi khai báo đã xác nhận.
