# Ghi lượt từ pipeline chat

**Trạng thái:** service **đã triển khai**. Route chat mới `POST /api/v1/text2sql/chat` (`ChatService` trong `backend/modules/text2sql/services/chat_service.py`) ghi lượt qua service này từ ngày 2026-11-19, khi request có `user_id`. Từ ngày 2026-11-20 route stream `POST /api/v1/text2sql/chat/stream` ghi lượt theo đúng trình tự này. Từ ngày 2026-11-20 route ghi lượt hỏi lại (`needs_clarification`, `continuation`) và lượt chạy tiếp (`continued_from`); xem [hỏi lại và chạy tiếp](../text2sql/api-chat.md#hỏi-lại-và-chạy-tiếp). Service không commit; tầng gọi quyết định commit.

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

## Trình tự trong route chat

Mọi bước ghi chạy trên một thread với một `Session`, **ngoài** graph LangGraph (các nhánh song song của graph không chạm `Session`): với `/chat` là thread và `Session` của request; với `/chat/stream` là thread riêng của stream, mở `Session` riêng vì dependency của request bị dọn trước khi stream xong. Bước 1 đến 3 là `ChatService.prepare`, bước 4, 5 là `ChatService.execute`; với stream, bước 3 xong thì gửi event `turn`.

1. Có `conversation_id` thì `get_owned` (404 `conversation_not_found` nếu không thuộc `user_id`) và so `connection_id` (khác thì 400 `text2sql_invalid_request`), rồi `recent_history(conversation_id, 6)`. Có `resume_id` thì thay vì đọc lịch sử: khóa dòng checkpoint, kiểm tra chủ sở hữu, gọi `continuable_turn(conversation, turn_id của lượt đang chờ)` và xóa dòng (commit cùng `begin_turn`). Bước này chạy trước mọi lời gọi LLM.
2. `Text2SqlAgentService.start` (giải mã URI, đọc catalog). Lỗi ở đây (connection tạm dừng, URI hỏng) trả lỗi request và **không** ghi lượt.
3. Hội thoại mới thì `start` (tiêu đề từ câu hỏi); `begin_turn` (chạy tiếp thì `continued_from` là lượt đang chờ) khóa dòng hội thoại, cấp `sequence` kế tiếp, ghi lượt `running`, cập nhật `last_message_at`; **commit** ngay để lượt đang chạy hiện trong lịch sử.
4. Chạy graph. Xong thì `complete_turn` với trạng thái cuối (graph dừng để hỏi lại thì lưu checkpoint rồi ghi `needs_clarification`) và **commit** trước khi trả response.
5. Graph ném lỗi (LLM, embedding, Qdrant, database nguồn, lỗi bất ngờ): `rollback` phần dở dang, `complete_turn(status="error", error_code=..., error_message=...)`, **commit**, rồi ném lại lỗi để route trả mã lỗi như cũ. `error_code` là `code` của lỗi ứng dụng (ví dụ `text2sql_agent_unavailable`) hoặc `internal_error`; `error_message` là thông điệp của lỗi ứng dụng hoặc chỉ tên lớp lỗi với lỗi bất ngờ (không lưu chi tiết có thể chứa URI hay SQL). Không ghi được lỗi thì chỉ log; lượt khi đó còn `running`. Đang chạy tiếp mà lỗi thì dòng checkpoint được ghi lại để người dùng gửi lại câu trả lời.

Với `/chat/stream`, client ngắt kết nối giữa chừng thì lần ghi event tiếp theo ném `Text2SqlClientDisconnected` và bước 5 ghi lượt `error` với `error_code="client_disconnected"` (đang chạy tiếp thì checkpoint được ghi lại). Lượt chỉ còn `running` khi tiến trình chết hoặc không ghi được lỗi.

## Dữ liệu route chat lưu

| Trường | Nội dung |
| --- | --- |
| `answer` | Câu trả lời cuối (`ChatOut.answer`). |
| `rewritten_question` | `preprocess.rewritten_question`. |
| `flow` | `metric` nếu có kết quả `query_metric`; `dataset` nếu chỉ có kết quả `run_sql`; còn lại `none`. |
| `rewrite` | `rewritten_question`, `is_split`, `execution_mode`, `stages`, và mỗi câu đơn: `position`, `question`, `depends_on`, `question_type`, `business_concepts`, `metrics` (tên các metric được truy hồi). Không lưu toàn bộ tri thức truy hồi. |
| `steps` | Mỗi câu đơn: `position`, `question`, `answer`, `exhausted`, `steps` (mỗi bước: `tool`, `arguments`, `sql`, `row_count`, `truncated`, `notes`, `error`; bước có kết quả thêm `result_id`, `explanations` (bỏ khóa rỗng), `chart`, `chart_source`, `display`; không có dòng dữ liệu). |
| `results` | Mỗi bước `query_metric`, `run_sql`, `get_column_values` thành công: `position`, `kind` (`metric`, `sql`, `column_values`), `tool`, `sql`, `columns`, `rows`, `row_count`, `truncated`; mục `metric` có thêm `metric.name` để `metric_usage` đếm. Bước `query_metric`/`run_sql` có thêm `result_id`, `fields`, `chart`, `chart_source`, `chart_types`, `display` (biểu đồ cuối cùng của agent, kể cả sau `make_chart`). |
| `duration_ms` | Thời gian từ `begin_turn` tới khi xong graph. |
| `clarification_question`, `clarification_options` | Chỉ khi `status = needs_clarification`: câu hỏi lại (cũng là `answer`) và các lựa chọn agent đưa ra (tối đa 8). Nhiều câu đơn cùng hỏi lại thì gộp thành một câu hỏi đánh số, không có lựa chọn. |
| `continuation` | Chỉ khi `status = needs_clarification`: `{"kind": "text2sql_clarification", "resume_id", "expires_at"}`. Bản thân checkpoint nằm ở `technical.text2sql_chat_checkpoints`, không ở cột này. |

Lượt `needs_clarification` chỉ lưu `steps`, `results` của các câu đơn đã xong. Lượt chạy tiếp lưu đầy đủ mọi câu đơn. `pii`, `assumptions`, `model`, `dataset_id` để trống.

## Dữ liệu và PII

Quy tắc chung: `results` lưu đúng dữ liệu đã gửi cho client, không hơn. Service chuẩn hóa JSON (giá trị không phải JSON như `Decimal`, ngày giờ thành chuỗi) và giữ tối đa `CONVERSATION_MAX_STORED_ROWS` dòng cho mỗi mục có `rows`, đặt `stored_truncated`. `metric_usage` của câu hỏi gợi ý đọc `results[].kind == "metric"` và `results[].metric.name`.

Từ khi gỡ presidio (2026-11-19), route chat **không che PII**: dòng trong `ChatOut.answers[].steps[].rows` là dữ liệu thô của database nguồn, nên `results` lưu dòng thô (đã cắt số dòng). Cột chứa PII chỉ được đánh dấu `contains_pii` trong catalog để agent biết. Cần bổ sung che PII (trước cả response lẫn bản lưu) trước khi dùng với dữ liệu thật có PII.

## Lịch sử gần đây

`recent_history` trả tối đa `limit` lượt gần nhất theo thứ tự thời gian, gồm lượt `answered`, `needs_clarification`, `cannot_answer`, `join_ambiguous`, `join_not_declared` (bỏ `running` và `error`); mỗi `HistoryTurn` có `question`, `rewritten_question`, `answer` cắt tối đa 500 ký tự (thêm `…`), `status` và `clarification_question`. Route chat đưa danh sách này (6 lượt) vào task `rewrite` thay cho `chat_history` client gửi.

## Trạng thái tiếp tục

`complete_turn(continuation=...)` dùng cho lượt chờ người dùng: `join_ambiguous` của pipeline cũ, và `needs_clarification` của route chat text2sql (chỉ giữ `resume_id`, `expires_at`; checkpoint của graph nằm ở bảng kỹ thuật của text2sql). Cột này không có trong API. `continuable_turn` nhận lượt có trạng thái trong `CONTINUABLE_STATUSES` (`join_ambiguous`, `needs_clarification`) và `continuation` là object, ngược lại 409 `conversation_turn_not_continuable`. Lượt tiếp tục là lượt mới (`continued_from` trỏ về lượt cũ); lượt cũ không đổi.
