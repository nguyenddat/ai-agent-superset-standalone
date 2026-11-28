# API kiểm tra kết nối database nguồn

**Trạng thái:** đã triển khai route. **Endpoint:** `POST /api/v1/database-connections/test`.

## Mục đích và đầu vào

JSON đầu vào gồm `dialect` (`postgresql`), `driver` tùy chọn (`psycopg`) và `uri`. Secret chỉ đi qua request và bộ nhớ trong thời gian kiểm tra; thao tác này không ghi metadata database. Thành công trả `{"ok":true,"message":"Kết nối thành công."}`.

## Luồng xử lý hiện tại

1. Route kiểm tra cấu trúc dữ liệu vào; đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng.
2. Service tạo SQLAlchemy URL theo dialect/driver được hỗ trợ, đặt timeout và thử mở một connection.
3. Đóng connection và engine sau phép thử, kể cả khi lỗi.
4. Trả trạng thái thành công; lỗi driver/kết nối được chuyển thành thông điệp an toàn, không trả stack trace hoặc secret.

## Điều kiện lỗi

Dữ liệu sai trả 422; database nguồn không truy cập được trả 503, dạng `{"detail":"..."}`. Route đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng và chưa giới hạn host/cổng; cần bổ sung trước khi mở backend ra mạng không tin cậy.

## Chưa quyết định

Service hiện chỉ hỗ trợ PostgreSQL qua `psycopg`, timeout kết nối 5 giây và không giữ pool sau phép thử. Cơ chế xác thực người gọi và giới hạn host/cổng chưa được chốt. Kiểm tra kết nối không tự đăng ký database.
