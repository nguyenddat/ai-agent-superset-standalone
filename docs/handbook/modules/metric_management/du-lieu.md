# Dữ liệu và migration Metric Management

**Trạng thái:** đã triển khai trong revision `f6c1a2d937e4`, sau Data Lineage `d51a78e4b2c0`. Chỉ thay metadata database của standalone.

| Bảng | Vai trò |
| --- | --- |
| `metrics` | Metric tự tạo (`origin=manual`) hoặc bản sao Superset (`origin=superset`); lưu tên, expression và trường trình bày. Metric tự tạo gắn `table_id`; bản nhập lưu `source_url`, ID metric/dataset, database nguồn, người tạo metric và người tạo dataset nếu Superset cung cấp, schema, tên bảng và SQL dataset ảo. `(source_url, source_metric_id)` duy nhất. |
| `metric_domains` | Quan hệ nhiều-nhiều `(metric_id, domain_id)` tới `business_domains` (revision `4d8a1c7e3b92`); xóa metric hoặc miền sẽ xóa bản ghi ghép. Đồng bộ Superset không đụng tới bảng này. |
| `superset_users` | Bản sao username, họ tên, email theo `(source_url, source_id)`, không chứa mật khẩu hay quyền đăng nhập. |
| `superset_databases` | Bản sao tên/backend theo `(source_url, source_id)` và `connection_id` tùy chọn đến connection standalone. Không lưu URI Superset. |

Khi bảng metadata standalone bị xóa, `metrics.table_id` thành `NULL` để giữ bản ghi nhập và dấu vết nguồn. Metric thủ công không còn bảng sẽ cần gán lại trước khi sử dụng. Khi connection standalone bị xóa, liên kết của database Superset thành `NULL`. Khi metric biến mất ở Superset, sync đặt `is_active=false`, không xóa lịch sử. Đồng bộ lại cùng ID sẽ kích hoạt lại. Không xóa user hoặc database nguồn vắng mặt để giữ tham chiếu lịch sử.
