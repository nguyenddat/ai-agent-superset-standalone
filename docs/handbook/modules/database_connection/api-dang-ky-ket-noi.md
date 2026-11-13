# API đăng ký kết nối database nguồn

**Trạng thái:** dự kiến, chưa có route. **Method dự kiến:** `POST`. Đường dẫn và schema JSON chưa chốt.

## Đầu vào và kết quả

Đầu vào gồm tên hiển thị, dialect/driver và thông tin kết nối. Kết quả là ID và metadata không nhạy cảm của kết nối; không trả URI rõ, URI đã mã hóa hoặc mật khẩu.

## Luồng xử lý dự kiến

1. Kiểm tra quyền quản trị, tên hợp lệ và loại database được hỗ trợ.
2. Kiểm tra kết nối bằng logic service dùng chung với luồng kiểm tra kết nối.
3. Mã hóa URI bằng khóa do backend quản lý rồi tạo `database_connections`; không bao giờ lưu URI rõ vào `uri_ciphertext`.
4. Repository flush để nhận ID và phát hiện tên trùng; caller commit một lần.
5. Trả kết nối đã tạo. Đồng bộ schema/bảng/cột là thao tác riêng để có thể theo dõi và thử lại khi database nguồn chậm.

## Điều kiện lỗi

Tên hoặc cấu hình sai là 400; thiếu quyền là 403; tên đã tồn tại là 409; database nguồn không truy cập được là lỗi kết nối an toàn cho client. Khi bất kỳ bước nào thất bại, transaction metadata rollback.

## Chưa quyết định

Cách quản lý khóa mã hóa, cơ chế chống đăng ký trùng cùng một nguồn và đường dẫn endpoint phải được chốt trước khi triển khai.
