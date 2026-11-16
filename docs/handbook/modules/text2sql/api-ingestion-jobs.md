# API job ingestion của Text2SQL

**Trạng thái: đã triển khai ở backend.** Các API này chỉ ghi và đọc hàng đợi nên không cần Qdrant hay OpenRouter; việc embed do [worker](worker-ingestion.md) làm. Như các module khác, API chưa có xác thực.

## Xếp job ingest lại

`POST /api/v1/text2sql/ingestion/jobs` trả `202 Accepted`.

```json
{"connection_id":"<UUID>","topics":["metric","glossary"]}
```

`topics` không bắt buộc; bỏ trống là cả sáu topic. Topic không hợp lệ trả 422, connection không tồn tại trả 404. Endpoint chỉ ghi job `manual` rồi trả về ngay; nếu topic đã có job chờ thì job đó được dùng lại (không tạo thêm).

Phản hồi:

```json
{"connection_id":"<UUID>","topics":["metric","glossary"]}
```

Dùng cho nút "Ingest lại" của giao diện. Gọi xong, theo dõi tiến độ bằng API bên dưới.

## Xem job

`GET /api/v1/text2sql/ingestion/jobs?connection_id=<UUID>&status=failed&limit=50`

Mọi tham số đều tùy chọn; `status` là một trong `pending`, `running`, `succeeded`, `failed`, `superseded`; `limit` từ 1 đến 200, mặc định 50. Kết quả xếp mới nhất trước.

```json
[{
  "id": "<UUID>", "connection_id": "<UUID>", "topic": "metric", "source": "event", "status": "succeeded",
  "attempts": 1, "run_after": "2026-11-16T08:00:00Z", "started_at": "2026-11-16T08:00:01Z",
  "finished_at": "2026-11-16T08:00:02Z", "last_error": null,
  "result": {"total": 42, "indexed": 3, "unchanged": 39, "deleted": 0, "seconds": 1.2},
  "created_at": "2026-11-16T08:00:00Z"
}]
```

(Ví dụ cấu trúc, không phải số liệu thật.)

## Đồng bộ ngay trong request

`POST /api/v1/text2sql/ingestion/sync` vẫn có, chạy đồng bộ trong request và nhận thêm `topics` tùy chọn. Xem [API ingestion và retrieve](api-ingestion-retrieve.md). Chỉ nên dùng khi cần kết quả tức thì; luồng thông thường dùng hàng đợi.
