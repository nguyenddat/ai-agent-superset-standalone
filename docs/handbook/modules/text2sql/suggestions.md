# Câu hỏi gợi ý (`GET /api/v1/text2sql/suggestions`)

**Trạng thái: đã triển khai** (2026-11-16). Mã: `backend/modules/text2sql/chat/suggestions.py` (`SuggestionService`), route `backend/modules/text2sql/routes/suggestions.py`, đăng ký trong router text2sql (`routes/__init__.py`). Đọc dữ liệu của module [`conversation`](../conversation/README.md) (`ConversationService.answered_questions`, `metric_usage`), [`expert_rule_management`](../expert_rule_management/README.md) (`ExpertRuleService.discovery`) và `metric_management`.

Trả danh sách câu hỏi mẫu cho màn hình trống của tab `Hỏi dữ liệu`. Không gọi LLM, không gọi Qdrant hay Jev, không chạy truy vấn trên database nguồn.

## Request

```text
GET /api/v1/text2sql/suggestions?connection_id=<UUID>&user_id=alice&limit=6
```

| Tham số | Ràng buộc |
| --- | --- |
| `connection_id` | UUID, bắt buộc. Connection không tồn tại trả 404 `{"detail": "Không tìm thấy connection."}` như các route text2sql khác. Connection đang tạm dừng vẫn trả gợi ý. |
| `user_id` | Tùy chọn, tối đa 255 ký tự; chuỗi rỗng coi như không có. Không có thì bỏ nguồn `history`. |
| `limit` | Số nguyên 1 đến 20, mặc định 6. Ngoài khoảng trả 422. |

## Response

`200`, danh sách tối đa `limit` mục:

```json
[
  {"question": "Doanh thu theo vùng năm 2025?", "source": "history"},
  {"question": "Hôm nay mưa lớn không?", "source": "rule_example"},
  {"question": "Doanh thu theo tháng", "source": "metric"},
  {"question": "Tồn kho là bao nhiêu?", "source": "metric"}
]
```

`source` thuộc `history`, `rule_example`, `metric`. `question` đã gộp khoảng trắng thừa (nhiều khoảng trắng thành một, bỏ đầu cuối).

## Thứ tự và bỏ trùng

Các nguồn được lấy lần lượt; nguồn sau chỉ được đọc khi chưa đủ `limit` mục. Câu hỏi trùng (so sánh không phân biệt hoa thường sau khi gộp khoảng trắng) chỉ giữ lần xuất hiện đầu, tức là giữ nguồn ưu tiên cao hơn. Câu rỗng hoặc dài quá 2000 ký tự (giới hạn của route chat) bị bỏ.

1. **`history`**: câu hỏi của **chính** `user_id` trên connection này, chỉ lượt có trạng thái `answered`, bỏ lượt có đánh giá `down`, mới nhất trước (theo thời điểm tạo lượt). Không bao giờ lấy câu hỏi của người dùng khác (quyết định quyền riêng tư). Đọc tối đa `max(limit × 5, 50)` lượt gần nhất trước khi bỏ trùng.
2. **`rule_example`**: `examples[].question` của các quy tắc chuyên gia đang được áp dụng cho connection, cùng nguồn với `GET /api/v1/expert-rules/discovery` (bản đang phục vụ và còn hiệu lực, tương đương `rule.serving.examples` với `is_discoverable=true`). Thứ tự theo tên quy tắc rồi thứ tự ví dụ.
3. **`metric`**: một câu dựng từ mỗi metric chạy được của connection (`is_active=true`, có bảng thuộc connection, không phải metric của dataset ảo `source_sql`). Bảng của metric có cột kiểu `date` hoặc `timestamp*` thì câu là `"<nhãn metric> theo tháng"`, ngược lại `"<nhãn metric> là bao nhiêu?"`; nhãn là `label`, không có thì `name`. Metric được dùng nhiều hơn đứng trước: số lần đếm từ `results[].metric.name` (mục `kind=metric`) của tối đa 500 lượt `answered` gần nhất trên connection, mọi người dùng; chỉ dùng số đếm, không lộ câu hỏi của ai. Cùng số lần (kể cả khi chưa có lượt nào được lưu) thì theo nhãn không phân biệt hoa thường, rồi `name`, rồi ID.

Hiện pipeline chat chưa ghi lượt vào module `conversation` (xem [ghi lượt từ pipeline](../conversation/ghi-luot-tu-pipeline.md)), nên `history` và thứ tự theo tần suất chỉ có dữ liệu khi lượt đã được ghi.

## Giới hạn

- `user_id` do client gửi, **chưa xác thực**, như mọi API hiện tại; ai biết `user_id` của người khác thì xem được câu hỏi đã trả lời của người đó trên connection.
- Câu `metric` là mẫu cố định, không kiểm tra trước xem pipeline có trả lời được không.
- Mỗi request đọc metadata database: một truy vấn lượt hỏi, `discovery` của quy tắc chuyên gia (một vài truy vấn cho mỗi quy tắc), một truy vấn metric, một truy vấn cột thời gian, một truy vấn kết quả các lượt; các nguồn sau bị bỏ qua khi đã đủ `limit`.

## Kiểm thử

`tests/test_text2sql_suggestions.py` (`TestClient`, SQLite trong bộ nhớ, `ExpertRuleService.discovery` được thay bằng dữ liệu giả): thứ tự nguồn và bỏ trùng không phân biệt hoa thường, khoảng trắng; bỏ lượt bị `down`, lượt không `answered`, lượt của connection khác và câu hỏi của người khác; không có `user_id` thì không có `history`; metric dùng nhiều đứng trước, bỏ metric tạm dừng và metric dataset ảo; `limit` mặc định 6, dừng sớm không đọc nguồn sau, 0 và 21 trả 422; connection không tồn tại 404.
