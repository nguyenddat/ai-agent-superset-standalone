# Ghi lượt từ pipeline chat

**Trạng thái:** **đã triển khai** (service có từ trước; pipeline chat gọi service từ 2026-11-16). Service không commit; tầng pipeline chat (`backend/modules/text2sql/chat/turns.py`, `pipeline.py`) quyết định commit. Hợp đồng request và event phía client ở [luồng chat](../text2sql/chat-flow.md#hội-thoại-và-lịch-sử).

```python
from backend.modules.conversation.services import ConversationService, HistoryTurn, title_from_question

service = ConversationService(session)
service.start(connection_id, user_id, question) -> Conversation
service.get_owned(conversation_id, user_id) -> Conversation
service.begin_turn(conversation, question, retry_of=None, continued_from=None) -> ConversationTurn
service.complete_turn(turn, *, status, flow=None, answer=None, rewritten_question=None, steps=None, results=None,
                      rewrite=None, assumptions=None, pii=None, dataset_id=None, duration_ms=None, model=None,
                      error_code=None, error_message=None, clarification_question=None,
                      clarification_options=None, continuation=None) -> ConversationTurn
service.recent_history(conversation_id, limit=6) -> list[HistoryTurn]
service.continuable_turn(conversation, turn_id) -> ConversationTurn
```

## Trình tự trong pipeline chat

1. Route (session ngắn, chỉ đọc, trước khi stream): có `conversation_id` thì `get_owned` (404 nếu không thuộc người dùng) và so `connection_id` (khác thì 422). Tiếp tục chọn cách nối thì `continuable_turn`: lượt phải thuộc hội thoại (404 `Không tìm thấy lượt hỏi đáp.`), có `status=join_ambiguous` và `continuation` (409 `conversation_turn_not_continuable`).
2. Generator mở một session riêng cho việc ghi lượt: hội thoại mới thì `start` (tiêu đề từ câu hỏi); lấy `recent_history` (trừ khi tiếp tục chọn cách nối); `begin_turn` khóa dòng hội thoại, cấp `sequence` kế tiếp, ghi lượt `running` (kèm `continued_from` khi tiếp tục; lượt đó phải cùng hội thoại), cập nhật `last_message_at`, đặt tiêu đề nếu còn rỗng; **commit** ngay để lượt đang chạy hiện trong lịch sử và client nhận event `turn`.
3. Khi stream gặp `done` hoặc `error`: `complete_turn` với trạng thái cuối (không nhận `running`) và dữ liệu thu từ các event; **commit** trước khi gửi event đó. Client ngắt kết nối giữa chừng: `complete_turn(status="error", error_code="client_disconnected", ...)`. Lượt chỉ còn `running` khi tiến trình chết.

## Dữ liệu đã che PII

`results` và mọi trường JSON phải là dữ liệu **đã che PII** như event `data` gửi cho client; service không bao giờ nhận dữ liệu thô và không tự che. Service chuẩn hóa JSON (giá trị không phải JSON như `Decimal`, ngày giờ thành chuỗi) và giữ tối đa `CONVERSATION_MAX_STORED_ROWS` dòng cho mỗi mục có `rows`, đặt `stored_truncated`. `metric_usage` của câu hỏi gợi ý đọc `results[].kind == "metric"` và `results[].metric.name`, đúng cấu trúc payload `data` của luồng metric.

## Lịch sử gần đây

`recent_history` trả tối đa `limit` lượt gần nhất theo thứ tự thời gian, gồm lượt `answered`, `needs_clarification`, `cannot_answer`, `join_ambiguous`, `join_not_declared` (bỏ `running` và `error`); mỗi `HistoryTurn` có `question`, `rewritten_question`, `answer` cắt tối đa 500 ký tự (thêm `…`), `status` và `clarification_question`. Pipeline chat đưa danh sách này (dạng dict, đúng năm trường) vào context của `QuestionRewriteAgent` ([gói agent](../agent_package.md#questionrewriteagent-với-lịch-sử-hội-thoại)).

## Trạng thái tiếp tục

`complete_turn(continuation=...)` chỉ được pipeline truyền cho lượt `join_ambiguous`. Nội dung là những gì cần để chạy tiếp mà không gọi lại LLM (xem [luồng chat](../text2sql/chat-flow.md#chọn-cách-nối-ở-lượt-sau)). Cột này không có trong API. Lượt tiếp tục là lượt mới (`continued_from` trỏ về lượt cũ); lượt cũ không đổi.
