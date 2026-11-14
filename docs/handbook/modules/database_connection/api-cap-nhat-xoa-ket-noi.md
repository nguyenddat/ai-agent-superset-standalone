# API cập nhật hoặc xóa kết nối

**Trạng thái:** đã triển khai. **Endpoint:** `PATCH /api/v1/database-connections/{id}` và `DELETE /api/v1/database-connections/{id}`.

## Cập nhật

Route kiểm tra ID UUID; service sửa `name`, `is_active`, `uri` và các danh sách `schema_includes`, `schema_excludes`, `table_includes`, `table_excludes`. Nếu thay URI, service kiểm tra kết nối mới trước khi mã hóa và lưu. Không cho request ghi trực tiếp `uri_ciphertext`, `created_at` hoặc ID. Tên trùng trả 409; dữ liệu sai trả 422. Route commit một lần và trả chi tiết kết nối không chứa secret. Đổi [phạm vi metadata](api-pham-vi-metadata.md) không tự đồng bộ nguồn.

## Xóa

Xóa thành công trả 204, không có body. Theo FK hiện tại, xóa connection sẽ xóa schema, table và column con bằng cascade. Xóa ID không tồn tại trả 404. Khi có dataset hoặc hợp đồng nghiệp vụ tham chiếu metadata này, cần xem lại chính sách xóa.

`is_active` cho phép vô hiệu hóa connection mà vẫn giữ metadata. Route hiện chưa có xác thực/phân quyền.
