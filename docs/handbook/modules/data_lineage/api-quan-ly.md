# Quản lý phép biến đổi

**Trạng thái:** đã triển khai. Các đường dẫn có tiền tố `/api/v1/data-lineage/connections/{connection_id}`.

| Endpoint | Chức năng |
| --- | --- |
| `GET /transformations` | Liệt kê khai báo có toàn bộ bảng nguồn và đích trong phạm vi metadata. |
| `POST /transformations` | Tạo khai báo, trả 201. |
| `GET /transformations/{id}` | Đọc một khai báo, trả 404 nếu ngoài kết nối hoặc phạm vi. |
| `PUT /transformations/{id}` | Thay toàn bộ khai báo và danh sách input/dependency trong một transaction. |
| `DELETE /transformations/{id}` | Xóa khai báo, trả 204. |

Body ghi gồm `target_table_id`, `name`, `description`, `sql_text`, `origin`, `source_table_ids[]` (ít nhất một) và `dependencies[]`. Mỗi dependency có `source_column_id`, `target_column_id` nullable và `role`. Cột nguồn phải thuộc một bảng input; cột đích phải thuộc bảng target; `value` cần cột đích. Danh sách bảng nguồn hoặc liên kết cột lặp trả 422. Tên phép biến đổi trùng trong một bảng đích trả 409. SQL tối đa 1 MB UTF-8, chỉ lưu chứ không thực thi. `origin=view_sql` hoặc `sql_job` cần SQL; `view_sql` còn yêu cầu bảng đích là view/materialized view. `origin` là nhãn nguồn do client khai báo, chưa được chứng thực tự động.

Các bảng nguồn và đích phải cùng kết nối, đang được bộ lọc metadata chọn. `PUT` gửi lại toàn bộ input/dependency, kể cả các mục muốn giữ; nếu cần sửa từng mục, frontend phải ghép danh sách trước khi gửi.
