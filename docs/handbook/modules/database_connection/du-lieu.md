# Mô hình dữ liệu của `database_connection`

**Trạng thái:** đã có model UUID v7, migration và repository; chưa có đồng bộ metadata từ database nguồn.

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

Các FK hiện có `ON DELETE CASCADE`: xóa connection sẽ xóa metadata con. Bốn bảng kế thừa `BaseModel`: ID là UUID v7 tạo trong Python; `created_at` và `updated_at` được lưu trên từng bảng. Các khóa ngoại cùng dùng UUID. `uri_ciphertext` là vị trí lưu URI sau mã hóa; code mã hóa chưa có, nên chưa được phép lưu URI rõ vào trường này.

`database_tables` chứa cả table và view; `table_type` phân biệt hai loại. Metadata này là snapshot phục vụ khám phá, không phải dữ liệu của bảng nguồn. Các cột `last_synced_at` cho biết lần quan sát metadata; hiện chưa có cột đánh dấu bản ghi đã biến mất khỏi nguồn. Khóa ngoại và chỉ mục của bảng nguồn chưa được lưu; khi có yêu cầu suy luận đường join, thiết kế migration riêng cho quan hệ nhiều cột.

Migration nằm trong `backend/migrations/versions/init_database_module/`, theo thứ tự connection → schema → table → column. Revision tiếp theo chuyển ID và khóa ngoại số nguyên của dữ liệu cũ sang UUID v7, giữ các thuộc tính và quan hệ. Khi downgrade về số nguyên, ID được đánh lại theo thứ tự bản ghi.
