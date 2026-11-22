# Hỏi đáp: `POST /api/v1/text2sql/chat` và `POST /api/v1/text2sql/chat/stream`

**Trạng thái:** **đã triển khai** một lượt hỏi đáp đầy đủ, ngày 2026-11-19: tiền xử lý (viết lại, tách câu, phân loại, truy hồi top K), agent truy vấn database nguồn và trả lời từng câu đơn, tổng hợp câu trả lời, ghi lượt vào [`conversation`](../conversation/README.md) khi có `user_id`. Hỏi lại khi thiếu thông tin (dừng graph và chạy tiếp từ checkpoint) **đã triển khai** ngày 2026-11-20. Stream từng bước của graph qua SSE (`/chat/stream`, mục [Stream](#stream-post-apiv1text2sqlchatstream)) **đã triển khai** ngày 2026-11-20. Stream chữ của câu trả lời (`answer_delta`, `answer_reset`), event báo công cụ bắt đầu chạy (`tool_started`), `synthesize_started` và bước tổng hợp viết Markdown thuần **đã triển khai** ngày 2026-11-20 theo [thiết kế](../../../reports/2026-11-20-thiet-ke-tra-loi-stream-bieu-do.md) mục 3. Chuẩn hóa thực thể và thời gian bằng code là **dự kiến**. Truy vấn trên PostgreSQL thật chưa được kiểm thử tự động; test dùng runner giả.

Luồng thiết kế đầy đủ nằm ở mục 7 của [taxonomy câu hỏi](../../../reports/2026-11-19-taxonomy-cau-hoi-benchmark.md).

## Request

```json
{
  "connection_id": "uuid",
  "user_id": "user-1",
  "conversation_id": "uuid hoặc null",
  "resume_id": "uuid hoặc null",
  "question": "Thành phố nào mưa nhiều nhất tuần qua, nhiệt độ ở đó hôm qua bao nhiêu?",
  "chat_history": []
}
```

- `question`: 1 đến 2000 ký tự sau khi bỏ khoảng trắng hai đầu.
- `user_id`: tùy chọn. Có `user_id` thì tìm tri thức riêng của người dùng và **ghi lượt** vào `conversation` (mục dưới).
- `conversation_id`: tùy chọn; chỉ hợp lệ khi có `user_id` (thiếu thì 422). Bỏ trống thì mỗi request có `user_id` mở một hội thoại mới; muốn hỏi tiếp trong cùng hội thoại thì gửi lại `conversation_id` của response trước.
- `resume_id`: tùy chọn; gửi `resume_id` của response `needs_clarification` trước đó để **chạy tiếp** lượt đang chờ, khi đó `question` là câu trả lời của người dùng cho câu hỏi lại (mục [Hỏi lại và chạy tiếp](#hỏi-lại-và-chạy-tiếp)). Lượt thuộc hội thoại thì phải gửi kèm đúng `user_id` và `conversation_id`.
- `chat_history`: tối đa 50 lượt, cũ đến mới, mỗi lượt có `question` và `answer` (câu trả lời cuối cùng của bot, lượt hỏi lại thì là câu hỏi lại) như `HistoryTurn` của `conversation`; trường khác bị bỏ qua. **Chỉ dùng khi không có `user_id`** (chế độ không lưu, ví dụ benchmark): service gửi 6 lượt cuối cho LLM và cắt `answer` còn 500 ký tự. Có `user_id` thì `chat_history` bị bỏ qua: lịch sử lấy từ các lượt đã lưu của hội thoại (`recent_history`, 6 lượt), hội thoại mới thì rỗng. Client không sửa được lịch sử mà LLM thấy.

## Ghi lượt vào `conversation`

Chỉ khi có `user_id`; không có thì không ghi gì và `conversation_id`, `turn_id` của response là `null`. Mọi thao tác ghi chạy trên một thread duy nhất với một `Session` (thread của request với `/chat`, thread riêng của stream với `/chat/stream`), ngoài graph (nhánh song song không dùng `Session`). `ChatService.chat` gồm `prepare` (bước 1 đến 3) và `execute` (bước 4, 5):

1. Có `conversation_id`: hội thoại phải thuộc `user_id` (404 `conversation_not_found`) và cùng `connection_id` (400 `text2sql_invalid_request`); đọc `recent_history`. Có `resume_id` thì nhận checkpoint (mục dưới) thay cho đọc lịch sử. Các kiểm tra này chạy trước mọi lời gọi LLM.
2. `Text2SqlAgentService.start`. Lỗi ở bước này (connection tạm dừng, URI hỏng) trả lỗi mà không ghi lượt.
3. Hội thoại mới thì `start` (tiêu đề từ câu hỏi). `begin_turn` ghi lượt `running` (khi chạy tiếp thì có `continued_from` trỏ về lượt đang chờ), rồi commit.
4. Chạy graph. Xong thì `complete_turn` (`answered`, hoặc `needs_clarification` khi graph dừng ở câu hỏi lại, kèm `clarification_question`, `clarification_options`, `continuation`), commit, trả response.
5. Graph lỗi: rollback, `complete_turn(status="error")` với `error_code` của lỗi (ví dụ `text2sql_agent_unavailable`, lỗi bất ngờ là `internal_error`), commit, rồi trả mã lỗi như bảng Lỗi. Đang chạy tiếp mà lỗi thì checkpoint được ghi lại như cũ để người dùng gửi lại câu trả lời.

Với `/chat/stream`: sau bước 3 stream gửi event `turn`; client ngắt kết nối giữa chừng thì bước 5 ghi `error_code = client_disconnected`.

Dữ liệu lưu (`answer`, `rewritten_question`, `flow`, `rewrite`, `steps`, `results`, `duration_ms`) mô tả ở [ghi lượt từ pipeline](../conversation/ghi-luot-tu-pipeline.md#dữ-liệu-route-chat-lưu). `results` giữ tối đa `CONVERSATION_MAX_STORED_ROWS` dòng mỗi kết quả và **chưa che PII**, giống dòng trong response.

## Hỏi lại và chạy tiếp

Câu hỏi thiếu thông tin bắt buộc mà không có cách hiểu hợp lý (metric mơ hồ giữa nhiều ứng viên, đối tượng mơ hồ, bảng trộn số liệu thật với dự báo mà không nói khoảng thời gian) thì graph **dừng** bằng `interrupt()` của LangGraph và trả câu hỏi lại. Request sau mang câu trả lời chạy tiếp đúng lượt đó từ checkpoint (`Command(resume=...)`): không chạy lại `preprocess`, không trả lời lại các câu đơn đã xong, và agent của câu đang chờ tiếp tục đúng cuộc hội thoại công cụ của nó.

Ai quyết định hỏi lại:

- Agent của từng câu đơn gọi công cụ `ask_user(question, options)`. Prompt giữ nguyên tắc: ưu tiên giả định hợp lý và nói rõ, chỉ hỏi lại khi không có cách hiểu hợp lý; `options` lấy từ knowledge hoặc dữ liệu (nhãn metric, giá trị cột). Mỗi câu đơn hỏi lại tối đa 2 lần (`MAX_CLARIFICATIONS`); quá thì công cụ báo lỗi để agent tự chọn giả định.
- Bước `preprocess` không hỏi lại (prompt `rewrite` không đổi).

Cách dừng mà không làm lại việc tốn kém:

1. `ask_user` ném `AgentPause`; vòng `tool_agent` dừng ngay (không gọi `interrupt()` trong graph con) và trả `ToolAgentPause` gồm toàn bộ messages, số lượt đã dùng và `tool_call_id` của lời gọi đang chờ.
2. Nút `answer_question` trả `PendingQuestion` (câu hỏi lại, `options`, `ToolAgentPause`, các bước đã chạy) vào khóa `pending` của state, **không** gọi `interrupt()`. Vì vậy khi chạy tiếp, LangGraph không chạy lại vòng agent đã tốn LLM.
3. `dispatch` vẫn gửi mọi câu khác đã đủ điều kiện (câu độc lập chạy hết; câu phụ thuộc câu đang chờ thì chờ). Hết việc mà còn `pending` thì sang nút `clarify`: nút nhỏ này gọi `interrupt()` **một lần** cho mọi câu đang chờ. Nhiều nhánh song song cùng hỏi lại thì gộp thành một câu hỏi đánh số, không kèm `options`; một câu thì giữ `options` của nó.
4. Chạy tiếp: `clarify` chạy lại (rẻ), nhận câu trả lời, ghi vào `replies` cho mọi câu đang chờ; `dispatch` gửi lại các câu đó kèm `PendingQuestion` và câu trả lời. `AgentRun.answer` nối `ToolMessage` `{"user_reply": ...}` vào messages cũ rồi chạy tiếp vòng agent; bước `ask_user` trong `steps` có ghi chú `Người dùng trả lời: ...`. Agent có thể hỏi lại lần nữa; graph lại dừng.

Checkpoint:

- Mỗi lần chạy graph dùng `SnapshotSaver` (lớp con của `InMemorySaver`) với `durability="exit"`, nên chỉ ghi checkpoint khi graph dừng hoặc kết thúc, không ghi sau từng bước. Graph dừng thì `export_thread` đóng gói checkpoint, writes và blobs của thread bằng serializer msgpack của LangGraph (`JsonPlusSerializer` với danh sách lớp được phép: các schema của text2sql, `PendingQuestion`, `ToolAgentPause`; không dùng pickle), rồi `ChatService` lưu vào bảng `technical.text2sql_chat_checkpoints` ([dữ liệu](du-lieu.md#technicaltext2sql_chat_checkpoints)) trên thread của request. Chạy tiếp thì nạp lại vào một `SnapshotSaver` mới (`import_thread`). Nhờ vậy checkpoint sống qua nhiều request, nhiều worker và khi backend khởi động lại; nhánh của graph không chạm `Session`.
- Vì sao không dùng `langgraph-checkpoint-postgres`: thư viện tự tạo bảng bằng `setup()` (không theo Alembic, không nằm trong schema `technical`), cần pool kết nối riêng và không có cơ chế hết hạn. `MemorySaver` thuần không đủ vì mất khi restart và không chia sẻ giữa các worker.
- `resume_id` là id ngẫu nhiên (UUID v4) của thread, cũng là khóa chính của dòng checkpoint. Lần chạy tiếp mà lại dừng thì dùng lại cùng `resume_id`, hạn mới.
- Nhận checkpoint: khóa dòng (`FOR UPDATE`), kiểm tra còn hạn và cùng `connection_id`, `user_id`, `conversation_id` (sai thì 404 `text2sql_clarification_not_found`, không lộ dòng có tồn tại hay không); lượt thuộc hội thoại thì `continuable_turn` kiểm tra lượt đang chờ còn `needs_clarification` (409 `conversation_turn_not_continuable` nếu không); rồi xóa dòng trong cùng transaction với `begin_turn`. Hai request cùng `resume_id` thì request sau nhận 404. Chạy tiếp lỗi thì dòng được ghi lại.
- Hạn: `TEXT2SQL_CLARIFICATION_TTL_MINUTES` (mặc định 1440 phút). Mỗi lần lưu checkpoint mới, các dòng đã hết hạn bị xóa. Xóa hội thoại hoặc lượt đang chờ thì checkpoint bị xóa theo (`ON DELETE CASCADE`).

Ghi lượt khi có `user_id`: lượt dừng được ghi `needs_clarification`, `answer` là câu hỏi lại, kèm `clarification_question`, `clarification_options`, `continuation = {"kind": "text2sql_clarification", "resume_id", "expires_at"}`; `steps`, `results` chỉ gồm các câu đơn đã xong. Câu trả lời của người dùng tạo **lượt mới** (`question` là câu trả lời, `continued_from` là lượt đang chờ) và lượt mới này lưu câu trả lời đầy đủ, `steps`, `results` của mọi câu đơn. Lượt cũ giữ nguyên. Không có `user_id` thì checkpoint vẫn được lưu (`user_id`, `conversation_id` rỗng) và `resume_id` là khóa duy nhất để chạy tiếp.

Client: khi response có `status = needs_clarification`, hiển thị `clarification_question` và các `options` (nếu có) làm lựa chọn nhanh; câu người dùng gõ tiếp theo gửi kèm `resume_id` (và `conversation_id`). Người dùng bỏ qua câu hỏi lại mà hỏi câu khác thì gửi không có `resume_id`; checkpoint cũ hết hạn theo TTL. Với `/chat/stream`, `resume_id` có trong event `clarification` và `done`. API hội thoại trả `resume_id` và `resume_expires_at` của lượt đang chờ còn hạn ([API lượt hỏi đáp](../conversation/api-luot-hoi-dap.md)), nên lượt chờ mở lại từ lịch sử vẫn chạy tiếp được.

## Luồng xử lý (`ChatService.chat`)

Route kiểm tra `connection_id` tồn tại (404 nếu không). `ChatService.chat` gọi `Text2SqlAgentService.start` trước khi gọi LLM: giải mã URI của connection (connection tạm dừng thì 400), đọc một lần bản chụp catalog (`AgentCatalog`: bảng, cột, metric, quy tắc chuyên gia đang hiệu lực) và tạo bộ nhớ đệm truy vấn cho cả lượt. Sau đó chạy graph LangGraph trong `services/chat_graph.py`:

```text
preprocess ─► dispatch ─(Send cho mỗi câu đã đủ câu phụ thuộc)─► answer_question ─┐
                 ▲                                                                 │
                 ├─────────────────────────────────────────────────────────────────┘
                 ├─(hết câu, còn câu chờ hỏi lại)─► clarify (interrupt) ─┐
                 │◄──────────────────────── (chạy tiếp) ─────────────────┘
                 └─(hết câu)─► synthesize ─► END
```

1. `preprocess` (`ChatService.preprocess`):
   - `get_chat_completion("rewrite", ...)` với `question` và `chat_history`: trả câu viết lại và `sub_questions`. `sub_questions` chỉ có khi câu cần tách thành từ hai câu đơn trở lên (kèm `depends_on`); không cần tách thì hệ thống dùng chính `rewritten_question`.
   - Với các câu trong `questions`, chạy song song: `intent_classify` cho từng câu trong thread pool (tối đa 4 lời gọi cùng lúc); trong lúc đó thread chính embed mọi câu bằng **một** lời gọi, rồi lấy top 5 metric (`RetrievalService`) và top 5 mỗi topic `table`, `column`, `glossary`, `expert_rule` (`TopicSearchService`), cùng `own_knowledge` khi có `user_id`. Không rerank. Truy hồi chạy trên thread chính vì `Session` của SQLAlchemy không dùng chung giữa các thread.
   - Câu có `depends_on` vẫn được phân loại và truy hồi vì chỗ cần kết quả được ghi là `<kết quả câu N>`; kết quả này dùng lại, không tính lại khi câu trước đã có đáp án.
2. `dispatch` gửi (`Send`) mọi câu chưa trả lời mà các câu nó phụ thuộc đã có đáp án. Các câu cùng lượt chạy song song trên thread của LangGraph; lượt sau bắt đầu khi cả lượt trước xong, nên một câu có thể chờ câu cùng tầng mà nó không phụ thuộc.
3. `answer_question` gọi `AgentRun.answer` cho một câu đơn (mục dưới). Câu phụ thuộc nhận `prior_results`: câu hỏi, câu trả lời và bảng kết quả của bước truy vấn thành công cuối cùng ở các câu nó phụ thuộc. Agent hỏi lại thì câu đó vào `pending` thay vì `answers`.
4. `clarify`: chỉ chạy khi không còn câu nào gửi được mà vẫn có câu đang chờ; dừng graph bằng `interrupt()` (mục [Hỏi lại và chạy tiếp](#hỏi-lại-và-chạy-tiếp)).
5. `synthesize`: câu không tách thì dùng thẳng câu trả lời của agent; câu đã tách thì `ChatService._synthesize` gọi `get_chat_text(synthesize_prompt, params, on_text)` (`backend/agent_package/get_chat_text.py`) để ghép các câu trả lời con thành câu trả lời cho `rewritten_question`. `params` gồm `question` (`rewritten_question`), `today` (`YYYY-MM-DD (thứ ...)`, lấy từ `AgentRun.today`) và `answers[]` (`position`, `question`, `question_type`, `answer`). Mô hình trả **Markdown thuần**, không còn JSON và parser; prompt không đi qua `ChatPromptTemplate` nên dấu `{}` trong prompt và dữ liệu không bị coi là biến. Chuỗi rỗng thành `"Chưa trả lời được câu hỏi này."`; lỗi gọi LLM (`OpenAIError`) thành `Text2SqlAgentUnavailable` (503). Route JSON gọi `invoke`; route stream gọi `stream` và phát chữ qua `answer_delta` (mục [Stream](#stream-post-apiv1text2sqlchatstream)).

Nhánh song song không dùng `Session` của request: chúng chỉ đọc bản chụp catalog, gọi LLM và mở kết nối riêng tới database nguồn cho mỗi truy vấn.

## Agent trả lời một câu đơn

`AgentRun.answer` gọi `run_tool_agent` ([gói agent dùng chung](../agent_package.md)) với prompt `prompt_text2sql_agent.py`. Đầu vào của mô hình là JSON gồm `today` (ngày hiện tại theo `TEXT2SQL_TIMEZONE`, kèm thứ), `dates` (các khoảng tính sẵn từ `today` dạng `{"from", "before"}` nửa mở: `yesterday`, `last_7_days` (7 ngày tính đến hôm qua), `last_week`, `this_week` (tuần bắt đầu thứ Hai), `this_month`, `last_month`, mỗi khoảng kèm `label` để nói với người dùng, ví dụ `"hôm qua (thứ Năm, 19/11)"`; prompt yêu cầu dùng đúng các khoảng này thay vì tự tính), `question`, `question_type`, `business_concepts`, `knowledge` (rút gọn: metric có `id`, `name`, `label`, `description`; các topic khác có `name`, `text`) và `prior_results` (kèm `fields` và dòng đã định dạng của kết quả cuối).

Prompt (`prompt_text2sql_agent.py`) quy định văn phong câu trả lời: xưng "tôi", kết luận ở câu đầu, 1 đến 3 câu; chép số đúng như `rows` đã định dạng, đơn vị lấy từ `fields`; ngày nói theo `label` của `dates`, không ghi năm trùng năm hiện tại, không viết `YYYY-MM-DD`; không dùng tên cột, dấu gạch dưới, dấu `` ` ``, không nhắc "bản ghi", "metric", SQL, quy tắc; giả định tối đa một mệnh đề ở câu đầu. Những chi tiết về cách tính được hiển thị riêng từ `explanations` (mục dưới). Mục `# BIỂU ĐỒ` hướng dẫn khi nào đổi đề xuất biểu đồ và cấm hai trục y.

Agent kết hợp SQL do code dựng và SQL do LLM viết:

| Công cụ | Việc làm |
| --- | --- |
| `get_metric` | Định nghĩa metric, bảng, danh sách cột, quy tắc chuyên gia gắn với metric. |
| `get_table` | Mô tả bảng, độ chi tiết một dòng, các cột (kiểu, tên hiển thị, đồng nghĩa, `contains_pii`), metric của bảng. |
| `get_expert_rule` | Điều kiện, ngoại lệ, ví dụ của một quy tắc. |
| `get_column_values` | Giá trị phân biệt của một cột văn bản (tìm theo chuỗi, tối đa 50) để lọc đúng chính tả; `ILIKE` không thấy thì so khớp lại không phân biệt dấu; từ chối cột chứa PII. |
| `query_metric` | Code dựng SQL từ metric (`build_metric_query`): `filters`, `group_by`, `time_grain` (`DATE_TRUNC` theo ngày, tuần, tháng, quý, năm), `order_by`, `limit`, `skip_rules`, `assumption` (giả định bằng lời thường, tối đa 300 ký tự), `chart` (spec biểu đồ tùy chọn). |
| `run_sql` | Chạy một câu SELECT do LLM viết, sau khi qua `validate_select`. Tham số: `sql`, `purpose` (lời thường cho người dùng đọc, thành mục "Cách tính"), `assumption`, `rules_applied` (tên quy tắc chuyên gia đã tự áp, tối đa 10), `labels` (nhãn tiếng Việt cho cột tự đặt tên, tối đa 20), `chart`. |
| `make_chart` | Đặt hoặc đổi biểu đồ cho một kết quả đã có: `result_id`, `chart` (spec JSON, xem [biểu đồ](bieu-do.md)). Hợp lệ thì ghi bước `make_chart` và cập nhật bước dữ liệu; sai thì `ToolError` liệt kê các lỗi V*. Mô tả công cụ chỉ liệt kê các loại đang bật (`TEXT2SQL_CHART_TYPES_ENABLED`). |
| `ask_user` | Dừng và hỏi lại người dùng: `question` (tối đa 500 ký tự), `options` (tối đa 8, bỏ trùng). Kết quả trả về khi chạy tiếp là `{"user_reply": ...}`. |

`query_metric`:

- Kiểm biểu thức metric (chỉ các nút biểu thức và hàm tổng hợp được phép, cột phải thuộc bảng của metric) và kiểu giá trị lọc theo kiểu cột (số, ngày ISO, boolean, văn bản; `contains` dùng `ILIKE` có thoát `%`, `_`).
- Biểu thức metric được dùng `EXTRACT` (ví dụ `EXTRACT(EPOCH FROM ...)`). Gom `day`, `week`, `month` trên cột kiểu `date` thì ép kết quả `DATE_TRUNC` về `date`.
- Giá trị lọc văn bản (`equals`, `not_equals`, `in`, `not_in`, `contains`, `not_contains`) được đối chiếu với giá trị phân biệt thật của cột, không phân biệt dấu và hoa thường (`Đà Nẵng` khớp `Da Nang`). Khớp duy nhất thì đổi sang giá trị thật và ghi chú; `contains` khớp thì đổi thành `in`. Không khớp thì báo lỗi kèm các giá trị gần giống, trừ khi mẫu giá trị của cột bị cắt bớt. Cột chứa PII không được đối chiếu.
- Không có bộ lọc thời gian và `time_grain` thì thêm ghi chú khoảng dữ liệu đã gộp (MIN và MAX của cột ngày, hoặc ngày giờ, đầu tiên của bảng), để agent thấy khi khoảng đó gồm cả ngày tương lai.
- Không có `group_by` và không lọc theo cột văn bản nào (bảng có cột văn bản) thì thêm ghi chú kết quả là một số gộp mọi dòng của bảng (kèm độ chi tiết một dòng nếu data dictionary có), nhắc agent trả theo từng đối tượng hoặc nói rõ là số gộp khi câu hỏi không nêu đối tượng.
- Tự áp điều kiện của các quy tắc chuyên gia gắn với metric. Điều kiện trên cột mà câu hỏi đã lọc thì nhường cho bộ lọc của câu hỏi. Điều kiện trên cột đã nằm trong phần điều kiện của biểu thức metric (`CASE WHEN`, `FILTER (WHERE ...)`) thì không lọc thêm, để metric dạng tỷ lệ không bị sai. Quy tắc có tên trong `skip_rules` thì bỏ qua. Mỗi quy tắc đã áp, đã nhường hoặc đã bỏ, cùng các ngoại lệ của nó và cảnh báo của metric, được trả trong `notes`.
- Metric định nghĩa bằng `source_sql` không dựng tự động được; công cụ báo lỗi kèm `source_sql` để agent chuyển sang `run_sql`.

`validate_select` (sqlglot, phương ngữ PostgreSQL):

- Chỉ đúng một câu `SELECT` (có thể kèm `WITH`, `UNION`).
- Chặn ghi dữ liệu, `SELECT INTO`, `FOR UPDATE`, các hàm hệ thống (`pg_*`, `dblink*`, `lo_*`, `set_config`, `current_setting`, `nextval`...) và các hàm tự chạy truy vấn hoặc đọc cả bảng/schema từ chuỗi (`*to_xml*` như `query_to_xml`, `schema_to_xml`, `database_to_xml`; `ts_stat`, `ts_rewrite`, `crosstab*`, `connectby`), vì chúng vượt qua được kiểm tra bảng.
- Bảng phải thuộc connection: tên `schema.bảng`, hoặc tên bảng không kèm schema nếu tên đó là duy nhất trong connection. Tên không kèm schema được ghi đủ trước khi chạy.
- Trong `FROM` chỉ được dùng thêm CTE, `generate_series` và `unnest`. Tên CTE chỉ được coi là CTE ở chỗ PostgreSQL thấy nó: trong câu có `WITH` đó (kể cả truy vấn con), trong các CTE khai báo sau nó, và trong chính nó khi có `RECURSIVE`. Ngoài phạm vi đó tên được kiểm như tên bảng, để CTE trùng tên không che được bảng ngoài connection.

Lỗi để agent tự sửa:

- Lỗi của công cụ là thông báo cụ thể: cột không có (kèm danh sách cột hợp lệ), giá trị sai kiểu, bảng ngoài connection, lỗi cú pháp, mã và thông điệp lỗi của PostgreSQL, quá thời gian.
- Thông báo được trả lại cho mô hình để nó sửa và gọi lại. Gọi lại y nguyên một lời gọi đã lỗi thì bị chặn.
- Sau `TEXT2SQL_AGENT_MAX_STEPS` lượt công cụ, agent phải trả lời bằng kết quả đã có (`exhausted = true`).

Truy vấn chạy bằng `run_read_only` trên database nguồn (chỉ PostgreSQL):

- **Kết nối:** connection riêng, không pool; transaction `REPEATABLE READ` chỉ đọc; `statement_timeout` bằng `TEXT2SQL_QUERY_TIMEOUT_SECONDS`, `lock_timeout` 3 giây; luôn rollback. Phiên đặt `TimeZone` bằng `TEXT2SQL_TIMEZONE` (không phải UTC), nên ngày so với cột `timestamptz` tính theo giờ địa phương và giá trị `timestamptz` trả về kèm độ lệch (ví dụ `+07:00`).
- **Giới hạn dòng:** lấy tối đa `TEXT2SQL_QUERY_MAX_ROWS` dòng; có nhiều hơn thì `truncated = true`.
- **Cache:** cùng một câu SQL trong một lượt chỉ chạy một lần (`QueryCache`, dùng chung giữa các câu con).
- **Dòng gửi mô hình:** tối đa `TEXT2SQL_AGENT_MAX_ROWS_TO_LLM` dòng mỗi kết quả, đã che dữ liệu cá nhân (mục dưới).

### Che dữ liệu cá nhân

`PiiMasker` (`services/pii_masker.py`, dùng `presidio-analyzer` và `presidio-anonymizer`) che dòng ngay sau khi chạy SQL, trước khi tạo bước, gợi ý biểu đồ và đầu ra cho LLM. Vì vậy mọi thứ LLM thấy (đầu ra công cụ, kết quả câu trước đưa cho câu sau, câu trả lời từng câu đưa cho bước tổng hợp) và state của graph (cả checkpoint chờ hỏi lại) đều là dữ liệu đã che; `QueryCache` vẫn giữ dòng thô để dùng lại trong lượt. Người dùng thấy giá trị thật: mọi chỗ gửi client và bản lưu được đổi nhãn về giá trị thật (mục dưới).

- **Cột `contains_pii`:** mọi giá trị khác `None` (kể cả số, bool) bị thay. Giá trị nhận ra loại cụ thể thì dùng loại đó, còn lại là `<PII_n>`. Field của cột này chuyển thành `type: "text"`, `role: "dimension"`.
- **Chuỗi ở cột khác:** quét theo giá trị: email, số điện thoại (mẫu Việt Nam và quốc tế), thẻ tín dụng, IBAN, IP; thay phần khớp trong chuỗi, ví dụ `gọi <VN_PHONE_NUMBER_1>`. Chuỗi số trần chỉ che khi tên hoặc nhãn cột gợi ý (không phân biệt dấu): CCCD/CMND, mã số thuế, số tài khoản. Số không thuộc cột PII không bị đụng tới.
- **Nhãn thay thế:** dạng `<LOẠI_n>`; một `PiiMasker` cho mỗi lượt (`AgentRun`) nên cùng một giá trị có cùng nhãn ở mọi câu con và mọi kết quả của lượt (khóa luồng khi các câu chạy song song). Lượt khác đánh số lại.
- **Ghi chú:** kết quả có che thì thêm vào `notes` của bước (hiện trong mục SQL của client) một ghi chú "Đã che dữ liệu cá nhân trước khi gửi cho AI" kèm cột PII và số giá trị mỗi loại. Riêng `notes` trong đầu ra gửi LLM có thêm `PII_HINT`: nhãn là gì, chép nguyên nhãn vào câu trả lời, không đoán giá trị thật, không lọc theo nhãn. Ghi chú không chứa giá trị thật.
- **Phạm vi khác:** kết quả `get_column_values` và danh sách giá trị gợi ý trong lỗi lọc (`Giá trị gần giống`, `Một số giá trị có`) cũng được che. Ghi chú "đã đổi giá trị lọc" giữ giá trị khớp với chữ người dùng gõ.
- **Nạp:** Presidio và spaCy nạp lười ở lần che đầu tiên, dùng pipeline spaCy rỗng (không tải mô hình ngôn ngữ); chỉ chạy recognizer theo mẫu. Backend nạp sẵn ở luồng nền khi khởi động (`warm_up_masker` trong `lifespan`), nên câu hỏi đầu tiên không phải chờ vài giây.

#### Thay nhãn về giá trị thật cho người dùng

LLM chỉ thấy nhãn, nên câu trả lời nó viết cũng dùng nhãn. Prompt agent (mục 10 của `# CÂU TRẢ LỜI`) và prompt tổng hợp yêu cầu chép nguyên nhãn vào đúng chỗ của giá trị, không bọc trong dấu `, không nói giá trị đã bị che. Hệ thống đổi nhãn về giá trị thật ở mọi chỗ gửi chữ cho người dùng, bằng bảng nhãn của `PiiMasker` trong lượt (`unmask`):

- **Event stream:** `ChatService.execute` bọc `on_event` của graph bằng `UnmaskingEmit`. `answer_delta` giữ lại đuôi có thể là phần đầu của một nhãn bị cắt giữa hai đoạn (ví dụ `<PI`) cho tới đoạn sau (theo từng `position`, `round`; `answer_reset` bỏ phần đang giữ); `answer`, `question_answered`, `question_waiting` (câu hỏi lại và lựa chọn) được thay toàn bộ. Event `tool` được thay trong `rows`, `chart` (mọi chuỗi kể cả khóa, ví dụ tiêu đề, `colors.assign`, `colors.highlight`) và `explanations`; `sql`, `arguments` giữ nguyên vì là đúng thứ đã chạy.
- **Response và bản lưu:** `ChatOut.answer`, `clarification_question`, `clarification_options`, `answers[]` (câu trả lời, `rows`, `chart`, `explanations` của từng bước; `unmasked_answer`) và các trường tương ứng lưu vào lượt hội thoại (`steps`, `results`) là giá trị thật. State của graph (gửi tiếp cho LLM) giữ nguyên nhãn.
- **Nhận dạng nhãn:** nhãn có trong bảng của lượt mới được thay; chấp nhận cả dạng LLM thoát Markdown (`\<PII\_1\>`) và bọc trong cặp dấu `. Nhãn lạ (LLM tự đặt) và dấu `<` thường giữ nguyên.
- **Lịch sử cho lượt sau:** `ChatOut.history_answer` (cũng có trong event `done`) là câu trả lời còn nhãn nhưng bỏ số thứ tự (`<PII>`), vì lượt sau đánh số lại từ đầu; `null` khi câu trả lời không có nhãn. Lượt hội thoại lưu nó vào `pii.history_answer` để `recent_history` đưa cho bước viết lại câu hỏi thay cho câu trả lời có giá trị thật; chế độ không lưu thì client gửi nó trong `chat_history`.
- **Lượt chờ hỏi lại:** bảng nhãn được lưu cùng checkpoint (`masked_values`) và nạp lại khi chạy tiếp, nên nhãn trong snapshot vẫn thay được và giá trị mới đánh số tiếp (`<PII_2>`), không trùng nhãn cũ.

### Kết quả dữ liệu (`query_metric`, `run_sql`)

Mỗi bước thành công nhận `result_id` = `"<position>-<n>"` (`n` đếm các bước `query_metric`/`run_sql` thành công của câu đó, chạy tiếp sau hỏi lại vẫn đếm tiếp). Tên cột trùng được đổi thành `ten_2`, cột không tên (`?column?`) thành `cot_<i>`, kèm ghi chú. Toolkit dựng thêm:

- `fields` (`FieldOut`): nhãn, kiểu, đơn vị (`dictionary.unit` của cột, đơn vị của cột trong biểu thức metric, `currency` VND → "đồng", hoặc đơn vị trong ngoặc của `labels`), số lẻ và phần trăm (`dictionary.format` dạng d3), `additive`, `role`, `format_hint = "plain"` (năm, mã, id, cột nhóm, `EXTRACT`), `time_unit`, `pii`. Mã ở `services/display_format.py`.
- `explanations` (`ExplanationOut {kind, text, name?, status?, field?, start?, end?, values?}`), thứ tự: `metric`, `source`, `period`/`filter`, `group`, `order`, `rule` (`applied`, `yielded`, `skipped`; quy tắc đã nằm trong biểu thức metric không hiện), `value_match`, `data_range`, `scope`, `assumption`, `truncated`, `warning`. `run_sql` có `method` (từ `purpose`), `source` (bảng tìm bằng sqlglot, không tính CTE), `period`/`filter` từ `WHERE` đơn giản ở cấp ngoài cùng (có vế phức tạp như `OR` thì bỏ cả phần lọc), `rule` từ `rules_applied` (tên lạ thành ghi chú `Không có quy tắc '<tên>'.`). Giá trị lọc trên cột PII hiện là "(giá trị ẩn)". `text` dùng `today` của lượt. Mã ở `services/explanations.py`. Frontend hiển thị các mục này ở phần "Cách tính".
- `chart` (spec đề xuất `suggest_chart`, `chart_source = "auto"`) hoặc spec agent truyền kèm (`chart_source = "agent"`; sai thì giữ đề xuất và output có `chart_error`, bước vẫn thành công), `chart_types` (các loại hợp, kết thúc bằng `table`), `display` (`chart`, `chart_if_last`, `none`). Xem [biểu đồ](bieu-do.md).

Output gửi mô hình: `{result_id, sql, columns, fields (gọn: bỏ giá trị rỗng, `pii`, `role` mặc định), rows (đã định dạng vi-VN: số `1.234,5`, ngày "thứ Năm, 19/11", tháng "tháng 11", năm chỉ ghi khi khác năm hiện tại; ô số không hữu hạn thành null), row_count, truncated, notes?, chart (tóm tắt `{type, x, y, series}`), chart_types, display, chart_error?}`. `get_column_values` giữ dạng cũ (không có `result_id`). Dòng trong `steps` của response, event và bản lưu vẫn là giá trị thô.

## Response 200

```json
{
  "answer": "Tuần qua (10/11 đến 16/11/2026) Huế mưa nhiều nhất với 182 mm; hôm qua nhiệt độ trung bình ở Huế là 24,5 °C.",
  "status": "answered",
  "clarification_question": null,
  "clarification_options": [],
  "resume_id": null,
  "resume_expires_at": null,
  "conversation_id": "uuid",
  "turn_id": "uuid",
  "history_answer": null,
  "preprocess": {
    "rewritten_question": "Thành phố nào mưa nhiều nhất tuần qua, nhiệt độ ở đó hôm qua bao nhiêu?",
    "is_split": true,
    "execution_mode": "sequential",
    "questions": [
      {
        "position": 1, "question": "Thành phố nào mưa nhiều nhất tuần qua?", "depends_on": [],
        "question_type": "T7", "business_concepts": [],
        "knowledge": {
          "metrics": [{"metric_id": "uuid", "table_id": "uuid", "name": "tong_luong_mua", "label": "Tổng lượng mưa",
                       "description": null, "score": 1.12, "matched_topics": ["metric", "column"]}],
          "tables": [], "columns": [], "glossary": [], "expert_rules": [], "own_knowledge": []
        }
      },
      {"position": 2, "question": "Nhiệt độ ở <kết quả câu 1> hôm qua là bao nhiêu?", "depends_on": [1],
       "question_type": "T1", "business_concepts": [], "knowledge": {"...": "..."}}
    ],
    "stages": [[1], [2]]
  },
  "answers": [
    {
      "position": 1, "question": "Thành phố nào mưa nhiều nhất tuần qua?",
      "answer": "Huế mưa nhiều nhất tuần qua (10/11 đến 16/11/2026) với 182 mm.", "exhausted": false,
      "steps": [
        {"tool": "query_metric", "arguments": {"metric": "tong_luong_mua", "group_by": ["thanh_pho"], "...": "..."},
         "sql": "SELECT \"thanh_pho\", SUM(\"luong_mua\") AS \"tong_luong_mua\" FROM ...", "columns": ["thanh_pho", "tong_luong_mua"],
         "rows": [["Huế", 182]], "row_count": 1, "truncated": false, "notes": [], "error": null,
         "result_id": "1-1",
         "fields": [{"name": "thanh_pho", "label": "Thành phố", "type": "text", "role": "dimension", "...": "..."},
                    {"name": "tong_luong_mua", "label": "Tổng lượng mưa", "type": "number", "unit": "mm",
                     "additive": true, "role": "measure", "...": "..."}],
         "explanations": [{"kind": "metric", "text": "Chỉ số: Tổng lượng mưa", "name": "tong_luong_mua"},
                          {"kind": "period", "text": "Thời gian: 10–16/11", "field": "Ngày",
                           "start": "2026-11-10", "end": "2026-11-16"}],
         "chart": {"version": 1, "type": "bar", "encoding": {"...": "..."}}, "chart_source": "auto",
         "chart_types": ["bar", "bar_horizontal", "table"], "display": "chart_if_last"}
      ]
    },
    {"position": 2, "question": "Nhiệt độ ở <kết quả câu 1> hôm qua là bao nhiêu?", "answer": "...", "exhausted": false,
     "steps": []}
  ]
}
```

- `status`: `answered`, hoặc `needs_clarification` khi graph dừng để hỏi lại. Khi đó `answer` và `clarification_question` là câu hỏi lại, `clarification_options` là các lựa chọn (có thể rỗng), `resume_id` và `resume_expires_at` dùng để chạy tiếp, `answers` chỉ gồm các câu đơn đã xong. `conversation_id`, `turn_id`: hội thoại và lượt đã ghi; `null` khi không có `user_id`.
- `preprocess` là kết quả bước tiền xử lý. `metrics` cùng dạng với kết quả của [`POST /retrieve`](api-ingestion-retrieve.md); các topic khác gồm `entity_id`, `table_id`, `name`, `display_name`, `text` (văn bản đã index) và `score` (điểm hybrid của Qdrant).
- `answers` theo thứ tự `position`. `steps` gồm các lần chạy `query_metric`, `run_sql`, `get_column_values`, `ask_user`, kể cả lần lỗi (`error`), với đủ dòng kết quả (tối đa `TEXT2SQL_QUERY_MAX_ROWS`). Số trong `rows` là số JSON, ngày là chuỗi ISO; số không hữu hạn (`NaN`, `Infinity` của `numeric` hoặc `double precision`) thành chuỗi (`"NaN"`, `"inf"`...) để response, event SSE và bản lưu JSONB luôn là JSON hợp lệ. Bước `query_metric`/`run_sql` thành công có thêm `result_id`, `fields`, `explanations`, `chart`, `chart_source`, `chart_types`, `display` (mục [kết quả dữ liệu](#kết-quả-dữ-liệu-query_metric-run_sql)); bước `make_chart` có `arguments = {result_id, chart}`, `result_id`, `chart` đã chuẩn hóa, `chart_source = "agent"`, `display`. Mọi trường mới đều có giá trị mặc định nên checkpoint cũ (tạo trước khi có các trường này) vẫn chạy tiếp được.

## Stream: `POST /api/v1/text2sql/chat/stream`

Cùng body với `POST /chat`, cùng luồng xử lý và cùng cách ghi lượt, nhưng trả `text/event-stream` (Server-Sent Events) với từng bước của graph ngay khi bước đó xong. Tab `Hỏi dữ liệu` ở frontend dùng route này; `POST /chat` (JSON) vẫn giữ cho benchmark và cho client không cần tiến độ.

Mỗi event có dạng `event: <tên>` + `data: <JSON một dòng>`. Khi hàng đợi rỗng 10 giây, server gửi dòng chú thích `: keep-alive` để proxy không cắt kết nối.

| Event | Khi nào | `data` |
| --- | --- | --- |
| `turn` | Đầu stream, chỉ khi có `user_id` (lượt đã `begin_turn`) | `conversation_id`, `turn_id`, `continued_from` (lượt đang chờ khi chạy tiếp, ngược lại `null`) |
| `preprocess` | Xong `preprocess` (không có khi chạy tiếp) | `rewritten_question`, `is_split`, `execution_mode`, `stages`, `questions[]`: `position`, `question`, `depends_on`, `question_type`, `business_concepts`, `metrics` (`name`, `label` của metric truy hồi được), `glossary`, `expert_rules`, `own_knowledge` (tên hiển thị các mục truy hồi được) |
| `question_started` | Một câu đơn bắt đầu chạy agent | `position`, `question`, `resumed` (`true` khi câu đang chờ chạy tiếp với câu trả lời của người dùng) |
| `tool_started` | Ngay **trước** khi chạy một lời gọi công cụ của agent, trừ `ask_user` | `position`, `tool`, `subject`: nhãn dễ đọc do code giải bằng catalog: `get_metric`, `query_metric` → nhãn metric; `get_table` → nhãn bảng; `get_expert_rule` → tên quy tắc; `get_column_values` → nhãn cột; `run_sql` → `purpose` (cắt 80 ký tự); `make_chart` → `null`. Không giải được (tên sai) thì là tham số thô. Không gửi `arguments` (đã có ở `tool`) |
| `answer_delta` | Mỗi đoạn chữ mới của một vòng gọi mô hình, đã gom (đoạn đầu gửi ngay; sau đó gửi khi đủ 32 ký tự hoặc đã qua 50 ms từ lần gửi trước, và luôn gửi nốt khi vòng kết thúc) | `position` (`null` khi là chữ của bước tổng hợp), `round` (số thứ tự vòng gọi mô hình của câu đơn, bắt đầu từ 0, tăng sau mỗi lượt công cụ; chạy tiếp sau hỏi lại thì đếm tiếp; vòng hết lượt có `round = TEXT2SQL_AGENT_MAX_STEPS`; tổng hợp luôn 0), `final`, `text` |
| `answer_reset` | Vòng vừa stream chữ hóa ra có gọi công cụ (mô hình viết lời dẫn rồi gọi công cụ, hoặc gọi `ask_user`) | `position`, `round`. Client xóa phần chữ của vòng đó |
| `tool` | Sau **mỗi** lời gọi công cụ của agent | `position` và các trường của `AgentStepOut`: `tool`, `arguments`, `sql`, `columns`, `rows`, `row_count`, `truncated`, `notes`, `error`. `query_metric`, `run_sql`, `get_column_values` có SQL và **đủ dòng** (tối đa `TEXT2SQL_QUERY_MAX_ROWS`, giống JSON); `get_metric`, `get_table`, `get_expert_rule` chỉ có `tool`, `arguments`, `error`. `ask_user` không có event `tool` mà thành `question_waiting` |
| `question_waiting` | Agent của một câu đơn gọi `ask_user` | `position`, `question` (câu hỏi lại), `options` |
| `question_answered` | Một câu đơn có câu trả lời | `position`, `question`, `answer`, `exhausted` |
| `synthesize_started` | Đầu nút `synthesize` khi thật sự gọi mô hình (câu đã tách) | `{}` |
| `answer` | Xong `synthesize` (không có khi graph dừng để hỏi lại) | `answer` |
| `clarification` | Graph dừng ở `clarify` và checkpoint đã lưu | `question`, `options`, `resume_id`, `expires_at` |
| `done` | Cuối stream khi thành công | `status`, `answer`, `clarification_question`, `clarification_options`, `resume_id`, `resume_expires_at`, `conversation_id`, `turn_id`, `history_answer` (cùng nghĩa các trường của `ChatOut`) |
| `error` | Lỗi sau khi stream đã bắt đầu; stream đóng ngay sau event này, không có `done` | `code`, `message`. Lỗi ứng dụng giữ `code` và thông điệp của nó (ví dụ `text2sql_agent_unavailable`); lỗi bất ngờ là `internal_error` với thông điệp chung, chi tiết chỉ ở log |

Thứ tự:

```text
turn? → preprocess? →
  [mỗi position; các nhánh song song xen kẽ nhau, trong một position đúng thứ tự]
  question_started → ( tool_started → tool )* xen answer_delta / answer_reset → question_answered | question_waiting
→ (câu tách) synthesize_started → answer_delta(position = null, final = true)* → answer
→ (câu không tách) answer
→ clarification? → done | error
```

Client ghép theo `position`. Muốn có toàn bộ `preprocess.knowledge` hoặc `answers[].steps` dạng JSON thì dùng `POST /chat`.

**Cờ `final` của `answer_delta`:**

- Câu không tách (`is_split = false` và một câu): mọi delta của agent có `final = true`, vì vòng không gọi công cụ chính là câu trả lời của lượt. Vòng nào hóa ra gọi công cụ thì có `answer_reset` ngay sau phần chữ của vòng đó.
- Câu đã tách: delta của agent có `final = false` (bản nháp của câu con, frontend đặt trong mục thả xuống "Trả lời từng phần"); delta của bước tổng hợp có `position = null`, `final = true`.
- Bản chính thức vẫn là `question_answered.answer` (từng câu), `answer.answer` (cả lượt) và `done.answer`. Client **luôn ghi đè** bản nháp bằng bản chính thức: bản chính thức đã `strip()` và có thể là `"Chưa trả lời được câu hỏi này."` khi mô hình trả rỗng.
- Frontend (`features/text2sql/use-chat.ts`) gom `answer_delta`/`answer_reset` vào bộ đệm và áp một lần mỗi khung hình; event khác xả bộ đệm trước khi áp. `tool_started` chỉ dùng cho dòng tường thuật (`narration.ts`); `synthesize_started` vừa đổi dòng tường thuật vừa xóa câu trả lời tạm trước khi chữ tổng hợp đến, xem [Frontend](../../frontend/README.md#hỏi-dữ-liệu).

Ví dụ câu không tách có một vòng viết lời dẫn rồi gọi công cụ:

```text
event: question_started   data: {"position":1,"question":"…","resumed":false}
event: answer_delta       data: {"position":1,"round":0,"final":true,"text":"Để trả lời, tôi xem chỉ số."}
event: answer_reset       data: {"position":1,"round":0}
event: tool_started       data: {"position":1,"tool":"query_metric","subject":"Tổng lượng mưa"}
event: tool               data: {"position":1,"tool":"query_metric","result_id":"1-1",…}
event: answer_delta       data: {"position":1,"round":1,"final":true,"text":"Phú Quốc mưa nhiều nhất 7 ngày qua"}
event: answer_delta       data: {"position":1,"round":1,"final":true,"text":" (13–19/11), **46,9 mm**."}
event: question_answered  data: {"position":1,…,"answer":"Phú Quốc mưa nhiều nhất 7 ngày qua (13–19/11), **46,9 mm**."}
event: answer             data: {"answer":"…"}
event: done               data: {…}
```

**Route JSON `/chat` không stream:** `ChatService.execute(prepared, emit=None)` dựng `ChatGraphContext(streaming=False)`: nút `answer_question` không tạo bộ ghi event, agent không nhận `on_text`, `on_tool`, `on_tool_start` nên gọi mô hình bằng `invoke` như trước; `synthesize` gọi `get_chat_text` không có `on_text` (`invoke`). Response giữ nguyên hình dạng.

**Lưu trữ:** bản nháp và delta không lưu ở đâu. `steps[].answer` (bản chính thức của từng câu con) và `answer` của lượt lưu như trước; mục "Trả lời từng phần" khi mở lại lịch sử đọc `steps[].answer`.

Lỗi **trước** khi stream bắt đầu trả HTTP thường (JSON `{"detail": ...}`) với cùng mã như bảng [Lỗi](#lỗi): connection không có (404), hội thoại không thuộc người dùng (404), `resume_id` không hợp lệ (404, 409), connection tạm dừng hoặc URI hỏng (400, 503), request sai dạng (422). Lỗi từ `preprocess` trở đi (LLM, embedding, Qdrant, database nguồn) là event `error`, HTTP vẫn 200.

Cách chạy (`services/chat_stream.py`, `ChatStream`):

- Route là `async def`. Nó tạo một thread riêng; thread này mở `Session`, `QdrantRepository`, `OpenRouterEmbedding` **của riêng nó** qua `get_chat_service_factory` (`open_chat_service` trong `dependencies.py`) và đóng chúng khi xong. Không dùng dependency có `yield` của request, vì FastAPI dọn các dependency đó trước khi body của `StreamingResponse` chạy xong. `Session` chỉ được dùng trên thread này (`prepare`, ghi lượt, lưu checkpoint); các nhánh song song của graph không chạm `Session`.
- Thread chạy `ChatService.prepare` (kiểm tra connection, hội thoại, `resume_id`, `Text2SqlAgentService.start`, `begin_turn`) rồi báo sẵn sàng; route chờ tín hiệu này, nên lỗi ở bước này thành HTTP lỗi như trên. Sau đó `ChatService.execute` chạy graph và đẩy event vào hàng đợi `asyncio` qua `call_soon_threadsafe`; generator của response đọc hàng đợi.
- `run_chat_graph` dùng `graph.stream(stream_mode=["updates", "custom"])`. Event `preprocess`, `question_answered`, `question_waiting`, `answer` lấy từ chế độ `updates` (cập nhật state của từng nút); `question_started`, `tool_started`, `tool`, `answer_delta`, `answer_reset`, `synthesize_started` được ghi qua `get_stream_writer()` (chỉ khi `ChatGraphContext.streaming = true`) nên có cả bước của các nhánh song song chạy trên thread của LangGraph. `tool` đến từ `on_tool` của vòng agent (`tool_reporter` trong `text2sql_agent_service.py`): bước đã được toolkit ghi (`query_metric`, `run_sql`, `get_column_values`, `make_chart`) gửi đủ SQL và dòng, lời gọi chỉ đọc catalog gửi tên công cụ, tham số và lỗi. `tool_started` đến từ `on_tool_start` (`tool_starter`, `tool_subject`).
- **Stream chữ của agent:** `AgentRun.answer` dựng `DeltaBuffer(emit, position, final)` (`services/answer_stream.py`) và truyền `text_stream()` làm `on_text` cho `run_tool_agent`. Khi có `on_text`, mỗi vòng gọi mô hình dùng `stream` thay cho `invoke`: chữ được đẩy chừng nào message gộp chưa có `tool_call_chunks`; cuối vòng, nếu đã đẩy chữ mà message có `tool_calls` thì `DeltaBuffer` xả phần còn gom rồi phát `answer_reset`. Chunk công cụ đến trước chữ thì không đẩy chữ nào của vòng đó. Message chỉ có `invalid_tool_calls` (JSON tham số hỏng) được xử lý như khi `invoke` trả cùng message: vòng kết thúc, chữ được giữ (phần chữ đến sau chunk hỏng được đẩy nốt), không có `answer_reset`.
- **Stream chữ của bước tổng hợp:** nút `synthesize` (câu tách, `streaming = true`) phát `synthesize_started`, gọi `context.synthesize(preprocess, answers, on_text=SynthesizeStream(emit).delta)` rồi xả phần còn gom. `Synthesize` là `Protocol` với `on_text` tùy chọn; khi không stream nó được gọi đúng hai tham số.
- **Client ngắt kết nối:** khi generator của response bị đóng hoặc hủy, hoặc `request.is_disconnected()` (kiểm tra mỗi lần chờ keep-alive) báo ngắt, cờ dừng được bật. Lần ghi event tiếp theo, ở thread chính hay trong nhánh agent (sau mỗi lời gọi công cụ, hoặc ở lần gửi `answer_delta` kế tiếp khi mô hình đang stream chữ), ném `Text2SqlClientDisconnected` (`code = client_disconnected`); vòng agent dừng, LangGraph chờ các nhánh đang chạy dừng ở lần ghi event kế tiếp. `ChatService.execute` ghi lượt `status = error`, `error_code = client_disconnected`; đang chạy tiếp thì checkpoint được ghi lại để người dùng gửi lại câu trả lời.
- **Hủy lời gọi LLM khi Dừng:** lời gọi đang stream chữ (vòng trả lời của agent, bước tổng hợp) bị dừng ngay ở lần gửi delta kế tiếp: lỗi ném từ `on_text` lan qua vòng lặp `stream`, generator bị đóng (`contextlib.closing`) nên kết nối HTTP tới nhà cung cấp đóng theo. Nhà cung cấp không hỗ trợ hủy vẫn có thể tính tiền đủ phần đã sinh. Vòng gọi công cụ không có chữ nên chỉ dừng khi vòng đó xong. Lỗi khi tổng hợp đi cùng đường: `get_chat_text` và `ChatService._synthesize` chỉ bắt `OpenAIError`, nên `Text2SqlClientDisconnected` không bị đổi thành `Text2SqlAgentUnavailable`.
- **Phần chữ đã stream mất khi Dừng:** lượt lỗi lưu `answer = null`, nên chữ đã hiện trên màn hình **không còn khi tải lại lịch sử**; chỉ `steps[].answer` của các câu con đã xong còn lại. Đây là hành vi đã chấp nhận ở bản này (không lưu bản nháp). Không hỗ trợ nối lại stream sau khi rớt mạng.

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `TEXT2SQL_QUERY_TIMEOUT_SECONDS` | 15 | Thời gian tối đa của một truy vấn (1 đến 300). |
| `TEXT2SQL_QUERY_MAX_ROWS` | 200 | Số dòng tối đa lấy về mỗi truy vấn (1 đến 5000). |
| `TEXT2SQL_AGENT_MAX_ROWS_TO_LLM` | 50 | Số dòng mỗi kết quả gửi cho mô hình. |
| `TEXT2SQL_AGENT_MAX_STEPS` | 12 | Số lượt gọi công cụ tối đa cho một câu đơn. |
| `TEXT2SQL_TIMEZONE` | `Asia/Ho_Chi_Minh` | Múi giờ tính `today`. |
| `TEXT2SQL_CLARIFICATION_TTL_MINUTES` | 1440 | Thời gian giữ checkpoint của lượt đang chờ hỏi lại (5 đến 43200 phút). |
| `TEXT2SQL_CHART_TYPES_ENABLED` | rỗng (bật cả 32 loại) | Danh sách loại biểu đồ được dùng, cách nhau bằng dấu phẩy; `table` luôn bật. Áp cho đề xuất, `make_chart`, `chart_types` và các endpoint biểu đồ. |

## Lỗi

| Status | Khi nào |
| --- | --- |
| 400 | Connection đang tạm dừng, hoặc `conversation_id` thuộc connection khác (`Text2SqlInvalidRequest`) |
| 404 | `connection_id` không tồn tại; `conversation_id` không tồn tại hoặc không thuộc `user_id` (`conversation_not_found`); `resume_id` không có, đã dùng, hết hạn hoặc thuộc connection, người dùng, hội thoại khác (`text2sql_clarification_not_found`) |
| 409 | `resume_id` trỏ tới lượt không còn chờ trả lời (`conversation_turn_not_continuable`) |
| 422 | Request sai dạng, câu hỏi rỗng, hoặc có `conversation_id` mà thiếu `user_id` |
| 503 | Gọi LLM lỗi hoặc LLM trả JSON không khớp schema (`Text2SqlAgentUnavailable`); không giải mã được URI hoặc không kết nối được database nguồn (`Text2SqlQueryFailed`); không gọi được embedding (`EmbeddingUnavailable`) hoặc Qdrant (`Text2SqlIndexUnavailable`) |

Lỗi của từng truy vấn (SQL sai, quá thời gian, kết quả rỗng) không làm hỏng request: agent nhận thông báo lỗi và tự sửa; lỗi vẫn ghi trong `steps`.

Khi có `user_id`, mọi lỗi 503 và lỗi bất ngờ xảy ra sau `begin_turn` đều được ghi vào lượt với `status = error` trước khi trả lỗi.

Với `/chat/stream`, các lỗi sau khi stream bắt đầu là event `error` thay vì mã HTTP (mục [Stream](#stream-post-apiv1text2sqlchatstream)).
