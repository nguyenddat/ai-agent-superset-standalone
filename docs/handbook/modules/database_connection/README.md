# Module `database_connection`

Module sở hữu kết nối đến database nguồn và bản sao metadata của schema, bảng/view, cột trong metadata database của ứng dụng.

**Đã triển khai:** bốn model SQLAlchemy, bốn revision Alembic và import model cho autogenerate. **Chưa triển khai:** route, service, repository riêng của module, mã hóa/giải mã URI và tác vụ đồng bộ metadata. Những file API bên dưới mô tả luồng dự kiến; method và đường dẫn chính thức sẽ được chốt khi viết route.

## Tài liệu module

- [Mô hình dữ liệu](du-lieu.md)
- [Kiểm tra kết nối](api-kiem-tra-ket-noi.md)
- [Đăng ký kết nối](api-dang-ky-ket-noi.md)
- [Đọc kết nối và metadata](api-doc-metadata.md)
- [Đồng bộ metadata](api-dong-bo-metadata.md)
- [Cập nhật hoặc xóa kết nối](api-cap-nhat-xoa-ket-noi.md)

Luồng xử lý API áp dụng [hành vi chung](../../hanh-vi-api.md). `DATABASE_URL` luôn là metadata database của ứng dụng; kết nối được đăng ký là tài nguyên khác.
