# API quản lý expert rule

**Trạng thái:** đã triển khai tại `/api/v1/expert-rules`.

| Method | Path | Hành vi |
| --- | --- | --- |
| GET | `?connection_id=<uuid>` | Danh sách rule, bản hiện tại, bản đang phục vụ và `is_discoverable`. |
| GET | `/options?connection_id=<uuid>` | Bảng, cột, glossary đã duyệt và metric đang hoạt động có thể chọn. |
| GET | `/discovery?connection_id=<uuid>` | Chỉ rule đã duyệt với tất cả phụ thuộc còn hợp lệ. |
| POST | `/` | Tạo rule và revision 1 `draft`. |
| GET | `/{rule_id}` | Đọc rule. |
| GET | `/{rule_id}/revisions` | Lịch sử revision mới nhất trước. |
| PUT | `/{rule_id}/draft` | Tạo draft mới từ toàn bộ nội dung gửi lên. |
| POST | `/{rule_id}/approve` | Duyệt draft hiện tại sau khi kiểm tra lại phụ thuộc. |
| POST | `/{rule_id}/revoke` | Tạo revision thu hồi. |
| DELETE | `/{rule_id}` | Xóa rule và lịch sử. |

Body tạo gồm `connection_id`, `table_id`, `name`, `conditions` (1–50 mục), `glossary_term_ids` (1–50 mục), tùy chọn `description`, `group_name`, `exceptions`, `examples`, `metric_ids`. Body sửa gồm toàn bộ nội dung revision, `group_name` và `expected_revision`; tên và bảng của rule không đổi. Body duyệt/thu hồi chỉ cần `expected_revision`. Mỗi condition gồm `column_id`, `operator`, `value_type`, `value`; operator thuộc `equals`, `not_equals`, `contains`, `not_contains`, `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal`, `in`, `not_in`, `is_null`, `is_not_null`. `value_type` là `string`, `number`, `boolean`, `null` hoặc `array` và phải khớp `value`/operator. Ngoại lệ gồm `when`, `outcome`; ví dụ gồm `question`, `intent`.

`expected_revision` sai hoặc trạng thái không cho phép trả 409. Tên trùng trả 409; liên kết sai phạm vi, trùng hoặc không có bản glossary đã duyệt trả 400; request sai cấu trúc trả 422. Thay đổi chỉ ở nhóm cập nhật rule mà không tạo revision. Khi nội dung và các đối tượng đã ghim không đổi, thao tác sửa trả bản hiện tại. Khi glossary/metric đổi phiên bản hoặc nội dung rule đổi, thao tác sửa tạo draft mới. API chưa xác thực người gọi; không dùng trạng thái `approved` làm bằng chứng phê duyệt có phân quyền.
