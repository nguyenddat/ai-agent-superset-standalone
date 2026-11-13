# Module `database_connection`

Module sở hữu kết nối đến database nguồn và bản sao metadata của schema, bảng/view, cột trong metadata database của ứng dụng.

**Đã triển khai:** bốn model SQLAlchemy dùng UUID v7, các revision Alembic, bốn repository, service và FastAPI route cho CRUD kết nối cùng đồng bộ/đọc metadata PostgreSQL. URI được mã hóa bằng Fernet trước khi lưu. **Chưa triển khai:** xác thực/phân quyền, giới hạn nguồn được phép kết nối và đồng bộ nền.

Route nằm trong `routes/router_database_connection.py` và `routes/router_database_metadata.py`; request/response schema nằm trong `schemas/`, lỗi module nằm trong `utils/exceptions.py`. Các endpoint dùng tiền tố `/api/v1`.

Repository kế thừa CRUD từ `BaseRepository`, nhận `Session` và không tự commit. Các truy vấn riêng gồm connection theo tên/trạng thái hoạt động, schema theo connection, table theo schema và column theo table. Truy vấn theo tên dùng cặp khóa ngoại và tên để đúng phạm vi ràng buộc duy nhất.

`ConnectionService` chỉ nhận URI `postgresql+psycopg`, thử mở kết nối với timeout 5 giây và `NullPool`, rồi lưu ciphertext khi đăng ký. Service không commit; caller quyết định commit hoặc rollback. Kết quả đọc là `ConnectionSummary` không chứa ciphertext. Khóa mã hóa lấy từ `CONNECTION_ENCRYPTION_KEY` hoặc được truyền vào service. Chưa có cơ chế luân chuyển khóa.

## Tài liệu module

- [Mô hình dữ liệu](du-lieu.md)
- [Kiểm tra kết nối](api-kiem-tra-ket-noi.md)
- [Đăng ký kết nối](api-dang-ky-ket-noi.md)
- [Đọc kết nối và metadata](api-doc-metadata.md)
- [Đồng bộ metadata](api-dong-bo-metadata.md)
- [Cập nhật hoặc xóa kết nối](api-cap-nhat-xoa-ket-noi.md)

Luồng xử lý API áp dụng [hành vi chung](../../hanh-vi-api.md). `DATABASE_URL` luôn là metadata database của ứng dụng; kết nối được đăng ký là tài nguyên khác.
