# Own Knowledge

**Trạng thái:** migration, API backend và giao diện admin đã triển khai. Chat runtime tự phát hiện phần thiếu và giao diện hỏi lại người dùng chưa có trong standalone.

Khi AI Agent không tìm thấy glossary, metric hoặc expert rule đủ để hiểu câu hỏi, Agent gọi API push một câu hỏi làm rõ và các phương án. Câu trả lời chỉ được ghi vào kho riêng sau khi người dùng xác nhận. Agent đọc lại các định nghĩa riêng theo `user_id` và connection cho những lượt hỏi sau; khi lập luận, Agent cần ưu tiên ngữ nghĩa hệ thống đã duyệt, rồi mới dùng cách hiểu riêng. Nội dung người dùng xác nhận là ngữ nghĩa dạng văn bản, không được tự xem là SQL hoặc rule hệ thống.

Admin có thể xem các định nghĩa riêng, đánh dấu **giữ riêng**, hoặc chuyển thành glossary, metric, expert rule bằng payload hệ thống do admin cung cấp. Tạo glossary/rule sinh draft; tri thức riêng vẫn hoạt động đến khi bản hệ thống được duyệt và còn hợp lệ. Metric tự tạo hoạt động ngay sau khi admin cung cấp biểu thức SQL và tạo thành công. Nếu bản hệ thống bị thu hồi, vô hiệu hóa hoặc mất liên kết, tri thức riêng lại được trả cho Agent.

Các route dùng `X-Own-Knowledge-Key` và hai secret khác nhau: `OWN_KNOWLEDGE_AGENT_KEY`, `OWN_KNOWLEDGE_ADMIN_KEY` (mỗi khóa ít nhất 32 ký tự). Chỉ đặt chúng ở server; Agent phải lấy `user_id` từ phiên người dùng đã xác thực, không nhận ID do trình duyệt tự khai. Ứng dụng standalone chưa có hệ thống tài khoản riêng, nên ranh giới người dùng dựa trên dịch vụ Agent đáng tin cậy. Admin API yêu cầu `reviewer_id` để ghi nhận người thực hiện, nhưng giá trị này cũng do dịch vụ admin đáng tin cậy cung cấp.

Xem [dữ liệu](du-lieu.md), [API của AI Agent](api-agent.md) và [API admin](api-admin.md).
