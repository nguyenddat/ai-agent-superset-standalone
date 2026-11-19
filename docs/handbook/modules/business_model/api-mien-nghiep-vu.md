# API miền nghiệp vụ

**Trạng thái:** đã triển khai. Các endpoint có tiền tố `/api/v1/business-model`:

| Phương thức và đường dẫn | Chức năng |
| --- | --- |
| `GET /domains` | Liệt kê mọi miền và toàn bộ bảng thành viên. |
| `POST /domains` | Tạo miền, trả 201. |
| `PUT /domains/{domain_id}` | Thay thông tin và danh sách bảng thành viên. |
| `DELETE /domains/{domain_id}` | Xóa miền, trả 204; bảng, thuật ngữ, quy tắc và metric không bị xóa, chỉ bị gỡ khỏi miền. |

Body tạo/sửa: `name` bắt buộc (1–255 ký tự sau khi cắt khoảng trắng), `description` tối đa 2000 ký tự, `color` là `#RRGGBB` hoặc null, `table_ids` là danh sách tối đa 1000 ID bảng đã đồng bộ. Một bảng có thể thuộc nhiều miền; trong một request không được lặp ID. Service tạo từ điển mức bảng mặc định cho bảng chưa có từ điển, rồi thay toàn bộ danh sách thành viên của miền. Tên trùng không phân biệt hoa thường trả 409; miền hoặc bảng không tồn tại trả 404; ID bảng lặp trả 422. Miền là danh mục toàn ứng dụng, có thể gồm bảng từ nhiều kết nối; [API đọc mô hình](api-doc-mo-hinh.md) lọc thành viên theo kết nối.
