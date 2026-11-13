# API cập nhật hoặc xóa kết nối

**Trạng thái:** dự kiến, chưa có route. **Method dự kiến:** `PATCH` hoặc `DELETE`. Đường dẫn và schema JSON chưa chốt.

## Cập nhật

Route kiểm tra quyền và ID; service chỉ sửa trường được cho phép. Nếu thay URI, kiểm tra kết nối mới trước khi mã hóa và lưu. Không cho request ghi trực tiếp `uri_ciphertext`, `created_at` hoặc ID. Tên trùng trả 409. Caller commit một lần và response không chứa secret.

## Xóa

Route kiểm tra quyền; service kiểm tra phụ thuộc nghiệp vụ trước khi xóa. Theo FK hiện tại, xóa connection sẽ xóa schema, table và column con bằng cascade. Khi có dataset hoặc hợp đồng nghiệp vụ tham chiếu metadata này, phải chốt chính sách chặn xóa, vô hiệu hóa hoặc lưu lịch sử trước khi mở API xóa. Xóa ID không tồn tại trả 404.

`is_active` hiện cho phép vô hiệu hóa connection mà vẫn giữ metadata. Quy tắc phân quyền, thao tác khôi phục và đường dẫn endpoint được chốt khi triển khai.
