# API kiểm tra kết nối database nguồn

**Trạng thái:** dự kiến, chưa có route. **Method dự kiến:** `POST`. Đường dẫn và schema JSON chưa chốt.

## Mục đích và đầu vào

Người có quyền quản trị gửi loại database, driver và thông tin kết nối để kiểm tra trước khi lưu. Secret chỉ đi qua request và bộ nhớ trong thời gian kiểm tra; thao tác này không ghi metadata database.

## Luồng xử lý dự kiến

1. Route xác thực quyền và kiểm tra cấu trúc dữ liệu vào; không log mật khẩu hoặc URI đầy đủ.
2. Service tạo SQLAlchemy URL theo dialect/driver được hỗ trợ, đặt timeout và thử mở một connection.
3. Đóng connection và engine sau phép thử, kể cả khi lỗi.
4. Trả trạng thái thành công cùng loại database đã nhận diện; lỗi driver/kết nối được chuyển thành thông điệp an toàn, không trả stack trace hoặc secret.

## Điều kiện lỗi

Dữ liệu sai là 400; thiếu quyền là 403; database nguồn không truy cập được là lỗi nghiệp vụ của module, dự kiến 503. Chính sách giới hạn host và cổng cần được chốt trước khi mở route cho người dùng để tránh backend bị lợi dụng kết nối đến địa chỉ nội bộ.

## Chưa quyết định

Danh sách dialect hỗ trợ ban đầu, timeout, cơ chế xác thực và đường dẫn endpoint sẽ được ghi lại khi triển khai. Kiểm tra kết nối không tự đăng ký database.
