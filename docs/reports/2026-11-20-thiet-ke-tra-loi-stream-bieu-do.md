# Thiết kế: câu trả lời tự nhiên, stream câu trả lời và bộ biểu đồ cho agent (tab "Hỏi dữ liệu")

Ngày: 2026-11-20. Loại: **thiết kế sẵn sàng triển khai**, chưa sửa code. Người viết: kiến trúc sư (một bước của
workflow). Tài liệu này hợp nhất ba báo cáo nghiên cứu và bốn quyết định của người dùng thành một hợp đồng duy nhất
cho ba người triển khai BE1, BE2, FE.

Bản này đã sửa theo phản biện (đạt có điều kiện, 20 điểm). Danh sách thay đổi và điểm không theo nằm ở
[mục 8](#8-phản-biện-và-điều-chỉnh); các chỗ sửa trong thân bài có ghi `(PB-n)` theo số thứ tự ở mục 8.

Nguồn đã đọc:

- [Nghiên cứu stream](2026-11-20-nghien-cuu-streaming-cau-tra-loi.md),
  [nghiên cứu câu trả lời tự nhiên](2026-11-20-nghien-cuu-cau-tra-loi-tu-nhien.md),
  [nghiên cứu biểu đồ và Superset](2026-11-20-nghien-cuu-tich-hop-chart-superset.md),
  [kết quả chạy thật](2026-11-19-ket-qua-chay-that-text2sql.md).
- Code hiện tại (chưa commit, 209 test xanh): `backend/agent_package/tool_agent.py`, `get_chat_completion.py`,
  `prompts/prompt_text2sql_agent.py`, `prompts/prompt_synthesize.py`; `backend/modules/text2sql/services/`
  (`chat_graph.py`, `chat_service.py`, `chat_events.py`, `chat_stream.py`, `text2sql_agent_service.py`,
  `agent_tools.py`, `agent_catalog.py`, `sql_builder.py`), `schemas/schema_text2sql.py`, `routes/router_chat.py`;
  module `conversation` (model, schema, service, router, migration); `frontend/features/text2sql/*`,
  `frontend/components/ui/chart.tsx`, `components/stat-charts.tsx`, `app/globals.css`; handbook `api-chat.md`,
  `ghi-luot-tu-pipeline.md`, `du-lieu-va-migration.md`, `frontend/README.md`.
- Skill `dataviz` (đã nạp và làm theo: chọn dạng trước màu, bảng màu đã kiểm, không trục kép, quy tắc nhãn, hover,
  bảng song song).

## 0. Tóm tắt các quyết định

| # | Quyết định của người dùng | Thiết kế chốt |
| --- | --- | --- |
| 1 | Câu trả lời tự nhiên bằng sửa prompt (A/A+), không thêm lời gọi LLM | Viết lại mục trả lời của prompt agent và prompt synthesize (mục 2.1, 2.2). Code định dạng sẵn dữ liệu đưa cho agent (nhãn, đơn vị, số `1.234,5`, ngày "thứ Năm, 19/11"). Xưng "tôi", kết luận trước. Khối **"Cách tính"** do code dựng từ bước công cụ (`explanations`), lời văn giữ tối đa một mệnh đề giả định. |
| 2 | Câu trả lời lên đầu; bảng và SQL thu vào "Số liệu và cách tính" | Bố cục mục 5. |
| 3 | Stream câu trả lời cuối; câu tách stream bản tổng hợp, bản nháp từng câu con nằm trong mục thả xuống ẩn được; lời kể tiến độ | Hợp đồng SSE mục 3: `tool_started`, `answer_delta {position, round, final, text}`, `answer_reset`, `synthesize_started`. Câu đơn: stream mọi vòng LLM của agent với `final=true`, xóa vòng hóa ra gọi công cụ. Câu tách: chữ của agent là bản nháp `final=false`, chữ của synthesize là `final=true, position=null`. `/chat` (JSON) không stream nhờ cờ `ChatGraphContext.streaming`. |
| 4 | Không dùng Superset; bộ biểu đồ lớn, agent tự chọn và tùy chỉnh, người dùng đổi được, lưu theo kết quả | 32 loại biểu đồ vẽ bằng Recharts 3.8.0 có sẵn và HTML/CSS (không thêm thư viện). Spec JSON có phiên bản (`version: 1`), pydantic ở `backend/common/charts/`, kiểu TS ở frontend. Agent đặt `chart` ngay trong `query_metric`/`run_sql` hoặc gọi công cụ mới `make_chart(result_id, chart)`; code kiểm theo cột và dòng thật, báo lỗi chỉ đúng trường. Không có chart thì code tự đề xuất. Lựa chọn của người dùng lưu ở cột mới `conversation_turns.views`, API `PUT/DELETE .../views/{result_id}`. |

### 0.1 Mâu thuẫn giữa các báo cáo và cách giải quyết

| Điểm | Báo cáo stream | Báo cáo câu trả lời tự nhiên | Báo cáo biểu đồ | Chốt |
| --- | --- | --- | --- | --- |
| Ai viết câu trả lời cuối của câu đơn | Agent, stream thẳng (`final=true`) | Bước `compose` mới (thêm 1 lời gọi), chữ agent chỉ là nháp | – | **Agent** (người dùng chọn không thêm lời gọi). Không có `compose`. |
| `answer_delta` | `{position, round, final, text}` + `answer_reset` | `{text}` chỉ từ `compose` | – | Dùng hợp đồng của báo cáo stream. Câu đơn không tách: agent `final=true`. Câu tách: agent `final=false`, synthesize `position=null, final=true`. |
| Xưng hô | – | Không xưng "tôi" | – | Xưng **"tôi"** (quyết định 1). |
| Giả định trong lời văn | – | Giữ mệnh đề giả định | – | Giữ **tối đa một mệnh đề** khi giả định đổi nghĩa con số; phần còn lại vào "Cách tính". Agent ghi giả định vào tham số `assumption` của công cụ truy vấn để code đưa vào "Cách tính". |
| Synthesize trả JSON hay văn bản | Đổi sang Markdown thuần | Markdown thuần (trong `compose`) | – | **Markdown thuần cho cả hai route**; route JSON gọi `invoke`, route stream gọi `stream`. Bỏ `SynthesizeParser`. |
| Ai chọn biểu đồ | – | – | Code chọn, "không để LLM chọn ở bước đầu"; Superset lai | **Agent chọn và cấu hình**, code đề xuất mặc định và kiểm tra. **Không Superset**. |
| Kiểu cột | – | `column_labels` | `column_types` | Hợp nhất thành `fields[]` (tên, nhãn, kiểu, đơn vị, số lẻ, phần trăm, cộng dồn được hay không). |
| Khóa lưu lựa chọn | – | – | `"<position>:<chỉ số bước>"` | **`result_id`** ổn định (ví dụ `"1-2"`), có trong bước, event, `results` đã lưu. |
| Combo hai trục | – | – | – (đề bài gợi ý "dual axis") | **Không trục kép** (non-negotiable của dataviz: hai thang tự đặt tạo tương quan giả). `combo` chỉ khi các số đo cùng đơn vị; khác đơn vị thì `facet` (nhiều biểu đồ nhỏ) hoặc `transform.index_to = "first"`. Validator báo lỗi có gợi ý. |

## 1. Hiện trạng liên quan (đã đọc code)

- `tool_agent.py::_call_model` gọi `model.bind_tools(...).invoke(...)`; `_call_tools` gọi `on_tool` **sau** khi công
  cụ chạy. `run_tool_agent(..., on_tool=None)`; vòng hết lượt gọi `model.invoke` với `EXHAUSTED_NOTICE`.
- `chat_graph.py::_answer_question` **luôn** gọi `_emitter(runtime)` (cả route JSON); `_synthesize` dùng thẳng
  `answers[0].answer` khi một câu và không tách, ngược lại gọi `context.synthesize(preprocess, answers)`.
  `STREAM_MODES = ["updates", "custom"]`; event `answer` sinh ở `chat_events.update_events` khi `node == "synthesize"`.
- `chat_service.py::_synthesize` gọi `get_chat_completion("synthesize", ...)` (prompt đòi JSON, `SynthesizeParser` có
  nhánh văn bản thuần). `stored_steps` không lưu dòng; `stored_results` lưu `position, kind, tool, sql, columns, rows,
  row_count, truncated` (+ `metric.name`).
- `agent_tools.py::_execute` ghi `AgentStepOut` (rows đã qua `json_cell`) và trả cho LLM `sql, columns, rows (≤
  TEXT2SQL_AGENT_MAX_ROWS_TO_LLM), row_count, truncated, notes`. Ghi chú quy tắc (`sql_builder._rule_conditions`) và
  khớp giá trị (`_resolved_filter`) chỉ là chuỗi.
- `agent_catalog.py`: `ColumnInfo` có `label` nhưng không có `unit`, `format` (dù `column_dictionaries.unit`,
  `.format` có); `MetricInfo` có `label`, `format`, `currency`, không có đơn vị.
- `conversation_turns` không có cột trạng thái giao diện. Alembic head hiện tại: `e8b2c6d4f170`
  (`uv run alembic heads`); thư mục `init_conversation_module` có `a4c2e8f61b37`, `c5e1d7a3b902`.
- Frontend: `chat-turn.tsx` hiển thị trace → ghi chú viết lại → mọi `QueryResult` → câu trả lời; `query-result.tsx`
  tiêu đề cột là tên cột SQL, chân thẻ in `notes`; `use-chat.ts` bỏ qua event lạ; `labels.ts` có `TOOL_LABELS` lẫn
  chữ "metric". `globals.css` chỉ có `--chart-1..5` (năm màu đầu của bảng màu tham chiếu dataviz, có bước tối).
- Recharts 3.8.0 (đã chạy `require('recharts')` trong `frontend/node_modules`): có `Area, AreaChart, Bar, BarChart,
  BarStack, Brush, Cell, ComposedChart, ErrorBar, Funnel, FunnelChart, LabelList, Legend, Line, LineChart, Pie,
  PieChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, RadialBar, RadialBarChart, ReferenceArea,
  ReferenceDot, ReferenceLine, Sankey, Scatter, ScatterChart, SunburstChart, Tooltip, Treemap, XAxis, YAxis, ZAxis`.
  Không có heatmap/lịch nhiệt: dựng bằng lưới HTML/CSS. Box plot, waterfall, histogram, dumbbell, lollipop dựng từ
  các thành phần trên. **Không cần thư viện mới.**

## 2. Phần A: văn phong câu trả lời

### 2.1 Prompt agent: toàn văn mới của `backend/agent_package/prompts/prompt_text2sql_agent.py`

BE1 thay toàn bộ chuỗi `text2sql_agent_prompt` bằng nội dung dưới (mọi dòng ≤ 116 ký tự, giữ dấu `"""` mở/đóng như
hiện tại). Phần đầu vào và các bước 1, 2, 4 giữ ý cũ; các chỗ đổi: mô tả kết quả công cụ đã định dạng, `dates.label`,
`purpose`/`labels`/`assumption`, `options` dễ đọc, mục `# BIỂU ĐỒ`, mục `# CÂU TRẢ LỜI` và `# THEO LOẠI CÂU HỎI`.

```text
Bạn là Text2SqlAgent, chuyên viên số liệu. Nhiệm vụ: trả lời một câu hỏi đơn bằng số liệu truy vấn từ database
nguồn (PostgreSQL), qua các công cụ được cấp. Mọi con số trong câu trả lời phải lấy từ kết quả công cụ.

Đầu vào là JSON gồm:
- today: ngày hiện tại (kèm thứ) để quy đổi mốc thời gian. dates: các khoảng đã tính sẵn từ today, mỗi khoảng
  có from (ngày đầu), before (ngày sau ngày cuối) và label (cách nói với người dùng, ví dụ "hôm qua (thứ Năm,
  19/11)"): yesterday, last_7_days, last_week, this_week, this_month, last_month.
- question: câu cần trả lời, đã đủ ngữ cảnh. Câu hỏi gốc có thể có thêm ý khác; các ý đó do bước khác trả lời.
- question_type: loại câu hỏi (T1 tra cứu, T2 tổng hợp, T3 đếm, T4 có/không, T5 liệt kê, T6 phân nhóm, T7 cực trị,
  T8 so sánh, T9 dẫn xuất, T10 xu hướng, T11 phân bố, T12 bất thường, T13 tương quan, T15 vận hành dữ liệu,
  T22 định nghĩa nghiệp vụ). business_concepts: cụm từ phụ thuộc định nghĩa nghiệp vụ.
- knowledge: tri thức truy hồi được: metrics, tables, columns, glossary (thuật ngữ), expert_rules (quy tắc chuyên
  gia), own_knowledge (ghi chú riêng của người dùng). Chỉ là ứng viên, có thể không liên quan.
- prior_results: kết quả các câu trước mà câu này phụ thuộc; chỗ <kết quả câu N> trong question lấy từ câu N.

Kết quả của query_metric và run_sql gồm result_id (mã kết quả), columns (tên cột), fields (nhãn, đơn vị, kiểu từng
cột), rows (giá trị đã định dạng kiểu Việt Nam: số 1.234,5; ngày "thứ Năm, 19/11", tháng "tháng 11", chỉ ghi năm khi
khác năm của today), chart (biểu đồ hệ thống đề xuất), chart_types (các loại biểu đồ hợp với kết quả) và display:
"chart" (biểu đồ sẽ hiện dưới câu trả lời), "chart_if_last" (chỉ hiện nếu đây là kết quả cuối bạn lấy cho câu
này), "none" (không vẽ). Dùng một ngày trong rows để lọc ở lời gọi sau thì viết lại dạng YYYY-MM-DD.

# CÁCH LÀM
1. Đọc knowledge. Thuật ngữ trong business_concepts phải hiểu theo glossary và expert_rules, không theo nghĩa thông
   thường. T22 thì trả lời từ glossary, expert_rules, không cần truy vấn.
2. Có metric khớp đúng ý câu hỏi thì dùng query_metric: hệ thống dựng SQL, tự áp quy tắc chuyên gia gắn với metric.
   Cần chắc tên cột thì gọi get_metric hoặc get_table trước. Trước khi gọi, đối chiếu từng chiều phân nhóm và điều
   kiện lọc của câu hỏi với knowledge.columns: cột đúng nghĩa nằm ở bảng khác bảng của metric thì làm theo bước 3.
3. Không có metric phù hợp, hoặc cần nối bảng, so sánh kỳ, tính tỷ lệ, chênh lệch, tương quan, phát hiện bất thường
   thì dùng get_table để xem cột rồi viết SQL cho run_sql. Khi tự viết SQL, tự áp điều kiện của các quy tắc chuyên
   gia liên quan (xem bằng get_expert_rule) và ghi tên các quy tắc đã áp vào rules_applied. purpose của run_sql
   viết bằng lời thường cho người dùng đọc, ví dụ "Tổng lượng mưa từng thành phố trong 7 ngày qua"; labels đặt
   nhãn tiếng Việt có dấu cho các cột tự đặt tên.
   Chiều hoặc thuộc tính được hỏi không có trong bảng của metric (thường chỉ có ở bảng danh mục) thì nối sang bảng
   có cột đó bằng run_sql; không thay bằng một cột khác tên chỉ vì nghĩa gần giống.
4. Lọc theo giá trị văn bản (tên địa danh, loại, trạng thái): query_metric tự khớp giá trị với dữ liệu, không
   phân biệt dấu và hoa thường. Với run_sql, chưa chắc cách ghi trong dữ liệu thì gọi get_column_values trước.
5. Quy đổi thời gian: "hôm qua", "7 ngày qua", "tuần trước", "tuần này", "tháng này", "tháng trước" thì dùng
   đúng khoảng tương ứng trong dates, không tự tính lại: lọc >= from và < before. Mốc khác thì tự tính từ today:
   "N ngày qua" là N ngày gần nhất tính đến hôm qua, tuần bắt đầu thứ Hai.
6. Câu hỏi thiếu thông tin bắt buộc (không có mốc thời gian, đối tượng mơ hồ) mà dữ liệu cho phép một cách hiểu hợp
   lý thì chọn cách hiểu đó và ghi vào tham số assumption của query_metric hoặc run_sql bằng lời thường, ví dụ "Bạn
   chưa nêu thành phố nên tính cho từng thành phố". Không có cách hiểu hợp lý thì gọi ask_user, không truy vấn
   tiếp. Ưu tiên giả định hợp lý hơn hỏi lại.
   - Không có mốc thời gian: bảng chỉ chứa số liệu đã xảy ra (nhật ký, danh mục) thì tính trên toàn bộ dữ liệu và
     ghi vào assumption; bảng trộn số liệu đã xảy ra với số liệu dự báo hoặc kế hoạch thì không gộp toàn bộ mà hỏi
     lại khoảng thời gian, trừ câu về trạng thái hiện tại. query_metric không lọc thời gian sẽ ghi chú khoảng dữ
     liệu đã gộp; khoảng đó vượt quá today (có số liệu tương lai) thì không dùng kết quả gộp, hỏi lại khoảng thời
     gian.
   - Không nói đối tượng nào thì trả theo từng đối tượng nếu ít dòng, không gộp thành một con số.
   - Từ trong câu hỏi khớp nhiều metric hoặc nhiều giá trị khác nghĩa nhau, và chọn sai sẽ cho kết quả khác hẳn,
     thì hỏi lại.
7. Cách hỏi lại: gọi ask_user với một câu hỏi ngắn, cụ thể, xưng "tôi"; options là các lựa chọn lấy từ knowledge
   hoặc dữ liệu, viết ở dạng người dùng đọc được: tên tiếng Việt có dấu, nhãn chỉ số, khoảng thời gian dạng
   "13–19/11"; nhiều hơn 8 lựa chọn thì chọn các lựa chọn phổ biến. Không hỏi lại bằng câu trả lời văn bản. Kết quả
   của ask_user là user_reply: câu trả lời của người dùng; dùng nó rồi làm tiếp.

# KHI CÔNG CỤ BÁO LỖI
- Đọc kỹ thông báo lỗi và sửa đúng chỗ: tên cột, giá trị, kiểu dữ liệu, cú pháp. Không gọi lại y nguyên lời gọi đã
  lỗi.
- query_metric không diễn đạt được ý câu hỏi thì chuyển sang run_sql; run_sql lỗi cú pháp nhiều lần thì viết câu đơn
  giản hơn hoặc tách thành nhiều câu.
- Kết quả rỗng, NULL hoặc bằng 0 khi có lọc theo văn bản: kiểm tra lại giá trị lọc (get_column_values) và khoảng
  thời gian trước khi kết luận là không có dữ liệu.
- chart_error hoặc lỗi của make_chart nêu đúng trường sai: sửa đúng trường đó rồi gọi make_chart. Lỗi hai lần thì
  bỏ qua biểu đồ; dữ liệu vẫn dùng được.

# BIỂU ĐỒ
Kết quả có display "chart", và kết quả cuối có display "chart_if_last", được vẽ dưới câu trả lời. chart trong kết
quả là đề xuất của hệ thống; chỉ đổi khi đề xuất chưa làm rõ ý câu hỏi. Trả lời dựa vào một kết quả không phải kết
quả cuối mà cần biểu đồ thì gọi make_chart cho kết quả đó (display thành "chart"), hoặc nêu số trong lời văn.
- Biết trước hình dạng kết quả thì truyền chart ngay trong query_metric hoặc run_sql; cần đổi sau khi đã có kết quả
  thì gọi make_chart với result_id. Không gọi make_chart chỉ để lặp lại đúng đề xuất.
- Chọn theo việc người đọc cần làm: so sánh, xếp hạng giữa các nhóm: bar_horizontal sắp giảm dần (bar khi ít nhóm,
  nhãn ngắn); xu hướng theo thời gian: line với số đo như nhiệt độ, tỷ lệ; bar với số cộng dồn như lượng mưa, số
  lần; thành phần của tổng: bar_stacked, hoặc donut khi tối đa 6 phần và số không âm; hai số đo của cùng đối tượng:
  scatter; phân bố: histogram, box_plot; hai chiều phân loại: heatmap; so với mục tiêu hoặc ngưỡng: bullet, hoặc
  thêm reference_lines.
- Một con số, hai ba giá trị dễ nói bằng lời, danh sách chỉ có chữ: không cần biểu đồ.
- Không vẽ hai trục y. Hai số đo khác đơn vị thì dùng facet theo số đo, hoặc transform.index_to = "first".
- title ngắn bằng lời thường (cái gì, ở đâu, khi nào); reference_lines cho ngưỡng câu hỏi nhắc tới;
  colors.highlight cho đối tượng câu hỏi hướng tới.

# CÂU TRẢ LỜI
Viết như chuyên viên số liệu trả lời đồng nghiệp: xưng "tôi", gọi người hỏi là "bạn"; đúng, gọn, tự nhiên.
1. Câu đầu là kết luận: kết quả, đối tượng và thời gian trong một câu. Không mở đầu bằng "Theo dữ liệu", "Kết quả
   cho thấy", không nhắc lại câu hỏi.
2. Ngắn: thường 1 đến 2 câu, tối đa 3 câu; danh sách và bảng không tính. Không chào, không kết bằng lời mời hỏi
   tiếp.
3. Số: chép đúng giá trị trong rows (đã định dạng sẵn), không tự làm tròn lại, không đổi dấu phẩy, dấu chấm. Đơn vị
   lấy từ fields, cách số một khoảng trắng (22 °C, 8,6 mm), riêng % viết liền (66,1%). Không tự tính số mới; cần
   chênh lệch, tỷ lệ thì tính bằng truy vấn.
4. Thời gian: nói như người dùng hỏi, kèm ngày ngắn trong ngoặc, dùng label trong dates: "hôm qua (thứ Năm,
   19/11)", "7 ngày qua (13–19/11)". Nhắc một ngày cụ thể thì kèm thứ. Không ghi năm khi trùng năm của today.
   Không viết dạng 2026-11-19.
5. Tên gọi: dùng nhãn trong fields và tên chỉ số trong knowledge, không dùng tên cột, tên kỹ thuật (có dấu gạch
   dưới, mã viết hoa) hay dấu `. Giá trị lưu không dấu (Ha Noi, Hue) thì viết tên tiếng Việt có dấu đầy đủ khi chắc
   chắn (Hà Nội, Huế); không thêm tiền tố, không viết tắt (viết "Hồ Chí Minh", không viết "TP.HCM").
6. Không nhắc: bản ghi, bảng, cột, metric, truy vấn, SQL, công cụ, quy tắc chuyên gia, cách khớp giá trị, khoảng dữ
   liệu đã gộp, loại số liệu (dự báo hay thực đo) trừ khi câu hỏi hỏi đúng điều đó, và không mô tả biểu đồ. Hệ thống
   hiển thị những điều này riêng trong phần "Cách tính".
7. Giả định: chỉ khi giả định đổi cách hiểu con số (không nêu đối tượng, không nêu thời gian, chọn một trong nhiều
   nghĩa) thì thêm đúng một mệnh đề ngắn ở câu đầu, ví dụ "Bạn chưa nêu thành phố nên tôi liệt kê từng nơi:". Cả
   câu trả lời có tối đa một mệnh đề như vậy. Định nghĩa nghiệp vụ đã dùng (business_concepts) không viết vào lời
   văn; hệ thống hiện nó trong "Cách tính". Chỉ khi không có giả định và câu hỏi hỏi đúng định nghĩa đó (T22) mới
   nói định nghĩa.
8. Định dạng: Markdown ngắn, không tiêu đề. In đậm 1 đến 3 con số hoặc kết luận chính, không in đậm ngày tháng.
   Kết quả được vẽ dưới câu trả lời (xem # BIỂU ĐỒ) thì không chép lại cả bảng: nêu kết luận và 1 đến 3 điểm nổi
   bật. Kết quả không được vẽ thì nêu đủ số liệu cần cho câu trả lời.
9. Kết quả bị cắt (truncated) thì nói "Tôi mới lấy N dòng đầu." Không có dữ liệu hoặc không trả lời được thì nói
   thẳng và lý do ngắn; không bịa, không đoán.

# THEO LOẠI CÂU HỎI (question_type)
- T1, T2, T3, T9, T15: một câu chứa kết quả, đối tượng, thời gian.
- T4: mở đầu "Có," hoặc "Không," rồi đưa con số làm căn cứ nếu có; không đọc số đếm vô nghĩa như "ghi nhận 1 ngày
  có mưa" cho một ngày.
- Câu hỏi phủ định ("nơi nào không mưa"): trả lời khẳng định, tránh phủ định kép: "Không có nơi nào; cả 4 nơi đều
  có mưa."
- T5, T12: số lượng rồi liệt kê; từ 8 mục trở xuống liệt kê trong câu, nhiều hơn thì gạch đầu dòng. Mọi đối tượng
  đều thỏa thì nói "cả N ..." rồi vẫn liệt kê.
- T6, T10: một câu dẫn nêu điểm nổi bật (cao nhất, thấp nhất, tăng hay giảm), rồi gạch đầu dòng khi kết quả không
  được vẽ.
- T7: tên trước, giá trị sau; top-k thì liệt kê theo thứ hạng.
- T8: kết luận trước (A hơn B, kèm mức chênh nếu kết quả đã có), hai giá trị sau.
- T11: "dao động từ X đến Y".
- T13: kết luận bằng lời thường ("gần như không liên quan"); hệ số và số mẫu để trong ngoặc.
- T22: định nghĩa trong 1 đến 2 câu bằng lời thường.
```

Ghi chú cho BE1: dòng "Không có few-shot" của `docs/handbook/modules/agent_package.md` vẫn đúng với prompt agent (không
thêm ví dụ để giữ token mỗi vòng); prompt synthesize có ví dụ khác lĩnh vực (mục 2.2).

### 2.2 Prompt synthesize: toàn văn mới của `backend/agent_package/prompts/prompt_synthesize.py`

BE2 sở hữu file này (vì đổi đầu ra sang Markdown thuần và bỏ parser). File chỉ còn chuỗi `synthesize_prompt`; xóa
`SynthesizeResponse`, `SynthesizeParser`, `synthesize_parser` và các import của chúng. **Làm ở giai đoạn 2 của BE2**,
cùng lúc với `chat_service.py`, `get_chat_completion.py` và `tests/test_text2sql_agent.py` (dòng 12 đang import
`synthesize_parser`; `ChatService._synthesize` đang gọi `_complete("synthesize")`; prompt mới có dấu `{}` nên không
được đi qua `ChatPromptTemplate` của `get_chat_completion`). Sửa sớm hơn làm cả bộ test đỏ (PB-1).

```text
Bạn là AnswerSynthesizer, chuyên viên số liệu. Nhiệm vụ: ghép câu trả lời của các câu hỏi con thành một câu trả lời
liền mạch cho câu hỏi đầy đủ. Xưng "tôi", gọi người hỏi là "bạn".

Đầu vào là JSON gồm:
- question: câu hỏi đầy đủ của người dùng.
- today: ngày hiện tại kèm thứ.
- answers: các câu hỏi con theo thứ tự, mỗi câu có position, question, question_type và answer.

# SỐ LIỆU
1. Chỉ dùng số, tên, mốc thời gian có trong answers; chép nguyên cách viết số và đơn vị (1.234,5; 22 °C; 66,1%).
   Không tính thêm, không làm tròn lại, không thêm phép gộp mới.
2. Không thêm lưu ý, nguồn hay giả định nào không có trong answers.

# CÁCH VIẾT
1. Câu đầu đi thẳng vào ý chính; sau đó theo thứ tự các ý trong question, dùng từ nối ("còn", "ở đó", "trong khi
   đó"). Mốc thời gian chung chỉ nói một lần; câu sau phụ thuộc câu trước thì dùng "ở đó", "thành phố này".
2. Câu con có mệnh đề giả định ("Bạn chưa nêu ... nên tôi ...") thì giữ ý đó, viết một lần.
3. Câu con chưa trả lời được thì nói thẳng phần đó và lý do trong một câu. Không nhận xét phần question không hỏi.
4. Không nhắc: bản ghi, bảng, cột, metric, truy vấn, SQL, quy tắc chuyên gia, cách khớp giá trị, loại số liệu, biểu
   đồ. Hệ thống hiển thị những điều này riêng.
5. Ngắn: tối đa 3 câu, danh sách không tính. Markdown ngắn, không tiêu đề; in đậm 1 đến 3 con số hoặc kết luận
   chính, không in đậm ngày. Không lặp lại câu hỏi, không chào, không mời hỏi tiếp.

# ĐẦU RA
Chỉ viết câu trả lời bằng Markdown. Không bọc JSON, không bọc trong khối ```.

# VÍ DỤ (lĩnh vực khác, chỉ để thấy cách viết)
Đầu vào: question "Hôm qua cửa hàng nào bán chạy nhất, doanh thu ở đó bao nhiêu?", today "2031-03-14 (thứ Sáu)",
answers [{"position": 1, "answer": "Hôm qua (thứ Năm, 13/3), cửa hàng Bến Thành bán chạy nhất với **86 đơn**."},
{"position": 2, "answer": "Doanh thu của cửa hàng Bến Thành hôm qua (thứ Năm, 13/3) là **41.250.000 đồng**."}]
Đầu ra:
Hôm qua (thứ Năm, 13/3), cửa hàng Bến Thành bán chạy nhất với **86 đơn**, doanh thu ở đó là **41.250.000 đồng**.
```

`ChatService._synthesize` gửi `{"question": rewritten_question, "today": "<YYYY-MM-DD> (<thứ>)", "answers":
[{"position", "question", "question_type", "answer"}]}` (thêm `today`, `question_type` so với hiện tại; `today` lấy
từ `prepared.agent_run.today`).

### 2.3 Code định dạng sẵn dữ liệu cho agent

File mới `backend/modules/text2sql/services/display_format.py` (BE1). Không phụ thuộc thư viện mới (`babel` không có
trong `uv.lock`).

| Hàm | Đầu vào → đầu ra | Ví dụ |
| --- | --- | --- |
| `vi_number(value, decimals, grouped=True)` | số → chuỗi vi-VN. `float` đổi qua `Decimal(repr(value))`, **không** `Decimal(float)` (PB-16); `ROUND_HALF_UP`, cộng `+ 0` sau `quantize` để không ra `-0`. `decimals=None` → giữ tối đa 2 chữ số lẻ (bỏ số 0 cuối), riêng `abs < 1` giữ 3 chữ số có nghĩa. `grouped=False` → không có dấu chấm hàng nghìn. Giá trị không hữu hạn (NaN, ±Infinity) → `ValueError` (người gọi coi là null) | `1234.5,1 → "1.234,5"`, `41250000,0 → "41.250.000"`, `-0.04,1 → "0"`, `0.035,3 → "0,035"`, `77.55,None → "77,55"`, `21.0285,None → "21,03"`, `2026,0,grouped=False → "2026"` |
| `parse_d3_format(text)` | `MetricInfo.format` / `ColumnInfo.format` → `NumberStyle(decimals: int|None, percent: bool)` | `",.1f" → (1, False)`, `".1%" → (1, True)` (giá trị là tỷ lệ 0–1, nhân 100), `",d"`/`",.0f" → (0, False)`, `"SMART_NUMBER"`, `None`, chuỗi lạ → `(None, False)` |
| `number_display(value, field)` | ô số → chuỗi | `field.format_hint == "plain"` → `vi_number(value, 0, grouped=False)` (năm, mã, id: `2026 → "2026"`, `70000 → "70000"`); `field.percent`: `0.661 → "66,1%"`; `decimals` có sẵn (từ format của từ điển) → dùng; số nguyên → không lẻ; còn lại `decimals=None` của `vi_number`. Chuỗi không hữu hạn (`"NaN"`, `"inf"`, `"Infinity"`) trong cột số → `null` |
| `date_display(value, today, weekday)` | `date` hoặc chuỗi ISO → `"thứ Năm, 19/11"` (`weekday=True`) hoặc `"19/11"`; năm khác `today.year` thì thêm `/2025` | |
| `bucket_display(value, unit, today)` | ô của cột gom thời gian (PB-4) theo `field.time_unit` | `day` → như `date_display(weekday=True)`; `week` → `"tuần 16–22/11"`; `month` → `"tháng 11"` (khác năm: `"tháng 11/2025"`); `quarter` → `"quý 4"` (khác năm: `"quý 4/2025"`); `year` → `"2026"` (không dấu chấm, luôn ghi năm) |
| `datetime_display(value, today)` | → `"01:00 thứ Sáu, 20/11"` (giờ theo giá trị đã có độ lệch `+07:00`, không đổi múi). Cột `datetime` mà mọi giá trị khác NULL đúng 00:00:00 thì `result_fields` đã hạ thành `date` (PB-4), nên không ra `"00:00 thứ Năm, 19/11"` | |
| `period_label(start, before, today)` | khoảng nửa mở → `"19/11"` (1 ngày, kèm thứ), `"13–19/11"`, `"28/10–3/11"`, `"tháng 11"` (đúng cả tháng), khác năm thì thêm năm | |
| `dates_context(today)` | thay `date_ranges`: mỗi khoảng `{"from", "before", "label"}` | `yesterday.label = "hôm qua (thứ Năm, 19/11)"`, `last_7_days.label = "7 ngày qua (13–19/11)"`, `last_week = "tuần trước (9–15/11)"`, `this_week = "tuần này (16–22/11)"`, `this_month = "tháng này (tháng 11)"`, `last_month = "tháng trước (tháng 10)"` |
| `today_label(today)` | `"2026-11-20 (thứ Sáu)"` (giữ dạng hiện tại để agent quy đổi) | |
| `llm_rows(rows, fields, today)` | dòng `json_cell` → dòng hiển thị cho LLM: số qua `number_display`, cột có `time_unit` qua `bucket_display`, ngày khác qua `date_display(weekday=True)`, ngày giờ qua `datetime_display`, văn bản và boolean giữ nguyên (văn bản **không** đổi để lọc tiếp đúng giá trị thật) | |
| `humanize(alias)` | `"so_ngay_co_mua" → "So ngay co mua"` (chỉ dùng khi không tìm được nhãn) | |

Các ô định dạng trên **chỉ** đi vào LLM (tool output, `prior_results`). `AgentStepOut.rows`, SSE, JSON, `results` đã
lưu vẫn là giá trị JSON thô (số là số, ngày là ISO) để frontend tự định dạng và biểu đồ tính được.

**`fields`** (mới, trên mọi bước dữ liệu thành công), mô hình `FieldOut` trong `schemas/schema_text2sql.py`:

```python
class FieldOut(BaseModel):
    name: str                      # tên cột kết quả (đúng như columns)
    label: str                     # nhãn hiển thị tiếng Việt
    type: Literal["number", "date", "datetime", "text", "boolean", "other"]
    unit: str | None = None        # "°C", "mm", "km/h", "%", "đồng"...
    decimals: int | None = None    # từ format d3
    percent: bool = False          # giá trị là tỷ lệ 0–1, hiển thị ×100 kèm %
    additive: bool | None = None   # cộng dồn được (SUM/COUNT); None khi không biết
    role: Literal["measure", "dimension"] = "dimension"
    format_hint: Literal["plain"] | None = None    # số in thẳng chữ số, không dấu chấm hàng nghìn (năm, mã, id)
    time_unit: Literal["day", "week", "month", "quarter", "year"] | None = None   # cột gom thời gian
    pii: bool = False              # ColumnInfo.contains_pii của cột catalog tương ứng
```

Mọi trường mới đều có mặc định; `FieldOut` không có validator chặt hơn dữ liệu cũ (PB-2).

Quy tắc dựng `fields` (`display_format.result_fields(tool, args, columns, raw_rows, catalog)`, BE1):

0. **Tên cột duy nhất** (PB-6a): tên trùng trong `columns` (ví dụ `SELECT a.name, b.name`) đổi thành `name`, `name_2`,
   `name_3`; tên rỗng hoặc `?column?` đổi thành `cot_<i>` (i đếm từ 1 theo vị trí), nhãn lấy từ `args.labels` theo
   tên mới, không có thì `"Cột <i>"`. `AgentStepOut.columns`, output LLM, `results` đã lưu đều dùng tên đã đổi (dòng
   là mảng theo vị trí nên không đổi). Output LLM thêm `notes` một câu: "Cột trùng tên 'name' đã đổi thành 'name_2'."
1. `type` xét **mọi** giá trị khác NULL trước `json_cell` (PB-5): toàn `Decimal`/`int`/`float` (không tính `bool`) →
   `number`; toàn `bool` → `boolean`; toàn `date` → `date`; `date` lẫn `datetime` hoặc toàn `datetime` → `datetime`,
   rồi `datetime` mà mọi giá trị đúng 00:00:00 → `date` (PB-4); `time`, `UUID`, `bytes` (`"<binary>"`), `str` và mọi
   trường hợp lẫn kiểu khác → `text`. Cột toàn `NULL` thì theo `type_category(ColumnInfo.data_type)` nếu tìm được,
   không thì `other`. Số không hữu hạn (`Decimal('NaN')`, `float('inf')`) vẫn tính là `number`; sau `json_cell` chúng
   là chuỗi `"NaN"`, `"Infinity"`, `"inf"` và **mọi nơi** (profile, validator, `llm_rows`, FE) coi là null.
1b. `format_hint = "plain"` và `role = "dimension"` (PB-3) khi cột số là: khóa `group_by` hoặc `time_grain` của
   `query_metric`; cột `run_sql` có biểu thức chiếu nằm trong `GROUP BY` (sqlglot); tên hoặc nhãn có
   một từ (tách theo `_`, khoảng trắng, sau khi bỏ dấu và hạ chữ thường) thuộc `{"nam", "year", "id", "ma", "code",
   "key", "so_hieu"}`; hoặc biểu thức chiếu của `run_sql` là `EXTRACT(YEAR|QUARTER|MONTH|WEEK|DAY ...)` hay
   `DATE_PART(...)` (sqlglot đọc `args.sql`). Ngược lại `role = "measure"` khi `type == "number"`.
1c. `time_unit` (PB-4): cột `time_grain` của `query_metric` lấy `args.time_grain.grain`; `run_sql` lấy từ
   `DATE_TRUNC('<unit>', ...)` trong biểu thức chiếu (sqlglot), không đọc được thì `None`.
1d. `pii` (PB-15): `ColumnInfo.contains_pii` của cột catalog khớp tên (khóa `group_by` của `query_metric`, hoặc cột
   catalog cùng tên ở `run_sql`); cột tự đặt tên không khớp → `False`.
2. `query_metric`: cột giá trị (`metric.name`) có `label = metric.label or metric.name`; `decimals/percent` từ
   `metric.format`; `unit`: `currency` (VND → "đồng") nếu có, ngược lại đơn vị của cột duy nhất trong biểu thức metric
   (`ColumnInfo.unit`), không xác định được thì `None`; `additive` = biểu thức có hàm tổng hợp ngoài cùng là `SUM` hoặc
   `COUNT` (sqlglot, giống `metric_expression`). Cột `group_by`/`time_grain` có `label = ColumnInfo.label`, `unit`,
   `decimals` từ `ColumnInfo.unit`/`.format`.
3. `run_sql`: `label` ưu tiên `args.labels[alias]` → cột catalog cùng tên (duy nhất trong connection hoặc các bản
   trùng có cùng nhãn) → metric cùng `name` → `humanize(alias)`. `unit` từ cột/metric tìm được; nhãn dạng "Tổng lượng
   mưa (mm)" thì tách đơn vị trong ngoặc cuối. `additive = None`.
4. `agent_catalog.ColumnInfo` thêm `unit: str | None`, `format: str | None` (đọc `ColumnDictionary.unit`, `.format`
   trong `load_catalog`), `describe()` trả thêm hai trường này (agent thấy đơn vị khi `get_table`).

**Output gửi LLM của `query_metric`/`run_sql`** (thay đổi so với hiện tại, BE1 trong `agent_tools._execute`):

```json
{
  "result_id": "1-2",
  "sql": "SELECT ...",
  "columns": ["ten_thanh_pho", "tong_luong_mua"],
  "fields": [{"name": "ten_thanh_pho", "label": "Thành phố", "type": "text"},
             {"name": "tong_luong_mua", "label": "Tổng lượng mưa", "type": "number", "unit": "mm"}],
  "rows": [["Phu Quoc", "46,9"], ["Hue", "8,6"]],
  "row_count": 12, "truncated": false,
  "notes": ["..."],
  "chart": {"type": "bar_horizontal", "x": "ten_thanh_pho", "y": ["tong_luong_mua"]},
  "chart_types": ["bar_horizontal", "bar", "lollipop", "treemap", "donut", "table"],
  "display": "chart_if_last",
  "chart_error": "chỉ có khi chart truyền kèm lời gọi sai"
}
```

`display` (PB-9) do code tính, cùng một quy tắc với FE (mục 4.9): chart hiệu lực có `type` là `table`, hoặc `kpi`,
hoặc có < 3 điểm (đếm sau khi bỏ null theo V8) → `"none"`; `chart_source = "agent"` → `"chart"`; còn lại (đề xuất)
→ `"chart_if_last"`. `make_chart` cập nhật `display` của bước dữ liệu và trả `display` mới. `display` lưu trong bước
và `results` (mục 4.8).

`fields` gửi LLM bỏ khóa có giá trị `None`/`false`/`dimension` để tiết kiệm token (`pii` không gửi). `chart` gửi
LLM là **bản tóm tắt**
(`type`, `x`, `y`, `series`), không phải spec đầy đủ. `notes` giữ nguyên giọng kỹ thuật vì là kênh làm việc của agent
(prompt cấm chép vào câu trả lời).

**`prior_results`** (`text2sql_agent_service.prior_context`): `data` thành `{"fields": ..., "columns": ..., "rows":
llm_rows(...)}`; vẫn lấy bước dữ liệu thành công cuối. `today` dùng `today_label`, `dates` dùng `dates_context`.

### 2.4 Khối "Cách tính" (`explanations`) do code dựng

Mô hình trong `schemas/schema_text2sql.py`:

```python
ExplanationKind = Literal[
    "metric", "source", "period", "filter", "group", "order", "rule", "value_match", "data_range", "scope",
    "assumption", "method", "truncated", "warning",
]

class ExplanationOut(BaseModel):
    kind: ExplanationKind
    text: str                      # câu tiếng Việt có dấu, đã dùng nhãn, không tên cột kỹ thuật
    name: str | None = None        # tên quy tắc (kind = rule)
    status: Literal["applied", "yielded", "skipped"] | None = None   # kind = rule
    field: str | None = None       # nhãn cột (period, filter, value_match, data_range)
    start: str | None = None       # ISO YYYY-MM-DD hoặc ISO ngày giờ, ngày đầu (period, data_range)
    end: str | None = None         # ISO, ngày cuối **tính cả** (period đã đổi before thành ngày cuối; data_range)
    values: list[str] | None = None   # giá trị lọc hoặc giá trị khớp; None khi cột PII
```

Trường có cấu trúc (PB-11) để FE định dạng lại theo ngày **xem** (mở lại năm sau vẫn hiện năm): FE dựng lại câu cho
`period`/`data_range` từ `start`/`end` bằng cùng quy tắc `period_label` (bỏ năm khi trùng năm hiện tại của người xem);
`text` là bản dự phòng khi thiếu trường. Khi dựng `text`, `period_label` dùng `today` **của lượt** (`agent_run.today`),
không dùng ngày máy chủ lúc đọc. Mọi trường mới có mặc định.

Thêm vào `AgentStepOut`: `explanations: list[ExplanationOut] = []`. Chỉ bước `query_metric`, `run_sql` thành công có
mục; bước tra cứu, bước `get_column_values` (có trong `DATA_TOOLS` nhưng không có `result_id`, PB-19) và bước lỗi
để rỗng. Dựng ở file mới `services/explanations.py` (BE1), gọi từ `agent_tools` ngay khi ghi bước.

**`run_sql`** (PB-10) có thêm các mục sau, ngoài `method`, `assumption`, `truncated`:

- `source`: dùng sqlglot liệt kê bảng trong `FROM`/`JOIN` (bỏ CTE), đổi sang `TableInfo.label` khi tìm được trong
  catalog, nối bằng ", ": `Nguồn: Dự báo theo ngày, Danh mục thành phố`. Không tìm được bảng nào thì không có mục.
- `period`/`filter`: chỉ đọc `WHERE` ngoài cùng của câu `SELECT` chính, các vế nối bằng `AND`, dạng đơn giản
  `<cột> <op> <hằng>`, `<cột> BETWEEN <hằng> AND <hằng>`, `<cột> IN (<hằng>, ...)`, `<cột> IS [NOT] NULL`, với `<cột>`
  là cột catalog tìm được (bỏ bí danh bảng). Hằng ngày dạng `'YYYY-MM-DD'` hoặc `DATE '...'`. Vế khác (hàm, truy vấn
  con, `OR`, so hai cột, `CURRENT_DATE - ...`) **bỏ qua**, không đoán; nếu có vế bị bỏ qua thì không thêm gì (mục
  `method` đã nói câu tính gì). Lỗi phân tích → không có mục, không ném lỗi.
- `rule`: `RunSqlArgs.rules_applied: list[str] = Field(default_factory=list, max_length=10)` (tên quy tắc chuyên gia
  agent đã tự áp). Tên khớp `get_expert_rule` (cùng cách so `normalized`) → mục `rule` `status="applied"`, văn bản
  `Áp dụng quy tắc «<tên>»`; tên không có → bỏ qua và thêm vào `notes` cho agent "Không có quy tắc '<tên>'". Code
  **không** kiểm SQL có thật sự áp điều kiện của quy tắc (ngoài phạm vi; ghi vào handbook).
- Định nghĩa nghiệp vụ (PB-12): không viết vào lời văn; `query_metric` đã có ở mục `metric` (mô tả metric) và
  `rule`; `run_sql` có qua `rules_applied`.

**Cột PII** (PB-15): mục `filter`/`value_match` trên cột có `pii = True` chỉ ghi nhãn cột, không ghi giá trị:
`Lọc theo Số điện thoại (giá trị ẩn)`, `values = None`.

Để dựng được mà không phân tích chuỗi `notes`:

- `sql_builder.BuiltQuery` thêm `rules: list[RuleUse]` với `RuleUse(name, status: applied|yielded|built_in|skipped,
  columns: list[str])`. `_rule_conditions` trả cả `notes` (giữ nguyên cho agent) lẫn `rules`. Ngoại lệ của quy tắc
  **không** đưa vào "Cách tính".
- `agent_tools._resolve_filter_values` trả thêm `matches: list[ValueMatch(column, requested, matched: list[str])]`.
- `agent_tools._time_scope_notes` trả thêm `DataRange(column, start, end)`; `_entity_scope_notes` trả cờ `aggregated`.
- `QueryMetricArgs` (trong `sql_builder.py`) thêm `assumption: str | None = Field(None, max_length=300,
  description="Giả định đã chọn khi câu hỏi thiếu thông tin, viết bằng lời thường cho người dùng")` và `chart: dict |
  None` (mục 4.6). `RunSqlArgs` thêm `assumption`, `chart`, `rules_applied` (trên), `labels: dict[str, str] =
  Field(default_factory=dict, max_length=20)` (giá trị ≤ 80 ký tự) và đổi mô tả `purpose` thành "Câu này tính gì,
  viết bằng lời thường cho người
  dùng đọc (hiện trong phần Cách tính)". `build_metric_query` bỏ qua `assumption`, `chart` khi dựng SQL.

Thứ tự và mẫu câu (nhãn lấy từ catalog; ngày qua `period_label`; số qua `vi_number` + đơn vị):

| `kind` | Khi nào | Mẫu `text` |
| --- | --- | --- |
| `metric` | `query_metric` | `Chỉ số: Tổng lượng mưa` (+ `" – " + description` nếu có, cắt 160 ký tự) |
| `source` | `query_metric` | `Nguồn: Dự báo theo ngày` (`TableInfo.label`, thêm `"(mỗi dòng: {grain})"` khi có) |
| `method` | `run_sql` | `purpose` nguyên văn |
| `period` | Có cặp lọc `>=`/`<` (hoặc `>=`/`<=`, `equals`) trên cột ngày hoặc ngày giờ | `Thời gian: 13–19/11` (gộp `before` thành ngày cuối) |
| `filter` | Mỗi bộ lọc khác | `Thành phố: Hà Nội`, `Gió giật tối đa trên 40 km/h`, `Trạng thái khác Thất bại` (toán tử → "là", "khác", "trên", "từ", "dưới", "đến", "là một trong", "chứa", "không có giá trị") |
| `group` | `group_by`, `time_grain` | `Chia theo: Thành phố`; `Gộp theo: ngày` |
| `order` | `order_by`, `limit` | `Sắp xếp giảm dần theo Tổng lượng mưa, lấy 5 dòng đầu` |
| `rule` | `RuleUse` `applied` / `yielded` / `skipped` (bỏ `built_in`) | `Áp dụng quy tắc «Chỉ số theo ngày dùng bản ghi dự báo ngày»` / `Quy tắc «…» không lọc Thành phố vì câu hỏi đã lọc` / `Không áp quy tắc «…» theo yêu cầu` |
| `value_match` | `ValueMatch` | `«Hà Nội» được hiểu là «Ha Noi» trong dữ liệu` |
| `data_range` | Không lọc thời gian | `Không giới hạn thời gian: tính trên toàn bộ dữ liệu từ 13/11 đến 27/11` |
| `scope` | `aggregated` | `Số gộp chung, không chia theo đối tượng` |
| `assumption` | `args.assumption` | nguyên văn |
| `truncated` | `truncated` | `Chỉ lấy 200 dòng đầu theo giới hạn truy vấn` |
| `warning` | `metric.warning_text` | nguyên văn |

Nơi lưu và đi qua:

| Kênh | Có `explanations` | Ghi chú |
| --- | --- | --- |
| Bước (`AgentStepOut`) | Có | Một danh sách mỗi bước dữ liệu |
| SSE `tool` | Có | `step_event` dump cả model nên tự có |
| JSON `/chat` | Có, ở `answers[].steps[].explanations` | Thêm trường, không đổi trường cũ |
| `conversation_turns.steps` | Có | `stored_steps` thêm khóa `explanations`, `result_id`, `chart` (bước `make_chart`) |
| `conversation_turns.results` | Không lặp lại | Frontend ghép từ `steps` theo `result_id`; mục kind `column_values` không có `result_id` thì không ghép, không vẽ, chỉ hiện trong "Các bước xử lý" như hiện nay (PB-19) |

Lời văn: prompt cho phép tối đa một mệnh đề, ưu tiên giả định; mọi thứ khác (kể cả định nghĩa nghiệp vụ) ở khối
này. Bộ chấm `clarify_or_assume` của
`run_eval.py` đọc thêm `explanations` kind `assumption` (mục 6, BE1).

## 3. Phần B: hợp đồng stream

### 3.1 Event SSE mới (chỉ thêm, không đổi event cũ)

| Event | Khi nào | `data` |
| --- | --- | --- |
| `tool_started` | Ngay **trước** khi chạy một công cụ (trong `tool_agent._call_tools`), trừ `ask_user` | `position: int`, `tool: str`, `subject: str | null` |
| `answer_delta` | Mỗi đoạn chữ mới của một vòng LLM, đã gom (≥ 32 ký tự hoặc 50 ms) | `position: int | null`, `round: int`, `final: bool`, `text: str` |
| `answer_reset` | Vòng vừa stream chữ hóa ra có gọi công cụ | `position: int`, `round: int` |
| `synthesize_started` | Đầu nút `synthesize` khi thật sự gọi LLM (câu tách) | `{}` |

- `subject` do code giải bằng catalog (an toàn, có `try`/`except ToolError` trả tham số thô): `get_metric`,
  `query_metric` → nhãn metric; `get_table` → nhãn bảng; `get_expert_rule` → tên quy tắc; `get_column_values` →
  nhãn cột; `run_sql` → `purpose` (cắt 80 ký tự); `make_chart` → `null`. Không gửi `arguments` (đã có ở `tool`).
- `round`: số thứ tự vòng gọi model trong câu đơn, lấy từ `state["rounds"]` của `tool_agent` lúc gọi model
  (bắt đầu từ 0, tăng mỗi khi qua nút `tools`; khi chạy tiếp sau hỏi lại thì tiếp tục từ `pause.rounds`; vòng hết lượt
  có `round = max_steps`). Synthesize luôn `round = 0`.
- `final`:
  - câu không tách (`not preprocess.is_split and len(preprocess.questions) == 1`): mọi delta của agent có `final =
    true` (đây có thể là câu trả lời của lượt; nếu vòng gọi công cụ thì có `answer_reset`);
  - câu tách: delta của agent có `final = false` (bản nháp của câu con); delta của synthesize có `position = null,
    final = true`.
- Bản chính thức vẫn là `question_answered.answer` (từng câu) và `answer.answer` (cả lượt), rồi `done.answer`. Client
  **luôn ghi đè** bản nháp bằng bản chính thức (bản chính thức đã `strip()` và có thể là `EMPTY_ANSWER`).

Thứ tự:

```text
turn → preprocess →
  [mỗi position, xen kẽ giữa các nhánh song song, đúng thứ tự trong một position]
  question_started → ( tool_started → tool )* xen answer_delta / answer_reset → question_answered | question_waiting
→ (câu tách) synthesize_started → answer_delta(position=null, final=true)* → answer
→ (câu đơn) answer
→ clarification? → done | error
```

Ví dụ câu đơn có một vòng đã stream chữ rồi gọi công cụ (model khác có thể làm vậy; `gpt-6-luna` 0/820 lần):

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

### 3.2 Backend (BE2)

1. `backend/agent_package/tool_agent.py`
   - Kiểu mới: `TextStream` (dataclass `delta: Callable[[int, str], None]`, `end: Callable[[int, bool], None]`) và
     `ToolStartCallback = Callable[[str, dict[str, Any]], None]`.
   - `ToolAgentContext` thêm `on_text: TextStream | None = None`, `on_tool_start: ToolStartCallback | None = None`.
   - `_call_model`: `on_text is None` → giữ `invoke` (route JSON, `ScriptedModel` cũ). Ngược lại `_stream_round(
     runnable, messages, on_text, round)`: `for chunk in runnable.stream(messages)`, `acc = chunk if acc is None else
     acc + chunk`; chỉ đẩy `chunk.text` khi `acc.tool_call_chunks` còn rỗng; cuối vòng `message =
     message_chunk_to_message(acc)`, gọi `on_text.end(round, discard=streamed and bool(message.tool_calls))` (cùng
     điều kiện với `_route` dòng 138). Áp cho cả nhánh hết lượt (model không `bind_tools`). Message chỉ có
     `invalid_tool_calls` (JSON tham số hỏng khi stream) đi tiếp **đúng như khi `invoke`** trả cùng message (PB-17):
     `_route` thấy `tool_calls` rỗng nên kết thúc, chữ đã stream được giữ (không `answer_reset`); không tự sửa tham số.
     Lưu ý: khi stream, chunk chứa tham số hỏng nằm trong `tool_call_chunks`, nên chữ đến **sau** chunk đó không được
     đẩy; cuối vòng nếu `discard` là `False` và còn chữ chưa đẩy thì đẩy nốt trước `end` để bản nháp khớp bản chính
     thức.
   - `_call_tools`: gọi `on_tool_start(name, args)` trước `_run_tool`, trừ `ask_user`.
   - `run_tool_agent(..., on_text=None, on_tool_start=None)`. Không import `backend.modules`.
2. File mới `backend/agent_package/get_chat_text.py`: `get_chat_text(system_prompt: str, params: dict, on_text:
   Callable[[str], None] | None = None) -> str`. Messages là `[SystemMessage(system_prompt), HumanMessage(json.dumps(
   params, ensure_ascii=False, indent=2, default=to_jsonable_python))]` (không qua `ChatPromptTemplate` để khỏi lo dấu
   `{}`); `on_text is None` → `get_chat_model().invoke(...).text`; ngược lại stream và gọi `on_text(chunk.text)`.
   Trả `text.strip()`; log thời gian như `get_chat_completion`. Lỗi `OpenAIError` để lan ra. Không bắt ngoại lệ nào
   khác: `Text2SqlClientDisconnected` ném từ `on_text` phải lan qua `get_chat_text` và `ChatService._synthesize`
   (chỉ bắt `OpenAIError`) ra tới `ChatStream`.
3. `get_chat_completion.py`: bỏ task `synthesize` khỏi `PROMPTS_BY_TASK` và import của nó. **Giai đoạn 2** (PB-1).
4. `prompt_synthesize.py`: toàn văn mục 2.2. **Giai đoạn 2** (PB-1).
5. File mới `backend/modules/text2sql/services/answer_stream.py`: `DeltaBuffer(emit, position, final, min_chars=32,
   max_delay=0.05)` với `delta(round, text)` (gom, đổi `round` thì xả trước), `end(round, discard)` (xả; `discard` →
   phát `answer_reset {position, round}` **sau khi** xả phần còn lại của vòng đó) và `text_stream()` trả `TextStream`.
   Thêm `SynthesizeStream(emit)` cho `position=null, round=0, final=true`.
6. `chat_events.py`: hằng tên event và builder `tool_started_event(position, tool, subject)`, `delta_event(...)`,
   `reset_event(...)`. `update_events` giữ nguyên (event `answer` vẫn từ nút `synthesize`; **giữ tên nút** để snapshot
   hỏi lại cũ chạy tiếp được).
7. `chat_graph.py`:
   - `ChatGraphContext` thêm `streaming: bool = False`.
   - `_answer_question`: `emit = _emitter(runtime) if runtime.context.streaming else None`; chỉ ghi `question_started`
     khi `emit` khác `None`. `AnswerQuestion` giữ chữ ký (nhận `Emit | None`).
   - `Synthesize` thành `Protocol` có `__call__(self, preprocess, answers, on_text: Callable[[str], None] | None =
     None) -> str` (tham số thứ ba **tùy chọn**, PB-1). `_synthesize`: câu không tách giữ như cũ; câu tách: nếu
     `streaming` thì `emit("synthesize_started", {})` rồi gọi `context.synthesize(preprocess, answers,
     on_text=SynthesizeStream(emit).delta)`, ngược lại gọi **đúng hai tham số** như hiện nay. Nhờ vậy
     `ChatService._synthesize(preprocess, answers)` cũ và các fake trong test vẫn chạy trong lúc BE1 làm giai đoạn 2.
8. `chat_service.py` (**sau BE1**, mục 7):
   - `ChatService.__init__` thêm `text_completion: TextCompletion = get_chat_text` (để test thay bản giả).
   - `execute`: `ChatGraphContext(..., streaming=emit is not None)`.
   - `_synthesize(preprocess, answers, on_text=None)`: gọi `self.text_completion(synthesize_prompt, params, on_text)`,
     bắt `OpenAIError` → `Text2SqlAgentUnavailable` như `_complete`. Chuỗi rỗng → `EMPTY_ANSWER`.
9. `text2sql_agent_service.py` (**sau BE1**): trong `AgentRun.answer`, khi `emit` khác `None` dựng
   `DeltaBuffer(emit, item.position, final=not preprocess.is_split and len(preprocess.questions) == 1).text_stream()`
   và `on_tool_start` phát `tool_started` với `subject` (hàm `tool_subject(catalog, tool, args)` đặt cùng file).
   `emit is None` → không dựng gì (route JSON đi đường `invoke` y như cũ).
10. `chat_stream.py`, `router_chat.py`: **không đổi**. `_emit` đã kiểm cờ dừng mỗi event.

### 3.3 Route JSON, lưu trữ, hỏi lại, ngắt kết nối

- **`/chat` (JSON)**: `execute(prepared, emit=None)` → `streaming=False` → không writer cho agent, không `on_text`,
  không `tool_started`; synthesize gọi `invoke` với prompt Markdown. Response giữ nguyên hình dạng; chỉ khác chữ của
  câu trả lời và các trường thêm trong `steps` (`result_id`, `fields`, `explanations`, `chart`, `chart_source`,
  `chart_types`).
- **Lưu trữ**: bản nháp không lưu ở đâu. `steps[].answer` (bản chính thức của từng câu con) và `answer` (bản cuối)
  lưu như hiện nay; mục thả xuống "Trả lời từng phần" khi mở lại lịch sử đọc `steps[].answer`.
- **Hỏi lại**: `ask_user` là vòng gọi công cụ → chữ đã stream của vòng đó bị `answer_reset`. Client xóa phần nháp
  (`final=true` thì xóa `turn.answer`). Chạy tiếp: `question_started {resumed: true}` rồi delta như thường, cờ `final`
  tính từ `preprocess` trong state đã nạp. `ToolAgentContext` không được checkpoint nên không cần migrate snapshot;
  thêm `streaming` vào `ChatGraphContext` (context, không phải state) không ảnh hưởng snapshot.
- **Ngắt kết nối/Dừng**: delta đi qua `_emitter` → `ChatStream._emit` ném `Text2SqlClientDisconnected` ở lần ghi kế
  tiếp; lỗi lan qua `runnable.stream`, đóng generator và kết nối HTTP của lời gọi LLM (nhà cung cấp không hỗ trợ hủy
  vẫn tính tiền đủ). Vòng gọi công cụ không có delta nên chỉ dừng khi vòng đó xong. Lượt ghi `error/client_disconnected`
  như hiện tại; frontend giữ phần chữ đã hiện với trạng thái "stopped". Cập nhật câu "Lời gọi LLM đang chạy dở không bị
  hủy giữa chừng" trong `api-chat.md`. Dừng trong lúc synthesize đang stream đi cùng đường: lỗi ném từ `on_text` lan
  qua `get_chat_text` và `ChatService._synthesize` (chỉ bắt `OpenAIError`). Ghi rõ trong `api-chat.md` (PB-17): khi
  Dừng, lượt lưu `answer = None` nên phần chữ đã stream **mất khi tải lại lịch sử**; chỉ `steps[].answer` của các câu
  con đã xong còn lại (chấp nhận ở bản này, không lưu bản nháp).
- **Synthesize lỗi giữa chừng**: giữ hành vi hiện tại (event `error`, `Text2SqlAgentUnavailable`); frontend hiện phần
  đã nhận kèm "Câu trả lời bị gián đoạn" (đã có trong `chat-turn.tsx`). Không thêm dự phòng.
- Không hỗ trợ nối lại stream sau khi rớt mạng (ngoài phạm vi).

### 3.4 Lời kể tiến độ (frontend, mẫu cố định, không gọi LLM)

`frontend/features/text2sql/narration.ts` (FE). Dòng hiện tại = event mới nhất; câu tách thêm tiền tố `Câu N: `.

| Event | Câu kể |
| --- | --- |
| Đã gửi, chưa có `preprocess` | `Đang đọc câu hỏi…` |
| `preprocess` tách câu | `Đã tách thành N câu hỏi nhỏ` |
| `question_started` (`resumed`) | `Đang tiếp tục với câu trả lời của bạn…` |
| `tool_started get_metric` | `Đang tìm chỉ số «subject»…` |
| `tool_started get_table` | `Đang xem dữ liệu «subject»…` |
| `tool_started get_expert_rule` | `Đang đọc quy tắc «subject»…` |
| `tool_started get_column_values` | `Đang kiểm tra cách ghi «subject»…` |
| `tool_started query_metric` | `Đang truy vấn «subject»…` |
| `tool_started run_sql` | `Đang tính: subject…` (không có `subject` thì `Đang chạy truy vấn…`) |
| `tool_started make_chart` | `Đang dựng biểu đồ…` |
| `tool` có `error` | `Truy vấn chưa được, đang thử cách khác…` |
| `answer_reset` | `Đang tra thêm dữ liệu…` |
| `answer_delta` đầu tiên của câu (`final=false`) | `Đang viết câu trả lời cho câu N…` |
| `answer_delta` đầu tiên `final=true` | `Đang viết câu trả lời…` |
| `synthesize_started` | `Đang tổng hợp câu trả lời…` |
| `question_waiting` | `Đang chờ bạn trả lời` |

`TOOL_LABELS` trong `labels.ts` đổi sang tiếng Việt không có "metric": `Đọc định nghĩa chỉ số`, `Xem mô tả bảng`,
`Đọc quy tắc`, `Tra giá trị cột`, `Tính chỉ số`, `Chạy truy vấn`, `Dựng biểu đồ`, `Hỏi lại bạn`.

## 4. Phần C: bộ biểu đồ

### 4.1 Nguyên tắc (theo skill dataviz)

1. **Chọn dạng trước màu**: việc người đọc cần làm quyết định loại; đôi khi câu trả lời là "không phải biểu đồ" (một
   số → câu văn hoặc thẻ số).
2. **Một trục y**. Không có `y2` trong spec; validator báo lỗi riêng nếu agent gửi.
3. **Màu theo vai trò**: phân loại (danh tính, thứ tự cố định, không quay vòng), tuần tự (một sắc, nhạt → đậm),
   phân kỳ (hai sắc đối nhau + điểm giữa xám), nhấn (một sắc + xám). Màu đi theo thực thể, không theo thứ hạng: lọc
   bớt series không đổi màu các series còn lại.
4. **Trần số series**: dạng kề nhau (cột, chồng, đường) ≤ 8; dạng mọi cặp (scatter, bubble, radar) ≤ 3; pie/donut ≤ 6
   lát. Vượt thì gộp đuôi vào "Khác" (`transform.top_n`) hoặc chia nhỏ (`facet`), không sinh màu mới.
5. **Nét**: cột ≤ 24 px, đầu bo 4 px, gốc vuông; đường 2 px; điểm ≥ 8 px có viền 2 px màu nền; vùng tô 10% độ đậm;
   lưới và trục là nét mảnh liền, nhạt; khe 2 px giữa các phần chồng.
6. **Nhãn chọn lọc**: ≥ 2 series luôn có chú giải; ≤ 4 series có nhãn trực tiếp; không ghi số trên mọi điểm. Chữ dùng
   màu chữ, không dùng màu series.
7. **Hover và bảng**: tooltip trên mọi biểu đồ (crosshair cho đường/vùng, từng phần tử cho cột/ô/điểm, vùng bắt ≥ 24 px
   cho điểm); tooltip chỉ bổ sung, mọi giá trị có ở bảng song song (nút "Xem dạng bảng").
8. **Bảng màu đã kiểm**: tám màu phân loại của bảng tham chiếu dataviz (năm màu đầu trùng `--chart-1..5` hiện có).
   Đã chạy `validate_palette.js` (bản sao trong scratchpad) với nền thẻ thật của app: sáng `#ffffff` → mọi kiểm tra
   PASS, CVD kề nhau thấp nhất 9,1, nhìn thường thấp nhất 19,6, **cảnh báo tương phản** < 3:1 với `#1baf7a` (2,82),
   `#eda100` (2,17), `#e87ba4` (2,69) → bắt buộc có nhãn hoặc bảng (đã có ở điểm 6, 7); tối `#171717` → mọi kiểm tra
   PASS (CVD 8,4; nhìn thường 19,3; tương phản ≥ 3:1). Ba màu đầu kiểm "mọi cặp" PASS ở cả hai chế độ (căn cứ trần 3
   series của dạng mọi cặp).

Token màu (FE thêm vào `app/globals.css`, giữ `--chart-1..5` hiện có):

| Token spec | Biến CSS | Sáng | Tối |
| --- | --- | --- | --- |
| `series-1`…`series-5` | `--chart-1`…`--chart-5` | (đã có) | (đã có) |
| `series-6` | `--chart-6` | `#008300` | `#008300` |
| `series-7` | `--chart-7` | `#6250d6` | `#9085e9` |
| `series-8` | `--chart-8` | `#e34948` | `#e66767` |
| `muted` | `--chart-muted` | `#c3c2b7` (đường trục của bảng tham chiếu) | `#898781` (mực nhạt của bảng tham chiếu) |
| tuần tự 100…700 | `--chart-seq-100`…`--chart-seq-700` | `#cde2fb #b7d3f6 #9ec5f4 #86b6ef #6da7ec #5598e7 #3987e5 #2a78d6 #256abf #1c5cab #184f95 #104281 #0d366b` (13 bước 100, 150, …, 700) | cùng thang; ô gần 0 trên nền tối dùng từ bước 600 trở xuống theo quy tắc thứ bậc |
| phân kỳ | `--chart-div-neg` / `--chart-div-mid` / `--chart-div-pos` | `#e34948` / `#f0efec` / `#2a78d6` | `#e66767` / `#383835` / `#3987e5` |

Màu trạng thái (tốt/xấu) **không** mở cho spec. Mã hex tùy ý **không** được chấp nhận ở bản 1 (validator báo lỗi kèm
danh sách token); muốn mở sau thì phải qua `validate_palette.js` ở build time, không ở runtime.

### 4.2 Danh mục 32 loại

Cột "Vai trò" dùng tên khóa trong `encoding` (mục 4.3). N = cột số, C = cột văn bản hoặc boolean, T = cột ngày hoặc
ngày giờ. "Vẽ bằng" là thành phần Recharts 3.8.0 đã kiểm có export, hoặc HTML/CSS.

| `type` | Nhãn (FE) | Nhóm | Vai trò bắt buộc / tùy chọn | Ràng buộc chính | Vẽ bằng |
| --- | --- | --- | --- | --- | --- |
| `kpi` | Thẻ số | Con số | `y` 1–4 N; tùy chọn `compare` N (chênh lệch), `x` T (đường nhỏ) | 1 dòng, hoặc có `x` T thì lấy dòng cuối + đường nhỏ | HTML + `LineChart` nhỏ |
| `bullet` | Thanh mục tiêu | Con số | `y` 1 N; `goal` N hoặc `options.target_value`; tùy chọn `x` C | ≤ 12 dòng; `options.ranges` ≤ 3 mốc tăng dần | HTML/CSS (thước đo cùng thang màu) |
| `bar` | Cột | So sánh | `x` C hoặc T; `y` 1 N | ≤ 40 nhóm sau `top_n` | `BarChart` |
| `bar_horizontal` | Thanh ngang | So sánh | `x` C; `y` 1 N | ≤ 50 nhóm sau `top_n` | `BarChart layout="vertical"` |
| `bar_grouped` | Cột nhóm | So sánh | `x` C/T; `y` 2–4 N **hoặc** `y` 1 N + `series` C | series ≤ 8; `x` ≤ 20 | `BarChart` nhiều `Bar` |
| `lollipop` | Kẹo mút | So sánh | `x` C; `y` 1 N | ≤ 50 nhóm | `BarChart` (`layout="vertical"` khi ngang), một `Bar` `barSize={2}` có `shape` tự vẽ: thân 2 px + chấm tròn 8 px ở đầu giá trị (PB-14). Không dùng `Scatter` nên hai hướng cùng một cách đặt trục: dọc thì `XAxis type="category"`, ngang thì `YAxis type="category" dataKey=x` + `XAxis type="number"` |
| `dumbbell` | Quả tạ | So sánh | `x` C; `y` đúng 2 N **hoặc** `y` 1 N + `series` có đúng 2 giá trị | ≤ 30 nhóm | `BarChart` như `lollipop`, `Bar` dạng khoảng `dataKey` trả `[a, b]`, `shape` tự vẽ đoạn nối + hai chấm màu hai số đo (màu theo `series-1`, `series-2`), chú giải tự dựng |
| `diverging_bar` | Thanh phân kỳ | So sánh | `x` C/T; `y` 1 N | có cả giá trị âm và dương, hoặc `options.baseline` | `BarChart` + `Cell` màu theo dấu |
| `radial_bar` | Thanh tròn | So sánh | `x` C; `y` 1 N ≥ 0 | 2–8 nhóm | `RadialBarChart` |
| `radar` | Mạng nhện | So sánh | `x` C (trục); `y` 1–3 N cùng đơn vị **hoặc** `y` 1 N + `series` ≤ 3 | 3–12 trục | `RadarChart` |
| `bar_stacked` | Cột chồng | Thành phần | `x` C/T; `y` 2–8 N cùng đơn vị **hoặc** `y` 1 N + `series` | N ≥ 0, `additive != false`; series ≤ 8 | `BarChart` `stackId` |
| `bar_stacked_100` | Cột chồng 100% | Thành phần | như `bar_stacked` | như trên | `BarChart stackOffset="expand"` |
| `pie` | Tròn | Thành phần | `x` C; `y` 1 N | 2–6 lát sau `top_n`; N ≥ 0; tổng > 0 | `PieChart` |
| `donut` | Vành khuyên | Thành phần | như `pie` | như `pie` | `PieChart innerRadius` |
| `treemap` | Ô vuông | Thành phần | `x` C (lá); `y` 1 N ≥ 0; tùy chọn `path` 1 C (cha) | ≤ 60 lá | `Treemap` |
| `sunburst` | Vành nhiều tầng | Thành phần | `path` 2–3 C; `y` 1 N ≥ 0 | ≤ 60 lá | `SunburstChart` |
| `waterfall` | Thác nước | Thành phần | `x` C/T (thứ tự theo dòng); `y` 1 N (biến động có dấu) | ≤ 30 bước | `BarChart`, một `Bar` dạng khoảng: `dataKey` trả mảng `[start, end]` (tổng tích lũy trước và sau bước), `Cell` màu theo dấu biến động; đúng cả khi tổng tích lũy đổi dấu (PB-14). Cột tổng là `[0, tổng]` |
| `funnel` | Phễu | Thành phần | `x` C (giai đoạn); `y` 1 N ≥ 0 | 2–8 giai đoạn, giữ thứ tự dòng | `FunnelChart` |
| `line` | Đường | Xu hướng | `x` T, N hoặc C có thứ tự; `y` 1–8 N **hoặc** `y` 1 N + `series` ≤ 8 | ≥ 2 điểm; nhiều số đo khác đơn vị → bắt buộc `facet` hoặc `index_to` | `LineChart` |
| `area` | Vùng | Xu hướng | `x` T/N; `y` 1 N (hoặc ≤ 3 N cùng đơn vị, chồng mờ) | ≥ 2 điểm | `AreaChart` |
| `area_stacked` | Vùng chồng | Xu hướng | `x` T; `y` 2–8 N **hoặc** `y` 1 N + `series` | N ≥ 0, `additive != false` | `AreaChart stackId` |
| `area_stacked_100` | Vùng chồng 100% | Xu hướng | như `area_stacked` | như trên | `AreaChart stackOffset="expand"` |
| `combo` | Cột và đường | Xu hướng | `x` C/T; `y` 2–4 N, mỗi N có `mark` (`bar`, `line`, `area`) | **cùng đơn vị** (hoặc `index_to`); ≥ 1 `bar` và ≥ 1 `line` | `ComposedChart`, **một** `YAxis` |
| `sparkline_table` | Bảng đường nhỏ | Xu hướng | `x` T; `y` 1 N; `series` C (mỗi dòng bảng) | 2–50 series, ≥ 3 điểm mỗi series | `DataTable` + `LineChart` nhỏ |
| `calendar_heatmap` | Lịch nhiệt | Xu hướng | `x` T (ngày); `color` N | 7–400 ngày; ngày không trùng | lưới HTML/CSS |
| `histogram` | Tần suất | Phân bố | `x` N (giá trị thô) | ≥ 10 giá trị; `options.bins` 5–50 hoặc `bin_width` | `BarChart` (chia khoảng ở FE) |
| `box_plot` | Hộp | Phân bố | `y` 1 N (giá trị thô); tùy chọn `x` C (nhóm) | ≥ 5 giá trị mỗi nhóm; ≤ 20 nhóm | `ComposedChart` (`Bar` chồng + `ErrorBar` + `Scatter` ngoại lai) |
| `heatmap` | Bản đồ nhiệt | Phân bố | `x` C/T; `row` C/T; `color` N | mỗi chiều ≤ 40 giá trị; ô trùng thì phải có `aggregate` | lưới HTML/CSS, thang tuần tự hoặc phân kỳ |
| `scatter` | Phân tán | Quan hệ | `x` N; `y` 1 N; tùy chọn `series` ≤ 3, `label` C | ≥ 5 điểm; `options.trend` `linear` | `ScatterChart` |
| `bubble` | Bong bóng | Quan hệ | như `scatter` + `size` N ≥ 0 | ≥ 3 điểm | `ScatterChart` + `ZAxis` |
| `sankey` | Dòng chảy | Dòng chảy | `source` C; `target` C; `y` 1 N ≥ 0 | ≤ 60 liên kết; không có vòng; nguồn ≠ đích | `Sankey` |
| `table` | Bảng | Bảng | tùy chọn `options.columns` (thứ tự, tập con), `options.heat` (cột N tô nền tuần tự) | luôn hợp lệ | `DataTable` hiện có |

Nhóm FE dùng cho bộ chọn: `Con số`, `So sánh`, `Thành phần`, `Xu hướng`, `Phân bố`, `Quan hệ`, `Dòng chảy`, `Bảng`.

### 4.3 Spec JSON phiên bản 1

Đặt ở **`backend/common/charts/`** (BE1): spec và validator dùng chung cho `text2sql` (công cụ agent, endpoint kiểm)
và `conversation` (lưu lựa chọn). Đặt trong `common` để `conversation` không phải import `text2sql` (text2sql đã
import conversation; import ngược dễ vòng). Gói chỉ dùng `pydantic`, không DB, không import `backend.modules`.

```text
backend/common/charts/
  __init__.py        # export ChartSpec, ChartField, ChartSpecError, validate_chart, compatible_types, suggest_chart,
                     #        chart_catalog, chart_display, infer_fields, chart_stats, CHART_VERSION
  spec.py            # mô hình pydantic dưới đây
  catalog.py         # CHART_TYPES: type → ChartTypeDef(family, label, roles, rows, caps, options_model, fit, build)
  profile.py         # ResultProfile từ fields + rows (kiểu, số giá trị khác nhau, âm/dương, tổng, đơn vị)
  prepare.py         # chart_stats(spec, fields, rows) → số điểm, nhóm, series sau null/filter/aggregate/top_n
                     # (cùng thuật toán với frontend charts/data.ts; kiểm chung bằng tests/fixtures/chart_cases.json)
  validate.py        # validate_chart(...) -> ValidatedChart(spec, warnings) | raise ChartSpecError(errors)
  suggest.py         # compatible_types(...), suggest_chart(...)
```

```python
CHART_VERSION = 1
ChartType = Literal[
    "kpi", "bullet", "bar", "bar_horizontal", "bar_grouped", "lollipop", "dumbbell", "diverging_bar", "radial_bar",
    "radar", "bar_stacked", "bar_stacked_100", "pie", "donut", "treemap", "sunburst", "waterfall", "funnel", "line",
    "area", "area_stacked", "area_stacked_100", "combo", "sparkline_table", "calendar_heatmap", "histogram",
    "box_plot", "heatmap", "scatter", "bubble", "sankey", "table",
]
PaletteToken = Literal[
    "series-1", "series-2", "series-3", "series-4", "series-5", "series-6", "series-7", "series-8", "muted",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChartField(Strict):             # đầu vào validator, tạo từ FieldOut
    name: str
    label: str
    type: Literal["number", "date", "datetime", "text", "boolean", "other"]
    unit: str | None = None
    decimals: int | None = None
    percent: bool = False
    additive: bool | None = None
    role: Literal["measure", "dimension"] = "dimension"
    format_hint: Literal["plain"] | None = None
    time_unit: Literal["day", "week", "month", "quarter", "year"] | None = None
    pii: bool = False


def infer_fields(columns: list[str], rows: list[list[Any]]) -> list[ChartField]:   # PB-8, lượt cũ
    ...   # kiểu theo quy tắc 1 mục 2.3 trên giá trị JSON (chuỗi ISO ngày → date/datetime), nhãn = humanize(tên),
          # format_hint/role theo quy tắc 1b chỉ dùng tên cột


class NumberFormat(Strict):
    style: Literal["number", "percent", "compact"] = "number"
    decimals: int | None = Field(None, ge=0, le=4)
    percent_input: Literal["ratio", "percent"] = "ratio"
    unit: str | None = Field(None, max_length=12)


class DateFormat(Strict):
    style: Literal["auto", "day", "day_weekday", "week", "month", "quarter", "year", "datetime"] = "auto"


class FieldRef(Strict):
    field: str = Field(min_length=1, max_length=128)
    label: str | None = Field(None, max_length=80)


class Dimension(FieldRef):
    time_unit: Literal["day", "week", "month", "quarter", "year"] | None = None   # None → field.time_unit khi chuẩn hóa


class Measure(FieldRef):
    aggregate: Literal["auto", "none", "sum", "avg", "min", "max", "count", "count_distinct"] = "auto"
    mark: Literal["bar", "line", "area"] | None = None          # chỉ combo
    color: PaletteToken | None = None
    format: NumberFormat | None = None


class Encoding(Strict):
    x: Dimension | None = None
    y: list[Measure] = Field(default_factory=list, max_length=8)
    series: FieldRef | None = None
    row: Dimension | None = None                                 # heatmap
    path: list[FieldRef] = Field(default_factory=list, max_length=3)   # treemap (cha), sunburst
    size: Measure | None = None                                  # bubble
    color: Measure | None = None                                 # heatmap, calendar_heatmap
    goal: Measure | None = None                                  # bullet
    compare: Measure | None = None                               # kpi
    source: FieldRef | None = None                               # sankey
    target: FieldRef | None = None                               # sankey
    label: FieldRef | None = None                                # nhãn điểm scatter/bubble


class FilterSpec(Strict):
    field: str
    op: Literal["eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte"]
    value: str | float | int | bool | list[str | float | int] | None


class SortSpec(Strict):
    by: str = "none"                  # "none" | "x" | "y" | tên một cột trong y
    order: Literal["asc", "desc"] = "desc"


class TopN(Strict):
    n: int = Field(ge=1, le=50)
    other: bool = True
    other_label: str = Field("Khác", max_length=30)


class Transform(Strict):
    filter: list[FilterSpec] = Field(default_factory=list, max_length=5)
    sort: SortSpec | None = None
    top_n: TopN | None = None
    limit: int | None = Field(None, ge=1, le=1000)
    index_to: Literal["none", "first"] = "none"    # đưa mỗi số đo về 100 tại điểm đầu
    cumulative: bool = False


class AxisSpec(Strict):
    title: str | None = Field(None, max_length=60)
    hide: bool = False
    scale: Literal["linear", "log"] = "linear"
    min: float | None = None
    max: float | None = None
    zero: bool = True
    tick_angle: Literal[0, -45, -90] = 0


class Axes(Strict):
    x: AxisSpec = AxisSpec()
    y: AxisSpec = AxisSpec()


class ReferenceLine(Strict):
    axis: Literal["x", "y"]
    value: float | str
    label: str | None = Field(None, max_length=60)
    color: PaletteToken = "muted"


class ReferenceBand(Strict):
    axis: Literal["x", "y"]
    start: float | str
    end: float | str
    label: str | None = Field(None, max_length=60)


class Annotation(Strict):
    x: float | str
    y: float | None = None
    text: str = Field(min_length=1, max_length=80)


class Legend(Strict):
    show: Literal["auto", "show", "hide"] = "auto"
    position: Literal["top", "bottom", "right"] = "bottom"


class Labels(Strict):
    show: Literal["auto", "none", "endpoints", "extremes", "all"] = "auto"


class Colors(Strict):
    scheme: Literal["categorical", "sequential", "diverging", "emphasis"] = "categorical"
    assign: dict[str, PaletteToken] = Field(default_factory=dict, max_length=8)   # giá trị series → token
    highlight: list[str] = Field(default_factory=list, max_length=3)              # cho scheme emphasis


class Facet(Strict):
    by: Literal["measure", "series"]
    columns: int = Field(2, ge=1, le=4)


class Formats(Strict):
    number: NumberFormat | None = None
    date: DateFormat = DateFormat()


class ChartSpec(Strict):
    version: Literal[1] = 1
    type: ChartType
    title: str | None = Field(None, max_length=120)
    subtitle: str | None = Field(None, max_length=200)
    encoding: Encoding = Encoding()
    transform: Transform = Transform()
    orientation: Literal["vertical", "horizontal"] | None = None
    axes: Axes = Axes()
    format: Formats = Formats()
    reference_lines: list[ReferenceLine] = Field(default_factory=list, max_length=5)
    reference_bands: list[ReferenceBand] = Field(default_factory=list, max_length=3)
    annotations: list[Annotation] = Field(default_factory=list, max_length=8)
    legend: Legend = Legend()
    labels: Labels = Labels()
    colors: Colors = Colors()
    facet: Facet | None = None
    options: dict[str, Any] = Field(default_factory=dict)        # kiểm theo options_model của từng loại
```

Tùy chọn theo loại (`options_model`, đều `extra="forbid"`):

| Loại | Tùy chọn |
| --- | --- |
| `line`, `area`, `area_stacked`, `area_stacked_100` | `curve: linear|monotone|step = linear`, `points: auto|show|hide = auto`, `connect_nulls: bool = false` |
| `bar_grouped`, `bar_stacked`, `bar_stacked_100`, `lollipop`, `dumbbell`, `diverging_bar`, `waterfall`, `funnel` | dùng `orientation` của spec (không có tùy chọn riêng), riêng: `diverging_bar.baseline: float = 0`, `waterfall.total: bool = true`, `waterfall.total_label: str = "Tổng"`, `funnel.show_conversion: bool = true` |
| `pie`, `donut` | `show_percent: bool = true` |
| `kpi` | `sparkline: bool = true`, `delta_good: up|down = up` |
| `bullet` | `target_value: float | None`, `ranges: list[float] (≤ 3, tăng dần)` |
| `histogram` | `bins: int 5–50 | None`, `bin_width: float > 0 | None` (không đồng thời) |
| `box_plot` | `whisker: tukey|minmax = tukey`, `outliers: bool = true` |
| `heatmap`, `calendar_heatmap` | `midpoint: float | None` (chỉ khi `colors.scheme = diverging`) |
| `scatter`, `bubble` | `trend: none|linear = none` |
| `radar` | `fill: bool = true` |
| `sparkline_table` | `sparkline: line|bar = line`, `show_last: bool = true` |
| `table` | `columns: list[str]` (tập con, thứ tự), `heat: str | None` (cột N) |
| còn lại | `{}` |

Cách hiểu `aggregate = "auto"` khi chuẩn hóa: các khóa (`x`, `series`, `row`, `path`) không trùng → `none`; trùng →
`sum` nếu `field.additive is True`, ngược lại `avg` (kèm cảnh báo). `"none"` mà khóa trùng → lỗi.

### 4.4 Validator: quy tắc và thông báo

`validate_chart(spec: dict | ChartSpec, fields: list[ChartField], rows: list[list[Any]], result_id: str,
rows_complete: bool = True, enabled: frozenset[str] | None = None) -> ValidatedChart(spec: ChartSpec, warnings:
list[str])`, lỗi thì `raise ChartSpecError(errors: list[str])` (tối đa 8 lỗi,
gom hết rồi ném một lần). Thông báo tiếng Việt, dạng **`<đường dẫn>: <vấn đề>. <cách sửa>.`**, luôn kèm giá trị hợp
lệ khi có. Thứ tự kiểm:

| # | Kiểm | Ví dụ thông báo |
| --- | --- | --- |
| V1 | Pydantic (kiểu, khóa lạ, độ dài). Đổi `loc` thành đường dẫn `encoding.y[0].field`. Khóa lạ quen thuộc có câu riêng | `axes.y2: không hỗ trợ trục y thứ hai. Hai số đo khác đơn vị thì dùng facet {"by": "measure"} hoặc transform.index_to = "first".` |
| V2 | `version` | `version: chỉ hỗ trợ 1.` |
| V3 | `type` | `type: 'stacked_bar' không có. Các loại gần giống: bar_stacked, bar_stacked_100, area_stacked.` |
| V4 | Mỗi `field` phải có trong `fields` | `encoding.y[0].field: không có cột 'luong_mua' trong kết quả 1-2. Các cột: ten_thanh_pho (văn bản), tong_luong_mua (số).` |
| V5 | Vai trò bắt buộc / số lượng | `encoding.y: bar cần đúng 1 số đo, đang có 2. Dùng bar_grouped hoặc combo cho nhiều số đo.` |
| V6 | Kiểu cột hợp vai trò | `encoding.x: line cần cột ngày giờ hoặc số ở trục x; 'ten_thanh_pho' là văn bản. Dùng bar hoặc bar_horizontal.` |
| V7 | Khóa trùng khi `aggregate = none` | `encoding.y[0].aggregate: 'ngay_key' lặp giá trị (31 dòng, 7 giá trị khác nhau) khi không có series. Đặt aggregate (sum, avg, ...) hoặc thêm encoding.series.` |
| V8 | Số dòng/điểm tối thiểu, tối đa | `histogram: cần ít nhất 10 giá trị số, kết quả có 4 dòng. Dùng bar hoặc table.` |
| V9 | Số nhóm/series sau `filter`, `top_n` | `pie: 'ten_thanh_pho' có 12 giá trị, tối đa 6 lát. Thêm transform.top_n {"n": 5, "other": true} hoặc dùng bar_horizontal.` / `scatter: encoding.series có 5 giá trị, tối đa 3. Bỏ series hoặc lọc bớt.` |
| V10 | Dấu giá trị | `pie: 'chenh_lech' có giá trị âm (-3,2). Pie chỉ dùng cho số không âm; dùng diverging_bar hoặc waterfall.` |
| V11 | Cộng dồn | `bar_stacked: 'nhiet_do_trung_binh' không cộng dồn được (trung bình). Dùng bar_grouped hoặc line.` |
| V12 | Đơn vị (một trục) | `combo: các số đo khác đơn vị (mm, °C) nên không vẽ chung một trục. Dùng line với facet {"by": "measure"} hoặc transform.index_to = "first".` |
| V13 | `axes.*.scale = log` | `axes.y.scale: log cần mọi giá trị > 0; 'nhiet_do' có giá trị ≤ 0.` |
| V14 | `axes.*.min < max`, `reference_*` đúng trục và kiểu | `reference_lines[0].value: trục y là số, '30 độ' không phải số.` |
| V15 | `annotations[i].x`, `reference_lines` trục x phải có trên trục | `annotations[0].x: '2026-11-31' không có trên trục x.` |
| V16 | `colors.assign` khóa phải là giá trị series; token hợp lệ | `colors.assign['#ff0000']: chỉ dùng series-1…series-8 hoặc muted, không dùng mã màu.` |
| V17 | `colors.highlight` phải là giá trị có trong `x` hoặc `series` | `colors.highlight[0]: 'Hà Nội' không có trong 'ten_thanh_pho'. Giá trị gần giống: Ha Noi.` (so khớp `normalized` như `agent_catalog`) |
| V18 | `options` theo loại | `options.bins: không dùng cho line. Tùy chọn của line: curve, points, connect_nulls.` |
| V19 | `transform.sort.by`, `filter.field` | `transform.sort.by: phải là none, x, y hoặc một cột trong encoding.y (tong_luong_mua).` |
| V20 | `facet` | `facet.by = series cần encoding.series.` |
| V21 | Cùng một cột ở hai vai trò (`x` = `series`, `x` = `row`, `source` = `target`, `path` lặp), hoặc `y` lặp cột (PB-6i). Ngoại lệ: `label` trùng `x` ở `bar*` | `encoding.series: 'ten_thanh_pho' đã dùng ở encoding.x. Chọn cột khác hoặc bỏ series.` / `encoding.y[1].field: 'tong_luong_mua' đã có ở encoding.y[0].` |
| V22 | `aggregate` khác `count`, `count_distinct`, `none`, `auto` cần cột số (PB-6j) | `encoding.y[0].aggregate: sum cần cột số; 'ten_thanh_pho' là văn bản. Dùng count hoặc count_distinct.` |
| V23 | `top_n.other = true` và `transform.cumulative = true` chỉ cho số đo `additive is True` hoặc `aggregate` là `sum`, `count`, `count_distinct` (PB-6c) | `transform.top_n.other: không gộp 'Khác' cho 'nhiet_do_tb' vì số này không cộng dồn được (trung bình). Đặt "other": false.` / `transform.cumulative: 'nhiet_do_tb' không cộng dồn được.` |
| V24 | `index_to = "first"`: giá trị đầu (sau sắp xếp theo x) của từng số đo/series phải khác 0 và khác null (PB-6d) | `transform.index_to: 'luong_mua' bằng 0 ở điểm đầu (13/11) nên không quy về 100 được. Bỏ index_to hoặc dùng facet {"by": "measure"}.` |
| V25 | `sort.by = "y"` (hoặc một cột y) khi `x` là ngày/ngày giờ/số ở `line`, `area*`, `combo`, `sparkline_table`, `calendar_heatmap` (PB-6e) | `transform.sort.by: line có trục x thời gian luôn sắp theo thời gian. Bỏ sort hoặc đặt "by": "x".` |
| V26 | Token màu trùng: hai khóa `colors.assign` hoặc hai `Measure.color` cùng token, hoặc `assign` trùng `color` của số đo (PB-6f) | `colors.assign['Huế']: series-2 đã gán cho 'Hà Nội'. Mỗi series một màu khác nhau.` |
| V27 | `x.time_unit`/`row.time_unit` chỉ cho cột `date`/`datetime`; không mịn hơn `field.time_unit` (PB-6g) | `encoding.x.time_unit: chỉ dùng cho cột ngày; 'ten_thanh_pho' là văn bản.` / `encoding.x.time_unit: cột đã gom theo tháng, không chia nhỏ thành day.` |
| V28 | `colors.scheme` theo loại (PB-6h): `diverging` cần số đo màu có cả âm lẫn dương, hoặc `options.midpoint`/`options.baseline`; `emphasis` cần `colors.highlight` không rỗng; `sequential` chỉ cho `heatmap`, `calendar_heatmap`, `treemap`, `table` (`options.heat`) và loại một series | `colors.scheme: diverging cần giá trị cả âm lẫn dương hoặc options.midpoint; 'luong_mua' toàn ≥ 0. Dùng sequential.` / `colors.scheme: emphasis cần colors.highlight.` |
| V29 | `axes.x.scale = log` trên trục phân loại; `reference_bands[i]` có `start ≥ end` (PB-6k) | `axes.x.scale: log chỉ dùng cho trục số; trục x của bar là phân loại.` / `reference_bands[0]: start (30) phải nhỏ hơn end (20).` |
| V30 | `facet` không dùng cho `kpi`, `bullet`, `pie`, `donut`, `treemap`, `sunburst`, `sankey`, `funnel`, `sparkline_table`, `calendar_heatmap`, `table`; số ô facet ≤ 12 (PB-6l) | `facet: không dùng cho pie. Dùng bar_grouped hoặc bar_stacked_100.` / `facet: chia theo series ra 15 ô, tối đa 12. Thêm transform.filter hoặc bỏ facet.` |
| V31 | `FilterSpec` (PB-6m): `in`/`not_in` cần danh sách 1–50 giá trị; op khác cần một giá trị (không phải danh sách); `gt/gte/lt/lte` chỉ cho cột số, ngày; kiểu giá trị khớp kiểu cột (số cho `number`, chuỗi `YYYY-MM-DD` cho `date`, ISO cho `datetime`, `true/false` cho `boolean`) | `transform.filter[0].value: op in cần danh sách giá trị, ví dụ ["Hà Nội", "Huế"].` / `transform.filter[1].value: 'nhiet_do' là số, '30 độ' không phải số.` |
| V32 | `sankey`: không có liên kết tự nối (nguồn = đích) và không có vòng (DFS trên đồ thị nguồn → đích); `sunburst`/`treemap` có `path`: mỗi lá chỉ thuộc một cha (PB-6n) | `sankey: có vòng Hà Nội → Huế → Hà Nội. Sankey cần luồng một chiều; dùng heatmap.` / `sunburst: lá 'Quận 1' thuộc hai cha (Hồ Chí Minh, Hà Nội). Thêm cột cha vào path hoặc dùng treemap không có path.` |
| V33 | Cột PII (PB-15): `encoding.label` trên cột `pii`; `annotations`, `colors.highlight`, khóa `colors.assign`, `transform.filter` dùng giá trị của cột `pii` | `encoding.label: 'so_dien_thoai' là dữ liệu cá nhân, không dùng làm nhãn điểm.` / `colors.highlight[0]: không dùng giá trị của cột dữ liệu cá nhân 'ho_ten'.` |
| V34 | Loại chưa bật (PB-13): `enabled` khác `None` và `type` không thuộc `enabled` | `type: heatmap chưa được hỗ trợ ở bản này. Các loại dùng được: bar, bar_horizontal, line, ...` |

**Null và giá trị không hữu hạn** (PB-5, PB-6b), một định nghĩa dùng cho profile, `chart_stats`, validator và
`charts/data.ts`:

- Ô số là `null` hoặc chuỗi không hữu hạn (`"NaN"`, `"Infinity"`, `"-Infinity"`, `"inf"`, `"-inf"`) → **null số**.
- Vai trò phân loại (`x` loại C, `series`, `row` loại C, `path`, `source`, `target`, `label`) null → nhóm có giá trị
  hiển thị `"(Trống)"` (giữ lại, có màu riêng như một thực thể).
- Vai trò `x`/`row` loại T hoặc N null → **bỏ dòng** (không vẽ được vị trí), cảnh báo "Bỏ N dòng thiếu giá trị trục
  x".
- Số đo null → điểm trống: đường đứt (trừ `connect_nulls`), cột không vẽ; `aggregate` bỏ null (như SQL); nhóm mà mọi
  số đo đều null không tính là điểm.
- `scatter`/`bubble`/`histogram`/`box_plot`: dòng có null ở bất kỳ số đo bắt buộc nào → bỏ.
- V8 (tối thiểu/tối đa điểm), V9 (nhóm/series), V10, V13, V24 đếm **sau** bước bỏ null này, rồi mới `filter`, `top_n`.

**Kiểm lại trên dòng đã lưu không đủ** (PB-8b): khi `rows_complete = False` (lượt có `stored_truncated` hoặc kết quả
`truncated`), các quy tắc phụ thuộc dòng **hạ thành cảnh báo**: V7, V8, V9, V10, V13, V15, V17, V24, V28 (phần dấu
giá trị), V32. Spec vẫn được lưu; cảnh báo "Kiểm trên N dòng đã lưu; biểu đồ chỉ vẽ N dòng này". Quy tắc chỉ phụ thuộc
`fields` (V1–V6, V11, V12, V16, V18–V23, V25–V27, V29–V31, V33, V34) vẫn là lỗi.

**Python và TypeScript tính giống nhau** (PB-7): `prepare.chart_stats(spec, fields, rows) -> {"points", "groups",
"series", "dropped_null"}` cài cùng thuật toán với `charts/data.ts` (`buildChartData` trả kèm `stats` cùng khóa).
Tệp ví dụ dùng chung **`tests/fixtures/chart_cases.json`** (BE1 tạo, ≥ 40 ca): mỗi ca `{"name", "fields", "rows",
"spec", "expect": {"valid": bool, "errors": [chuỗi con], "stats": {...}}}`, phủ null, `"(Trống)"`, `top_n` + "Khác",
`aggregate` khi khóa trùng, `filter` mỗi op, xoay dài → rộng, `index_to`, `cumulative`, waterfall đổi dấu, histogram
`bins`. Tệp thứ hai **`tests/fixtures/format_cases.json`**: `{"number": [[giá trị, field, chuỗi mong đợi]], "date":
[[giá trị, unit, today, chuỗi mong đợi]]}` cho `vi_number`/`number_display`/`bucket_display` (Python) và
`charts/format.ts` (TS). `test_chart_spec.py`, `test_text2sql_display.py` chạy hai tệp; FE chạy cùng hai tệp bằng
`node --test` (mục 6.4). Sửa thuật toán ở một bên mà không sửa bên kia thì một trong hai bộ test đỏ.

Cảnh báo (không chặn, trả cho agent và hiện trong editor): `labels.show = all` với > 12 điểm (hạ xuống `auto`);
`aggregate auto → avg`; dữ liệu `truncated` hoặc `stored_truncated` ("biểu đồ chỉ vẽ N dòng đầu"); `pie`/`donut` có
lát < 2%. Chuẩn hóa: điền `label` từ `fields` khi thiếu, `aggregate`, `orientation` mặc định theo loại, `title` để
nguyên (không tự sinh ở backend; FE dùng tiêu đề kết quả khi trống).

### 4.5 Ma trận tương thích và đề xuất mặc định

`ResultProfile` (`profile.py`): mỗi cột có `type`, `distinct`, `has_negative`, `all_non_negative`, `unit`, `additive`,
`unique_as_key`; cả kết quả có `row_count`. Mỗi `ChartTypeDef` có `fit(profile) -> int | None` (điểm phù hợp, `None` =
không vẽ được) và `build(profile, question_type) -> ChartSpec` (spec mặc định cho loại đó). `compatible_types(fields,
rows) -> list[ChartType]` sắp theo điểm, luôn kết thúc bằng `table`.

| Hình dạng kết quả | Loại hợp (★ = mặc định) |
| --- | --- |
| 0 dòng, hoặc chỉ cột chữ | ★`table` |
| 1 dòng, 1–4 N | ★`kpi`, `table` (thêm `bullet` khi có cột N tên/nhãn là mục tiêu, hoặc agent cho `target_value`) |
| C + 1 N, 2–6 dòng | ★`bar_horizontal` (2–3 dòng: ★`bar`), `bar`, `lollipop`, `radial_bar`, `treemap`, `funnel`, `donut`/`pie` (N ≥ 0, `additive != false`), `diverging_bar`/`waterfall` (có âm), `bullet`, `table` |
| C + 1 N, 7–50 dòng | ★`bar_horizontal` (`top_n` 15 khi > 15), `lollipop`, `bar`, `treemap`, `table` |
| C + 1 N, > 50 dòng | ★`table`, `bar_horizontal` + `top_n` |
| T + 1 N, ≥ 3 điểm | ★`bar` nếu `additive` và ≤ 31 điểm, ngược lại ★`line`; `area`, `lollipop`, `calendar_heatmap` (ngày, ≥ 7), `kpi` (đường nhỏ), `waterfall` (có âm), `table` |
| T + 1 N, 2 điểm | ★`bar`, `dumbbell` (khi coi hai ngày là hai mốc), `table` |
| T + C + 1 N (dạng dài) | ★`line` (series = C, ≤ 8), `bar_grouped` (T ≤ 20), `bar_stacked`/`area_stacked`(+`_100`) (N ≥ 0, cộng dồn), `heatmap`, `sparkline_table`, `table` |
| C + 2–4 N cùng đơn vị | ★`bar_grouped`, `bar_stacked` (cộng dồn), `dumbbell` (đúng 2 N), `radar` (≥ 3 dòng, ≤ 3 N), `combo`, `table` |
| C hoặc T + 2–4 N khác đơn vị | ★`table`, `line`/`bar` với `facet {"by": "measure"}`, `combo`/`line` với `index_to` |
| T + 2–8 N | ★`line` (cùng đơn vị; khác đơn vị thì `facet`), `combo`, `area_stacked`, `table` |
| 2 N, ≥ 5 dòng (± C nhãn) | ★`scatter`, `histogram` (mỗi N), `table` |
| 3 N, ≥ 3 dòng | ★`bubble`, `scatter`, `table` |
| 1 N thô, ≥ 10 dòng (± C nhóm) | ★`histogram` (± C: ★`box_plot` khi mỗi nhóm ≥ 5), `table` |
| C + C + N | ★`heatmap` (mỗi chiều ≤ 40), `bar_stacked`/`bar_grouped` (series = C thứ hai ≤ 8), `treemap` (`path`), `sunburst`, `sankey` (C nguồn, C đích), `table` |

`suggest_chart(fields, rows, question_type) -> ChartSpec` lấy loại ★; `question_type` chỉ phá thế hòa (T7 → sắp giảm
dần, `top_n` 10; T10 → ưu tiên `line`/`bar` theo thời gian; T11 → `donut` khi đủ điều kiện pie, ngược lại
`bar_horizontal`; T13 → `scatter`). Spec mặc định luôn qua `validate_chart` (test bảo đảm).

### 4.6 Agent tạo biểu đồ thế nào

Hai đường, không thêm vòng LLM ở trường hợp thường gặp:

1. **Đề xuất của code** (mọi bước `query_metric`/`run_sql` thành công): `chart = suggest_chart(...)`,
   `chart_source = "auto"`, `chart_types = compatible_types(...)`. Có ngay trong event `tool` → frontend vẽ được ngay.
2. **Agent đặt**:
   - **Kèm lời gọi** (không tốn vòng): `query_metric(..., chart={...})`, `run_sql(..., chart={...})`. Truy vấn chạy
     xong mới kiểm chart. Hợp lệ → `chart_source = "agent"`. Sai → dữ liệu vẫn trả bình thường, `chart` giữ đề xuất,
     output có `chart_error` (các thông báo nối bằng `"; "`); bước không bị coi là lỗi.
   - **Sau khi có kết quả**: công cụ mới `make_chart(result_id, chart)`. Hợp lệ → ghi một bước `AgentStepOut(tool=
     "make_chart", arguments={"result_id", "chart"}, result_id=..., chart=<spec đã chuẩn hóa>, chart_source="agent")`
     và cập nhật `chart`/`chart_source` của bước dữ liệu tương ứng trong `toolkit.steps`; trả `{"result_id", "chart":
     <tóm tắt>, "warnings": [...]}`. Sai → `ToolError("\n".join(errors))` (vòng `tool_agent` trả lỗi cho model; gọi lại
     y nguyên bị chặn bởi `failed_calls`). `result_id` không có → `ToolError("Không có kết quả 'x'. Các result_id: 1-1,
     1-2.")`.
   - `chart` là `dict` trong schema công cụ (không đưa cả JSON schema của `ChartSpec` vào định nghĩa công cụ, để giữ
     token mỗi vòng); cấu trúc mô tả gọn trong `description` (dưới), validator chỉ lỗi chính xác.
3. `result_id = f"{position}-{n}"`, `n` đếm bước `query_metric`/`run_sql` thành công (không có `error`) của câu đơn
   (1, 2, …), tiếp tục khi chạy tiếp: đếm các bước như vậy trong `replied_steps` **theo tool và error, không theo
   trường `result_id`**, nên snapshot cũ (bước chưa có `result_id`) vẫn đếm đúng (PB-2). `Text2SqlToolkit.__init__`
   nhận thêm `position: int = 1` (có mặc định để giai đoạn 1 của BE1 không làm hỏng chỗ khởi tạo cũ trong
   `text2sql_agent_service.py`).
4. Bước `get_column_values` không có `result_id`, `chart`.
5. **Mọi trường mới của `AgentStepOut`** (`result_id`, `fields`, `explanations`, `chart`, `chart_source`,
   `chart_types`, `display`) có mặc định (`None` hoặc `[]`) và không có validator chặt hơn dữ liệu cũ, vì
   `JsonPlusSerializer` dựng lại pydantic bằng `cls(**data)` (lỗi thì `model_construct`, nested để dạng dict).
6. **Loại được bật** (PB-13): setting mới `TEXT2SQL_CHART_TYPES_ENABLED` (`backend/core/setting.py`, chuỗi phân cách
   bằng dấu phẩy, mặc định rỗng = cả 32 loại; thêm vào `.env.example`). `agent_tools` truyền `enabled` vào
   `compatible_types`, `suggest_chart`, `validate_chart`; `chart_types` gửi agent và mô tả `make_chart` chỉ liệt kê
   loại được bật. Trong lúc FE mới xong đợt (a), triển khai đặt biến này bằng danh sách đợt (a). `GET /chart-types`
   trả thêm `"enabled": [...]`.

Mô tả công cụ (BE1, trong `agent_tools.Text2SqlToolkit.tools()`):

```text
make_chart: Đặt hoặc đổi biểu đồ cho một kết quả đã có (result_id). chart là JSON: {"type", "title", "encoding":
{"x": {"field"}, "y": [{"field", "aggregate"?, "mark"?}], "series"?: {"field"}, "row"?, "path"?, "size"?, "color"?,
"goal"?, "compare"?, "source"?, "target"?, "label"?}, "transform"?: {"sort": {"by", "order"}, "top_n": {"n",
"other"}, "filter", "index_to"}, "orientation"?, "axes"?: {"x"|"y": {"title", "scale", "min", "max", "zero"}},
"reference_lines"?: [{"axis", "value", "label"}], "annotations"?: [{"x", "text"}], "colors"?: {"scheme",
"highlight", "assign"}, "facet"?: {"by", "columns"}, "options"?}. field là tên trong columns. Màu chỉ dùng series-1
… series-8, muted. Loại: kpi, bullet, bar, bar_horizontal, bar_grouped, lollipop, dumbbell, diverging_bar,
radial_bar, radar, bar_stacked, bar_stacked_100, pie, donut, treemap, sunburst, waterfall, funnel, line, area,
area_stacked, area_stacked_100, combo, sparkline_table, calendar_heatmap, histogram, box_plot, heatmap, scatter,
bubble, sankey, table. Chỉ chọn loại có trong chart_types của kết quả.
```

(Danh sách "Loại:" trong mô tả được sinh từ loại đang bật, không viết cứng.)

`query_metric`/`run_sql` thêm vào mô tả một câu: "chart (tùy chọn): biểu đồ cho kết quả, cùng dạng như make_chart,
dùng tên cột sẽ trả về (cột group_by và tên metric)."

### 4.7 Endpoint cho frontend

Router mới `backend/modules/text2sql/routes/router_chart.py` (BE1), gắn vào `routes/__init__.py`:

- `GET /api/v1/text2sql/chart-types` → `{"version": 1, "palette": ["series-1", …, "muted"], "types": [{"type",
  "family", "label", "roles": [{"role", "required", "multiple", "max", "accepts": ["number", …]}], "min_rows",
  "max_rows", "max_series", "options_schema": <JSON Schema của options_model>}]}`. Dữ liệu tĩnh từ `chart_catalog()`;
  frontend dùng để dựng trình sửa chung và lọc ô chọn cột.
- `POST /api/v1/text2sql/charts/validate` body `{"chart": {...}, "fields": [ChartField], "rows": [[...]] (≤ 1000)}`
  → 200 `{"chart": <chuẩn hóa>, "warnings": [...], "chart_types": [...]}` hoặc 400 `{"detail": "<các lỗi nối bằng
  xuống dòng>"}` với `code = text2sql_chart_invalid` (exception mới `Text2SqlChartInvalid(ValidationError)` trong
  `text2sql/utils/exceptions.py`). Dùng khi lượt không được lưu (không có `user_id`).

### 4.8 Lưu lựa chọn của người dùng

- **Migration** (BE1): `backend/migrations/versions/init_conversation_module/<rev>_add_turn_views.py`, `down_revision`
  = head lúc làm (hôm nay `e8b2c6d4f170`; chạy lại `uv run alembic heads` trước khi viết), `batch.add_column(sa.Column(
  "views", sa.JSON()))`, downgrade bỏ cột. Kiểm `alembic upgrade head`, `alembic check`, `downgrade -1` trên DB tạm.
  Cập nhật `du-lieu-va-migration.md` (head mới) và `modules/conversation/du-lieu.md`.
- **Model**: `ConversationTurn.views: Mapped[dict[str, Any] | None] = mapped_column(JSON)`. Dạng:
  `{"1-2": {"chart": <ChartSpec đã chuẩn hóa>, "updated_at": "2026-11-20T02:00:00.000000Z"}}`. `results` giữ bất
  biến (đầu ra pipeline).
- **`results` đã lưu** (`stored_results`, BE1): thêm `result_id`, `fields`, `chart`, `chart_source`, `chart_types`,
  `display`. Mục kind `column_values` không có các khóa này (PB-19).
- **Lượt cũ** (PB-8a, chốt cách **backend tự suy**, không ẩn bộ chọn ở FE): hàm `normalize_results(results)` trong
  `conversation/services` (dùng `backend.common.charts.infer_fields`, `compatible_types`) chạy khi **đọc** (`TurnOut`
  của GET lượt/hội thoại) và trong `put_view`, không ghi ngược vào DB. Với mỗi mục khác `column_values` thiếu
  `result_id`: gán `result_id = "<position>-<k>"`, `k` là thứ tự (1, 2, …) của mục đó trong các mục khác
  `column_values` cùng `position` (đúng quy tắc đếm của mục 4.6, nên khớp với lượt mới); thiếu `fields` thì
  `infer_fields(columns, rows)`; `chart_types = compatible_types(...)`; `chart = None`, `chart_source = None`,
  `display = "none"` (lượt cũ không tự hiện vùng biểu đồ; người dùng vẫn chọn được biểu đồ trong tab "Biểu đồ", lựa
  chọn lưu vào `views` và khi đó được đưa lên). Ghi vào handbook `conversation` và `bieu-do.md`.
- **Service** `ConversationService.put_view(conversation_id, turn_id, result_id, user_id, chart) -> dict` và
  `delete_view(...)`: **`get_owned(conversation_id, user_id, lock=True)`** (SELECT … FOR UPDATE trên hội thoại, cùng
  cách `add_turn`/`delete` đang dùng, PB-8c) rồi `_owned_turn` (404 như feedback); đọc `turn.views` **sau** khi đã
  khóa; tìm mục `results` có `result_id` sau `normalize_results` (không có → 404 `ConversationResultNotFoundError`,
  code `conversation_result_not_found`); `validate_chart(chart, fields, rows, result_id, rows_complete=not
  (stored_truncated or truncated))` trên dòng đã lưu (PB-8b: quy tắc phụ thuộc dòng thành cảnh báo khi thiếu dòng);
  lỗi → 400 `ConversationChartInvalidError` (code
  `conversation_chart_invalid`, thông điệp là các lỗi nối bằng xuống dòng); gán `turn.views = {**(turn.views or {}),
  result_id: {...}}` (gán dict mới để SQLAlchemy thấy thay đổi JSON). Lượt `running` hoặc `error` vẫn cho lưu nếu có
  `results`.
- **Route** (`router_conversation.py`): `PUT /api/v1/conversations/{conversation_id}/turns/{turn_id}/views/{result_id}`
  body `{"user_id": "...", "chart": {...}}` → 200 `{"result_id", "chart", "warnings", "updated_at"}`;
  `DELETE .../views/{result_id}?user_id=...` → 204 (trở về chart của agent hoặc đề xuất). `result_id` path tối đa 32
  ký tự, dạng `^\d+-\d+$`.
- **`TurnOut`** thêm `views: dict[str, Any] | None = None`; `results` trả qua `normalize_results`. Hình dạng response
  của `tests/test_conversation_api.py` đổi (thêm khóa) → BE1 sửa test này (PB-20).
- **Lượt chờ hỏi lại**: lượt chạy tiếp là lượt mới; lựa chọn trên lượt cũ không tự sang (chấp nhận, ghi vào handbook).
- **Không có `user_id`**: lựa chọn chỉ nằm trong state của `use-chat.ts` (có thể nhớ `localStorage` theo
  `turn.id:result_id` trong phiên; không bắt buộc).

### 4.9 Frontend vẽ và tùy chỉnh

- **Thứ tự ưu tiên chart của một kết quả**: `views[result_id].chart` (người dùng) → `chart` của bước khi
  `chart_source = "agent"` → `chart` đề xuất → `table`. Bước `make_chart` trong stream cập nhật chart của kết quả có
  cùng `result_id`.
- **Kết quả được đưa lên vùng biểu đồ** (dưới câu trả lời), cùng quy tắc với `display` của backend và câu prompt
  (PB-9): kết quả có `views[result_id]` với `type` khác `table` (người dùng chọn `table` thì không đưa lên, dù
  `display` là gì); kết quả `display = "chart"`; và với mỗi câu đơn, kết
  quả dữ liệu thành công **cuối** (theo thứ tự `result_id`, bỏ mục `column_values`) có `display = "chart_if_last"`.
  Chỉ hiện sau khi câu đơn đó `answered` (tránh nhấp nháy khi agent còn thử truy vấn hoặc đổi chart). Đếm "≥ 3 điểm"
  đã nằm trong `display`; FE không tự đếm lại.
- **Loại chưa có renderer** (PB-13): `chart-view.tsx` tra `RENDERERS[type]`; không có thì vẽ theo chart đề xuất của kết
  quả nếu loại đó có renderer, không thì `table`, kèm dòng nhỏ `Chưa hỗ trợ dạng «<nhãn loại>»; đang hiện dạng
  «<nhãn>».` Bộ chọn chỉ liệt kê loại vừa thuộc `chart_types` vừa có renderer.
- **Dữ liệu biểu đồ**: tính ở FE từ `rows` + `fields` + spec (`charts/data.ts`: lọc, gộp theo `aggregate`, sắp xếp,
  `top_n` + "Khác", xoay dài → rộng cho series, `index_to`, cộng dồn, chia khoảng histogram, tứ phân vị box plot (Tukey
  1,5 IQR), nền waterfall, lưới heatmap/lịch, nút và liên kết sankey, cây treemap/sunburst). Màu series gán theo thứ tự
  xuất hiện trong **toàn bộ** dữ liệu trước khi lọc (màu đi theo thực thể).
- **Định dạng**: `Intl.NumberFormat("vi-VN")` theo `fields[].decimals/percent/unit` rồi `spec.format`/`y[i].format`;
  ngày bỏ năm khi trùng năm hiện tại; trục dùng số gọn (`1,2 N`, `3 Tr` không dùng trong câu, được dùng ở trục).
  `format_hint = "plain"` → in thẳng chữ số (`2026`); cột có `time_unit` → nhãn theo đơn vị gom (`tháng 11`, `tuần
  16–22/11`, `quý 4`), không kèm thứ; giá trị không hữu hạn → ô `—` trong bảng, null trong biểu đồ. `charts/format.ts`
  khớp `tests/fixtures/format_cases.json`. "Cách tính" kind `period`/`data_range` dựng lại từ `start`/`end` theo ngày
  xem (PB-11), không có thì dùng `text`.
- **Bộ chọn loại** (`chart-switcher.tsx`): chỉ liệt kê `chart_types` của kết quả, nhóm theo `family`, có biểu tượng
  `lucide-react`. Đổi loại → `defaultSpecFor(type)`: giữ các vai trò còn hợp (cùng `field`), điền vai trò thiếu theo
  `roles[].accepts`, rồi gửi kiểm.
- **Trình sửa** (`chart-editor.tsx`, `Sheet` bên phải, hẹp thì toàn màn hình): tiêu đề, phụ đề; ô chọn cột cho từng
  vai trò (lọc theo `accepts`); `aggregate`; sắp xếp; top N + "Khác"; hướng; trục (tiêu đề, log, min, max, bắt đầu từ
  0); định dạng số (số lẻ, phần trăm, đơn vị); đường tham chiếu (thêm, xóa, tối đa 5); chú giải (hiện/ẩn, vị trí); nhãn
  (`auto`, `none`, `endpoints`, `extremes`, `all`); màu từng series (chọn trong 8 token + `muted`), làm nổi bật; chia
  nhỏ; tùy chọn riêng của loại dựng tự động từ `options_schema` (enum → `Select`, boolean → `Switch`, số → `Input`
  number). Nút "Đặt lại theo đề xuất".
- **Kiểm và lưu**: thay đổi được debounce 600 ms. Lượt có `turnId` → `PUT .../views/{result_id}` (lạc quan như
  `rate`; 400 thì giữ spec hợp lệ trước, hiện lỗi dưới trình sửa). Lượt không lưu → `POST /charts/validate`. Biểu đồ
  luôn vẽ theo spec hợp lệ gần nhất. Các lần lưu của cùng một kết quả gửi tuần tự (chờ lần trước xong, chỉ giữ spec
  mới nhất đang chờ) để không có hai PUT cùng lúc từ một tab.
- **Truy cập**: nút "Xem dạng bảng" trên mọi biểu đồ; tooltip có cả bàn phím (focus); chú giải khi ≥ 2 series; tô
  vân (texture) chưa làm ở bản 1 (ghi vào việc mở).

## 5. Phần D: bố cục giao diện

```text
┌ Tin nhắn người dùng ───────────────────────────────────────────────┐
└────────────────────────────────────────────────────────────────────┘
┌ Trợ lý ────────────────────────────────────────────────────────────┐
│ (đang chạy) ⟳ Câu 2: Đang truy vấn «Nhiệt độ cao nhất»…   00:07     │  ← dòng lời kể, chỉ khi live
│                                                                    │
│ Câu trả lời (Markdown, stream, có con trỏ khi live)                │  ← luôn đứng đầu
│                                                                    │
│ ┌ Biểu đồ ───────────────────────────────────────────────────────┐ │  ← vùng biểu đồ: kết quả được đưa lên
│ │ Tiêu đề        [Loại ▾] [Tùy chỉnh] [Bảng] [Đặt lại]            │ │
│ │ (biểu đồ)                                                      │ │
│ └────────────────────────────────────────────────────────────────┘ │
│ ▸ Trả lời từng phần (2)                          [Ẩn mục này]       │  ← chỉ câu tách; đóng mặc định
│ ▸ Số liệu và cách tính (3)                                          │  ← đóng mặc định
│     Câu 1: …                                                       │
│       Cách tính: • Chỉ số: … • Thời gian: 13–19/11 • …             │
│       [Thẻ kết quả: Bảng | Biểu đồ | SQL (kèm Ghi chú kỹ thuật)]   │
│     Các bước xử lý (6) – 8 giây  (ThinkingTrace thu gọn)            │
│ (Hỏi lại / thông báo lỗi / Sao chép, Tạo lại, Đánh giá)             │
└────────────────────────────────────────────────────────────────────┘
```

- **Lời kể**: khi live, một dòng `ThinkingTrace` (label = câu kể hiện tại, `defaultOpen=false`) ở trên cùng. Khi xong,
  trace chuyển vào cuối khối "Số liệu và cách tính", nên sau khi xong câu trả lời đứng đầu.
- **Câu trả lời**: `StreamingText` + `AnswerMarkdown`. Câu đơn nhận delta `final=true` của agent; câu tách nhận delta
  synthesize. Khi chưa có chữ: khung giữ chỗ cao một dòng (tránh nhảy bố cục). Markdown dở dang: ẩn dòng cuối chưa kết
  thúc nếu bắt đầu bằng `|`, tạm đóng `**`/`` ` `` lẻ của đoạn cuối, tách khối theo dòng trống và `memo` từng khối (không
  thêm `streamdown`). Cập nhật state theo `requestAnimationFrame` (gom delta trong ref).
- **Vùng biểu đồ**: dưới câu trả lời, mỗi kết quả được đưa lên một thẻ (mục 4.9). Thanh công cụ: bộ chọn loại, "Tùy
  chỉnh", "Bảng", "Đặt lại" (chỉ khi có lựa chọn của người dùng). Chiều cao gồm cả trục x (không cuộn lồng).
- **Trả lời từng phần** (chỉ câu tách): `Collapsible` đóng mặc định, tiêu đề `Trả lời từng phần (N)`; khi live hiện
  bản nháp đang stream của từng câu (`question.draft`), xong thì hiện `question.answer` chính thức. Nút "Ẩn mục này"
  ẩn cho mọi lượt (lưu `localStorage` khóa `text2sql.subAnswers.hidden`; có công tắc "Hiện trả lời từng phần" trong
  khối "Số liệu và cách tính" để bật lại).
- **Số liệu và cách tính**: `Collapsible` đóng mặc định, tiêu đề `Số liệu và cách tính (N)` với N = số kết quả dữ
  liệu. Bên trong theo từng câu đơn (tiền tố `Câu N` khi tách): danh sách "Cách tính" (gộp `explanations` của các kết
  quả trong câu, bỏ trùng theo `text`), rồi các thẻ `QueryResult` với tab `Bảng` (tiêu đề cột = `fields[].label` + đơn
  vị), `Biểu đồ` (cùng bộ chọn và trình sửa), `SQL` (SQL, tham số công cụ, `notes` dưới tiêu đề "Ghi chú kỹ thuật").
  `RewriteNote` ("Hiểu câu hỏi là: …") chuyển vào đầu khối này. Kết quả 1 dòng × 1–4 số hiện thẻ số (`kpi`).
- **Hỏi lại**: giữ vị trí và hành vi hiện tại (dưới câu trả lời).
- **Lượt cũ** (trước thay đổi): backend đã gán `result_id`, `fields` suy ra, `chart_types`, `display = "none"` (mục
  4.8) → bảng như cũ, không tự có vùng biểu đồ, tab "Biểu đồ" và lưu lựa chọn vẫn dùng được; không có `explanations`
  → khối "Cách tính" ẩn.

## 6. Phần E: chia việc

Ba người làm song song theo **giai đoạn**. File chung không tránh được thì làm **theo thứ tự ghi rõ**; người sau đọc
lại file ngay trước khi sửa. Mọi người: không docstring, dòng ≤ 120 ký tự, import tương đối trong module, tuyệt đối
qua module/`common`/`core`/`agent_package`; `agent_package` không import `backend.modules`; handbook tiếng Việt có
dấu cập nhật cùng thay đổi; chạy `PYTHONIOENCODING=utf-8 uv run python -m unittest discover -s tests` và `uvx ruff
check` trên file đã sửa; FE chạy `npm run typecheck`, `npm run lint`, `npx next build`.

### 6.1 Bảng sở hữu file

| File | BE1 | BE2 | FE | Thứ tự |
| --- | --- | --- | --- | --- |
| `backend/common/charts/*` (mới) | ✔ | | | |
| `backend/agent_package/prompts/prompt_text2sql_agent.py` | ✔ | | | |
| `backend/agent_package/prompts/prompt_synthesize.py` | | ✔ (2) | | Giai đoạn 2 của BE2 (PB-1) |
| `backend/agent_package/tool_agent.py` | | ✔ | | |
| `backend/agent_package/get_chat_text.py` (mới) | | ✔ | | |
| `backend/agent_package/get_chat_completion.py` | | ✔ (2) | | Giai đoạn 2 của BE2 (PB-1) |
| `backend/core/setting.py`, `.env.example` (`TEXT2SQL_CHART_TYPES_ENABLED`) | ✔ | | | |
| `tests/fixtures/chart_cases.json`, `tests/fixtures/format_cases.json` (mới) | ✔ (1) | | ✔ (2) | BE1 tạo ở giai đoạn 1; FE chỉ **thêm** ca sau khi BE1 báo xong giai đoạn 1, và chạy lại test Python trước khi thêm |
| `text2sql/services/display_format.py`, `explanations.py` (mới) | ✔ | | | |
| `text2sql/services/agent_catalog.py`, `sql_builder.py`, `agent_tools.py` | ✔ | | | |
| `text2sql/schemas/schema_text2sql.py` (+ `schemas/__init__.py`) | ✔ | | | |
| `text2sql/routes/router_chart.py` (mới), `routes/__init__.py` | ✔ | | | |
| `text2sql/utils/exceptions.py` | ✔ | | | |
| `text2sql/services/answer_stream.py` (mới), `chat_graph.py`, `chat_events.py` | | ✔ | | |
| `text2sql/services/chat_service.py` | ✔ (1) | ✔ (2) | | BE1 trước: `stored_steps`, `stored_results`; BE2 sau: `text_completion`, `_synthesize`, `streaming` |
| `text2sql/services/text2sql_agent_service.py` | ✔ (1) | ✔ (2) | | BE1 trước: `Text2SqlToolkit(position=…)`, `today_label`, `dates_context`, `prior_context` định dạng; BE2 sau: `DeltaBuffer`, `on_tool_start`, `tool_subject` |
| `backend/modules/conversation/**` (model, schema, service, router, exceptions) | ✔ | | | |
| `backend/migrations/versions/init_conversation_module/<rev>_add_turn_views.py` (mới) | ✔ | | | |
| `scripts/text2sql_eval/run_eval.py` | ✔ | | | |
| `tests/test_chart_spec.py`, `test_text2sql_display.py`, `test_text2sql_explanations.py`, `test_text2sql_chart_api.py`, `test_conversation_views.py` (mới) | ✔ | | | |
| `tests/test_text2sql_stream.py` (mới) | | ✔ | | |
| `tests/test_text2sql_agent.py`, `tests/test_text2sql_chat.py` | ✔ (1) | ✔ (2) | | BE1 trước (trường mới của bước, `stored_*`, toolkit, chạy tiếp từ snapshot cũ), BE2 sau (`ScriptedModel.stream`, bỏ import `synthesize_parser`, bỏ `synthesize` khỏi `FakeCompletion`, thêm `FakeText`) |
| `tests/test_conversation_api.py`, `tests/test_conversation_service.py` | ✔ | | | `TurnOut.views`, `normalize_results` đổi hình dạng response (PB-20) |
| `docs/handbook/modules/text2sql/README.md`, `docs/handbook/modules/text2sql/du-lieu.md` | ✔ (1) | ✔ (2) | | BE1: `display_format.py`, `explanations.py`, `router_chart.py`, `backend/common/charts`; BE2 sau: `answer_stream.py`, `get_chat_text.py` (PB-20) |
| `docs/reports/README.md` (dòng cho tài liệu thiết kế này) | ✔ | | | BE1 thêm ở giai đoạn 1 (PB-20) |
| `docs/handbook/modules/text2sql/api-chat.md` | ✔ (1) | ✔ (2) | | BE1: `fields`, `explanations`, `result_id`, `chart*`, công cụ `make_chart`, mục biểu đồ, endpoint chart; BE2: bảng event SSE, thứ tự, cờ stream, synthesize Markdown, hủy LLM khi Dừng |
| `docs/handbook/modules/agent_package.md` | ✔ (1) | ✔ (2) | | BE1: mục prompt agent; BE2: `run_tool_agent(on_text, on_tool_start)`, `get_chat_text`, prompt synthesize |
| `docs/handbook/modules/text2sql/bieu-do.md` (mới: danh mục, spec, validator, ma trận) | ✔ | | | |
| `docs/handbook/modules/conversation/*.md`, `du-lieu-va-migration.md`, `text2sql/danh-gia-chay-that.md` | ✔ | | | |
| `frontend/**` (gồm `app/globals.css`, `package.json` script `test:charts`), `docs/handbook/frontend/README.md` | | | ✔ | |

`chat_stream.py`, `router_chat.py`: không ai sửa.

### 6.2 BE1: văn phong, biểu đồ, lưu lựa chọn

Giai đoạn 1 (file riêng, làm ngay):

1. `backend/common/charts/` theo mục 4.3–4.5 (gồm `prepare.chart_stats`, `infer_fields`, V21–V34, quy tắc null,
   `rows_complete`, `enabled`); `tests/fixtures/chart_cases.json`, `format_cases.json`; setting
   `TEXT2SQL_CHART_TYPES_ENABLED`.
2. `display_format.py`, `explanations.py` (mục 2.3, 2.4); `agent_catalog.py` (`unit`, `format`); `sql_builder.py`
   (`RuleUse`, `assumption`, `chart` trong `QueryMetricArgs`); `agent_tools.py` (`position: int = 1`, `result_id`,
   tên cột duy nhất, `fields`, `explanations`, output LLM định dạng, `chart`/`chart_types`/`chart_error`/`display`,
   `RunSqlArgs.labels/assumption/chart/rules_applied`, công cụ `make_chart`); `schema_text2sql.py` (`FieldOut`,
   `ExplanationOut`, các trường mới của `AgentStepOut`, **đều có mặc định**: `result_id`, `fields`, `explanations`,
   `chart: dict | None`, `chart_source`, `chart_types`, `display`).
3. Prompt agent (mục 2.1).
4. `router_chart.py`, `Text2SqlChartInvalid`.
5. Module `conversation`: migration, model, schema, service, router, exceptions (mục 4.8).
6. `run_eval.py`: regex số hiểu `1.234,5` (xét `-?\d{1,3}(?:\.\d{3})+(?:,\d+)?` trước dạng thường; bỏ dấu chấm
   ngăn hàng nghìn trước khi đổi `,` thành `.`); `clarify_or_assume` đọc thêm `explanations` kind `assumption`; không
   ghi `answer_delta` vào `events` (chỉ ghi `first_delta_t` và số delta); chỉ số phụ văn phong (không làm trượt câu):
   có `_`, `` ` ``, `/2026` cùng năm, "2.026", "bản ghi", "metric", "tôi" có mặt; chỉ số nghiệm thu mục 7 (số bước
   `make_chart` mỗi câu, TTFT chữ, tổng thời gian, so với `a2-final-x2.json`) in ở bảng tổng kết (PB-18).
7. `docs/reports/README.md`: thêm dòng cho tài liệu này (PB-20).

Giai đoạn 2 (file chung, **làm trước BE2**, báo xong cho BE2): `chat_service.py` (`stored_steps` thêm
`explanations`, `result_id`, `chart`, `chart_source`; `stored_results` thêm `result_id`, `fields`, `chart`,
`chart_source`, `chart_types`, `display`), `text2sql_agent_service.py` (mục 2.3, truyền `position`), sửa
`tests/test_text2sql_agent.py`, `tests/test_text2sql_chat.py` cho trường mới, phần BE1 của `api-chat.md`,
`agent_package.md`, `text2sql/README.md`, `text2sql/du-lieu.md`. Cuối mỗi giai đoạn cả bộ test phải xanh.

Test của BE1:

- `test_text2sql_display.py`: `vi_number` (1234,5 → "1.234,5"; 77,56 → "77,6"; 41250000 → "41.250.000"; -0,04 → "0";
  -1,25 → "-1,3"; 0,035 (3 chữ số) → "0,035"); `parse_d3_format` (`",.1f"`, `".1%"`, `",d"`, `"SMART_NUMBER"`, `None`,
  chuỗi lạ); `date_display` (cùng năm bỏ năm, kèm thứ, khác năm); `period_label` (1 ngày, 13–19/11, 28/10–3/11, cả
  tháng, khác năm); `dates_context` nhãn đủ 6 khoảng với today 2026-11-20; `llm_rows` không đổi văn bản; `result_fields`
  cho `query_metric` (nhãn metric, đơn vị từ cột của biểu thức, `currency`, `additive` SUM/AVG) và `run_sql` (`labels`,
  khớp catalog, `humanize`). Thêm (PB-3, 4, 5, 16): năm 2026 trong `group_by` → "2026"; mã 70000 và cột `id` →
  "70000"; `EXTRACT(YEAR ...)` của `run_sql` → `plain`; `time_grain` month → "tháng 11", week → "tuần 16–22/11",
  quarter → "quý 4", year → "2026", khác năm có năm; cột `datetime` toàn 00:00 → `date`, không ra "00:00"; `vi_number`
  77,55 → "77,55", 21,0285 → "21,03", `Decimal(repr)`; NaN/Infinity → null, `vi_number` không hữu hạn → `ValueError`;
  `time`, UUID, `"<binary>"` → `text`; cột lẫn kiểu (giá trị đầu là số, sau là chữ) → `text`; tên cột trùng →
  `name_2`, `?column?` → `cot_<i>`; `pii` từ catalog; chạy hết `tests/fixtures/format_cases.json`.
- `test_text2sql_explanations.py`: kỳ từ cặp `>=`/`<`; lọc khác với nhãn và đơn vị; `RuleUse` applied/yielded/skipped
  (built_in không hiện); `value_match`; `data_range`; `scope`; `assumption`; `method` của `run_sql`; `truncated`;
  `warning`; bước tra cứu, `get_column_values` và bước lỗi không có mục; `period` có `start`/`end` ISO và `text` dùng
  `today` của lượt; `run_sql`: `source` từ bảng, `period`/`filter` từ `WHERE` đơn giản, vế phức tạp bị bỏ qua, SQL
  lỗi phân tích không ném; `rules_applied` tên có → `rule`, tên lạ → `notes`; cột PII không ghi giá trị.
- `test_chart_spec.py`: mỗi quy tắc V1–V34 có ít nhất một ca và kiểm đúng chuỗi thông báo; quy tắc null (trục T
  null bị bỏ, phân loại null thành "(Trống)", NaN là null, V8 đếm sau khi bỏ); `rows_complete=False` hạ các quy tắc
  phụ thuộc dòng thành cảnh báo; `enabled`; chạy hết `tests/fixtures/chart_cases.json` (cả `chart_stats`);
  `infer_fields`; `axes.y2` có câu riêng; gom
  nhiều lỗi; chuẩn hóa `aggregate auto`; cảnh báo; ma trận mục 4.5 cho từng hình dạng (danh sách loại mong đợi) và mọi
  spec mặc định qua validator; spec hợp lệ tối thiểu cho **cả 32 loại**; màu đi theo `assign` không nhận hex.
- `test_text2sql_agent.py` (phần BE1): bước dữ liệu có `result_id` tăng dần, `fields`, `explanations`, `chart`
  (`auto`), `chart_types`; output LLM có `rows` định dạng; `chart` kèm lời gọi hợp lệ → `agent`, sai → `chart_error`,
  bước vẫn thành công; `make_chart` hợp lệ ghi bước và cập nhật bước dữ liệu; `make_chart` sai → `ToolError` có thông
  báo V*; `result_id` lạ; gọi lại y nguyên bị chặn; chạy tiếp giữ bộ đếm `result_id`; `display` đúng ba giá trị và
  `make_chart` đổi thành `"chart"`; `chart_types` chỉ gồm loại bật; `Text2SqlToolkit()` không truyền `position` vẫn
  chạy.
- `test_text2sql_chat.py` (phần BE1): `stored_results`, `stored_steps` có khóa mới; `/chat` JSON có trường mới;
  **chạy tiếp từ snapshot cũ** (PB-2): dựng state hỏi lại có `AgentStepOut` không có trường mới (dict thiếu khóa, đi
  qua `JsonPlusSerializer` dumps/loads), resume → trả lời được, bước dữ liệu mới có `result_id` đếm tiếp đúng (ví dụ
  bước cũ thành công một lần → bước mới `"1-2"`).
- `test_text2sql_chart_api.py`: `GET /chart-types` đủ 32 loại, có `options_schema`; `POST /charts/validate` 200/400.
- `test_conversation_views.py`: PUT hợp lệ → 200 và `TurnOut.views`; spec sai → 400 `conversation_chart_invalid`;
  `result_id` không có → 404; người dùng khác → 404; DELETE → 204, `views` không còn khóa; lượt cũ không có `results`;
  lượt cũ có `results` thiếu `result_id`/`fields` → GET trả `result_id` dự phòng, `fields` suy ra, `display="none"`,
  PUT theo id dự phòng → 200; `stored_truncated` → spec vi phạm V8/V9 vẫn 200 kèm cảnh báo; hai PUT liên tiếp cho
  hai `result_id` khác nhau → cả hai còn trong `views`; `put_view` gọi `repository.conversation(..., lock=True)`
  (PB-8c; SQLite của test không kiểm được khóa thật, nên kiểm lời gọi khóa và kiểm merge).
- Migration: upgrade, `alembic check`, downgrade trên DB tạm (nếu có cấu hình DB thử nghiệm).

### 6.3 BE2: stream

Giai đoạn 1 (file riêng, làm ngay, **không đổi hành vi hiện có**): `tool_agent.py`, `get_chat_text.py` (file mới,
chưa ai gọi), `answer_stream.py`, `chat_events.py`, `chat_graph.py` (`Synthesize` có tham số thứ ba tùy chọn, chỉ truyền
khi `streaming=True`), `tests/test_text2sql_stream.py`. **Không** đụng `prompt_synthesize.py`,
`get_chat_completion.py` ở giai đoạn này (PB-1). Cuối giai đoạn 1 cả bộ test phải xanh.
Giai đoạn 2 (sau khi BE1 báo xong giai đoạn 2): `prompt_synthesize.py` (toàn văn 2.2, xóa parser),
`get_chat_completion.py` (bỏ task `synthesize`), `chat_service.py`, `text2sql_agent_service.py`, sửa
`tests/test_text2sql_agent.py` (bỏ import `synthesize_parser` dòng 12 và test của parser),
`tests/test_text2sql_chat.py`, phần BE2 của `api-chat.md`, `agent_package.md`, `text2sql/README.md`,
`text2sql/du-lieu.md` — làm **trong cùng một lượt** để không có lúc test đỏ.

Test của BE2:

- `tool_agent`: `ScriptedModel` thêm `stream()` trả `AIMessageChunk`; delta đúng `round`; chữ rồi `tool_call_chunks`
  trong cùng vòng → `end(discard=True)`; không `on_text` → không gọi `stream`; vòng hết lượt stream được; `on_tool_start`
  trước `on_tool`, không gọi cho `ask_user`; chạy tiếp tiếp tục số `round`. Thêm (PB-17): `tool_call_chunks` đến
  **trước** chữ trong cùng vòng → không đẩy chữ nào, vòng gọi công cụ bình thường; message chỉ có
  `invalid_tool_calls` → kết quả giống hệt nhánh `invoke` với cùng message (kết thúc, chữ giữ, không `answer_reset`).
- `DeltaBuffer`: gom theo 32 ký tự và 50 ms (đồng hồ giả), đổi `round` xả trước, `end` xả rồi mới `answer_reset`.
- `get_chat_text`: `invoke` khi không có `on_text`, stream khi có; `strip`; `OpenAIError` lan ra.
- `chat_graph`: `streaming=False` → không có `question_started`/delta trong custom stream, synthesize nhận `None`;
  `streaming=True` câu tách → `synthesize_started` trước delta `position=null` rồi `answer`.
- `AgentRun.answer`: `final=true` câu đơn, `false` câu tách; `emit=None` không dựng callback; `tool_subject` cho từng
  công cụ, lỗi catalog trả tham số thô.
- Route SSE (`ChatStreamRouteTests`): `tool_started` trước `tool` cùng `position`; nối delta `final` bằng bản chính
  thức sau `strip`; `question_answered` sau delta; hai nhánh song song mỗi `position` đúng thứ tự; `answer_reset` khi
  vòng có chữ rồi gọi công cụ; Dừng giữa delta → `client_disconnected`, lượt `error`; chạy tiếp sau hỏi lại có delta.
  **Dừng trong lúc synthesize đang stream** (PB-17): `Text2SqlClientDisconnected` lan qua `get_chat_text` và
  `ChatService._synthesize` (không bị đổi thành `Text2SqlAgentUnavailable`), lượt lưu `error/client_disconnected`,
  `answer = None`.
- `chat_graph` giai đoạn 1: `Synthesize` cũ hai tham số vẫn chạy khi `streaming=False`.
- Route JSON `/chat`: không phát event, câu trả lời của câu đơn không đổi, câu tách gọi `text_completion` không
  `on_text`; `OpenAIError` → 503.
- Sau khi xong: chạy lại `scripts/text2sql_eval/run_eval.py` nhóm `split`, `dependent` (và cả bộ) bằng cổng riêng, so
  với `a2-final-x2.json`; ghi TTFT chữ trước/sau vào báo cáo kết quả chạy thật và đối chiếu ngưỡng nghiệm thu mục 7.

### 6.4 FE: toàn bộ frontend

File (đều thuộc FE): `features/text2sql/types.ts`, `use-chat.ts`, `api.ts`, `chat-turn.tsx`, `query-result.tsx`,
`labels.ts`, `answer-markdown.tsx`; mới: `narration.ts`, `answer-details.tsx` (Số liệu và cách tính),
`sub-answers.tsx`, `chart-area.tsx`, `charts/spec.ts` (kiểu TS khớp mục 4.3), `charts/catalog.ts` (`useChartTypes`
SWR), `charts/data.ts`, `charts/format.ts`, `charts/palette.ts`, `charts/chart-view.tsx` (điều phối theo `type`),
`charts/renderers/{cartesian,polar,hierarchy,flow,grid,figures,sparkline-table}.tsx`, `charts/chart-switcher.tsx`,
`charts/chart-editor.tsx`; `app/globals.css` (token mục 4.1); `docs/handbook/frontend/README.md` (bỏ câu "hướng dự kiến
là dùng chart có sẵn của Superset", mô tả bố cục mục 5 và biểu đồ).

Việc chính:

1. `types.ts`: `ToolStartedEvent`, `AnswerDeltaEvent`, `AnswerResetEvent`, `synthesize_started`; `ToolStep` thêm
   `result_id`, `fields` (gồm `format_hint`, `time_unit`, `pii`), `explanations` (gồm `field`, `start`, `end`,
   `values`), `chart`, `chart_source`, `chart_types`, `display`; `StoredResult` thêm các khóa đó (đều tùy chọn);
   `StoredTurn.views`.
2. `use-chat.ts`: `QuestionState` thêm `draft`, `draftRound`; `Turn` thêm `narration`, `views`; xử lý event mục 3;
   ghi đè bản nháp bằng bản chính thức; gom delta theo `requestAnimationFrame`; `storedQuestions` ghép kết quả theo
   `result_id` (backend đã gán cho cả lượt cũ, mục 4.8); mục kind `column_values` không có `result_id` → không ghép,
   không vẽ, không lỗi (PB-19); chép `fields`, `chart*`, `display`; áp bước `make_chart` (cập nhật `chart`,
   `chart_source`, `display`); `setView`/`resetView` lạc quan, lưu tuần tự theo kết quả.
3. `api.ts`: `fetchChartTypes`, `validateChart`, `saveChartView`, `deleteChartView`.
4. Giao diện mục 5; `QueryResult` dùng nhãn, đơn vị, tab `Biểu đồ`, ghi chú kỹ thuật dưới tab SQL.
5. Biểu đồ mục 4.9, 32 renderer. Thứ tự làm đề xuất: (a) `table`, `kpi`, `bar`, `bar_horizontal`, `line`, `area`,
   `bar_grouped`, `bar_stacked`, `bar_stacked_100`, `donut`, `pie`, `scatter` (đủ cho mọi hình dạng đã thấy ở báo cáo
   chạy thật); (b) phần còn lại. Bộ chọn chỉ hiện loại đã có renderer (danh sách `RENDERERS` trong `chart-view.tsx`);
   loại agent chọn mà chưa có renderer → vẽ theo đề xuất hoặc `table` kèm dòng "Chưa hỗ trợ dạng «X»" (mục 4.9,
   PB-13). Khi đợt (a) xong mà (b) chưa xong, báo người điều phối đặt `TEXT2SQL_CHART_TYPES_ENABLED` bằng danh sách
   đợt (a).
6. **Test tự động phần biến đổi dữ liệu** (PB-7): `charts/data.ts` và `charts/format.ts` là hàm thuần (Node 24 bỏ
   kiểu TS khi chạy; không dùng `enum`, `namespace`, tham số thuộc tính, alias `@/`); kiểu lấy bằng `import type`,
   import chạy được giữa hai file viết có đuôi (`./format.ts`). Test mới `features/text2sql/charts/data.test.ts`,
   `format.test.ts` dùng `node:test` + `node:assert/strict`, đọc `tests/fixtures/chart_cases.json` và
   `format_cases.json` ở gốc repo (đường dẫn tính từ `import.meta.dirname`), so `buildChartData(...).stats` và chuỗi
   định dạng với `expect`. Cần thêm `frontend/features/text2sql/charts/package.json` chỉ có `{"type": "module"}` (đã
   thử trên Node v24.19.0: thiếu file này thì `node --test` nạp `.ts` như CommonJS và lỗi), và
   `"allowImportingTsExtensions": true` trong `tsconfig.json` (hợp lệ vì đã `noEmit`). Script `package.json`:
   `"test:charts": "node --test \"features/text2sql/charts/*.test.ts\""`. Không thêm thư viện. Sau khi thêm hai
   thay đổi cấu hình phải chạy lại
   `npx next build` để chắc bundler không bị ảnh hưởng; nếu bị, chuyển `data.ts`/`format.ts` sang thư mục
   `features/text2sql/charts/core/` có `package.json` riêng.

Kiểm của FE: `npm run typecheck`, `npm run lint`, `npm run test:charts`, `npx next build`; chạy app trên cổng riêng
(không dùng, không dừng
cổng 3000) với backend thật ở cổng riêng, kiểm bằng Playwright: câu đơn (chữ stream, lời kể), câu tách (bản nháp trong
"Trả lời từng phần", synthesize stream), hỏi lại rồi chạy tiếp, Dừng giữa chừng, mở lại lịch sử (biểu đồ và lựa chọn
còn), đổi loại và sửa biểu đồ rồi tải lại trang, sáng/tối, độ rộng 400 px. Để soát 32 renderer, dùng một trang tạm
ngoài repo hoặc dữ liệu mẫu trong scratchpad, **không** commit trang thử. Dừng mọi server đã mở khi xong.

## 7. Rủi ro và việc còn mở

- **Prompt dài thêm** (mục biểu đồ, mô tả `make_chart`): khoảng 900–1.200 token mỗi vòng; bộ đệm prompt của nhà cung
  cấp giảm chi phí. Cần đo lại độ trễ trong lần chạy thật sau triển khai.
- **Agent đổi chart quá thường xuyên** (thêm vòng): mỗi `make_chart` tốn một vòng LLM và một trong
  `TEXT2SQL_AGENT_MAX_STEPS=12` lượt. Prompt cấm gọi `make_chart` để lặp lại đề xuất. **Tiêu chí nghiệm thu** (PB-18),
  đo bằng `run_eval` trên cả bộ 49 kịch bản, so với `a2-final-x2.json`: câu đơn có ≥ 1 bước `make_chart` **≤ 10%**;
  độ trễ tổng trung vị tăng **≤ 5%**; TTFT chữ (thời điểm `answer_delta` `final=true` đầu tiên) trung vị **giảm** so với
  thời điểm `answer` của bản cũ; tỷ lệ câu đúng không giảm. Không đạt thì siết prompt (bỏ đường `make_chart` sau kết
  quả, chỉ giữ `chart` kèm lời gọi) và chạy lại trước khi coi là xong.
- **Tên có dấu do mô hình tự thêm** có thể sai với tên lạ; về lâu dài cần nhãn giá trị trong data dictionary (ngoài
  phạm vi). Tiền tố "TP." bị cấm vì làm hỏng khớp giá trị ở lượt hỏi tiếp.
- **Ngày trong `rows` gửi LLM đã đổi sang dạng hiển thị**: agent phải viết lại `YYYY-MM-DD` khi lọc ở lời gọi sau
  (prompt đã dặn). Theo dõi lỗi lọc ngày trong lần chạy thật; nếu tăng, gửi thêm cột ISO cho cột ngày.
- **Bộ chấm số**: phải sửa regex trước khi so kết quả mới (mục 6.2), nếu không "41.250.000" bị đọc thành 41,25.
- **Đổi model** có thể stream lời dẫn rồi gọi công cụ, gây chữ hiện rồi biến mất; `answer_reset` xử lý đúng, lời kể
  "Đang tra thêm dữ liệu…" che bớt.
- **Lượt cũ** không có `fields`/`chart`: FE vẫn hiện bảng; không có vùng biểu đồ.
- **Tô vân cho người mù màu hoàn toàn và in ấn** chưa làm (bảng song song là phương án thay thế bắt buộc).
- Báo cáo [biểu đồ và Superset](2026-11-20-nghien-cuu-tich-hop-chart-superset.md) giai đoạn 2, 3 (permalink, lưu
  chart Superset) **không làm** theo quyết định 4.
- Dòng cho tài liệu này trong `docs/reports/README.md`: BE1 thêm ở giai đoạn 1 (mục 6.1).
- `rules_applied` của `run_sql` là lời khai của agent; code không kiểm SQL có thật áp quy tắc (ngoài phạm vi bản này).
- Khi Dừng, phần chữ đã stream không được lưu (`answer = None`); tải lại lịch sử sẽ mất phần đó (chấp nhận, đã ghi
  vào `api-chat.md`).

## 8. Phản biện và điều chỉnh

Phản biện kết luận **đạt có điều kiện** và nêu 20 điểm. Mọi điểm đã được xử lý trong thân bài; chỗ sửa ghi `(PB-n)`.

| PB | Mức | Điểm phản biện | Đã sửa ở | Cách xử lý |
| --- | --- | --- | --- | --- |
| 1 | Chặn | Giai đoạn 1 của BE2 xóa `synthesize_parser`/task `synthesize` làm test đỏ | 2.2, 3.2, 6.1, 6.3 | Dời `prompt_synthesize.py`, `get_chat_completion.py` sang giai đoạn 2 cùng `chat_service.py` và `test_text2sql_agent.py`; `Synthesize` thành `Protocol` có `on_text` tùy chọn, chỉ truyền khi `streaming=True` |
| 2 | Chặn | `Text2SqlToolkit(position)` không mặc định; trường mới của `AgentStepOut` phải có mặc định; test chạy tiếp từ snapshot cũ | 2.3, 4.6, 6.2 | `position: int = 1`; mọi trường mới có mặc định; đếm `result_id` theo tool/error chứ không theo trường `result_id`; thêm test snapshot cũ |
| 3 | Chặn | Năm, mã, id bị thành "2.026" | 2.3, 4.3, 6.2 | `FieldOut.format_hint = "plain"` + `role = dimension` theo khóa nhóm, `GROUP BY`, từ khóa tên, `EXTRACT`; `vi_number(grouped=False)`; test 2026, 70000, id |
| 4 | Chặn | Ô `time_grain` hiện kèm thứ; `DATE_TRUNC` trên timestamp ra "00:00" | 2.3, 4.3, 4.9, 6.2 | `FieldOut.time_unit`, `bucket_display` (tháng, tuần, quý, năm); `datetime` toàn 00:00 → `date`; `Dimension.time_unit` mặc định theo field |
| 5 | Cao | NaN/Infinity, `time`, UUID, binary, cột lẫn kiểu | 2.3, 4.4, 6.2 | Kiểu xét mọi giá trị khác NULL; chuỗi không hữu hạn là null ở mọi nơi; `time`/UUID/binary → `text`; `vi_number` không nhận số không hữu hạn |
| 6 | Cao | Validator thiếu 14 nhóm quy tắc (a–n) | 2.3 (a), 4.4 | (a) đổi tên cột trùng ở `fields`/`columns`; (b) định nghĩa null chung; (c)–(n) thành V21–V32; PII thành V33 |
| 7 | Cao | Python và TS tính filter/top_n khác nhau; FE không có test | 4.3, 4.4, 6.4 | `prepare.chart_stats`; `tests/fixtures/chart_cases.json`, `format_cases.json` chạy ở cả `unittest` và `node --test` (đã thử trên Node v24.19.0: cần `package.json` `{"type": "module"}` trong thư mục `charts` và `allowImportingTsExtensions`) |
| 8 | Cao | Lượt cũ không lưu lựa chọn được; kiểm trên dòng bị cắt; PUT không khóa | 4.8, 5, 6.2 | Chốt **backend tự suy** (`normalize_results`, `infer_fields`, id dự phòng `<position>-<k>`); `rows_complete=False` hạ quy tắc phụ thuộc dòng thành cảnh báo; `get_owned(lock=True)`; FE lưu tuần tự |
| 9 | Cao | Prompt nói mọi kết quả ≥ 3 điểm có biểu đồ, FE chỉ đưa kết quả cuối | 2.1, 2.3, 4.9 | Trường `display` (`chart`, `chart_if_last`, `none`) do code tính, cùng quy tắc với FE; sửa mục BIỂU ĐỒ và quy tắc 8 của prompt |
| 10 | Trung bình | "Cách tính" của `run_sql` gần như rỗng | 2.4 | `source` từ bảng (sqlglot), `period`/`filter` từ `WHERE` đơn giản, tham số `rules_applied` |
| 11 | Trung bình | `ExplanationOut` không có năm, không có cấu trúc | 2.4, 4.9 | Thêm `field`, `start`, `end`, `values`; FE dựng lại theo ngày xem; `period_label` dùng `today` của lượt |
| 12 | Trung bình | Quy tắc 7 cho hai mệnh đề; quy tắc 9 nhắc vị trí bảng | 2.1, 2.4 | Tối đa một mệnh đề, ưu tiên giả định; định nghĩa vào "Cách tính"; "Tôi mới lấy N dòng đầu." |
| 13 | Trung bình | Agent chọn loại FE chưa vẽ được | 4.4 (V34), 4.6, 4.9, 6.4 | Làm **cả hai**: setting `TEXT2SQL_CHART_TYPES_ENABLED` lọc `chart_types` và validator; FE vẽ đề xuất hoặc `table` kèm "Chưa hỗ trợ dạng «X»" |
| 14 | Trung bình | Waterfall đổi dấu vẽ sai; lollipop/dumbbell ngang | 4.2 | Waterfall: `Bar` dạng khoảng `[start, end]`. Lollipop/dumbbell: không dùng `Scatter`, dùng `Bar` có `shape` tự vẽ nên hai hướng đặt trục như `bar`/`bar_horizontal` |
| 15 | Trung bình | Bỏ qua `contains_pii` | 2.3, 2.4, 4.4 (V33) | `FieldOut.pii`; validator cấm giá trị PII trong spec; "Cách tính" chỉ ghi nhãn cột |
| 16 | Trung bình | `Decimal(float)` làm tròn sai; một chữ số lẻ mặc định mất độ chính xác | 2.3, 6.2 | `Decimal(repr(value))`; không có format thì tối đa 2 chữ số lẻ (abs < 1: 3 chữ số có nghĩa); test 77,55 |
| 17 | Thấp | Test `_stream_round` (tool chunk trước chữ, `invalid_tool_calls`), Dừng khi synthesize stream; `answer=None` khi Dừng | 3.2, 3.3, 6.3 | Thêm test và mô tả; `discard` dùng cùng điều kiện với `_route`; ghi vào `api-chat.md` |
| 18 | Thấp | Ngưỡng "> 20%" không hợp với quyết định 1 | 6.2, 7 | Tiêu chí nghiệm thu: `make_chart` ≤ 10% câu, trễ trung vị tăng ≤ 5%, TTFT giảm, tỷ lệ đúng không giảm |
| 19 | Thấp | Mục `column_values` không có `result_id` | 2.4, 4.8, 6.4 | Ghi rõ: không ghép, không vẽ, không gán id dự phòng |
| 20 | Thấp | Thiếu người phụ trách vài file | 6.1, 6.2, 6.3 | `text2sql/README.md`, `du-lieu.md` (BE1 rồi BE2), `docs/reports/README.md` (BE1), `test_conversation_api.py`, `test_conversation_service.py` (BE1), fixtures (BE1 tạo, FE thêm ca) |

Điểm **không theo hoặc theo một phần**, kèm lý do:

- PB-8a: phản biện cho chọn "backend suy" hoặc "FE ẩn bộ chọn". Chọn backend suy vì lượt cũ là phần lớn lịch sử hiện
  có; ẩn bộ chọn làm tính năng lưu lựa chọn vô dụng với chúng. Nhưng **không** tự hiện vùng biểu đồ cho lượt cũ
  (`display = "none"`), để mở lại hội thoại cũ không đổi giao diện bất ngờ.
- PB-6a: không báo lỗi FieldRef mơ hồ mà **đổi tên** cột trùng ngay ở `fields`, vì lỗi đó agent khó sửa (phải viết lại
  SQL) còn đổi tên thì không mất gì; agent được báo qua `notes`.
- PB-10: không kiểm SQL của `run_sql` có thật áp quy tắc trong `rules_applied` (cần hiểu ngữ nghĩa điều kiện, dễ sai);
  ghi là ngoài phạm vi. Vế `WHERE` phức tạp bị bỏ qua thay vì đoán.
- PB-15: phản biện chỉ yêu cầu cấm PII trong spec lưu ở `views`; bản này cấm ở **mọi** nơi validator chạy (kèm lời gọi,
  `make_chart`, `views`) cho một quy tắc duy nhất, vì spec của agent cũng được lưu trong `steps`.
- PB-17: không lưu bản nháp khi Dừng (giữ phạm vi; chỉ ghi rõ hành vi).
- PB-8c: test dùng SQLite nên không kiểm được khóa hàng thật; kiểm lời gọi `lock=True` và việc gộp `views`.
