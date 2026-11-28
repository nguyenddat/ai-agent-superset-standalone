# API đồng bộ Superset

**Trạng thái:** đã triển khai; đồng bộ một chiều Superset → standalone, kích hoạt thủ công. Cần `SUPERSET_URL`, `SUPERSET_USERNAME`, `SUPERSET_PASSWORD` trong môi trường backend. Tài khoản Superset phải được phép đọc API users, databases và datasets. Nếu Superset không mở Security Users API, cần bật cấu hình tương ứng của Superset. Backend tải hết dữ liệu trước khi ghi; lỗi truy cập Superset trả 503 và không commit một phần.

| Method | Path | Chức năng |
| --- | --- | --- |
| `POST` | `/api/v1/metrics/superset/sync` | Đăng nhập Superset, phân trang users/databases/datasets, đọc chi tiết từng dataset và upsert metric. |
| `GET` | `/api/v1/metrics/superset/users` | Xem user đã nhập. |
| `GET` | `/api/v1/metrics/superset/databases` | Xem database đã nhập và connection đang liên kết. |
| `PUT` | `/api/v1/metrics/superset/databases/{id}/link` | Gửi `{"connection_id":"<UUID>"}` để liên kết, hoặc `null` để bỏ liên kết. |

Sync lặp lại dùng `(source_url, source_id)` cho user/database và `(source_url, source_metric_id)` cho metric, không nhân bản. Metric không còn ở Superset được đánh dấu inactive. Đối với dataset vật lý, khi database đã liên kết, backend tìm bảng có cùng schema/tên trong metadata standalone và gắn `table_id` nếu có. Dataset ảo giữ SQL nguồn và không tự gắn bảng. Superset không bị ghi thay đổi.

Backend chỉ kết nối Superset qua REST API có bearer token; không lưu mật khẩu Superset vào metadata database. Địa chỉ Superset từ trong container có thể khác địa chỉ trình duyệt, ví dụ `http://host.docker.internal:8089` khi chạy Superset trên Docker Desktop. API đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng; khi triển khai ngoài máy phát triển vẫn nên đặt endpoint sync sau lớp truy cập tin cậy.

Tham chiếu API chính thức: [Superset REST API](https://superset.apache.org/docs/rest-api/), [Superset dataset API](https://superset.apache.org/docs/api/).
