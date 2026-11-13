# Kiến trúc ứng dụng

## Ranh giới hệ thống

```text
frontend/ → backend/modules/ → metadata database của ứng dụng
                         └──→ database nguồn đã đăng ký
```

Ứng dụng standalone không cần chạy Superset để lưu kết nối hay metadata. `DATABASE_URL` cấu hình metadata database của chính ứng dụng. URI của database nguồn nằm trong bản ghi `database_connections` và chỉ được dùng sau khi giải mã ở lớp nghiệp vụ tương ứng. Bốn bảng metadata nguồn là bản sao thông tin schema, bảng và cột; migration không tạo bảng trong database nguồn.

## Các lớp backend

| Lớp | Trách nhiệm |
| --- | --- |
| `backend/common` | Base ORM, repository, exception và formatter dùng chung; không phụ thuộc `core` hoặc module nghiệp vụ. |
| `backend/core` | Settings, engine và session của metadata database, hạ tầng bảo mật chung. |
| `backend/modules/<module>` | Model, repository, service, schema nhập/xuất, route và lỗi theo nghiệp vụ. |
| `backend/migrations` | Phiên bản schema metadata database; import các model để đối chiếu Alembic. |

Module khác dùng service hoặc repository của module sở hữu dữ liệu; không gọi route nội bộ như một hàm nghiệp vụ. Route đọc request và trả response; service xử lý quy tắc; repository truy vấn bằng session được truyền vào. Caller của service sở hữu transaction và gọi commit khi toàn bộ thao tác thành công.

## Trạng thái hiện tại

`database_connection` là module nghiệp vụ đầu tiên. Đã có bốn model và bốn migration trong `init_database_module`; các thư mục service, repository và route chưa có logic. `backend/__init__.py` hiện chỉ là entrypoint mẫu. `frontend/` mới có thư mục khởi tạo. Các luồng API trong handbook là thiết kế để triển khai sau, không phải endpoint đang hoạt động.

Các model database hiện có dùng ID số nguyên theo migration đã tạo. `BaseModel` trong `common` cung cấp UUID v7 và timestamps cho model mới; muốn đổi ID của bảng hiện có phải tạo migration riêng.
