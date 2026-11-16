# API ingestion và retrieve của Text2SQL

**Trạng thái: đã triển khai ở backend.** Cần Qdrant tại `QDRANT_URL` và `OPENROUTER_API_KEY` để gọi `openai/text-embedding-3-small` qua OpenRouter. `TEXT2SQL_COLLECTION` mặc định `text2sql_semantics_v1`, vector 1536 chiều theo `TEXT2SQL_EMBEDDING_DIMENSIONS`. Backend trong Compose dùng `http://qdrant:6333`.

## Đồng bộ index

`POST /api/v1/text2sql/ingestion/sync`

```json
{"connection_id":"<UUID>","topics":["metric","glossary"]}
```

`topics` không bắt buộc; bỏ trống là cả sáu topic (`table`, `column`, `metric`, `glossary`, `expert_rule`, `own_knowledge`), topic không hợp lệ trả 422. Backend đọc dữ liệu của connection từ PostgreSQL, dựng document cho các topic được chọn (xem [embed và retrieve](embed-retrieve.md)). Metric cần bảng vật lý; metric virtual hoặc mất liên kết không được lập index. Glossary, quy tắc và tri thức riêng chỉ lập index khi đang được AI sử dụng. Endpoint tạo collection và payload index nếu chưa có, so `content_hash`, chỉ gọi embedding cho point mới/đổi, upsert theo ID ổn định và xóa point cũ **thuộc các topic được chọn** trong connection. Gọi lại cùng dữ liệu trả `indexed=0`.

```json
{"connection_id":"<UUID>","topics":["metric","glossary"],"total":42,"indexed":3,"unchanged":39,"deleted":1}
```

Endpoint này chạy đồng bộ trong request. Luồng thông thường không gọi nó mà dùng hàng đợi: backend tự xếp job khi dữ liệu đổi, [worker](worker-ingestion.md) xử lý theo lịch và theo job, còn giao diện xếp job bằng [API job](api-ingestion-jobs.md). Connection không tồn tại trả 404; Qdrant/OpenRouter lỗi trả 503.

## Truy hồi metric

`POST /api/v1/text2sql/retrieve`

```json
{"connection_id":"<UUID>","question":"Doanh thu theo tháng?","k":5}
```

`k` nằm trong 1–10, mặc định 5. Backend embed câu hỏi một lần, dùng Qdrant hybrid dense + BM25/RRF (BM25 khớp không dấu) để tìm point theo từng topic trong đúng connection, rồi quy tín hiệu bảng/cột về metric. Xếp hạng hiện dựa trên vị trí metric, bảng/cột liên quan và khớp tên/nhãn; chỉ trả metric còn hoạt động và gắn bảng vật lý trong PostgreSQL. Chưa có bước rerank bằng LLM hoặc cross-encoder.

```json
{"candidates":[{"metric_id":"<UUID>","table_id":"<UUID>","name":"revenue","label":"Doanh thu","description":null,"score":1.32,"matched_topics":["metric","table"]}]}
```

`score` là điểm xếp hạng nội bộ, không phải xác suất. Endpoint chỉ trả ứng viên; chưa chọn metric cuối cùng và chưa chạy SQL. Connection không tồn tại trả 404; chưa đồng bộ collection hoặc Qdrant/OpenRouter lỗi trả 503.
