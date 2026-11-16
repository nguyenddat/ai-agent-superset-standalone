# Luồng hỏi đáp `ask_data`

**Trạng thái: đã triển khai** dưới dạng MCP tool [`ask_data`](../../mcp-server.md) (mã ở `backend/modules/text2sql/chat/`). Khi `no_metric`, `ask_data` không tự chạy truy vấn nhiều bảng: thông điệp `fallback` hướng agent sang `find_fields` → `plan_join` → `query_dataset` (đã triển khai, xem [find-fields-join.md](find-fields-join.md)).

MCP tool `ask_data` vẫn tồn tại độc lập với route chat HTTP [`POST /api/v1/text2sql/chat`](chat-flow.md); route chat dùng lại các bước công khai của `AskService` (`rewrite`, `candidates`, `plan`, `fallback`), còn `prepare` ghép đúng các bước đó nên `ask_data` giữ nguyên hành vi.

Một lời gọi `ask_data(connection_id, question, user_id?)` chạy một luồng cố định phía server. Client (agent) không phải tự ghép chuỗi tool.

## Các bước

1. **Truy hồi theo câu hỏi gốc.** Embed câu hỏi đúng một lần, tìm `glossary`, `expert_rule` (và `own_knowledge` nếu có `user_id`) bằng `TopicSearchService`, rồi mở rộng một bước theo liên kết (thuật ngữ sang quy tắc và ngược lại).
2. **Viết lại câu hỏi (luôn chạy, một lượt).** Một lần gọi LLM với prompt cố định (`question_rewrite_prompt`) cùng câu hỏi gốc, thuật ngữ, quy tắc, tri thức riêng và tên metric liên kết. Kết quả: câu hỏi diễn đạt bằng ngôn ngữ thường theo thuật ngữ và quy tắc, kèm danh sách id đã dùng. Id không có trong đầu vào bị bỏ; câu rỗng thì giữ câu gốc.
3. **Tìm metric.** Ứng viên là metric liên kết với thuật ngữ đã chọn (không qua ngưỡng, vì liên kết do người quản trị duyệt), cộng top 5 metric tìm theo câu hỏi viết lại rồi chấm lại bằng Jev; chỉ giữ metric có điểm từ `TEXT2SQL_ASK_METRIC_MIN_SCORE` (mặc định 0,6) trở lên. Không còn ứng viên nào thì trả `no_metric` ngay, không gọi thêm LLM. Nếu Jev lỗi thì dùng danh sách chưa lọc và để bước lập plan quyết định. Ngưỡng 0,6 do người dùng chọn, chưa hiệu chỉnh bằng dữ liệu thật; ngưỡng cao có thể bỏ sót metric đúng khi câu viết lại dài.
4. **Lập plan (một lượt LLM).** Prompt `query_plan_prompt` nhận câu hỏi viết lại, ứng viên metric và cột của bảng; trả metric, `group_by`, thời gian, bộ lọc, sắp xếp. Một câu hỏi có thể sinh nhiều truy vấn (nhiều đại lượng). LLM có thể trả `no_metric` hoặc `needs_clarification`.
5. **Dựng truy vấn bằng code.** Tên cột được ánh xạ về id (theo tên kỹ thuật hoặc tên hiển thị), giá trị ép kiểu theo cột, rồi dùng chung bộ dựng và chạy của [`query_metric`](query-metric.md) (chỉ đọc, giới hạn thời gian, che PII).
6. **Điều kiện quy tắc chuyên gia áp dụng tự động.** Mọi điều kiện của quy tắc liên kết với metric được thêm bằng code, mô hình không có cách bỏ. Chỉ khi câu hỏi tự lọc cùng cột thì điều kiện quy tắc nhường và được ghi vào `rules[].overridden`. Quy tắc chỉ áp dụng cho metric mà nó liên kết.
7. **Đồng ý PII.** Nếu truy vấn đụng cột PII, tool hỏi người dùng qua elicitation trước khi chạy (kết quả chuẩn bị được cache 120 giây).

## Kết quả

`status`: `answered`, `no_metric`, `needs_clarification`. Kèm `rewrite` (câu gốc, câu viết lại, mục đã dùng), `queries[]` (metric, `source`, `rules`, kết quả, SQL, tham số), `plan_analysis`, `assumptions`, `message`. Với `no_metric`, `fallback` có `status: not_implemented` và tối đa ba bảng ứng viên.

## Prompt

Hai agent `QuestionRewriteAgent` và `QueryPlanAgent` nằm ở `backend/agent_package/agents/` (kèm schema đầu ra `RewriteDraft`, `PlanDraft`; hàm gọi chung `invoke_structured` nằm ở `get_chat_models.py`, `AskService` nhận hai agent qua `rewriter` và `planner`). Hai prompt là hằng số cố định trong `backend/agent_package/prompts/`, dùng few-shot ở các lĩnh vực không liên quan dữ liệu thật (nhân sự, giáo dục, bệnh viện, thời tiết) và chain of thought có cấu trúc: trường `analysis` đứng đầu schema nên mô hình phải suy luận từng bước trước khi quyết định. Prompt viết lại cấm chọn bảng, cột.

## Quyết định thiết kế

- **Một lượt, không retry** ở mọi bước; lỗi tên cột hoặc id trả `Text2SqlInvalidRequest` gộp mọi truy vấn lỗi kèm danh sách cột hợp lệ.
- Chỉ dùng model cấu hình ở `OPENROUTER_MODEL` (mặc định `openai/gpt-6-luna`) cho cả hai lần gọi (viết lại và lập plan). LLM lỗi hoặc không có khóa thì trả `AgentUnavailableError` (503, mã `agent_unavailable`).
- Quy tắc là phần của luồng, không phải lựa chọn của agent: lỗi phổ biến khi agent tự ghép tool là bỏ qua quy tắc và cho số sai mà không báo.

## Kiểm thử

`tests/test_text2sql_ask.py` dùng LLM giả và dữ liệu tổng hợp. Thử nghiệm với model thật trên hai bộ dữ liệu tổng hợp (bán lẻ và vận chuyển, mỗi bộ 10 câu): lượt cuối đạt 10/10 cho cả hai; lượt chạy lại sau đó đạt 10/10 và 9/10. Ca lỗi: câu hỏi nhiều đại lượng, quy tắc của một metric bị mô hình áp sang metric kia dưới dạng bộ lọc tường minh. Hai bộ này đã dùng để chỉnh prompt nên không còn là bộ kiểm độc lập; cần bộ dữ liệu mới để đo thật.

## Giới hạn

- Hai lần gọi LLM nối tiếp (khoảng 9 đến 16 giây mỗi câu hỏi).
- `user_id` và `connection_id` do client cung cấp, không xác thực ([MCP server](../../mcp-server.md)).
- Giá trị lọc phải lấy được từ mô tả cột; không có NER cho tên riêng.
- `ask_data` không tự chạy nhánh nhiều bảng; với `no_metric` nó gợi ý bảng và chỉ tới `find_fields`, `plan_join`, `query_dataset` để agent gọi tiếp.
