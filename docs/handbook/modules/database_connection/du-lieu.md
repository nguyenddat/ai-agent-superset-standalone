# Mô hình dữ liệu của `database_connection`

**Trạng thái:** đã triển khai model UUID v7, migration, repository, mã hóa URI và đồng bộ metadata từ database nguồn PostgreSQL.

```text
database_connections (1)
  └── (n) database_schemas
          └── (n) database_tables
                  └── (n) database_columns
```

| Bảng | Trường chính | Ràng buộc |
| --- | --- | --- |
| `database_connections` | `id`, `name`, `dialect`, `driver`, `uri_ciphertext`, `is_active`, `created_at`, `updated_at` | `name` duy nhất. |
| `database_schemas` | `id`, `connection_id`, `name`, `last_synced_at`, `created_at`, `updated_at` | FK đến connection; cặp `(connection_id, name)` duy nhất. |
| `database_tables` | `id`, `schema_id`, `name`, `table_type`, `description`, `last_synced_at`, `created_at`, `updated_at` | FK đến schema; cặp `(schema_id, name)` duy nhất. |
| `database_columns` | `id`, `table_id`, `name`, `data_type`, `ordinal_position`, `is_nullable`, `is_primary_key`, `default_value`, `description`, `created_at`, `updated_at` | FK đến table; cặp `(table_id, name)` duy nhất. |

Các FK hiện có `ON DELETE CASCADE`: xóa connection sẽ xóa metadata con. Bốn bảng kế thừa `BaseModel`: ID là UUID v7 tạo trong Python; `created_at` và `updated_at` được lưu trên từng bảng. Các khóa ngoại cùng dùng UUID. `uri_ciphertext` lưu URI đã mã hóa bằng Fernet với khóa `CONNECTION_ENCRYPTION_KEY`; không lưu URI rõ vào trường này.

`database_tables` chứa table, view và materialized view; `table_type` (`TABLE`, `VIEW`, `MATERIALIZED_VIEW`) phân biệt các loại. Metadata này là snapshot phục vụ khám phá, không phải dữ liệu của bảng nguồn. Các cột `last_synced_at` cho biết lần quan sát metadata. Schema, bảng hoặc cột không còn ở nguồn bị xóa khi đồng bộ, nên snapshot luôn khớp lần đọc gần nhất; ứng dụng không giữ lịch sử metadata đã biến mất. Khóa ngoại và chỉ mục của bảng nguồn chưa được lưu; khi có yêu cầu suy luận đường join, thiết kế migration riêng cho quan hệ nhiều cột.

Migration nằm trong `backend/migrations/versions/init_database_module/`, theo thứ tự connection → schema → table → column. Revision tiếp theo chuyển ID và khóa ngoại số nguyên của dữ liệu cũ sang UUID v7, giữ các thuộc tính và quan hệ. Khi downgrade về số nguyên, ID được đánh lại theo thứ tự bản ghi.
