# Text2SQL: chỉ mục tri thức và truy hồi

**Trạng thái:** module chỉ còn phần chỉ mục vector: `ingestion` (sáu topic, worker, trigger) và `retrieve` (truy hồi top K, rerank tùy chọn). Phần hỏi đáp (luồng `ask_data`, pipeline chat `POST /api/v1/text2sql/chat`, câu hỏi gợi ý, chạy metric, truy vấn nhiều bảng), MCP server và các agent LLM của text2sql đã gỡ ngày 2026-11-19 để làm lại. Route chat mới (`POST /api/v1/text2sql/chat`, JSON) chạy đủ một lượt: hiểu câu hỏi, agent truy vấn database nguồn và trả lời, hỏi lại khi thiếu thông tin, ghi lượt vào `conversation`; `POST /api/v1/text2sql/chat/stream` chạy cùng luồng và stream từng bước qua SSE cho tab `Hỏi dữ liệu`, gồm cả chữ của câu trả lời (`answer_delta`), công cụ bắt đầu chạy (`tool_started`) và bước tổng hợp (`synthesize_started`); bước tổng hợp gọi `get_chat_text` của `agent_package` và trả Markdown thuần. Xem [hỏi đáp](api-chat.md).

## Phạm vi

Module `backend/modules/text2sql/` dựng chỉ mục Qdrant cho sáu loại tri thức (bảng, cột, metric, thuật ngữ, quy tắc chuyên gia, tri thức riêng) của từng connection và truy hồi trên chỉ mục đó. Module đọc dữ liệu của `database_connection`, `data_dictionary`, `metric_management`, `glossary_management`, `expert_rule_management` và `own_knowledge` qua service/model của các module đó; không sao chép bảng nghiệp vụ. Embedding dùng `OpenRouterEmbedding` ở `backend/agent_package/get_embedding_models.py`.

```text
backend/modules/text2sql/
├── models/        IngestionJob (hàng đợi), ChatCheckpoint (checkpoint lượt chat chờ hỏi lại); schema technical
├── repositories/  QdrantRepository, IngestionJobRepository, ChatCheckpointRepository, truy vấn chỉ đọc nguồn
├── services/      ingestion, trigger, retrieve, topic search, rerank, chat (graph, event, stream SSE), agent text2sql,
│                  display_format.py (định dạng số/ngày vi-VN, fields), explanations.py (mục "Cách tính"),
│                  answer_stream.py (gom chữ stream thành answer_delta/answer_reset)
├── schemas/       schema của route ingestion, retrieve và chat
├── routes/        router_ingestion.py (ingestion, retrieve), router_chat.py (chat, chat/stream),
│                  router_chart.py (danh mục và kiểm tra biểu đồ)
├── utils/         exceptions.py, topics.py
├── dependencies.py
└── worker.py      tiến trình chạy job ingestion
```

Chi tiết cấu trúc và thuật toán: [embed và retrieve](embed-retrieve.md). Bảng kỹ thuật: [dữ liệu](du-lieu.md). Vận hành đồng bộ: [worker và hàng đợi](worker-ingestion.md). Đánh giá trên database nguồn và LLM thật: [chạy đánh giá thật](danh-gia-chay-that.md). Biểu đồ của kết quả (danh mục 32 loại, spec, bộ kiểm tra, đề xuất; mã ở `backend/common/charts/`): [biểu đồ](bieu-do.md).

## API

| Method | Path | Tài liệu |
| --- | --- | --- |
| `POST` | `/api/v1/text2sql/ingestion/jobs` | [xếp và xem job ingestion](api-ingestion-jobs.md) |
| `GET` | `/api/v1/text2sql/ingestion/jobs` | [xếp và xem job ingestion](api-ingestion-jobs.md) |
| `POST` | `/api/v1/text2sql/ingestion/sync` | [đồng bộ trực tiếp và truy hồi top K metric](api-ingestion-retrieve.md) |
| `POST` | `/api/v1/text2sql/retrieve` | [đồng bộ trực tiếp và truy hồi top K metric](api-ingestion-retrieve.md) |
| `POST` | `/api/v1/text2sql/chat` | [hỏi đáp](api-chat.md) |
| `POST` | `/api/v1/text2sql/chat/stream` | [hỏi đáp, stream SSE](api-chat.md#stream-post-apiv1text2sqlchatstream) |
| `GET` | `/api/v1/text2sql/chart-types` | [biểu đồ](bieu-do.md#spec) |
| `POST` | `/api/v1/text2sql/charts/validate` | [biểu đồ](bieu-do.md#spec) |

Việc đồng bộ còn chạy tự động: `register_triggers()` trong `backend/main.py` xếp job khi dữ liệu nguồn đổi, và service `ingestion-worker` phát lịch đồng bộ định kỳ.

## Còn lại sau khi gỡ phần hỏi đáp

- Bảng `technical.text2sql_query_datasets` (migration `7e4c1a9b5d32`) vẫn còn trong database nhưng không còn model; `alembic check` sẽ báo bảng này lệch với metadata cho tới khi có migration xóa bảng hoặc phần hỏi đáp mới dùng lại nó.
- Tab `Hỏi dữ liệu` ở frontend dùng lại được từ ngày 2026-11-20 qua `POST /api/v1/text2sql/chat/stream` ([frontend](../../frontend/README.md#hỏi-dữ-liệu)). Câu hỏi gợi ý (`GET /api/v1/text2sql/suggestions`) chưa làm lại; tab đã bỏ phần gọi route này.
- Route chat ghi lượt vào module [`conversation`](../conversation/README.md) khi có `user_id` ([ghi lượt từ pipeline](../conversation/ghi-luot-tu-pipeline.md)). API hội thoại trả `resume_id` của lượt đang chờ còn hạn, nên lượt chờ mở lại từ lịch sử vẫn chạy tiếp được.
- Lượt lưu không có các lời gọi chỉ đọc catalog (`get_metric`, `get_table`, `get_expert_rule`) mà stream đã gửi; mở lại từ lịch sử chỉ thấy các bước truy vấn và hỏi lại.
