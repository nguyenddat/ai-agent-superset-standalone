# API đọc mô hình nghiệp vụ

**Trạng thái:** đã triển khai. **Endpoint:** `GET /api/v1/business-model/connections/{connection_id}`.

Service kiểm tra kết nối tồn tại (không có trả 404), đọc các schema và bảng đã đồng bộ, từ điển mức bảng, tầng, miền, hai canvas và cạnh lineage. Đây là thao tác chỉ đọc; bảng chưa có từ điển vẫn xuất hiện với tên vật lý, `is_saved = false`, `table_kind = null` và `layer_id = null`.

Response gồm `connection_id`, `layers[]`, `domains[]`, `tables[]`, `business_canvas`, `lineage_canvas` và `lineage_edges[]`. `domains[].table_ids` chỉ gồm bảng thuộc kết nối đang đọc; tầng và miền là các danh mục toàn ứng dụng. Hai canvas trả `{}` nếu chưa lưu. `tables[]` có ID, tên schema/bảng, loại bảng vật lý, tên hiển thị, phân loại `table_kind`, tầng và trạng thái đã có từ điển.

Cạnh `relation` được suy từ `column_dictionaries.referenced_column_id` giữa hai bảng cùng kết nối, luôn hướng từ bảng tham chiếu đến bảng được tham chiếu; thứ tự tầng không biến quan hệ FK thành dòng dữ liệu. Bảng chưa có từ điển mức bảng vẫn có thể xuất hiện trong cạnh suy ra. Cạnh thủ công được ghép vào; bản ghi `is_hidden` ẩn cạnh cùng hướng và loại. `lineage_edges[]` chỉ trả cạnh đang hiển thị, kèm `origin` (`dictionary` hoặc `manual`), `id` của bản ghi override nếu có, `label` và `color`. Đồ thị data flow từ phép biến đổi có API riêng trong `data_lineage`.
