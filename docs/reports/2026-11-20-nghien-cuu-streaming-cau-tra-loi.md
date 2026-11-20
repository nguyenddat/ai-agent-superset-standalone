# Nghiên cứu: stream quá trình trả lời (tab "Hỏi dữ liệu")

Ngày: 2026-11-20. Trạng thái: **nghiên cứu, chưa triển khai**. Không sửa code; mọi thử nghiệm là script tạm ngoài repo.

## 1. Tóm tắt

- Hôm nay câu trả lời đến **nguyên khối**: agent gọi `model.invoke` (`backend/agent_package/tool_agent.py::_call_model`), synthesize trả JSON qua `PydanticOutputParser` (`get_chat_completion.py`), stream SSE chỉ có event cấp bước (`chat_events.py::update_events`).
- Số đo thật (mục 3) cho thấy: phần **sinh chữ** của câu trả lời cuối chỉ chiếm khoảng 0,5–1,5 s trong tổng median 13,3 s. Stream token tự nó **không làm câu trả lời xong sớm hơn**, chỉ cho chữ hiện sớm hơn khoảng 1 s với câu đơn, sớm hơn nhiều hơn với câu tách (synthesize p90 9,4 s). Phần người dùng thấy "im lặng" nhiều nhất là **6 s tiền xử lý** và **các vòng gọi công cụ** (median 3 vòng LLM mỗi câu). Vì vậy **lời kể tiến độ dễ đọc** (mục b) đem lại nhiều giá trị hơn token streaming và nên làm trước.
- Cách đề xuất: **không dùng `stream_mode="messages"`**. Dùng `model.stream()` ngay trong vòng agent và trong synthesize, đẩy từng đoạn chữ qua **chính stream writer đang dùng cho event `tool`** (`chat_graph.py::_emitter`), thành các event SSE **mới, bổ sung** (`answer_delta`, `answer_reset`, `tool_started`, `synthesize_started`). Event cũ (`question_answered`, `answer`, `done`) giữ nguyên và vẫn là nguồn sự thật. Hợp đồng route JSON, lưu hội thoại và hỏi lại/chạy tiếp không đổi (lưu ý: route JSON hôm nay vẫn nhận `emit` khác `None`, xem mục 6.2 bước 2).
- Đã chạy thử với model giả trên đúng hình graph (Send song song + graph `tool_agent` lồng trong node) và gọi thật OpenRouter (`openai/gpt-6-luna`) để xác nhận hình dạng chunk, thứ tự, việc dừng giữa chừng.

## 2. Hiện trạng (đã đọc code)

| Thành phần | File | Điểm liên quan đến streaming |
|---|---|---|
| Route | `backend/modules/text2sql/routes/router_chat.py` | `/chat` (JSON) gọi `ChatService.chat`; `/chat/stream` dùng `ChatStream` |
| Cầu nối thread sang asyncio | `services/chat_stream.py` | Thread `_work` chạy `prepare` rồi `execute(prepared, self._emit, self.stopped.is_set)`; `_emit` ném `Text2SqlClientDisconnected` khi client đã ngắt; event đi qua `asyncio.Queue` bằng `call_soon_threadsafe`; keep-alive 10 s |
| Graph | `services/chat_graph.py` | `graph.stream(..., stream_mode=["updates", "custom"], durability="exit")`. `_emitter` lấy `get_stream_writer()` **trong node ngoài** rồi truyền closure `emit` xuống agent. Node `_synthesize` trả thẳng `answers[0].answer` khi chỉ có một câu và không tách |
| Agent một câu | `services/text2sql_agent_service.py`, `agent_package/tool_agent.py` | `run_tool_agent` gọi `tool_agent_graph.invoke(...)` (graph con, chạy **trong** node `answer_question`); `_call_model` gọi `model.bind_tools(...).invoke(...)`; `on_tool` báo **sau** khi công cụ chạy xong |
| Synthesize | `chat_service.py::_synthesize`, `prompts/prompt_synthesize.py` | Prompt đòi JSON `{"answer": ...}`; `SynthesizeParser` đã có nhánh dự phòng nhận văn bản thuần nếu không bắt đầu bằng `{` hoặc ``` |
| Model | `agent_package/get_chat_models.py` | `ChatOpenAI(model=config.openrouter_model, base_url=openrouter, max_tokens=4096, timeout=60, max_retries=2)`, không đặt `streaming`, `stream_usage` |
| Frontend | `frontend/features/text2sql/use-chat.ts`, `chat-turn.tsx`, `labels.ts`, `answer-markdown.tsx`, `frontend/lib/sse.ts` | `use-chat.ts` xử lý event bằng chuỗi `if/else if`, **bỏ qua event lạ** nên thêm event không làm hỏng client cũ. `chat-turn.tsx` đã bọc câu trả lời trong `StreamingText` (status `streaming`) và `ChatNotice` đã có tiêu đề "Câu trả lời bị gián đoạn" khi có `turn.answer` mà lỗi |

Phiên bản đã kiểm tra trong `uv.lock` và `.venv`: `langgraph 1.2.23`, `langgraph-checkpoint 4.3.2`, `langchain-core 1.8.0`, `langchain-openai 1.7.4`, `openai 3.50.0`, `fastapi 0.162.5`, `starlette 1.10.0`. Frontend (`frontend/node_modules`): `react 19.3.0`, `next 16.4.6`, `react-markdown 10.1.0`, `remark-gfm 4.0.1`; **chưa** có `streamdown`/`remend`.

## 3. Ngân sách độ trễ (số đo thật)

Nguồn: `scripts/text2sql_eval/results/a2-final-x2.json` (file có 112 lượt; số liệu dưới đây tính trên 100 lượt có event `preprocess`, bỏ 12 lượt chạy tiếp sau hỏi lại vì không có bước tiền xử lý; model `openai/gpt-6-luna`, route stream) và `a2-trace*.jsonl` (389 lần chạy agent).

| Đại lượng | Median | p90 |
|---|---|---|
| Tổng thời gian lượt | 13,34 s | 19,76 s |
| Event đầu tiên (`turn`) | 0,69 s | 1,01 s |
| Event `preprocess` đến lúc | 6,29 s | 8,17 s |
| Câu con dài nhất (`question_started` → `question_answered`) | 6,0 s | 10,67 s |
| Phần đuôi sau câu con, câu tách (12 lượt, chủ yếu là synthesize) | 2,61 s | 9,42 s |
| Phần đuôi, câu đơn | 0,05 s | 0,07 s |
| Số vòng LLM mỗi lần chạy agent | 3 (tối đa 7) | |
| Token ra của câu trả lời cuối | 60,5 | 140 (tối đa 310) |
| Thông điệp AI có gọi công cụ mà **kèm chữ** | **0 / 820** | |

Gọi thật OpenRouter (script `proto_openrouter.py`, mục 9):

- Vòng có công cụ: chunk đầu ở 1,06 s đã là `tool_call_chunks` với `name` và `id`, các chunk sau chỉ có `args` từng mảnh; `content` luôn rỗng; chunk áp chót có `finish_reason='tool_calls'`, chunk cuối có `usage_metadata`.
- Vòng trả lời: chunk chữ đầu ở 1,04 s, 47 token xong sau thêm 0,4 s (`'N'`, `'hi'`, `'ệt'`, ... chuỗi Python đã giải mã UTF-8 nên không vỡ ký tự).
- Câu văn bản thuần có suy luận ẩn: chunk chữ đầu ở **2,62 s** vì 126 token `reasoning` không được stream (không có trong `additional_kwargs`).
- `usage_metadata` có ở chunk cuối **dù không bật `stream_usage`** (`ChatOpenAI.stream_usage` là `None` vì `base_url` không phải OpenAI; OpenRouter luôn trả usage ở chunk cuối trên endpoint Chat Completions, [tài liệu streaming OpenRouter](https://openrouter.ai/docs/api-reference/streaming)).

Kết luận: chữ của câu đơn sẽ bắt đầu hiện khoảng 1–1,5 s trước khi xong; câu tách thì phần synthesize (p90 9,4 s) có lợi rõ hơn. Khoảng im lặng lớn nhất là 0,7–6,3 s (tiền xử lý) và mỗi vòng công cụ (khoảng 1–3 s), nên cần lời kể tiến độ.

## 4. Kiểm chứng hành vi thư viện

### 4.1 `stream_mode="messages"` với graph hiện tại

Đọc `langgraph/pregel/_messages.py::StreamMessagesHandler` (1.2.23):

- `on_chat_model_start`: `if not self.subgraphs and len(ns) > 0 and ns != self.parent_ns: return`. Lời gọi LLM trong graph con (namespace khác rỗng) **bị bỏ** nếu không bật `subgraphs=True`. Bỏ qua cả lời gọi có tag `"nostream"` (`langgraph.constants.TAG_NOSTREAM`).
- Handler kế thừa `_StreamingCallbackHandler`, mà `BaseChatModel._should_stream` (`langchain_core/language_models/chat_models.py`, dòng 590–626) trả `True` khi có handler loại này. Nghĩa là bật mode `messages` thì **mọi** `invoke` của chat model trong graph tự chuyển sang streaming, kể cả `rewrite` (ra JSON).
- `on_chain_end` còn phát lại nguyên thông điệp từ output của node (khử trùng theo `message.id`), gồm cả `ToolMessage` ở bản v1.

Chạy thử (`proto_graph.py`), graph cùng hình với `chat_graph.py`: Send hai câu song song, mỗi node `answer_question` gọi `inner.invoke(...)` một graph agent/tools, sau đó `synthesize`:

- `subgraphs=False`: **chỉ có token của `synthesize`** (node cấp cao nhất), metadata có `langgraph_node='synthesize'` và `tags=['synthesize']` nếu gọi với `config={"tags": [...]}`. Token của agent và cả `writer(...)` gọi trong node của graph con đều **không** xuất hiện.
- `subgraphs=True`: mỗi phần tử thành bộ ba `(namespace, mode, chunk)`, namespace là `('answer_question:<task_id>',)`. Token của hai nhánh song song **xen kẽ nhau**, metadata **không có `position`** (chỉ có `langgraph_node='agent'`, `checkpoint_ns`). `ToolMessage` cũng đi ra kênh messages, và các update của graph con (`agent`, `tools`) đi ra kênh updates. Code hiện tại (`for mode, chunk in graph.stream(...)` rồi `update_events(node, update)`) sẽ phải lọc lại theo namespace.

Đánh giá: dùng được nhưng phải (1) bật `subgraphs=True` và đổi cách đọc stream, (2) gắn tag vị trí câu cho từng lời gọi (`with_config(tags=[f"q{position}"])`) rồi tra ngược, (3) gắn `nostream` cho `rewrite`, `intent_classify`, (4) tự lọc vòng có gọi công cụ. Nhiều chỗ ngầm hơn cách 4.2 mà không thêm lợi ích.

### 4.2 Stream writer tự đẩy (`get_stream_writer` + callback): cách đề xuất

Code hiện tại đã lấy writer trong node ngoài (`_emitter`) và truyền closure xuống agent qua `on_tool`, nên writer dùng được từ bên trong graph con mà không cần `subgraphs=True`. Chạy thử `proto_callback.py`: trong `_call_model` của graph con, đổi `invoke` thành vòng `for chunk in model.stream(messages)`, cộng dồn `acc = acc + chunk`, đẩy `chunk.content` qua callback, cuối vòng `message_chunk_to_message(acc)`:

- Event `custom` của hai nhánh song song xen kẽ, nhưng **trong mỗi `position` đúng thứ tự** (mỗi nhánh một thread sản xuất duy nhất).
- `message_chunk_to_message` trên chunk cộng dồn cho ra `AIMessage` có `tool_calls` đã parse đầy đủ (cả với OpenRouter thật: `{'metric': 'avg_temperature', 'group_by': ['city']}`) và `usage_metadata`. Vòng agent sau đó không cần đổi.
- Chữ đến **trước** `tool_call_chunks` trong cùng vòng (model giả cố ý viết "Để trả lời, tôi tra metric." rồi gọi công cụ) đã bị đẩy đi. Phải có event `answer_reset` để client xóa bản nháp của vòng đó. Với model hiện tại điều này chưa xảy ra lần nào (0/820), nhưng đổi model thì có thể.
- Callback ném lỗi giữa chừng (giả lập client ngắt): lỗi lan ra khỏi `graph.stream` (đúng như `Text2SqlClientDisconnected` hôm nay). Với `ChatOpenAI`, generator đóng sẽ đóng response HTTP (`with context_manager as response:` trong `langchain_openai/chat_models/base.py::_stream`). Thử thật: `gen.close()` sau 5 chunk kết thúc ngay. Vậy **nút Dừng sẽ đóng được kết nối của lời gọi LLM đang chạy** (ở lần đẩy delta kế tiếp); hôm nay tài liệu ghi "Lời gọi LLM đang chạy dở không bị hủy giữa chừng". Lưu ý: theo [tài liệu OpenRouter](https://openrouter.ai/docs/api-reference/streaming), ngắt kết nối chỉ dừng xử lý và **dừng tính tiền** với các nhà cung cấp hỗ trợ hủy (OpenAI, Azure, Anthropic, DeepInfra, xAI, ...); với nhà cung cấp không hỗ trợ (Google, Google AI Studio, Bedrock, Groq, Mistral, ...) model vẫn chạy hết và vẫn tính tiền đủ. Lời gọi đang ở vòng gọi công cụ (content rỗng, không có delta) cũng không bị đóng cho tới khi nó tự xong, vì không có lần ghi event nào giữa chừng.
- Nên đẩy `chunk.text` (thuộc tính của `BaseMessage` ở langchain-core 1.x, ghép các khối văn bản) thay vì `chunk.content`: nếu đổi sang model/nhà cung cấp trả `content` dạng danh sách khối (reasoning, text), `content` không còn là chuỗi. Code hiện tại cũng dùng `last.text.strip()` trong `run_tool_agent`.

### 4.3 Synthesize đang trả JSON

- Stream token của JSON vô ích nếu đẩy nguyên văn. `langchain_core.utils.json.parse_partial_json` có parse được tiền tố (`'{"answer": "Hà Nội **22,4°C**.\n- Huế: 25'` thành `{'answer': 'Hà Nội **22,4°C**.\n- Huế: 25'}`), nhưng **ném `JSONDecodeError`** khi model bọc trong ```` ```json ````. Tuy vậy `langchain_core.utils.json.parse_json_markdown` (cũng là thứ `JsonOutputParser` dùng khi stream với `partial=True`) bóc rào ```` ```json ```` rồi mới gọi `parse_partial_json`, nên tiền tố có rào vẫn parse được (đã chạy thử: ```` ```json\n{"answer": "abc ```` thành `{'answer': 'abc'}`). Vậy stream JSON làm được, nhưng vẫn phải tự tính phần chữ mới giữa hai lần parse, chịu chi phí parse lại cả chuỗi mỗi chunk, và giữ nhánh dự phòng văn bản thuần của `SynthesizeParser`. Phức tạp hơn đáng kể so với văn bản thuần.
- Thêm một lời gọi "trả lời cuối không công cụ" sau JSON: tốn thêm khoảng 1–2,6 s và thêm token, không hợp lý.
- **Đề xuất: synthesize trả văn bản Markdown thuần.** Schema JSON chỉ có một trường `answer`, `SynthesizeParser` vốn đã chấp nhận văn bản thuần, nên đổi prompt và bỏ parser là đủ: prompt kết thúc bằng "Chỉ viết câu trả lời bằng Markdown, không bọc JSON", gọi `get_chat_model().stream(...)` qua `ChatPromptTemplate`, rồi `StrOutputParser` hoặc nối chuỗi. Đây là thay đổi hành vi LLM nên phải chạy lại nhóm `split` và `dependent` của bộ đánh giá.

### 4.4 Câu trả lời cuối là `AIMessage` cuối của vòng công cụ

Không biết trước vòng nào là vòng cuối. Với `bind_tools`, OpenRouter/OpenAI cho thấy ngay ở chunk đầu đó là vòng gọi công cụ (`tool_call_chunks` có `name`). Quy tắc an toàn: chỉ đẩy `content` khi `acc.tool_call_chunks` còn rỗng; cuối vòng, nếu đã đẩy chữ mà thông điệp có `tool_calls` thì phát `answer_reset {position, round}`. Vòng "hết lượt" (`EXHAUSTED_NOTICE`, gọi model không công cụ) cũng stream được theo cùng cách.

## 5. Phương án

| | A. `stream_mode="messages"` + `subgraphs=True` | B. Writer + callback trong agent/synthesize (đề xuất) | C. Chỉ lời kể tiến độ, không stream token |
|---|---|---|---|
| Token câu con song song | Có, phải tra `position` bằng tag | Có, `position` gắn sẵn trong closure | Không |
| Token synthesize | Có (node cấp cao) | Có | Không |
| Lọc JSON của rewrite/intent | Phải gắn `nostream` | Không cần, chỉ stream nơi gọi `.stream` | – |
| Đổi cách đọc `graph.stream` | Có (bộ ba, update của graph con lẫn vào) | Không | Không |
| Route JSON | Không stream vì không có writer, nhưng `invoke` vẫn tự stream nếu có handler | Chỉ giữ `invoke` nếu thêm cờ "đang stream" (hôm nay `_answer_question` luôn truyền `emit` khác `None`, kể cả route JSON); không thêm cờ thì route JSON cũng stream rồi bỏ event, kết quả vẫn như cũ | Không đổi |
| Hủy LLM khi Dừng | Không trực tiếp | Có (lỗi từ callback đóng stream HTTP) | Không |
| Công sức | Trung bình, nhiều chỗ ngầm | Nhỏ đến trung bình | Nhỏ |

Phương án D, gom câu tách độc lập không qua LLM synthesize để giảm hẳn 2,6–9,4 s, nằm ngoài chủ đề streaming. Ghi ở mục 8 để người dùng quyết.

## 6. Thiết kế đề xuất

### 6.1 Hợp đồng SSE: chỉ **thêm** event, không đổi event cũ

| Event mới | Khi nào | `data` |
|---|---|---|
| `tool_started` | Ngay trước khi chạy một công cụ (trong `_call_tools`) | `position`, `tool`, `arguments` (không có SQL hay dòng). Không phát cho `ask_user` |
| `answer_delta` | Mỗi đoạn chữ mới (đã gom khoảng 50 ms) | `position` (số, hoặc `null` cho synthesize), `round` (vòng LLM trong câu), `final` (`true` nếu đoạn chữ này sẽ thành câu trả lời của lượt: câu đơn không tách, hoặc synthesize), `text` |
| `answer_reset` | Vòng vừa stream chữ hóa ra có gọi công cụ | `position`, `round` |
| `synthesize_started` | Đầu node `_synthesize` khi thật sự gọi LLM | `{}` |
| (tùy chọn) `preprocess_progress` | Sau bước `rewrite` (trước intent và truy hồi) | `stage: "rewritten"`, `rewritten_question`, `question_count` |

Quy tắc giữ nguyên: `question_answered.answer` và `answer.answer` vẫn là **bản chính thức**. Client thay bản nháp bằng bản này: bản chính thức đã `strip()` và có thể là `EMPTY_ANSWER`. `done` không đổi. Thứ tự trong một `position`: `question_started` → (`tool_started` → `tool`)\* xen `answer_delta`/`answer_reset` → `question_answered` hoặc `question_waiting`. Synthesize: `synthesize_started` → `answer_delta(position=null, final=true)`\* → `answer`.

Ví dụ câu đơn:

```
event: question_started   data: {"position":1,"question":"…","resumed":false}
event: tool_started       data: {"position":1,"tool":"query_metric","arguments":{"metric":"nhiet_do_tb"}}
event: tool               data: {"position":1,"tool":"query_metric",…,"row_count":12}
event: answer_delta       data: {"position":1,"round":1,"final":true,"text":"Nhiệt độ trung bình"}
event: answer_delta       data: {"position":1,"round":1,"final":true,"text":" tuần trước là **24,1°C**…"}
event: question_answered  data: {"position":1,…,"answer":"…"}
event: answer             data: {"answer":"…"}
event: done               data: {…}
```

### 6.2 Backend

1. `backend/agent_package/tool_agent.py`
   - Thêm vào `ToolAgentContext`: `on_text: TextCallback | None` (gồm `delta(round, text)` và `end(round, discard: bool)`) và `on_tool_start: Callable[[str, dict], None] | None`.
   - `_call_model`: nếu `on_text is None` thì giữ `invoke` (route JSON, test `ScriptedModel` không đổi); ngược lại dùng hàm `_stream_round(runnable, messages, on_text, round)` như mục 4.2, trả `AIMessage` qua `message_chunk_to_message`. Áp cho cả nhánh hết lượt.
   - `_call_tools`: gọi `on_tool_start(name, args)` trước `_run_tool`, trừ `ask_user`.
   - `run_tool_agent(..., on_text=None, on_tool_start=None)`. `agent_package` không import từ `modules`, giữ đúng quy ước.
2. `services/text2sql_agent_service.py::AgentRun.answer`: **lưu ý** `chat_graph.py::_answer_question` luôn gọi `_emitter(runtime)` và truyền `emit` khác `None`, kể cả với route JSON (`ChatService.chat` → `execute(..., emit=None)` → `run_chat_graph(on_event=None)` chỉ bỏ event ở vòng đọc stream, writer trong node vẫn được gọi). Hôm nay vì vậy `on_tool` cũng chạy ở route JSON. Muốn route JSON giữ đúng `invoke` thì phải thêm cờ, ví dụ `ChatGraphContext.streaming: bool` (đặt `= on_event is not None` trong `run_chat_graph`/`execute`) và chỉ dựng `on_text`/`on_tool_start` khi cờ bật. Không thêm cờ thì route JSON vẫn đúng kết quả (chunk được ghép lại) nhưng đi đường stream. Khi cờ bật, dựng `on_text` gắn `item.position` và cờ `final = not preprocess.is_split and len(preprocess.questions) == 1`, có bộ gom ~50 ms hoặc ≥ 32 ký tự, xả khi `end`. Dựng `on_tool_start` phát `tool_started`.
3. `services/chat_events.py`: thêm builder `delta_event`, `reset_event`, `tool_started_event` (tên event là hằng).
4. `prompts/prompt_synthesize.py` + `agent_package`: thêm hàm stream văn bản thuần, ví dụ `stream_chat_text(system_prompt, params, on_text=None) -> str`, dùng `get_chat_model()`. `invoke` khi `on_text` là `None`. Đổi prompt synthesize sang Markdown thuần. Bỏ `synthesize` khỏi `PROMPTS_BY_TASK` hoặc giữ parser cũ cho tương thích, tùy quyết định ở mục 8.
5. `services/chat_graph.py`: đổi kiểu `Synthesize = Callable[[PreprocessOut, list[QuestionAnswerOut], Emit | None], str]`; `_synthesize` lấy `_emitter(runtime)`, phát `synthesize_started` rồi truyền emit. `STREAM_MODES` giữ `["updates", "custom"]`.
6. `services/chat_service.py::_synthesize`: dùng hàm mới, bắt `OpenAIError` như `_complete`. Hàm stream nên được tiêm qua constructor `ChatService` giống `completion: Completion = get_chat_completion` (ví dụ `text_completion`), để test thay bằng bản giả thay vì gọi `get_chat_model()` thật. (Tùy chọn) `preprocess(..., emit)` phát `preprocess_progress` sau `rewrite`. Cần truyền emit vào `ChatGraphContext.preprocess`.
7. `chat_stream.py` không đổi: `_emit` đã kiểm tra `stopped` ở mỗi event, nên delta đầu tiên sau khi client ngắt sẽ ném `Text2SqlClientDisconnected` và đóng stream LLM.
8. Lưu hội thoại (`_complete_turn`) không đổi: chỉ lưu bản chính thức; bản nháp không lưu. Client ngắt giữa chừng thì lượt vẫn thành `error/client_disconnected` như hôm nay.
9. Hỏi lại/chạy tiếp: `ask_user` là vòng gọi công cụ nên không có chữ; nhánh chạy tiếp (`pending`/`reply`) đi qua cùng `AgentRun.answer` nên tự có delta. Snapshot checkpoint không chứa callback vì `ToolAgentContext` không được checkpoint, chỉ có `ToolAgentPause.messages`.

### 6.3 Frontend

1. `types.ts`: thêm `ToolStartedEvent`, `AnswerDeltaEvent`, `AnswerResetEvent` vào union `ChatEvent`.
2. `use-chat.ts`
   - `QuestionState` thêm `draft?: string`, `draftRound?: number`, `activeTool?: {tool, arguments}`; `Turn` thêm `phaseNote?` (hoặc suy ra) và dùng `turn.answer` cho bản nháp `final`.
   - `answer_delta`: `final` thì nối vào `turn.answer`; ngược lại nối vào `question.draft`. Có `round` mới thì bắt đầu chuỗi mới. `answer_reset`: xóa phần của vòng đó. `question_answered`/`answer`: **ghi đè** bằng bản chính thức (sửa nhánh `done` hiện dùng `turn.answer || outcome.answer`, vẫn đúng vì `answer` đã ghi đè).
   - Gộp cập nhật: đẩy delta vào ref và `setTurns` một lần mỗi `requestAnimationFrame`, để 100 chunk/s không thành 100 lần render Markdown.
3. Lời kể tiến độ (`labels.ts`, deterministic, không gọi LLM):
   - Chưa có `preprocess`: "Đang đọc câu hỏi…" (đã có bước "Hiểu câu hỏi" ở trạng thái running; đổi chữ là đủ).
   - `tool_started`: `get_metric` "Đang xem định nghĩa chỉ số «label»…", `get_table` "Đang xem cấu trúc bảng «table»…", `get_expert_rule` "Đang đọc quy tắc «rule»…", `get_column_values` "Đang kiểm tra cách ghi giá trị của «column»…", `query_metric` "Đang truy vấn «label»…", `run_sql` "Đang chạy truy vấn…". Nhãn metric lấy từ `preprocess.questions[].metrics` như `dataResults` đang làm.
   - `tool`: dòng tương ứng chuyển thành thì quá khứ ("Đã lấy 12 dòng").
   - Có `answer_delta` đầu tiên: "Đang viết câu trả lời…". `synthesize_started`: "Đang tổng hợp câu trả lời…".
   - Dòng hiện tại hiển thị ở nhãn của `ThinkingTrace` (`label` prop); danh sách bước vẫn còn nhưng tên công cụ thô chỉ ở phần chi tiết.
4. Câu tách: bản nháp của từng câu con hiển thị trong mục của câu đó trong `ThinkingTrace` (đang thu gọn), **không** ở ô trả lời chính. Ô chính chỉ nhận delta `final` của synthesize. Như vậy người dùng không thấy hai bản trả lời trùng nhau.
5. Markdown đang dở (`answer-markdown.tsx`):
   - `react-markdown` không render HTML thô (không có `rehype-raw`) nên chuỗi dở dang không gây XSS.
   - Lỗi hiển thị tạm thời: `**22,4` hiện dấu sao cho tới khi đóng; dòng bảng `| Hà Nội | 22` hiện như đoạn văn cho tới khi có dòng phân cách. Cách nhẹ: khi `status === "streaming"`, (a) tạm ẩn dòng cuối chưa kết thúc nếu bắt đầu bằng `|`; (b) đóng tạm `**` hoặc `` ` `` lẻ của đoạn cuối; (c) tách theo dòng trống thành khối và `memo` từng khối, để khối đã xong không parse lại.
   - Cách nặng hơn: thay bằng [`streamdown`](https://github.com/vercel/streamdown) (Vercel, cùng props với react-markdown, có `remend` sửa cú pháp dở và cache theo khối). Phải thêm dependency và kiểm tra tương thích `components` hiện có. Câu trả lời ngắn (median 150 ký tự, tối đa 517 ký tự trong bộ đánh giá) nên cách nhẹ là đủ.
6. Dừng: `stop()` đã `abort()` fetch. Phía server Starlette đóng generator, `stopped` được bật, delta kế tiếp ném lỗi và stream LLM bị đóng. Phần nháp đã hiện giữ nguyên với trạng thái "stopped".
7. Nối lại khi rớt mạng: **không hỗ trợ** được nếu không đổi kiến trúc. Lượt chạy gắn với request; ngắt là dừng. Muốn nối lại phải tách lượt chạy khỏi request: hàng đợi nền, log event theo `id:`, và `GET .../turns/{id}/events?after=N`. Đề xuất giữ như hiện tại: báo "Kết nối bị ngắt" kèm nút hỏi lại; lượt đã xong thì mở lại từ lịch sử.

### 6.4 Tài liệu cần cập nhật khi triển khai

`docs/handbook/modules/text2sql/api-chat.md` (bảng event, thứ tự, đoạn "Lời gọi LLM đang chạy dở không bị hủy"), `docs/handbook/modules/agent_package.md` (tham số mới của `run_tool_agent`, hàm stream văn bản), `docs/handbook/frontend/README.md` nếu có mục tab chat. Đánh dấu **đã triển khai** theo `AGENTS.md`.

## 7. Kế hoạch triển khai từng bước

| Bước | Nội dung | File | Kiểm thử |
|---|---|---|---|
| 1 | Lời kể tiến độ: `tool_started`, `synthesize_started`; frontend hiển thị câu "Đang …" | `tool_agent.py`, `text2sql_agent_service.py`, `chat_events.py`, `chat_graph.py`, `types.ts`, `use-chat.ts`, `labels.ts`, `chat-turn.tsx` | `tests/test_text2sql_agent.py::ToolAgentTests`: `on_tool_start` gọi trước `on_tool`, không gọi cho `ask_user`. `tests/test_text2sql_chat.py::ChatStreamRouteTests`: thứ tự `tool_started` trước `tool` cùng `position`. `npm run typecheck`, `npm run lint` |
| 2 | Token câu con và câu đơn: `answer_delta`/`answer_reset`, gom 50 ms | `tool_agent.py`, `text2sql_agent_service.py`, `chat_events.py`, `use-chat.ts` | Thêm `stream()` cho `ScriptedModel`, trả list `AIMessageChunk`. Test: (a) delta theo đúng `position`, `final` đúng; (b) vòng có công cụ sau chữ thì có `answer_reset`; (c) không có callback thì gọi `invoke`, và route JSON (`/chat`) không dựng callback nhờ cờ `streaming` ở bước 2 của 6.2; (d) ghép delta bằng bản chính thức sau `strip`; (e) `ChatStreamStopTests`: dừng giữa delta ra `client_disconnected`, lượt ghi `error`. Test hai nhánh song song: delta của mỗi `position` đúng thứ tự |
| 3 | Synthesize Markdown thuần + stream | `prompt_synthesize.py`, `get_chat_completion.py` hoặc hàm mới trong `agent_package`, `chat_service.py`, `chat_graph.py` | `FakeCompletion` thêm đường văn bản; test `answer` bằng nối các delta `final`; chạy lại `scripts/text2sql_eval/run_eval.py` nhóm `split`, `dependent` (và cả bộ 98 câu để chắc không lệch) |
| 4 | Hiển thị Markdown dở dang, gộp theo frame | `answer-markdown.tsx`, `use-chat.ts` | Kiểm tra tay bằng câu có bảng và danh sách; Playwright chụp giữa stream |
| 5 | (Tùy chọn) `preprocess_progress` sau rewrite | `chat_service.py::preprocess`, `chat_graph.py::_preprocess` | Test event có trước `preprocess`; lượt chạy tiếp không có event này |
| 6 | Tài liệu và báo cáo đo lại | mục 6.4; `run_eval.py` ghi thêm thời điểm `answer_delta` đầu tiên | So TTFT chữ trước/sau |

Bước 1 độc lập và cho lợi ích lớn nhất trên mỗi dòng code; bước 2 và 3 tách được để dễ review.

## 8. Rủi ro và câu hỏi cho người dùng

Rủi ro:

- **Đổi model.** Model khác (Claude, Gemini qua OpenRouter) hay viết lời dẫn trước khi gọi công cụ, nên người dùng sẽ thấy chữ hiện rồi bị xóa. `answer_reset` xử lý được về đúng sai, nhưng trải nghiệm hơi giật. Có thể đổi thành: chữ của vòng bị reset chuyển thành một dòng lời kể trong trace thay vì biến mất.
- **Synthesize đổi sang văn bản thuần** là thay đổi prompt, có thể làm lệch kết quả bộ đánh giá; bắt buộc chạy lại.
- **Số event tăng** (khoảng 20–40 event/câu sau khi gom). Proxy có buffer thì vẫn cần `X-Accel-Buffering: no` (đã có). Log hoặc `run_eval.py` nếu ghi mọi event sẽ phình; nên bỏ `answer_delta` khỏi log mặc định.
- **Chữ nháp khác bản chính thức** (khoảng trắng đầu/cuối, `EMPTY_ANSWER`, chữ đã đẩy trước `answer_reset`). Client luôn ghi đè bằng bản chính thức.
- **Suy luận ẩn** của model làm chữ đầu đến chậm (2,6 s trong thử nghiệm), không stream được phần này. Lời kể tiến độ che khoảng này.
- **Lượt chạy tiếp từ checkpoint**: snapshot cũ không có trường mới nào nên không cần migrate. Vẫn nên có test lượt chạy tiếp có delta.
- **Hủy khi Dừng không đồng nghĩa ngừng tính tiền**: phụ thuộc nhà cung cấp OpenRouter định tuyến tới (mục 4.2). Vòng gọi công cụ không có delta nên chỉ dừng sau khi vòng đó xong.

Câu hỏi:

1. Câu tách: bản nháp của câu con có nên hiện (trong trace thu gọn) hay chỉ hiện lời kể, để ô trả lời chỉ stream bản tổng hợp?
2. Đổi synthesize sang Markdown thuần có được không (cần chạy lại đánh giá)? Hay giữ JSON cho route `/chat` và chỉ stream ở `/chat/stream`? Giữ cả hai tức là hai prompt.
3. Có muốn bỏ hẳn LLM synthesize với câu tách độc lập (ghép câu trả lời con theo mẫu) để giảm 2,6–9,4 s, đổi lại câu văn kém liền mạch hơn?
4. Lời kể tiến độ dùng mẫu cố định ở frontend (đề xuất, không tốn thời gian) hay muốn agent tự viết một câu dẫn trước mỗi lần gọi công cụ (tự nhiên hơn nhưng thêm token và độ trễ, có thể ảnh hưởng độ chính xác)?
5. Có cần nối lại sau khi rớt mạng không? Nếu cần thì phải chạy lượt ở nền, độc lập với request: việc lớn, nên tách thành đề xuất riêng.
6. Thêm dependency `streamdown` hay tự xử lý Markdown dở dang (đề xuất tự xử lý vì câu trả lời ngắn)?

## 9. Script thử nghiệm (ngoài repo, có thể xóa)

- `C:\Users\dat\AppData\Local\Temp\claude\d--Code-Superset-AI\3428e385-9db2-46b6-835b-611b745f0661\scratchpad\stream\proto_graph.py`: model giả có `_stream` (chữ + `tool_call_chunk`), graph ngoài Send song song, graph con lồng, so sánh `stream_mode=["updates","custom","messages"]` với `subgraphs=False/True`.
- `...\scratchpad\stream\proto_callback.py`: cách B, gồm delta theo `position`, `answer_reset`, dừng giữa chừng.
- `...\scratchpad\stream\proto_openrouter.py`: gọi thật OpenRouter (khóa đọc từ settings, không in), hình dạng chunk khi `bind_tools`, vòng trả lời, văn bản thuần, đóng generator sớm.

Nguồn tham khảo: [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming), [tham chiếu `stream`](https://reference.langchain.com/python/langgraph/stream), [OpenRouter streaming](https://openrouter.ai/docs/api-reference/streaming), [vercel/streamdown](https://github.com/vercel/streamdown). Hành vi cụ thể ở trên được xác nhận bằng đọc mã đã cài và chạy script, không chỉ dựa vào tài liệu.

## Kiểm tra lại (2026-11-20, người rà soát độc lập)

Đã xác nhận đúng (đọc mã đã cài, chạy lại script):

- Phiên bản trong `uv.lock` và `frontend/node_modules` khớp; `streamdown`/`remend` chưa cài.
- `langgraph/pregel/_messages.py` (1.2.23): điều kiện `TAG_NOSTREAM` và `not self.subgraphs and len(ns) > 0 and ns != self.parent_ns` ở `on_chat_model_start`; `BaseChatModel._should_stream` (dòng 590–626) trả `True` khi có `_StreamingCallbackHandler`.
- Chạy lại `proto_graph.py` và `proto_callback.py`: kết quả đúng như mô tả ở mục 4.1, 4.2 (chỉ token `synthesize` khi `subgraphs=False`, writer của graph con không ra; bộ ba namespace, xen kẽ, `ToolMessage` khi `subgraphs=True`; delta đúng thứ tự trong mỗi `position`, lỗi từ callback lan ra khỏi `graph.stream`).
- Số đo mục 3 tính lại khớp (tổng median 13,335 s, p90 19,73 s; `preprocess` median 6,29 s; câu con dài nhất median 6,0 s).
- `use-chat.ts` bỏ qua event lạ; `ScriptedModel` chỉ có `invoke`.
- Không chạy lại `proto_openrouter.py` (gọi thật, tốn tiền); các số về OpenRouter giữ nguyên theo người nghiên cứu.

Đã sửa trong báo cáo:

1. **Route JSON không "y như cũ"**: `_answer_question` luôn truyền `emit` khác `None` (cả với `/chat`), nên điều kiện "có `emit` thì dựng `on_text`" sẽ khiến route JSON cũng stream. Đã thêm đề xuất cờ `ChatGraphContext.streaming` (mục 1, bảng mục 5, mục 6.2 bước 2, test bước 2).
2. **`parse_partial_json` với rào ```` ```json ````**: đúng là ném lỗi, nhưng `parse_json_markdown` / `JsonOutputParser` xử lý được. Đã sửa mục 4.3 cho công bằng; đề xuất văn bản thuần vẫn giữ.
3. **Hủy LLM khi Dừng**: bổ sung rằng OpenRouter chỉ dừng xử lý và tính tiền với nhà cung cấp hỗ trợ hủy, và vòng gọi công cụ (không có delta) không bị đóng giữa chừng (mục 4.2, mục 8).
4. Đề nghị đẩy `chunk.text` thay vì `chunk.content` (mục 4.2).
5. Mục 3: ghi rõ 100 lượt là lượt có `preprocess` trong 112 lượt của file.
6. Mục 6.2 bước 6: hàm stream synthesize cần tiêm qua constructor `ChatService` như `completion` để test được.
7. Sửa URL tài liệu OpenRouter thành `https://openrouter.ai/docs/api-reference/streaming`.
