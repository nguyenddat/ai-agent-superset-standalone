# API đọc kết nối và metadata

**Trạng thái:** đã triển khai các route `GET`.

## Các dạng đọc

- `GET /api/v1/database-connections`: danh sách kết nối, `offset` mặc định 0 và `limit` mặc định 100 (tối đa 100).
- `GET /api/v1/database-connections/dialects`: danh sách dialect/driver hỗ trợ, hiện có PostgreSQL và psycopg.
- `GET /api/v1/database-connections/{id}`: chi tiết kết nối, không trả URI.
- `GET /api/v1/database-connections/{id}/schemas`: danh sách `id`, `name`, `last_synced_at`.
- `GET /api/v1/schemas/{id}/tables`: danh sách `id`, `name`, `table_type`, `description`, `last_synced_at`.
- `GET /api/v1/tables/{id}/columns`: danh sách `name`, `data_type`, `ordinal_position`, `is_nullable`, `is_primary_key`, `default_value`, `description`.
Kết nối gồm ID, tên, dialect/driver, trạng thái và thời gian tạo/sửa. Metadata được đọc từ snapshot trong metadata database.

## Luồng xử lý hiện tại

1. Route kiểm tra ID UUID; đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng.
2. Service xác nhận bản ghi cha tồn tại trước khi đọc danh sách con.
3. Repository chỉ truy vấn metadata database; Pydantic serialize response.
4. Trả 404 khi ID cha không tồn tại.

`last_synced_at` cần có trong kết quả để người dùng nhận biết snapshot cũ. Danh sách schema/bảng tuân theo [phạm vi metadata](api-pham-vi-metadata.md) của kết nối; đọc trực tiếp cột theo ID bảng không dùng bộ lọc này. API đọc không tự truy vấn database nguồn; làm mới metadata đi qua luồng đồng bộ riêng.
