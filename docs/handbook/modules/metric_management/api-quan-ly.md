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

Mọi metric, kể cả bản từ Superset, có thể gán vào một hoặc nhiều [miền nghiệp vụ](../business_model/api-mien-nghiep-vu.md) qua `business_domain_ids` (tối đa 50) khi tạo hoặc sửa; kết quả đọc có `business_domains` (`id`, `name`, `color`). Với metric Superset, `PATCH` chỉ chứa `business_domain_ids` được chấp nhận vì miền không đến từ Superset; kèm trường khác vẫn trả 409. ID miền không tồn tại trả 400.
