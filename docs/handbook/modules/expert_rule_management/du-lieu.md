# Dữ liệu expert rule

**Trạng thái:** migration `b9f4d7a2c183` đã triển khai sau glossary; `9b3e6f2a8c51` thay cột `group_name` bằng bảng ghép miền nghiệp vụ.

| Bảng | Vai trò |
| --- | --- |
| `expert_rules` | Tên, `normalized_name`, connection và bảng metadata. Tên duy nhất trong connection. |
| `expert_rule_revisions` | Mô tả, điều kiện, ngoại lệ, ví dụ dạng JSON và trạng thái `draft` / `approved` / `revoked`; unique `(rule_id, number)`. |
| `expert_rule_domains` | Quan hệ nhiều-nhiều `(rule_id, domain_id)` tới `business_domains`; xóa rule hoặc miền sẽ xóa bản ghi ghép. Không theo revision. |
| `expert_rule_glossary_links` | Quan hệ nhiều-nhiều từ revision rule tới thuật ngữ, ghim cả `glossary_revision_id` đã duyệt. |
| `expert_rule_metric_links` | Quan hệ nhiều-nhiều từ revision rule tới metric, lưu fingerprint SHA-256 của bảng, tên, biểu thức, mô tả và trạng thái metric. |

Khóa ngoại của bảng ghép dùng `ON DELETE CASCADE`. Service kiểm tra connection và bảng khi ghi; điều kiện phải trỏ tới cột của bảng, glossary phải có bản đang phục vụ liên kết tới bảng, metric phải đang hoạt động trên bảng. Discovery kiểm tra lại: cột còn đúng bảng, revision glossary được ghim vẫn đang phục vụ và còn liên kết sống tới bảng, fingerprint metric còn khớp. Nếu không, `is_discoverable=false` trong API quản lý và rule bị bỏ khỏi discovery. Chỉ cần gửi lại cùng nội dung để tạo revision mới ghim đối tượng hiện tại, rồi duyệt.

Các cột `created_by_id`, `updated_by_id` hiện để trống vì ứng dụng chưa có xác thực. `approved` là trạng thái dữ liệu, chưa phải phê duyệt bởi một vai trò độc lập. Migration `9b3e6f2a8c51` chuyển `group_name` cũ sang miền có tên trùng như glossary. Import/export file, gợi ý gom nhóm và phát hiện mâu thuẫn chưa triển khai trong standalone.
