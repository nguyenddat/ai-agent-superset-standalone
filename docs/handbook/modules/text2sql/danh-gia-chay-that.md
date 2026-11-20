# Text2SQL: chạy đánh giá trên database nguồn và LLM thật

**Trạng thái:** đã triển khai (công cụ dành cho người phát triển, không thuộc API và không chạy trong bộ unit test).

Bộ đánh giá gồm hai script trong `scripts/text2sql_eval/`:

- `serve.py`: chạy backend (`backend.main:app`, uvicorn) từ máy host, đổi địa chỉ database trong tiến trình để không phải sửa `.env` hay dữ liệu đã lưu, và tùy chọn ghi message của từng lượt agent ra file JSONL.
- `run_eval.py`: gửi bộ câu hỏi qua HTTP tới route [`POST /api/v1/text2sql/chat/stream`](api-chat.md#stream-post-apiv1text2sqlchatstream) (mặc định) hoặc `POST /api/v1/text2sql/chat`, đọc từng event SSE, chạy tiếp các lượt hỏi lại bằng `resume_id`, kiểm tra lượt đã lưu qua [API hội thoại](../conversation/api-luot-hoi-dap.md) và chấm bằng truy vấn gold chỉ đọc trên database nguồn.

`local_env.py` chứa phần đổi địa chỉ dùng chung cho hai script.

## Chạy

Từ gốc repository, khi Docker Compose đã chạy `postgres`, `qdrant` và database nguồn. Bước 1, chạy backend ở một cổng trống:

```bash
PYTHONIOENCODING=utf-8 uv run python scripts/text2sql_eval/serve.py --port 18100 \
  --app-db 127.0.0.1:15432 \
  --source-host-map warehouse-db=127.0.0.1:15433 \
  --trace-file scripts/text2sql_eval/results/trace.jsonl
```

Bước 2, chạy bộ câu hỏi:

```bash
PYTHONIOENCODING=utf-8 uv run python scripts/text2sql_eval/run_eval.py \
  --connection-id <uuid connection> --base-url http://127.0.0.1:18100 \
  --app-db 127.0.0.1:15432 \
  --source-host-map warehouse-db=127.0.0.1:15433 \
  --trace-file scripts/text2sql_eval/results/trace.jsonl \
  --workers 4 --repeat 2
```

`serve.py` nạp code của working tree, nên dùng nó thay cho container `backend` khi cần đánh giá code chưa build vào image. Sửa code thì khởi động lại `serve.py`.

| Tham số `serve.py` | Ý nghĩa |
| --- | --- |
| `--host`, `--port` | Địa chỉ lắng nghe, mặc định `127.0.0.1:18100`. |
| `--app-db` | `host:port` thay cho phần host trong `DATABASE_URL` khi `.env` dùng tên service Compose hoặc cổng nội bộ. Chỉ đổi trong tiến trình. |
| `--source-host-map` | `host=host:port`, đổi host của URI database nguồn sau khi giải mã (bọc `source_url` trong `text2sql_agent_service`). Không sửa dữ liệu đã lưu, không in URI. |
| `--trace-file` | Ghi mỗi lượt `run_tool_agent` thành một dòng JSONL: `question`, thời gian, `resumed`, `exhausted`, `paused`, message của model (tool call, số token, kết quả tool đã rút gọn). |

| Tham số `run_eval.py` | Ý nghĩa |
| --- | --- |
| `--connection-id` | Connection cần đánh giá (bảng `database_connections`). |
| `--base-url` | Backend đang chạy, mặc định `http://127.0.0.1:18100`. |
| `--endpoint` | `stream` (mặc định, route SSE) hoặc `json` (route `/chat`). |
| `--questions` | File câu hỏi, mặc định `scripts/text2sql_eval/questions.json`. |
| `--only` | Chỉ chạy các id hoặc loại liệt kê, cách nhau bằng dấu phẩy (ví dụ `T6-2,conversation`). |
| `--workers` | Số câu chạy song song. |
| `--repeat` | Chạy mỗi câu N lần để đo độ ổn định; id có hậu tố `#n`. |
| `--user-id` | `user_id` gửi kèm, mặc định `text2sql-eval`; chuỗi rỗng thì không ghi hội thoại. |
| `--keep-conversations` | Giữ hội thoại sau khi chấm; mặc định harness xóa hội thoại của từng câu qua `DELETE /api/v1/conversations/{id}`. |
| `--trace-file` | File JSONL mà `serve.py` đang ghi; message của agent được gắn vào kết quả theo nội dung câu đơn. |
| `--app-db`, `--source-host-map` | Như `serve.py`; harness dùng chúng để chạy gold và tạo connection tạm dừng. |
| `--out` | File kết quả; mặc định `scripts/text2sql_eval/results/<thời điểm>.json` (thư mục đã gitignore). |

## Bộ câu hỏi

Mỗi phần tử của `questions.json` có `id`, `type` (loại trong [taxonomy](../../../reports/2026-11-19-taxonomy-cau-hoi-benchmark.md), hoặc `split`, `dependent`, `missing`, `conversation`, `clarification`, `error`), `question` và cách chấm `check`:

| `check` | Đạt khi |
| --- | --- |
| `numbers` | Mọi giá trị số trong kết quả gold có trong câu trả lời (sai số mặc định 0,051 hoặc 0,5%, đổi bằng `tolerance`; số trong câu trả lời đọc theo kiểu Việt Nam: dạng có dấu chấm ngăn nghìn như `41.250.000`, `1.234,5` được xét trước, bỏ dấu chấm rồi đổi `,` thành `.`; `12,5` và `12.5` đều là 12,5); chuỗi trong gold (trừ ngày) có trong câu trả lời sau khi bỏ dấu; giá trị 0 chấp nhận cách nói "không có". |
| `entities`, `first_entity` | Mọi giá trị cột đầu (hoặc chỉ dòng đầu) có trong câu trả lời; gold rỗng thì câu trả lời phải nói là không có. |
| `bool` | Câu đầu của câu trả lời khớp có/không với giá trị gold. |
| `keywords` | Mỗi nhóm từ khóa có ít nhất một từ trong câu trả lời (đã bỏ dấu và dấu `*` của markdown). |
| `clarify`, `clarify_or_assume` | Lượt dừng với `status = needs_clarification`, hoặc câu trả lời có dấu `?`; với `clarify_or_assume` thì nêu rõ giả định (trong lời văn, hoặc một bước có mục `explanations` loại `assumption`), hoặc trả theo từng đối tượng (câu trả lời có ít nhất `breakdown` con số, khi câu hỏi có trường này), cũng đạt. Ghi chú phân biệt "hỏi lại (ask_user)", "hỏi lại bằng văn bản", "nêu giả định", "trả theo từng đối tượng". |

`gold` là danh sách câu SQL; câu hỏi đạt nếu khớp một trong số đó. `{today}` trong gold được thay bằng ngày theo `TEXT2SQL_TIMEZONE` lúc gửi câu hỏi. Cờ phụ `no_query`, `expect_split`, `expect_dependent` chỉ ghi chú.

Các trường cho kịch bản nhiều bước:

| Trường | Ý nghĩa |
| --- | --- |
| `turns` | Danh sách lượt (mỗi lượt có `question`, `check`, `gold`...) gửi lần lượt trong **cùng một hội thoại** (`conversation_id` của lượt trước), để kiểm tra câu nối tiếp dựa vào lịch sử đã lưu. Mọi lượt phải đạt. |
| `replies` | Khi lượt dừng với `needs_clarification`, gửi lần lượt các câu này kèm `resume_id` (và `conversation_id`). Chấm trên lượt cuối. |
| `expect_pause` | Lượt phải dừng hỏi lại bằng `ask_user` ít nhất một lần. |
| `connection` | `unknown` (UUID không tồn tại) hoặc `paused`: harness tạo tạm một connection `is_active = false` với URI giả không chứa mật khẩu, xóa sau khi chạy. |
| `bogus_resume` | Gửi kèm một `resume_id` ngẫu nhiên. |
| `expect_http_status` | Mã HTTP mong đợi (lỗi trước khi stream bắt đầu). |

Với mỗi câu có `user_id`, harness đọc `GET /api/v1/conversations/{id}/turns` và kiểm tra: số lượt lưu bằng số lần gửi, `turn_id`, `status`, `answer` khớp event `done`, lượt dừng có `resume_id` khớp event, lượt chạy tiếp có `continued_from` trỏ về lượt đang chờ. Sai lệch được tính là trượt.

Chấm tự động chỉ kiểm tra con số và thực thể; cần đọc lại câu trả lời để phát hiện giả định không hợp lý hoặc bước thừa.

## Kết quả

File JSON gồm `summary` theo loại, `events` (đếm số event SSE theo tên) và với mỗi câu: `turns` (mỗi lượt gồm các lần gửi `exchanges` với output dựng từ event: `preprocess`, `answers` theo `position` cùng các bước `tool`, `done`, danh sách event kèm thời điểm), `gold`, `verdict`, `timings` (tổng, event đầu tiên, `preprocess`, từng câu đơn từ `question_started` tới `question_answered`/`question_waiting`, số bước công cụ) và `agent_runs` lấy từ file trace. `timings` có thêm `make_chart` (số bước `make_chart`), `first_text` (thời điểm `answer_delta` có `final = true` đầu tiên, tức TTFT chữ; bản không stream chữ thì lấy thời điểm event `answer`) và `answer_deltas` (số event `answer_delta`). Event `answer_delta` không được ghi vào danh sách event để file kết quả không phình.

Chỉ số phụ, không làm trượt câu: `style` của mỗi lượt liệt kê dấu hiệu văn phong cần tránh có trong câu trả lời (`underscore` dấu `_`, `backtick` dấu `` ` ``, `same_year` ngày ghi năm trùng năm hiện tại như `19/11/2026`, `grouped_year` năm bị ngăn nghìn như `2.026`, `ban_ghi` "bản ghi", `metric`, `toi` có "tôi"); bảng tổng kết in số câu trả lời có từng dấu hiệu. Mục `acceptance` so lần chạy với file `--baseline` (mặc định `results/a2-final-x2.json`): tỷ lệ câu đơn có ít nhất một bước `make_chart` (ngưỡng ≤ 10%), trung vị tổng thời gian (tăng ≤ 5%), trung vị TTFT chữ (phải giảm so với thời điểm `answer` của bản cũ) và tỷ lệ câu đạt (không giảm). `--baseline ""` thì bỏ phần so sánh.

Kết quả các lần chạy và sửa lỗi kèm theo: [báo cáo ngày 2026-11-19](../../../reports/2026-11-19-ket-qua-chay-that-text2sql.md).
