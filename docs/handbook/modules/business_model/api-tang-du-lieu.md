# API tầng dữ liệu

**Trạng thái:** đã triển khai. Các endpoint có tiền tố `/api/v1/business-model`:

| Phương thức và đường dẫn | Chức năng |
| --- | --- |
| `GET /layers` | Liệt kê tầng theo `level`, `sort_order`, tên. |
| `POST /layers` | Tạo tầng, trả 201. |
| `PUT /layers/{layer_id}` | Thay toàn bộ thông tin tầng. |
| `DELETE /layers/{layer_id}` | Xóa tầng, trả 204; bảng đang gán tầng trở về `layer_id = null`. |
| `PUT /layers/order` | Sắp thứ tự và cấp của toàn bộ tầng. |
| `PUT /tables/{table_id}/layer` | Gán hoặc bỏ tầng của một bảng đã đồng bộ. |

Body tạo/sửa tầng: `name` bắt buộc (1–255 ký tự sau khi cắt khoảng trắng), `description` tối đa 2000 ký tự, `color` là `#RRGGBB` hoặc null, `level` và `sort_order` là số nguyên không âm (mặc định 0). Tên được kiểm tra trùng không phân biệt hoa thường; trùng trả 409. Không tìm thấy tầng trả 404.

`PUT /layers/order` nhận `{"levels": [["<layer_id>", ...], ...]}`; mỗi tầng đang có phải xuất hiện đúng một lần. Chỉ số nhóm thành `level`, vị trí trong nhóm thành `sort_order`; thiếu hoặc lặp trả 422. `PUT /tables/{table_id}/layer` nhận `{"layer_id": "<id>"}` hoặc null; bảng không tồn tại trả 404, tầng không tồn tại trả 404. Nếu bảng chưa có từ điển mức bảng, service tạo bản ghi mặc định rồi gán tầng. Mỗi thao tác ghi commit một lần ở route.
