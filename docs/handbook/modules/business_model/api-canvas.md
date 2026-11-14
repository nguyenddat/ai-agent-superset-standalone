# API lưu canvas

**Trạng thái:** đã triển khai. **Endpoint:** `PUT /api/v1/business-model/connections/{connection_id}/canvases/{view}`, với `view` là `business` hoặc `lineage`.

Body là `{"layout": {...}}`. Service kiểm tra kết nối tồn tại, ghi JSON của object vào `business_canvases` hoặc `lineage_canvases`, mỗi kết nối tối đa một bản ghi cho mỗi chế độ. Layout phải mã hóa được thành JSON và không vượt 1 MB UTF-8; sai trả 422. Route commit một lần. API đọc mô hình trả layout đã lưu hoặc `{}` nếu chưa có. Bố cục hiện là dữ liệu hiển thị, backend chưa kiểm tra cấu trúc. Giao diện hiện chưa dùng hai canvas: tab `Mô hình` tự tính bố cục từ thành viên miền và cạnh lineage, xem [handbook frontend](../../frontend/README.md#mô-hình-nghiệp-vụ).
