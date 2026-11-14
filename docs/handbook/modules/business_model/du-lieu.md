# Mô hình dữ liệu của `business_model`

**Trạng thái:** model, migration và API đã triển khai; giao diện miền nghiệp vụ đã triển khai (tab `Mô hình`), giao diện tầng và lineage dự kiến.

Revision `8c3f26b419d0` nối sau `1ee3a3e45c38` của `data_dictionary`. Các ID là UUID v7 khi tạo qua ORM. Năm bảng của module kế thừa `AuditedModel` nên có `created_at`, `updated_at`, `created_by_id`, `updated_by_id`; bảng ghép dùng khóa chính gồm hai UUID.

| Bảng | Nội dung và ràng buộc |
| --- | --- |
| `data_layers` | Tầng dữ liệu: `name` duy nhất, `description`, `color`, `level` và `sort_order` mặc định 0. Nhiều tầng có thể cùng `level`. |
| `business_domains` | Miền nghiệp vụ: `name` duy nhất, `description`, `color`. |
| `business_domain_tables` | Liên kết nhiều–nhiều giữa `business_domains.id` và `table_dictionaries.id`; cặp ID là khóa chính. Một bảng có thể thuộc nhiều miền. |
| `business_canvases` | `connection_id` duy nhất, FK đến `database_connections.id`; `layout` lưu bố cục dạng text JSON cho chế độ nghiệp vụ. |
| `lineage_canvases` | `connection_id` duy nhất, FK đến `database_connections.id`; `layout` lưu vị trí thẻ và hình dạng cạnh dạng text JSON. |
| `lineage_edges` | `source_table_dictionary_id`, `target_table_dictionary_id` tham chiếu `table_dictionaries.id`; `kind` (`flow` hoặc `relation` theo thiết kế), `label`, `color`, `is_hidden` mặc định false và `is_manual` mặc định true. Bộ `(source, target, kind)` duy nhất. |

`table_dictionaries.layer_id` là FK nullable đến `data_layers.id`. Xóa tầng đặt trường này về null; xóa từ điển bảng xóa bản ghi ghép miền và các cạnh lineage liên quan. Xóa kết nối xóa hai canvas của kết nối đó. Domain và layer có phạm vi toàn ứng dụng, còn canvas có phạm vi từng kết nối.

Migration không ghi dữ liệu vào các bảng mới và không sửa từ điển đã có, ngoài việc thêm `layer_id = null`. `downgrade` xóa các bảng mới rồi xóa cột này; chỉ chạy trên database thử nghiệm khi đã có dữ liệu nghiệp vụ trong module.
