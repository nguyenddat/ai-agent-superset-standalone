# API quản lý thuật ngữ

**Trạng thái:** đã triển khai tại `/api/v1/glossary`.

| Method | Path | Hành vi |
| --- | --- | --- |
| GET | `?connection_id=<uuid>` | Danh sách thuật ngữ của connection; mỗi mục có `current` và `serving`. |
| GET | `/discovery?connection_id=<uuid>` | Chỉ bản đang phục vụ đã duyệt, với liên kết còn hợp lệ. |
| POST | `/` | Tạo thuật ngữ và revision 1 `draft`. |
| GET | `/{term_id}` | Đọc thuật ngữ. |
| GET | `/{term_id}/revisions` | Lịch sử revision mới nhất trước. |
| PUT | `/{term_id}/draft` | Tạo revision nháp mới từ nội dung gửi lên. |
| POST | `/{term_id}/approve` | Duyệt revision nháp hiện tại. |
| POST | `/{term_id}/revoke` | Tạo revision thu hồi, dừng phục vụ bản đã duyệt. |
| DELETE | `/{term_id}` | Xóa thuật ngữ và lịch sử của nó. |

Body tạo gồm `connection_id`, `canonical_name`, `definition`, tùy chọn `business_domain_ids` (tối đa 50 ID miền nghiệp vụ), `synonyms` và `links`. Mỗi link có `kind` là `table`, `column` hoặc `metric`, và `id` UUID của đối tượng tương ứng. Body sửa gồm `definition`, `business_domain_ids`, `synonyms`, `links` và `expected_revision`; body duyệt/thu hồi chỉ cần `expected_revision`. Client gửi toàn bộ nội dung khi sửa. Tên chuẩn cố định sau khi tạo. Kết quả đọc, kể cả discovery, có `business_domains` gồm `id`, `name`, `color` của từng miền, xếp theo tên.

`expected_revision` phải bằng số revision mới nhất, nếu không trả 409. Khi nội dung không đổi, thao tác sửa chỉ cập nhật miền nghiệp vụ của thuật ngữ mà không tạo revision; riêng bản hiện tại đã thu hồi sẽ tạo draft mới. Tên chuẩn trùng trong connection trả 409. Liên kết sai phạm vi, trùng, đối tượng không tồn tại hoặc metric không hoạt động trả 400; ID miền nghiệp vụ không tồn tại cũng trả 400. ID thuật ngữ không tồn tại trả 404. Pydantic trả 422 cho request sai cấu trúc.

`serving` là revision `approved` mới nhất nếu không có revision `revoked` mới hơn. Một draft mới không ảnh hưởng đến `serving`. Sau khi thu hồi, cần tạo và duyệt draft mới để thuật ngữ xuất hiện lại trong discovery. API chưa xác thực người gọi; không dùng trạng thái `approved` làm bằng chứng phê duyệt có phân quyền ở môi trường chưa tin cậy.
