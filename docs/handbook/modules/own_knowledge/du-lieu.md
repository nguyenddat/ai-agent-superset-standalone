# Dữ liệu own knowledge

**Trạng thái:** migration `c6a8e2f41d90` đã triển khai sau expert rule.

| Bảng | Vai trò |
| --- | --- |
| `own_knowledge_clarifications` | Một lượt hỏi lại, thuộc connection và `user_id`; giữ câu hỏi gốc, loại còn thiếu, nguồn session/question, trạng thái `pending` / `confirmed` / `dismissed` và fingerprint chống gửi trùng. |
| `own_knowledge_proposals` | Các khái niệm Agent đề nghị làm rõ, gồm loại glossary/metric/expert rule, câu hỏi, tối đa 10 phương án và bảng ngữ cảnh nếu có. |
| `own_knowledge_entries` | Cách hiểu người dùng đã xác nhận, duy nhất theo `(connection_id, user_id, kind, normalized_name)`; giữ nguồn, version để chống ghi đè, trạng thái review và mục hệ thống được chuyển tới. |

Mọi khóa chính dùng UUID v7 như các module khác. Xóa connection xóa dữ liệu own knowledge liên quan. Xóa bảng ngữ cảnh đặt `table_id` về `NULL` nhưng giữ văn bản người dùng. `promoted_kind` và `promoted_id` là tham chiếu đa hình tới glossary/metric/expert rule; service kiểm tra đích khi tạo và khi quyết định có tiếp tục trả tri thức riêng cho Agent. Chúng không là khóa ngoại vật lý vì trỏ tới ba bảng khác nhau.

`review_status` có `pending`, `kept_own`, `promoted`. Người dùng sửa hoặc xác nhận lại cùng tên sẽ đưa mục đó về `pending`, xóa liên kết promotion cũ và tăng `version`; bản ghi hệ thống đã tạo trước đó không bị xóa. Nếu promotion tạo draft glossary/rule, Agent vẫn nhận mục riêng cho tới khi draft được duyệt. Bản system bị thu hồi hoặc không còn phục vụ khiến mục riêng hoạt động trở lại.

Khóa chống gửi trùng là duy nhất trong `(connection_id, user_id, idempotency_key)`. Cùng khóa và cùng nội dung trả lại câu hỏi cũ; cùng khóa với nội dung khác trả 409. Câu trả lời chỉ được chấp nhận một lần; retry cùng nội dung trả lại kết quả, câu trả lời khác trả 409. `confirmed_entry_ids` giữ ID các mục được ghi để retry vẫn trỏ đúng mục sau lần xác nhận khác. Các bước ghi của một request chạy trong một transaction.
