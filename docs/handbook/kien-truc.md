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

`database_connection` là module nghiệp vụ đầu tiên. Đã có bốn model, các migration trong `init_database_module`, bốn repository, service và FastAPI route cho đăng ký kết nối, CRUD và metadata. `backend/__init__.py` hiện chỉ là entrypoint mẫu. `frontend/` đã có giao diện Next.js, chưa nối API. API chưa có xác thực/phân quyền.

Các model database hiện có kế thừa `BaseModel` trong `common`, dùng ID UUID v7 và timestamps. Revision mới chuyển ID số nguyên đã tạo bởi các migration đầu sang UUID v7 cùng các khóa ngoại liên quan.
