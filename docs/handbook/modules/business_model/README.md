# Module `business_model`

Module tổ chức các bảng đã mô tả thành tầng dữ liệu và miền nghiệp vụ, rồi lưu vị trí hiển thị trên canvas và các cạnh lineage. Thiết kế tham khảo `business_model` của Semantic Layer trong `ai-agent-superset-extension`, thay Superset dataset bằng `table_dictionaries` và Superset database bằng `database_connections`.

**Đã triển khai:** model và revision Alembic `8c3f26b419d0` cho năm bảng của module, bảng ghép miền–bảng và `table_dictionaries.layer_id`; repository, service và API quản lý tầng, miền, canvas và cạnh lineage.

**Giao diện:** tab `Mô hình` của trang kết nối hiển thị bảng và miền nghiệp vụ dạng vùng Venn, xem [handbook frontend](../../frontend/README.md#mô-hình-nghiệp-vụ). Chưa có giao diện quản lý tầng và lineage.

**Dự kiến:** giao diện tầng dữ liệu và lineage, kiểm tra sâu cấu trúc và tọa độ trong `layout`, phân tích dữ liệu nguồn để xác nhận quan hệ. API hiện suy quan hệ tham chiếu từ cột được khai báo trong từ điển và có thể lưu cạnh thủ công hoặc ẩn cạnh suy ra. Dòng dữ liệu từ SQL được quản lý bởi [module Data Lineage](../data_lineage/README.md). Các API chưa có xác thực/phân quyền.

Gán tầng hoặc đưa bảng vào miền sẽ tạo `table_dictionaries` mặc định nếu bảng đó chưa có từ điển mức bảng. Đọc mô hình không tạo bản ghi. Cạnh lineage chỉ được ghi khi cả hai bảng cùng một kết nối; domain và tầng dùng chung toàn ứng dụng, còn canvas gắn với từng kết nối.

## Tài liệu module

- [Mô hình dữ liệu và migration](du-lieu.md)
- [Đọc mô hình của một kết nối](api-doc-mo-hinh.md)
- [Quản lý tầng dữ liệu và gán bảng](api-tang-du-lieu.md)
- [Quản lý miền nghiệp vụ](api-mien-nghiep-vu.md)
- [Lưu canvas](api-canvas.md)
- [Cạnh lineage](api-lineage.md)
