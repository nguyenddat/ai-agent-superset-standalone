# Đọc đồ thị Data Lineage

**Trạng thái:** đã triển khai. `GET /api/v1/data-lineage/connections/{connection_id}/graph` trả `connection_id` và `edges[]`.

Mỗi bảng input của một phép biến đổi tạo một cạnh `transform` hướng từ bảng nguồn đến bảng đích, kèm `transformation_id`, `origin` và các phụ thuộc cột từ chính bảng nguồn đó. Cạnh `flow` được khai báo thủ công trong `business_model.lineage_edges` cũng xuất hiện với `transformation_id=null`, `origin=manual_edge` và danh sách phụ thuộc cột rỗng. Quan hệ FK (`relation`) không nằm trong đồ thị dòng dữ liệu này.

Phép biến đổi có một nguồn hoặc đích bị lọc khỏi phạm vi metadata sẽ không xuất hiện. Đồ thị phản ánh snapshot metadata và quyền tại lần sync gần nhất; trước khi dùng cho truy vấn thực tế, vẫn phải kiểm tra quyền tại thời điểm thực thi.
