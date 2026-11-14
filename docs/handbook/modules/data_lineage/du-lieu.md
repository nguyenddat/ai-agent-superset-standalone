# Dữ liệu Data Lineage

**Trạng thái:** đã triển khai bằng revision Alembic `d51a78e4b2c0`, nối sau `b6431e2579af`. Migration chỉ thay metadata database của ứng dụng.

| Bảng | Nội dung và ràng buộc |
| --- | --- |
| `lineage_transformations` | Một phép biến đổi có `target_table_id` FK đến `database_tables`, `name`, `description`, `sql_text` nullable, `origin` (`manual`, `sql_job`, `view_sql`). `(target_table_id, name)` duy nhất. Có cột audit. |
| `lineage_transformation_inputs` | Mỗi hàng là một bảng nguồn của phép biến đổi. `(transformation_id, source_table_id)` duy nhất; hai FK `ON DELETE CASCADE`. |
| `lineage_column_dependencies` | Một cột nguồn và cột đích tùy chọn, gắn vai trò `value`, `group`, `join` hoặc `filter`. `value` bắt buộc có cột đích. Các FK `ON DELETE CASCADE`. |

`value` là cột cung cấp giá trị cho cột đích. `group` quyết định nhóm tổng hợp. `join` và `filter` ảnh hưởng tập bản ghi; các vai trò này có thể không gắn vào một cột đích riêng. SQL gốc là bằng chứng người dùng cung cấp, còn `inputs` và `dependencies` đã xác nhận là dữ liệu dùng để dựng đồ thị. Backend kiểm tra cột nguồn thuộc một bảng input, cột đích thuộc bảng target và mọi bảng cùng một kết nối.

Khi bảng đích bị xóa khỏi metadata, phép biến đổi bị xóa theo. Khi bảng/cột nguồn bị xóa, input/dependency liên quan bị xóa theo; phép biến đổi có thể còn nhưng thiếu nguồn và cần sửa lại. Bộ lọc tên chỉ ẩn phép biến đổi có bảng nguồn hoặc đích ngoài phạm vi; không xóa bản ghi. Lần sync xóa metadata vật lý vắng mặt vẫn có thể xóa dây chuyền theo các FK này.

`lineage_edges` và `lineage_canvases` của `business_model` vẫn tồn tại. `lineage_edges` chỉ lưu cạnh thủ công hoặc override, không lưu bản sao cạnh `transform` suy từ ba bảng mới.
