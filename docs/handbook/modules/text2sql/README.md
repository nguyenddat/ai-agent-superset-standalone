# Text2SQL: dùng metric có sẵn để trả lời câu hỏi

**Trạng thái:** `ingestion` (sáu topic, worker, trigger) và `retrieve` đã triển khai ở backend, và chạy metric trên database nguồn đã có qua MCP tool (xem [query-metric.md](query-metric.md)). Route chat streaming `POST /api/v1/text2sql/chat` (SSE, một lượt) đã triển khai, xem [chat-flow.md](chat-flow.md); endpoint đồng bộ `/text2sql/ask` mô tả bên dưới và `run_sql` vẫn dự kiến. Không tạo metric hoặc SQL tự do khi không tìm được metric phù hợp; thay vào đó agent dùng `find_fields`, `plan_join`, `query_dataset` (đã triển khai): server tự nối bảng theo quan hệ khai báo và lưu định nghĩa join thành dataset dùng lại.

## Mục tiêu và ranh giới

Người dùng chọn một `connection_id` rồi đặt câu hỏi bằng tiếng Việt. Agent lấy tối đa `k` metric liên quan trong **cùng connection**, chọn một metric có thể trả lời đúng ý hỏi, lập truy vấn có cấu trúc, chạy trên database nguồn đã đăng ký và trả số liệu cùng cách hiểu truy vấn. Câu hỏi cần nhiều metric nằm ngoài phạm vi đầu tiên.

Module `backend/modules/text2sql/` gồm `vector_store/` (`QdrantDbService`, `ingestion/` dựng document sáu topic, đồng bộ Qdrant, hàng đợi job và trigger, `retrieve/` tìm và xếp hạng, `rerank/` xếp hạng lại bằng Jev), `details/` (mô tả bảng, cột và chi tiết metric, thuật ngữ, quy tắc, tri thức riêng), `query/` (chạy metric trên database nguồn: biên dịch plan, thực thi chỉ đọc, che dữ liệu cá nhân), `dataset/` (tìm trường, đồ thị quan hệ và phương án nối, lưu dataset dùng lại, dựng và chạy truy vấn nhiều bảng), `chat/` (luồng hỏi đáp `ask_data` và pipeline chat streaming: `pipeline.py`, `events.py`, `dataset_flow.py`, `analysis_context.py`), `routes/` (router HTTP: `ingestion.py`, `chat.py`, `suggestions.py`), `common/`, `models/` và `worker.py` (tiến trình chạy job). Lớp ngoài cùng là [MCP server](../../mcp-server.md) với 15 tool. Embedding dùng `OpenRouterEmbedding` ở `backend/agent_package/get_embedding_models.py`. Module đọc dữ liệu của `database_connection`, `data_dictionary`, `metric_management`, `glossary_management`, `expert_rule_management` và `own_knowledge` qua service/model của các module đó; không sao chép bảng nghiệp vụ. Chat session, đề xuất metric/dataset và schema-link là các bước sau.

Module có một bảng PostgreSQL kỹ thuật là hàng đợi ingestion, nằm trong schema `technical` (xem [dữ liệu](du-lieu.md)). Collection và payload index được tạo trong Qdrant khi chạy ingestion lần đầu. Việc đồng bộ chạy bằng service `ingestion-worker` trong backend, không dùng Airflow: xem [worker và hàng đợi](worker-ingestion.md).

Chat streaming phía server: [chat-flow.md](chat-flow.md) (`POST /api/v1/text2sql/chat`). Câu hỏi gợi ý: [suggestions.md](suggestions.md) (`GET /api/v1/text2sql/suggestions`, đã triển khai). Hỏi đáp một lần gọi: [ask-flow.md](ask-flow.md) (`ask_data`). Tìm trường, nối bảng và `query_dataset`: [find-fields-join.md](find-fields-join.md). Dựng truy vấn nhiều bảng: [build-query.md](build-query.md). Dataset truy vấn dùng lại: [query-datasets.md](query-datasets.md). Chạy metric: [query-metric.md](query-metric.md) (MCP tool `query_metric`, đã triển khai; `run_sql` dự kiến). API hiện có: [xếp và xem job ingestion](api-ingestion-jobs.md), [đồng bộ trực tiếp và truy hồi top K metric](api-ingestion-retrieve.md). Thiết kế và phần còn dự kiến: [embed và retrieve](embed-retrieve.md).

## Luồng xử lý

```text
question + connection_id
  → retrieve top k metric đủ điều kiện
  → chọn metric hoặc xác nhận không đủ căn cứ
  → lập plan: metric, nhóm, thời gian, bộ lọc, sắp xếp, giới hạn
  → kiểm tra plan theo metadata thực
  → biên dịch và chạy SELECT giới hạn tài nguyên
  → trả số liệu, metric và điều kiện đã dùng
```

1. **Truy hồi.** Mặc định `k = 5`, giới hạn cấu hình 1–10. Xét metric `is_active=true`, thuộc connection được chọn và có `table_id` trỏ đến bảng vật lý còn tồn tại, gồm metric thủ công và metric đồng bộ từ Superset đã liên kết bảng. Metric của virtual dataset (`source_sql`) và metric mất liên kết chưa được chạy vì chưa có nguồn truy vấn tương ứng trong standalone. Truy hồi qua Qdrant từ các topic bảng, cột và metric, rồi xếp hạng để trả top K **metric**; xem [thiết kế embed và retrieve](embed-retrieve.md). Không dùng ID metric do mô hình tự bịa.
2. **Chọn metric.** Chat model chỉ nhận câu hỏi, tối đa `k` ứng viên và metadata cần thiết. Nó trả một ID trong danh sách, hoặc `no_match`; không được viết SQL. Server kiểm tra ID, connection, trạng thái và bảng lần nữa. Nếu nhiều ứng viên có nghĩa khác nhau mà câu hỏi không phân biệt được, trả `needs_clarification` kèm tên các metric; không tự chọn theo thứ hạng. Nếu không có ứng viên phù hợp, trả `no_metric`, không truy vấn database. Câu hỏi cần nhiều metric trả `needs_clarification` với lý do chưa hỗ trợ.
3. **Lập plan.** Plan có metric ID, `table_id`, cột group by, cột thời gian và khoảng thời gian, các filter `{column_id, operator, value}`, `order_by` và `limit`. Chỉ dùng cột thuộc đúng bảng của metric, toán tử trong allowlist và giá trị đúng kiểu cột. Câu hỏi không nói thời gian thì không tự thêm khoảng thời gian. Không tự suy ngưỡng định tính như “cao” hoặc “tốt”; trả `needs_clarification` nếu không có rule đã duyệt đủ rõ. Giai đoạn đầu chỉ lập plan trên một bảng, không join.
4. **Kiểm tra và chạy.** Biểu thức metric hiện được lưu như văn bản và API quản lý chưa chứng minh tính hợp lệ; do đó parser SQL kiểm tra cú pháp, hàm và tên cột trước khi dùng. SQL cuối cùng do server dựng từ tên schema/bảng/cột đã đối chiếu metadata và giá trị filter được bind, không ghép SQL do mô hình sinh. Chỉ chạy một `SELECT` tổng hợp, có timeout và giới hạn số dòng/nhóm. Lỗi biểu thức hoặc truy vấn được trả rõ để người dùng biết metric không thể chạy.
5. **Trả lời.** Response chứa trạng thái, metric ID/tên/biểu thức đã dùng, plan đã chuẩn hóa, dữ liệu hàng/cột và đơn vị/format nếu có. Câu trả lời bằng ngôn ngữ tự nhiên chỉ tóm tắt kết quả thực; không được bổ sung số không có trong dữ liệu. `null`/không có hàng phải được mô tả là không có dữ liệu, không coi là 0. Response trả SQL đã biên dịch để kiểm tra cách Agent lấy kết quả.

## API dự kiến

Phần dưới là thiết kế ban đầu cho endpoint đồng bộ, chưa triển khai; hỏi đáp qua HTTP hiện dùng route streaming ở [chat-flow.md](chat-flow.md).

`POST /api/v1/text2sql/ask` nhận:

```json
{"connection_id":"<UUID>","question":"Doanh thu theo tháng trong năm 2026?"}
```

Response thành công (ví dụ cấu trúc, không phải số liệu thật):

```json
{
  "status": "answered",
  "metric_candidates": [{"id": "<UUID>", "name": "Doanh thu", "score": 0.87}],
  "selected_metric_id": "<UUID>",
  "plan": {"table_id": "<UUID>", "group_by": ["<column UUID>"], "filters": [], "limit": 100},
  "result": {"columns": ["tháng", "Doanh thu"], "rows": [["2026-01", "123.45"]]},
  "answer": "...",
  "sql": "SELECT ..."
}
```

Khi chưa chạy truy vấn, `status` là `no_metric` hoặc `needs_clarification`, `result=null` và có thông điệp rõ cho người dùng. Lỗi request sai trả 422; connection không có trả 404; database nguồn tạm thời không dùng được trả 503. API đồng bộ trước; streaming có thể thêm sau mà không đổi các trạng thái nghiệp vụ.

## Kiểm chứng chấp nhận

- Có metric phù hợp: truy hồi đúng connection, chọn ID thật, chạy metric và trả đúng hàng/cột cùng điều kiện đã dùng.
- Không có metric hoặc câu hỏi mơ hồ: không gọi database nguồn, không sinh SQL tự do, trả trạng thái tương ứng.
- Metric không hoạt động, mất bảng, metric Superset chưa liên kết hoặc virtual dataset: không được chọn để chạy.
- Filter dùng cột ngoài bảng, giá trị sai kiểu hoặc biểu thức metric không phải phép tổng hợp hợp lệ: trả lỗi trước khi chạy truy vấn.
- Timeout, quá nhiều hàng, lỗi database và `NULL`: trả trạng thái/lỗi đúng nghĩa.
- Bài kiểm tra tích hợp trên PostgreSQL thử nghiệm đối chiếu số liệu với truy vấn dự kiến.

## Thứ tự triển khai

1. Triển khai [module embed, worker đồng bộ index và retrieve/ranking](embed-retrieve.md), tạo hợp đồng `MetricCandidate` và bộ truy hồi top K.
2. Tạo selector/planner trả JSON có schema, kiểm tra tất cả ID và điều kiện trên server.
3. Tạo compiler/executor PostgreSQL với timeout và giới hạn kết quả; chạy metric đủ điều kiện trên bảng vật lý.
4. Thêm API, giao diện hỏi đáp tối thiểu và kiểm chứng đầu cuối. Sau đó mới xét metric Superset, streaming, session và nhánh không có metric.
