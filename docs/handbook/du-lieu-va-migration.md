# Dữ liệu và migration

## Hai loại database

1. **Metadata database của ứng dụng:** `DATABASE_URL` trong `.env` hoặc biến môi trường. Backend dùng `backend.core.setting.Config` và `backend.core.database` để mở session. Alembic chỉ chạy trên database này.
2. **Database nguồn:** người dùng đăng ký để đọc metadata và dữ liệu. Thông tin kết nối nằm trong `database_connections.uri_ciphertext`; schema, bảng và cột được đồng bộ vào các bảng metadata của ứng dụng.

`DATABASE_URL` không được trỏ đến database nguồn chỉ để thử kết nối. Không chạy Alembic trên database nguồn.

## Cấu trúc Alembic

`alembic.ini` ở gốc repository, script nằm trong `backend/migrations/`. Revision đầu tiên là baseline; mỗi module có thư mục `backend/migrations/versions/init_<ten_module>_module/`. Module `database_connection` hiện dùng thư mục `init_database_module`. `version_locations` trong `alembic.ini` liệt kê các thư mục này. Revision của module đó lần lượt tạo connection, schema, table và column.

```powershell
uv sync
$env:DATABASE_URL = "postgresql+psycopg://app:password@localhost:5432/ai_agent"
uv run alembic upgrade head
uv run alembic check
```

Khi thêm bảng: viết model, import model trong `models/__init__.py` và bảo đảm `backend/migrations/env.py` import package model; tạo revision ở đúng thư mục bằng `--version-path`, xem lại script trước khi chạy upgrade. Không dùng `Base.metadata.create_all()` trong startup để thay Alembic.

## Khóa và thời gian

`BaseModel` mới cung cấp UUID v7, `created_at` và `updated_at`; `AuditedModel` thêm `created_by_id`, `updated_by_id` nullable. Bốn bảng của module `database_connection` đã được tạo với ID số nguyên. Chúng không tự chuyển sang UUID v7 khi thêm base model; việc đổi khóa phải có migration dữ liệu và khóa ngoại riêng.

Thời gian lưu trong cột timezone-aware theo UTC. Formatter ở `common` xuất thời gian thành ISO 8601 UTC có hậu tố `Z`. Các giá trị `last_synced_at` là thời điểm metadata được lấy từ database nguồn, không phải thời điểm dữ liệu nghiệp vụ của bảng nguồn thay đổi.
