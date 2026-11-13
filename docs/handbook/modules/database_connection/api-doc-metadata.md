# API đọc kết nối và metadata

**Trạng thái:** dự kiến, chưa có route. **Method dự kiến:** `GET`. Đường dẫn và schema JSON chưa chốt.

## Các dạng đọc

- Danh sách kết nối mà người gọi được phép xem; phân trang và sắp xếp ổn định.
- Chi tiết một kết nối, gồm ID, tên, dialect/driver, trạng thái và thời gian tạo/sửa; không trả secret.
- Danh sách schema theo connection, table/view theo schema và column theo table; đọc từ snapshot trong metadata database.

## Luồng xử lý dự kiến

1. Route xác thực và kiểm tra quyền trên connection được yêu cầu.
2. Service xác nhận quan hệ cha–con trước khi đọc, để không lộ metadata từ connection khác qua ID con.
3. Repository chỉ truy vấn metadata database; route dùng formatter chung cho thời gian và kiểu dữ liệu.
4. Trả 404 khi ID không tồn tại hoặc không được phép tiết lộ, theo chính sách phân quyền sẽ chốt.

`last_synced_at` cần có trong kết quả để người dùng nhận biết snapshot cũ. API đọc không tự truy vấn database nguồn; làm mới metadata đi qua luồng đồng bộ riêng.
