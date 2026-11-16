# Gói agent dùng chung (`backend/agent_package`)

**Trạng thái:** **đã triển khai** cho bốn agent `QuestionRewriteAgent`, `QueryPlanAgent`, `DatasetPlanAgent`, `AnalysisAgent`. Pipeline chat phía server ghép các agent này (route `POST /api/v1/text2sql/chat`) **đã triển khai**, xem [luồng chat](text2sql/chat-flow.md). Cập nhật 2026-11-16 (thêm `stream_structured` và `stream` của ba agent có đầu ra có cấu trúc; cùng ngày: `history` cho `QuestionRewriteAgent`, `clarification_options` cho hai agent lập kế hoạch).

`backend/agent_package/` chứa mọi lời gọi mô hình ngôn ngữ dùng chung. Module nghiệp vụ gọi agent, không tự gọi mô hình; `agent_package` không import từ `backend/modules`.

## Nguyên tắc

- Chỉ dùng một mô hình, cấu hình bằng `OPENROUTER_MODEL` (mặc định `openai/gpt-6-luna`), gọi qua OpenRouter bằng `langchain-openai`.
- Mỗi agent gọi mô hình **một lượt**: không retry ở tầng agent, không vòng lặp, không gọi công cụ. (`ChatOpenAI` tự thử lại lỗi mạng theo `max_retries`.)
- Prompt là hằng số tiếng Việt cố định trong `prompts/`; few-shot dùng lĩnh vực không liên quan dữ liệu thật (nhân sự, giáo dục, bệnh viện, thời tiết, hàng không).
- Agent có đầu ra có cấu trúc đặt trường `analysis` (chain of thought theo bước B1..Bn) **đứng đầu** schema để mô hình suy luận trước khi quyết định. Trường thừa trong đầu ra bị bỏ qua.
- Mọi lỗi mô hình (khởi tạo, gọi, đầu ra sai cấu trúc, lỗi giữa chừng khi stream) thành `AgentUnavailableError` (`errors.py`, mã `agent_unavailable`, 503).

## Hàm dùng chung (`get_chat_models.py`)

| Hàm | Vai trò |
| --- | --- |
| `get_chat_model()` | Tạo `ChatOpenAI` (nhiệt độ 0, tối đa 4096 token, timeout 60 giây), cache một thể hiện. |
| `build_messages(prompt, context)` | `SystemMessage` là prompt, `HumanMessage` là `context` dạng JSON (giữ tiếng Việt). |
| `structured_model(schema)` | `with_structured_output(schema, method="function_calling")`. |
| `invoke_structured(schema, prompt, context)` | Gọi một lượt, kiểm tra lại bằng `schema.model_validate`; lỗi, kết quả rỗng hoặc sai cấu trúc thành `AgentUnavailableError`. |
| `tool_model(schema)` | `bind_tools([schema], tool_choice=<tên schema>, parallel_tool_calls=False)`, cùng cách ép tool như `with_structured_output(method="function_calling")`. |
| `stream_structured(schema, prompt, context)` | Generator `Generator[ReasoningDelta, None, schema]`: stream **một lượt** gọi structured output, phát dần trường `analysis` khi mô hình đang sinh, cuối cùng trả draft đã kiểm tra (xem dưới). |
| `stream_text(prompt, context)` | Stream văn bản tự do: trả từng đoạn `chunk.content` khác rỗng (content dạng danh sách block thì nối phần text), lỗi lúc khởi tạo hoặc giữa chừng thành `AgentUnavailableError`. |
| `chunk_text(content)` | Lấy phần chữ của một chunk (chuỗi hoặc danh sách block). |

## Các agent

| Agent | File | Đầu vào (`context`) | Đầu ra |
| --- | --- | --- | --- |
| `QuestionRewriteAgent` | `agents/question_rewrite_agent.py`, prompt `prompt_text2sql_rewrite.py` | `question`, `today`, `glossary_terms`, `expert_rules`, `own_knowledge`, `history` (tùy chọn, xem dưới) | `RewriteDraft`: `analysis`, `rewritten_question`, `glossary_term_ids`, `rule_ids`, `own_knowledge_ids`, `changes` |
| `QueryPlanAgent` | `agents/query_plan_agent.py`, prompt `prompt_text2sql_plan.py` | `original_question`, `question`, `today`, `metric_candidates` | `PlanDraft`: `analysis`, `status` (`ok`, `no_metric`, `needs_clarification`), `queries` (tối đa 3), `assumptions`, `reason`, `clarification_question`, `clarification_options` |
| `DatasetPlanAgent` | `agents/dataset_plan_agent.py`, prompt `prompt_text2sql_dataset_plan.py` | `question`, `rewritten_question`, `today`, `tables` (đầu ra của `find_fields`), `expert_rules`, `own_knowledge` | `DatasetPlanDraft` (xem dưới) |
| `AnalysisAgent` | `agents/analysis_agent.py`, prompt `prompt_text2sql_analysis.py` | xem dưới | `stream(context)` trả `Iterator[str]`; `run(context)` nối toàn bộ thành `str` |

Ba agent đầu có hai phương thức trên cùng prompt và schema: `run(context)` dùng `invoke_structured` (MCP `ask_data` và `AskService.prepare` vẫn dùng), `stream(context)` dùng `stream_structured` và trả `Generator[ReasoningDelta, None, <Draft>]` (route chat dùng). Cách dùng:

```python
draft = yield from agent.stream(context)  # trong một generator; mỗi ReasoningDelta được phát ra ngoài
```

`AnalysisAgent` dùng `stream_text`.

### Stream suy luận của đầu ra có cấu trúc (`stream_structured`)

- `ReasoningDelta(index, text)` (dataclass bất biến): `index` là vị trí mục trong `analysis`, `text` là phần chữ mới; nối các `text` cùng `index` được đúng nguyên văn mục đó.
- Gọi `tool_model(schema).stream(build_messages(prompt, context))` một lần; tích lũy chuỗi đối số của tool call đầu tiên (theo `index` nhỏ nhất của `tool_call_chunks`), mỗi chunk mới parse JSON dở dang bằng `langchain_core.utils.json.parse_partial_json`, lấy các mục chuỗi của `analysis` và so với phần đã phát để sinh delta. Chỉ phát khi chữ mới nối tiếp chữ cũ (bỏ qua trạng thái tạm như escape `\u` chưa đủ, giữ lại nửa đầu cặp surrogate), nên không bao giờ phải "rút lại" chữ đã phát.
- Kết thúc: `json.loads` toàn bộ đối số rồi `schema.model_validate` như `invoke_structured`; sau đó phát nốt phần còn thiếu của `analysis` từ draft đã kiểm tra rồi `return` draft. Lỗi khởi tạo, lỗi giữa stream, không có tool call, JSON hỏng hoặc sai schema đều thành `AgentUnavailableError` (delta đã phát trước đó vẫn ở phía caller). Đóng generator sớm thì đóng stream của mô hình.
- Một lượt, không retry, không gọi thêm.
- **Giới hạn:** chỉ stream dần được khi nhà cung cấp gửi đối số tool call từng phần. Nếu đối số đến trong một chunk thì mọi delta đến một lần ở cuối (vẫn đúng nội dung). Chưa kiểm với OpenRouter/`openai/gpt-6-luna` thật.

### `QuestionRewriteAgent` với lịch sử hội thoại

**Đã triển khai** (2026-11-16). Khi route chat chạy trong một hội thoại (xem [luồng chat](text2sql/chat-flow.md#hội-thoại-và-lịch-sử)), `context` có thêm `history`: tối đa 6 lượt gần nhất, cũ trước mới sau, mỗi mục `question`, `rewritten_question`, `status`, `answer` (đã rút gọn tối đa 500 ký tự) và `clarification_question` (có thể `null`). Không có dòng dữ liệu, SQL hay kết quả truy vấn. Không có lượt trước thì **không có khóa `history`**, nên context của MCP `ask_data` không đổi.

Quy tắc 11 của prompt: `rewritten_question` phải là câu hỏi độc lập.

- Câu nối tiếp ("còn tháng trước thì sao?", "chia theo khu vực", "bỏ khách nội bộ đi"): lấy câu đã viết lại của lượt liên quan gần nhất làm nền rồi áp đúng thay đổi.
- Lượt gần nhất là `needs_clarification`: câu hiện tại là câu trả lời cho `clarification_question`, ghép với câu hỏi gốc của lượt đó.
- Câu hỏi mới, đủ ý và khác chủ đề: không kéo ngữ cảnh cũ vào.
- Bước B1 của `analysis` nêu rõ câu hỏi thuộc loại nào; `changes` ghi phần đã ghép từ lượt trước.

Prompt có thêm năm ví dụ few-shot (đổi kỳ, thêm chiều nhóm, thêm điều kiện loại trừ, trả lời câu hỏi làm rõ, câu hỏi mới không liên quan); ví dụ dùng miền dữ liệu trung tính (lượt khám, đơn hàng, học sinh), không dùng tên dữ liệu thật.

### Lựa chọn trả lời khi hỏi lại (`clarification_options`)

**Đã triển khai** (2026-11-16). `PlanDraft` và `DatasetPlanDraft` có `clarification_options: list[str]` (mặc định rỗng). Validator chuẩn hóa trước khi kiểm tra kiểu: bỏ mục không phải chuỗi hoặc rỗng, gọn khoảng trắng, bỏ trùng, giữ tối đa 4 mục (không đặt `max_length` trong schema để mô hình trả thừa không làm hỏng cả draft). Prompt yêu cầu chỉ điền khi `status` là `needs_clarification`: các lựa chọn ngắn, lời thường, không mã kỹ thuật, lấy từ các cách hiểu hợp lý của câu hỏi; không có lựa chọn rõ ràng thì để rỗng. `prompt_text2sql_plan.py` có thêm ví dụ 7, ví dụ 6 của `prompt_text2sql_dataset_plan.py` có lựa chọn. Pipeline chat trả các lựa chọn trong `done.clarification_options` và lưu vào lượt; MCP `ask_data` không trả trường này.

### `DatasetPlanAgent`

Dùng khi không có metric phù hợp: sau `find_fields`, agent lập kế hoạch dataset; server ánh xạ tên về ID, tính cách nối, dựng SQL và chạy (xem [tìm trường và nối bảng](text2sql/find-fields-join.md), [dựng truy vấn](text2sql/build-query.md)).

Đầu vào `tables`: mỗi bảng có `name` (`schema.bảng`), `short_name`, `description`, `grain`, `fields` (`name`, `display_name`, `data_type`, `semantic_role`, `description`, `unit`, `contains_pii`).

`DatasetPlanDraft` tham chiếu bảng và cột bằng **tên**, không bằng UUID:

- `analysis: list[str]` (đứng đầu), `status`: `ok`, `cannot_answer`, `needs_clarification`.
- `root_table: str | None` (`schema.bảng`), `tables: list[str]` (gồm cả gốc, tối đa 8).
- `select: list[DatasetSelectDraft]` (tối đa 20; cần ít nhất 1 khi `ok`, server kiểm tra): `column` (`bảng.cột`), `expression`, `aggregation` (`sum`, `avg`, `min`, `max`, `count`, `count_distinct`), `alias`.
- `group_by: list[str]` (`bảng.cột`, tên bảng không kèm schema), `time: DatasetTimeDraft | None` (`column`, `start`, `end` dạng YYYY-MM-DD, `granularity`).
- `filters: list[DatasetFilterDraft]`: `column`, `operator` (cùng `Operator` của `QueryPlanAgent`), `value`, `placement` (`where` mặc định hoặc `join`).
- `order_by: list[DatasetOrderDraft]` (`by` là alias hoặc `bảng.cột`, `direction`), `limit`, `assumptions`, `reason`, `clarification_question`, `clarification_options`.

Luật cốt lõi trong prompt:

1. Bảng gốc chọn theo **grain** của câu hỏi (bảng định nghĩa tập đối tượng đang hỏi); mọi bảng khác `LEFT JOIN` từ gốc ra ngoài.
2. Chỉ dùng bảng và cột có trong `tables`.
3. Lọc mặc định `placement=where`; chỉ dùng `placement=join` khi cần giữ dòng gốc không khớp, khi đó đếm cột của bảng nối.
4. Không lọc theo cột PII, không dùng cột PII làm cột thời gian hay trong biểu thức; được select hoặc group_by cột PII (kết quả bị che).
5. Có hàm tổng hợp thì cột thường trong select phải nằm trong group_by.
6. Tránh nhân dòng: không tổng hợp cột bảng "một" khi đã nối xuống bảng "nhiều", không trộn hai nhánh một-nhiều trong một hàm tổng hợp; chọn lại gốc.
7. Biểu thức chỉ dùng `bảng.cột`, SUM/COUNT/AVG/MIN/MAX, số học, CASE, COALESCE, NULLIF, ROUND, CAST sang số, ngày, chữ (không CHAR), không subquery.
8. Thời gian tương đối tính theo `today`, không tự thêm năm.
9. `cannot_answer` khi thiếu trường, `needs_clarification` khi câu hỏi mơ hồ; không đoán.

### `AnalysisAgent`

Viết câu trả lời cuối cho người dùng (markdown, tiếng Việt), stream từng đoạn. Đầu vào do server dựng: `question`, `rewritten_question`, `today`, `flow` (`metric`, `dataset`, `none`), `status` (`answered`, `no_metric`, `needs_clarification`, `join_ambiguous`, `join_not_declared`, `cannot_answer`, `error`), `rewrite`, `queries` (mỗi mục: `kind`, `metric`, `sql`, `parameters`, `columns`, `rows` đã che PII và đã cắt, `row_count`, `truncated`, `warnings`, `rules_applied`, `filters_overridden`), `assumptions`, `pii`, `message`, `join`, `clarification_question`.

Prompt yêu cầu: chỉ dựa trên dữ liệu trong ngữ cảnh, không bịa số; kết luận trước rồi chi tiết (bảng markdown ngắn khi hợp lý); nêu bộ lọc, quy tắc, giả định bằng lời thường, không lộ SQL trừ khi người dùng hỏi; nhắc khi dữ liệu bị cắt hoặc có cột bị che; giữ nguyên placeholder PII (`<PII_1>`) và không đoán giá trị gốc; định dạng số theo `format`/`currency`. Mỗi `status` có cách trả lời riêng: `no_metric`/`cannot_answer` nói rõ chưa trả lời được và gợi ý hỏi lại; `needs_clarification` đặt câu hỏi làm rõ; `join_ambiguous` liệt kê các cách nối và hỏi người dùng chọn; `join_not_declared` yêu cầu bổ sung khai báo quan hệ trong data dictionary, không tự đoán cách nối; `error` xin lỗi ngắn gọn, không lộ chi tiết nội bộ.

## Kiểm thử

`tests/test_agent_package_agents.py`, `tests/test_agent_package_new_agents.py` và `tests/test_agent_package_stream_structured.py` giả `get_chat_model` bằng `patch`, không gọi API thật. `test_agent_package_stream_structured.py` dùng mô hình giả có `bind_tools`/`stream` trả `AIMessageChunk` với `tool_call_chunks`, cắt JSON ở mọi vị trí và vị trí ngẫu nhiên (cả `ensure_ascii` để có escape `\uXXXX`, cặp surrogate, tiếng Việt, `\"`, `\\`, xuống dòng, mục rỗng): delta ghép lại đúng nguyên văn, delta đến trước khi stream xong, nhà cung cấp trả một lần ở cuối, JSON cuối hỏng hoặc sai schema, lỗi giữa stream, không có tool call, đóng sớm, ba agent `stream` trả đúng draft. Các test còn lại kiểm tra schema (`analysis` đứng đầu, enum khớp), prompt và context JSON được gửi, đầu ra hợp lệ, stream (content dạng list, chunk rỗng bị bỏ), lỗi thành `AgentUnavailableError`, prompt chứa các luật cốt lõi và không chứa tên dữ liệu thật.
