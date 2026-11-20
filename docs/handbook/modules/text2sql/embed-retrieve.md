# Embed và retrieve metric cho Text2SQL

**Trạng thái:** ingestion sáu topic, hàng đợi job, worker và trigger tự động đã triển khai ở backend. Truy hồi hybrid, ranking cơ bản và rerank tùy chọn bằng Jev cho metric đã có. Luồng hỏi đáp dùng chỉ mục này đã gỡ ngày 2026-11-19 để làm lại. PostgreSQL metadata là nguồn dữ liệu gốc; Qdrant là chỉ mục có thể tạo lại.

## 1. Cấu trúc module

```text
backend/modules/text2sql/
├── models/            IngestionJob (bảng hàng đợi, schema technical)
├── repositories/
│   ├── qdrant_repository.py          QdrantRepository, mọi lời gọi Qdrant
│   ├── ingestion_job_repository.py   IngestionJobRepository: enqueue, claim, retry, dọn job cũ; enqueue_jobs cho trigger
│   └── source_query_repository.py    source_url (giải mã URI connection), run_read_only (truy vấn chỉ đọc trên database nguồn)
├── services/
│   ├── catalog_context.py      load_context: đọc bảng, cột, metric của connection một lần cho mọi builder
│   ├── index_documents.py      IndexDocument, build_document, một builder cho mỗi topic, TOPIC_BUILDERS; referenced_columns (cột được biểu thức SQL của metric tham chiếu)
│   ├── ingestion_service.py    IngestionService.sync(connection_id, topics)
│   ├── ingestion_triggers.py   ghi job vào hàng đợi khi dữ liệu đổi
│   ├── retrieval_service.py    RetrievalService (xếp hạng metric)
│   ├── topic_search_service.py TopicSearchService (tìm theo từng topic)
│   ├── reranker.py             Reranker (giao diện) và JevReranker (Jev qua OpenRouter)
│   ├── chat_service.py         ChatService.preprocess (viết lại, tách câu, song song phân loại và truy hồi top K), ChatService.chat
│   ├── chat_graph.py           graph LangGraph của một lượt chat: tiền xử lý, chia câu theo depends_on, tổng hợp
│   ├── text2sql_agent_service.py  Text2SqlAgentService.start, AgentRun.answer (agent trả lời một câu đơn)
│   ├── agent_catalog.py        AgentCatalog: bản chụp bảng, cột, metric, quy tắc chuyên gia cho agent
│   ├── agent_tools.py          Text2SqlToolkit (sáu công cụ của agent), QueryCache
│   ├── sql_builder.py          build_metric_query: dựng SQL cho query_metric, áp quy tắc gắn với metric
│   └── sql_guard.py            validate_select: kiểm SQL do LLM viết trước khi chạy
├── schemas/schema_text2sql.py  schema của route ingestion, retrieve và chat
├── routes/              __init__.py (router cha /api/v1/text2sql), router_ingestion.py (ingestion, retrieve), router_chat.py (chat)
├── utils/
│   ├── exceptions.py   lỗi của module (connection không có, chỉ mục, rerank hoặc LLM không dùng được, yêu cầu sai)
│   └── topics.py       tên topic, TOPICS, chu kỳ mặc định, validate_topics
├── dependencies.py     get_index_services, get_chat_service
└── worker.py           tiến trình chạy job và phát lịch
```

Thêm topic: thêm tên vào `utils/topics.py` (cùng chu kỳ mặc định) và builder vào `TOPIC_BUILDERS` ở `services/index_documents.py`; hai danh sách phải cùng thứ tự.

`OpenRouterEmbedding` nằm ở `backend/agent_package/get_embedding_models.py`, cùng chỗ với `get_chat_models.py`, vì là phần dùng chung cho tính năng AI. Lỗi của nó là `EmbeddingUnavailable` (503).

## 2. Topic và point

| `topic` | Một point đại diện | Văn bản đưa vào embedding | Nguồn đọc |
| --- | --- | --- | --- |
| `table` | Một bảng vật lý | Tên schema/bảng, `display_name`, mô tả bảng và grain nếu có. | `database_connection`, `data_dictionary` |
| `column` | Một cột | Tên cột, `display_name`, `business_term`, mô tả, từ đồng nghĩa, đơn vị và tên bảng chứa nó. | `database_connection`, `data_dictionary` |
| `metric` | Một metric | `name`, `label`, mô tả, tên bảng và tên các cột được biểu thức tham chiếu. Biểu thức SQL vẫn ở PostgreSQL. | `metric_management` |
| `glossary` | Một thuật ngữ | Tên chuẩn, định nghĩa, từ đồng nghĩa và tên các bảng, cột, metric được liên kết. | `GlossaryService.discovery`: chỉ bản đã duyệt và đang phục vụ AI |
| `expert_rule` | Một quy tắc | Tên, nhóm, bảng, mô tả, điều kiện viết thành câu, ngoại lệ, câu hỏi ví dụ, thuật ngữ và metric. | `ExpertRuleService.discovery`: chỉ quy tắc đang áp dụng |
| `own_knowledge` | Một cách hiểu riêng của một người dùng | Tên, loại, cách hiểu, bảng ngữ cảnh. | `OwnKnowledgeService.active_entries`: bỏ mục đã có bản hệ thống thay thế |

Ba topic cuối dùng lại hàm discovery của module sở hữu dữ liệu, nên điều kiện "đã duyệt", "còn hiệu lực" luôn khớp với những gì AI Agent thực sự được dùng; ingestion không tự lọc trạng thái.

Mỗi point có payload tối thiểu: `topic`, `entity_id`, `connection_id`, `table_id`, `text`, `content_hash`, `model_version`, `embedding_dimensions`. Phần bổ sung theo topic: `metric` có `is_active`, `origin`, `column_ids`; `glossary` có `synonyms`, `table_ids`, `column_ids`, `metric_ids`; `expert_rule` có `glossary_term_ids`, `metric_ids`; `own_knowledge` có `user_id` và `kind`. ID point suy ổn định từ `(topic, entity_id)` để upsert không nhân bản. Một collection chứa mọi topic, có payload index cho các trường lọc (gồm `user_id`) và full-text index BM25 trên `text`. [Collections](https://qdrant.tech/documentation/manage-data/collections/), [Payload indexing](https://qdrant.tech/documentation/manage-data/indexing/).

Point `own_knowledge` là nội dung riêng của một người dùng nằm chung collection với dữ liệu chung. Truy hồi hiện chỉ đọc topic `metric`, `table`, `column`; khi retrieve bắt đầu dùng `own_knowledge`, bắt buộc lọc `user_id` lấy từ phiên đáng tin cậy.

**Model:** `openai/text-embedding-3-small` qua OpenRouter, mặc định 1536 chiều, cosine. Cả ingestion và retrieve dùng chung `TEXT2SQL_EMBEDDING_MODEL` và `TEXT2SQL_EMBEDDING_DIMENSIONS`; OpenRouter nhận batch văn bản trong `/api/v1/embeddings`. [OpenRouter Embeddings API](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings).

**Đồng bộ:** `IngestionService.sync(connection_id, topics)` dựng document của các topic được chọn, so `content_hash` với point đang có trong Qdrant, chỉ embed và upsert point mới hoặc đổi, rồi xóa point thuộc **các topic đó** mà không còn ở PostgreSQL. Việc xóa giới hạn theo topic nên một job của topic này không xóa nhầm point của topic khác. Đổi model cần collection mới và backfill trước khi đổi cấu hình truy hồi; không trộn vector của hai model. [Qdrant migration guidance](https://qdrant.tech/documentation/faq/qdrant-fundamentals/).

## 3. Điều phối: worker trong backend

Ingestion không còn dùng Airflow. Airflow là hệ thống riêng (scheduler, webserver, database) nên không nhúng được vào backend, và việc nó làm ở đây chỉ là gọi HTTP theo lịch. Thay vào đó, hàng đợi nằm trong PostgreSQL và service `ingestion-worker` chạy cùng image backend. Chi tiết trong [worker và hàng đợi ingestion](worker-ingestion.md).

```text
Người dùng sửa dữ liệu ─→ trigger ghi job vào outbox (cùng transaction)
POST /ingestion/jobs  ─→ ghi job (nút "Ingest lại")
Lịch của worker       ─→ ghi job theo chu kỳ riêng của từng topic
                              ↓
ingestion-worker lấy job bằng SELECT … FOR UPDATE SKIP LOCKED, chạy song song theo (connection, topic)
```

## 4. Module retrieve + ranking

`backend/modules/text2sql/retrieve/` nhận `(question, connection_id, k)` và trả `MetricCandidate[]`, không sinh SQL. `k` mặc định 5 và là **số metric cuối cùng**, không phải số point lấy từ Qdrant.

1. **Candidate recall.** Embed câu hỏi một lần. Truy vấn Qdrant với filter `connection_id` và `topic`. Lấy pool rộng hơn top K, ví dụ 30 point `metric`, 15 `table`, 30 `column`. Mỗi truy vấn là **hybrid**: một nhánh dense (cosine trên vector embedding) và một nhánh BM25 trên payload `text`, gộp bằng RRF trong cùng một lời gọi `points/query` (`QdrantRepository.search`). Nhánh BM25 dùng full-text index của Qdrant (`scoring: bm25`) nên không cần tự tính vector thưa; điểm BM25 phụ thuộc tần suất từ và độ hiếm của từ trong collection, từ hiếm như `doanh thu` điểm cao hơn từ phổ biến như `bảng`. Nhánh BM25 khớp theo từ (OR giữa các từ của câu hỏi) nên bổ trợ cho dense ở tên riêng, mã và thuật ngữ đúng chữ; dense bổ trợ lại khi câu hỏi diễn đạt khác. [Hybrid queries](https://qdrant.tech/documentation/hybrid-queries/), [Full-text index](https://qdrant.tech/documentation/manage-data/indexing/).

   **Khớp không dấu.** Chỉ mục `text` bật `ascii_folding` và `lowercase`, nên `nhiet do`, `NHIỆT ĐỘ` và `Nhiệt độ` khớp nhau, kể cả chữ `đ`. Người dùng thường gõ không dấu, và nếu thiếu bước này nhánh BM25 trả rỗng với các câu hỏi đó. `ensure_collection` tự dựng lại chỉ mục `text` nếu collection đã có chỉ mục theo cấu hình cũ (xóa rồi tạo lại, không cần đổi tên collection hay embed lại), nên lần chạy ingestion đầu tiên sau khi nâng cấp sẽ sửa collection đang dùng. Dựng lại chỉ mục trên collection lớn tốn thời gian trong lúc đó.
2. **Quy về metric.** Metric hit là ứng viên trực tiếp. Table hit chỉ cộng tín hiệu cho metric cùng `table_id`. Column hit chỉ cộng tín hiệu cho metric cùng bảng **và** có tham chiếu cột đó trong biểu thức; quan hệ này được parse từ SQL metric khi lập index hoặc tra lại metadata. Giới hạn tổng điểm ngữ cảnh để một bảng có nhiều cột không áp đảo metric hit. Loại metric inactive/mất bảng và nạp lại thông tin gốc từ PostgreSQL trước khi trả.
3. **Ranking cơ sở.** Xếp hạng từ vị trí metric trong kết quả RRF, cộng điểm ngữ cảnh bảng/cột có giới hạn và khớp chính xác tên/nhãn. Chỉ gồm metric còn hoạt động và gắn bảng vật lý trong PostgreSQL. Trọng số hiện là baseline; chưa có tập đánh giá để hiệu chỉnh.
4. **Xếp hạng lại bằng Jev (tùy chọn).** `RetrievalService.search(..., reranker)` nhận một `Reranker`; không truyền thì giữ nguyên thứ tự của bước 3. Hiện không caller nào truyền `Reranker`: API REST `/text2sql/retrieve` không rerank (trước đây chỉ các MCP tool tìm kiếm bật bước này).
   - **Đầu vào:** tối đa `TEXT2SQL_RERANK_POOL` ứng viên đầu (mặc định 20, không nhỏ hơn `k`). Với metric, đó là các metric đầu của bước 3, diễn đạt bằng văn bản đã lập index (tên, nhãn, mô tả, bảng, cột liên quan). Với các loại còn lại (`table`, `column`, `glossary`, `expert_rule`, `own_knowledge`), `TopicSearchService` lấy các point đầu của topic đó từ Qdrant (hybrid dense + BM25 + RRF) và dùng văn bản của point; riêng `own_knowledge` chỉ gồm point của đúng `user_id`.
   - **Jev:** `JevReranker` gọi `POST {OPENROUTER_BASE_URL}/systemone` với model `TEXT2SQL_RERANK_MODEL` (mặc định `typesafe/jev-1.14`), mỗi ứng viên một lời gọi, tối đa `TEXT2SQL_RERANK_CONCURRENCY` lời gọi song song (mặc định 8). Mỗi lời gọi hỏi một câu kiểu `score` ba mức (không liên quan, liên quan một phần, trả lời trực tiếp), với cách diễn đạt riêng cho từng loại (`SUBJECTS` trong `services/reranker.py`); điểm `score` Jev trả về (từ 0 đến 2, tương ứng ba mức) được chia cho 2 thành `rerank_score` trong [0, 1]. Dùng cùng khóa `OPENROUTER_API_KEY`. [OpenRouter System One](https://openrouter.ai/docs/api/api-reference/systemone/submit-a-system-one-request).
   - **Thứ tự cuối:** theo `rerank_score` giảm dần, đồng điểm thì theo điểm ở bước 3, rồi cắt lấy `k`.
   - **Khi Jev lỗi** (HTTP lỗi, bị từ chối, quá `TEXT2SQL_RERANK_TIMEOUT_SECONDS`, thiếu khóa): trả đúng thứ tự bước 3, `reranked=false` và `rerank_warning` mô tả; yêu cầu không thất bại. Một lời gọi lỗi là bỏ cả lượt rerank, không trộn điểm của một phần ứng viên.
   - **Chi phí và độ trễ:** thêm tối đa `TEXT2SQL_RERANK_POOL` lời gọi cho mỗi truy vấn. Thử với ba ứng viên mất khoảng một giây; giá công bố khoảng 0,042 USD cho một triệu token đầu vào, nhưng chưa kiểm chứng chất lượng trên tiếng Việt, xem mục 5.
5. **Dự kiến.** Dùng tập câu hỏi gắn nhãn để chỉnh trọng số và xác nhận Jev có cải thiện tiếng Việt cho từng loại, dùng thêm `glossary`, `expert_rule` và `own_knowledge` làm tín hiệu xếp hạng metric, rồi chọn một metric đủ căn cứ để lập plan. Điểm retrieval không tự chứng minh metric phù hợp.

Hợp đồng hiện có:

```json
{
  "metric_id": "<UUID>",
  "table_id": "<UUID>",
  "name": "revenue",
  "label": "Doanh thu",
  "description": null,
  "score": 0.87,
  "matched_topics": ["metric", "column"]
}
```

`score` là điểm ranking nội bộ để so thứ tự trong một request, không diễn giải là xác suất đúng. Khi có rerank, mỗi ứng viên có thêm `rerank_score` (0 đến 1); REST không trả trường này. Có thể trả thêm các điểm thành phần trong trace kỹ thuật để đánh giá chất lượng.

## 5. Đo chất lượng trước khi nối với executor

Tạo tập câu hỏi tiếng Việt gắn `connection_id`, metric đúng (hoặc `no_metric`) và các cặp dễ nhầm: doanh thu/doanh số, số đơn/số khách, tổng/trung bình, cùng tên ở hai connection, metric inactive. Đo `Recall@30` của bước lấy ứng viên, `MRR@5` và `Recall@5` sau ranking (có và không có `rerank`), cùng tỷ lệ `no_metric` sai. So sánh dense-only, BM25-only và hybrid; chỉ khuyến nghị bật `rerank` mặc định nếu Jev cải thiện trên tập đánh giá. Ghi latency embed query, Qdrant và rerank để chọn pool size/K. Qdrant cũng khuyến nghị chọn metric đánh giá theo mục tiêu của từng tầng retrieval. [Search tuning](https://qdrant.tech/documentation/search-tuning/before-tuning-a-qdrant-collection/).

## 6. Thứ tự triển khai

1. **Đã có:** Qdrant, `QdrantRepository`, embedding ở `agent_package`, ingestion sáu topic, hàng đợi job với worker song song, trigger tự động, API sync/job/retrieve, hybrid search và ranking cơ bản.
2. **Tiếp theo:** nút "Ingest lại" và màn hình trạng thái job ở frontend, bộ đánh giá tiếng Việt, tối ưu ranking/rerank, chọn metric rồi nối với planner và executor Text2SQL.
