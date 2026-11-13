# API đăng ký kết nối database nguồn

**Trạng thái:** đã triển khai route. **Endpoint:** `POST /api/v1/database-connections`.

## Đầu vào và kết quả

JSON đầu vào gồm `name`, `dialect` (`postgresql`), `driver` tùy chọn (`psycopg`) và `uri`. Thành công trả 201 cùng `id`, `name`, `dialect`, `driver`, `is_active`, `created_at`, `updated_at`; không trả URI rõ, URI đã mã hóa hoặc mật khẩu.

## Luồng xử lý hiện tại

1. Kiểm tra cấu trúc JSON, tên hợp lệ và loại database được hỗ trợ. Route hiện chưa xác thực người gọi.
2. Kiểm tra kết nối bằng logic service dùng chung với luồng kiểm tra kết nối.
3. Mã hóa URI bằng khóa do backend quản lý rồi tạo `database_connections`; không bao giờ lưu URI rõ vào `uri_ciphertext`.
4. Repository flush để nhận ID và phát hiện tên trùng; caller commit một lần.
5. Trả kết nối đã tạo. Đồng bộ schema/bảng/cột là thao tác riêng để có thể theo dõi và thử lại khi database nguồn chậm.

## Điều kiện lỗi

Tên, URI hoặc cấu hình sai trả 422; tên đã tồn tại trả 409; database nguồn không truy cập được trả 503 với thông điệp đã che secret. Lỗi có dạng `{"detail":"..."}`. Khi bất kỳ bước nào thất bại, transaction metadata rollback.

## Quyết định hiện tại

Service chỉ hỗ trợ `postgresql+psycopg`, kiểm tra kết nối trước khi mã hóa URI bằng Fernet. Tên được cắt khoảng trắng đầu/cuối, dài 1–255 ký tự và không trùng tên đã lưu. `ConnectionSummary` không có URI hay ciphertext. `CONNECTION_ENCRYPTION_KEY` là khóa Fernet do backend quản lý; mất khóa sẽ không giải mã được URI đã lưu. Route commit một lần sau khi service thành công.

## Chưa quyết định

Cơ chế xác thực/phân quyền, luân chuyển khóa và chống đăng ký trùng cùng một nguồn chưa được chốt.
