# API quản lý metric

**Trạng thái:** đã triển khai. Prefix `/api/v1/metrics`.

| Method | Path | Chức năng |
| --- | --- | --- |
| `GET` | `/api/v1/metrics?connection_id=<UUID>` | Danh sách metric, có thể lọc theo connection standalone. |
| `POST` | `/api/v1/metrics` | Tạo metric thủ công trên `table_id`. |
| `GET` | `/api/v1/metrics/{id}` | Xem chi tiết metric. |
| `PATCH` | `/api/v1/metrics/{id}` | Sửa metric thủ công. |
| `DELETE` | `/api/v1/metrics/{id}` | Xóa metric thủ công. |

Ví dụ tạo: `{"table_id":"<UUID>","name":"revenue","expression":"SUM(amount)","label":"Doanh thu"}`. Tên metric thủ công duy nhất trên một bảng. Có thể lưu thêm `description`, `format`, `currency`, `metric_type`, `warning_text`. Biểu thức được lưu như văn bản, tối đa 10.000 ký tự và không chứa dấu `;`; endpoint không chạy SQL. Metric có `origin=superset` chỉ đọc qua API này; sửa/xóa trả 409 để bảo toàn hướng đồng bộ.
