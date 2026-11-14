# Dữ liệu glossary và quan hệ ngữ nghĩa

**Trạng thái:** migration `a8e12c7f94b3` đã triển khai sau `metric_management`.

| Bảng | Vai trò |
| --- | --- |
| `glossary_terms` | Một thuật ngữ ổn định, thuộc `database_connections`, có tên chuẩn và nhóm. Unique `(connection_id, normalized_name)`. |
| `glossary_revisions` | Định nghĩa, từ đồng nghĩa, trạng thái `draft` / `approved` / `revoked`; unique `(term_id, number)`. |
| `glossary_links` | Liên kết của một revision tới đúng một bảng, cột hoặc metric qua khóa ngoại. Check constraint buộc `kind` khớp đúng một ID đích; unique theo `(revision_id, target_id)` cho mỗi loại. |

Liên kết được kiểm tra thuộc connection của thuật ngữ khi tạo revision. Metric phải đang hoạt động và có `table_id` trỏ tới bảng metadata trong connection. Khi bảng/cột/metric bị xóa, khóa ngoại `ON DELETE CASCADE` bỏ liên kết đó. Discovery lọc lại liên kết không còn hợp lệ, ví dụ metric đã bị vô hiệu hóa hoặc chuyển bảng. Thuật ngữ vẫn được trả về với các liên kết còn hiệu lực.

Thiết kế quan hệ là nhiều-nhiều: một revision có thể liên kết nhiều metric; một metric có thể được nhiều thuật ngữ giải thích. Module `expert_rule_management` đã có bảng ghép riêng từ revision rule tới `glossary_terms.id`, revision glossary đã duyệt và `metrics.id`. Service kiểm tra tất cả liên kết cùng connection và bảng. Như vậy một rule có thể dùng nhiều thuật ngữ và metric, và một bộ **glossary – metric – expert rule** được nối qua khóa ngoại có kiểm tra, không giới hạn một-một. Xem [dữ liệu expert rule](../expert_rule_management/du-lieu.md).

API hiện chưa có danh tính người dùng; các cột `created_by_id` và `updated_by_id` của `AuditedModel` để trống. Trạng thái duyệt hiện là trạng thái dữ liệu, chưa đại diện cho quy trình phê duyệt có kiểm soát quyền.
