# Chạy metric trên database nguồn (`query_metric`)

**Trạng thái: đã triển khai** dưới dạng MCP tool [`query_metric`](../../mcp-server.md). Truy vấn **do server dựng** từ một plan có cấu trúc, không phải SQL do AI viết. Cho phép AI gửi SQL tự do (`run_sql`) là bước **dự kiến** sau, với cơ chế an toàn riêng.

## Phạm vi

- Chạy **một metric** đã chọn (`search_metrics`, `get_metric`) trên **một bảng** của connection, không join.
- Chỉ PostgreSQL, giống phần đồng bộ metadata hiện có.
- Metric phải đang hoạt động, gắn bảng vật lý và không thuộc dataset ảo (`source_sql`).
- Code ở `backend/modules/text2sql/query/`; tool ở `backend/mcp_server/tools/query.py`.

## Plan

| Trường | Ý nghĩa |
| --- | --- |
| `metric_id` | Metric cần chạy. |
| `group_by` | Tối đa 5 ID cột để nhóm. Cột phải thuộc bảng của metric, kiểu văn bản, số, boolean, ngày, ngày giờ hoặc UUID. |
| `time` | `{column_id, start, end, granularity}` trên cột ngày hoặc ngày giờ. Khoảng thời gian là `[start, end)`; `granularity` (ngày, tuần, tháng, quý, năm) nhóm kết quả theo kỳ. Cần ít nhất một trong ba trường. Server không tự thêm khoảng thời gian. |
| `filters` | Tối đa 10 điều kiện nối bằng AND: `equals`, `not_equals`, `contains`, `not_contains`, `greater_than(_or_equal)`, `less_than(_or_equal)`, `in`, `not_in` (tối đa 50 giá trị), `is_null`, `is_not_null`. Toán tử và giá trị phải khớp kiểu cột: so sánh độ lớn chỉ cho số và thời gian, `contains` chỉ cho văn bản. |
| `order_by` | Tối đa 3 khóa: `"metric"`, `"time"` (khi có `granularity`) hoặc ID một cột trong `group_by`. Mặc định: theo kỳ tăng dần nếu có `granularity`, ngược lại theo metric giảm dần. NULL xếp cuối. |
| `limit` | Mặc định 100, bị cắt bởi `TEXT2SQL_QUERY_MAX_ROWS` (mặc định 200). |

Khóa lạ bên trong plan bị từ chối; tham số lạ ở cấp tool bị SDK bỏ qua và không bao giờ được dùng.

## Quy trình

```text
plan → prepare (kiểm tra, biên dịch) → [xác nhận nếu chạm cột PII] → execute (transaction chỉ đọc) → che PII → kết quả
```

1. **prepare:** nạp metadata của connection, kiểm tra plan, kiểm tra biểu thức metric và dựng SQL cùng tham số. Chưa chạm database nguồn.
2. **Xác nhận:** nếu `group_by` có cột PII, hỏi người dùng (xem [Dữ liệu cá nhân](#dữ-liệu-cá-nhân)).
3. **execute:** giải mã URI nguồn, đóng session database ứng dụng rồi mới chạy truy vấn nguồn.
4. **Che PII** trên các cột chiều, rồi trả kết quả.

## SQL được dựng thế nào

Chỉ một dạng duy nhất:

```sql
SELECT "region" AS "dim_1", SUM("amount") AS "metric_value"
FROM "public"."sales"
WHERE "status" = :p0 AND "order_date" >= :p1
GROUP BY 1
ORDER BY "metric_value" DESC NULLS LAST
LIMIT :p2
```

- Tên schema, bảng, cột lấy từ metadata đã đồng bộ và được trích dẫn; AI chỉ đưa ID cột, không đưa tên.
- **Mọi giá trị lọc là tham số bind**, kể cả danh sách của `in`. Giá trị của `contains` được escape `%`, `_`, `\`. Không có giá trị nào được ghép vào chuỗi SQL.
- Nhóm theo kỳ dùng `date_trunc`; với cột `DATE` kết quả ép về `date` để không phụ thuộc múi giờ. Phiên chạy đặt `TimeZone=UTC`.
- `LIMIT` lấy `limit + 1` dòng để biết kết quả có bị cắt (`truncated`).
- Kết quả trả kèm `sql` và `parameters` đã chạy để người dùng kiểm tra.

### Kiểm tra biểu thức metric

Biểu thức metric là văn bản do người dùng hoặc Superset nhập, nên được phân tích bằng sqlglot và chỉ chạy nếu **mọi nút cú pháp nằm trong danh sách cho phép**, rồi SQL được dựng lại từ cây đã kiểm tra:

- Cho phép: cột, hằng, `SUM`, `COUNT` (kể cả `COUNT(*)`, `DISTINCT`), `AVG`, `MIN`, `MAX`, phép tính số học, so sánh, `AND`/`OR`/`NOT`, `CASE`, `COALESCE`, `NULLIF`, `ROUND`, `ABS`, `CEIL`, `FLOOR`, `GREATEST`, `LEAST`, `IN`, `BETWEEN`, `LIKE`, và `CAST` sang kiểu cơ bản (số, `VARCHAR`, `TEXT`, ngày giờ, `BOOLEAN`; không nhận `CHAR` vì Postgres hiểu là `char(1)` và cắt cụt giá trị).
- Từ chối: gọi hàm khác (như `pg_sleep`), truy vấn con, hàm cửa sổ, `FILTER`, nối chuỗi, nhiều câu lệnh, dấu `;`, cột kèm tên bảng hoặc schema, cột không thuộc bảng của metric, biểu thức không có hàm tổng hợp, biểu thức quá dài, quá phức tạp hoặc lồng ngoặc/hàm quá sâu.
- Tên cột được thay bằng tên chính xác trong metadata, có trích dẫn.

Metric bị từ chối trả lỗi rõ lý do, không chạy gì.

## Chỉ đọc và transaction

Nhiều lớp độc lập, để một lớp lỏng không đủ gây ghi dữ liệu:

1. Server **chỉ dựng `SELECT`** (lớp thứ nhất; không có đường nào cho AI đưa câu lệnh vào).
2. Kết nối đặt `default_transaction_read_only=on` ngay từ lúc mở phiên.
3. Transaction mở tường minh với `READ ONLY` và mức cô lập `REPEATABLE READ`, nên toàn bộ truy vấn thấy một ảnh chụp nhất quán.
4. `SET LOCAL statement_timeout` (mặc định 15 giây, `TEXT2SQL_QUERY_TIMEOUT_SECONDS`), cùng `lock_timeout` 3 giây và `idle_in_transaction_session_timeout`.
5. Transaction luôn **rollback** (không bao giờ commit), kết nối dùng `NullPool` và được đóng sau mỗi lần chạy. Không để lại kết nối hay transaction treo.
6. Lỗi từ database nguồn được dịch sang lỗi nghiệp vụ: hết giờ trả "vượt quá N giây, hãy thu hẹp khoảng thời gian hoặc thêm bộ lọc"; lỗi khác chỉ trả thông điệp chung. **Không đưa URI, mật khẩu hay thông điệp lỗi SQL gốc** vào phản hồi hay log.

Lớp 2 đến 5 được kiểm chứng riêng: test tích hợp ném `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `CREATE`, `DROP`, `ALTER` và `SELECT … INTO` trực tiếp vào bộ thực thi bằng một tài khoản có đủ quyền ghi, tất cả bị từ chối và dữ liệu không đổi. Đây là điều kiện cần cho `run_sql` sau này.

Giá trị `NULL` giữ nguyên là `null` (không có dữ liệu), không đổi thành 0. `Decimal` trả dạng chuỗi để không mất độ chính xác.

## Dữ liệu cá nhân

Quy trình bốn bước, theo cách xử lý khi dán dữ liệu cá nhân vào chatbot:

| Bước | Thực hiện |
| --- | --- |
| 1. **Cảnh báo, hỏi trước** | Nếu `group_by` có cột đánh dấu `contains_pii` trong từ điển dữ liệu, server hỏi người dùng (MCP elicitation): cột nào sẽ được đọc, giá trị gốc sẽ không gửi cho AI. Từ chối hoặc hủy thì truy vấn không chạy. Kết quả luôn có `pii.warning` khi phát hiện dữ liệu cá nhân. |
| 2. **Phát hiện** | [Presidio](https://github.com/data-privacy-stack/presidio) Analyzer: nhận dạng bằng biểu thức chính quy, luật và checksum (email, thẻ tín dụng có Luhn, IBAN, IP, số điện thoại quốc tế) cùng các recognizer riêng cho Việt Nam. |
| 3. **Thay bằng placeholder** | Presidio Anonymizer thay giá trị bằng `<LOẠI_n>`. Cùng một giá trị luôn cùng placeholder trong một phản hồi, nên AI vẫn đếm và so sánh được các nhóm mà không thấy giá trị thật. |
| 4. **Không khôi phục** | Server không có đường nào trả lại giá trị gốc. |

**Cột chiều được quét ở mọi dòng**, kể cả cột không đánh dấu PII; cột metric và cột thời gian không bị quét.

| Loại | Cách nhận ra |
| --- | --- |
| `EMAIL_ADDRESS`, `CREDIT_CARD`, `IBAN_CODE`, `IP_ADDRESS`, `PHONE_NUMBER` | Recognizer có sẵn của Presidio (số điện thoại gồm vùng VN, US, GB, SG, JP, KR, CN). |
| `VN_PHONE_NUMBER` | Di động Việt Nam đầu 03, 05, 07, 08, 09, các dạng `0912345678`, `0912 345 678`, `091.234.5678`, `+84 912 345 678`. |
| `VN_CITIZEN_ID` (CCCD 12 số), `VN_IDENTITY_CARD` (CMND 9 số), `VN_TAX_CODE`, `VN_BANK_ACCOUNT` | Chuỗi số trần dễ nhầm với mã đơn hay mã sản phẩm, nên chỉ được nhận khi **tên hoặc nhãn cột gợi ý** (như "Số CCCD", "Mã số thuế", "STK"). So khớp không phân biệt dấu và hoa thường. |
| `PII` | Mọi giá trị khác `null` trong cột đánh dấu `contains_pii` mà Presidio không nhận ra loại cụ thể (ví dụ tên người), kể cả giá trị kiểu số, bool hay ngày (được đổi sang chuỗi rồi che). |

Hai quy tắc phòng truy vết một cá nhân:

- **Không lọc theo cột PII** và không dùng cột PII làm cột thời gian: số tổng hợp của đúng một người vẫn là dữ liệu của họ.
- Nhóm theo cột PII được phép (sau xác nhận) vì kết quả đã là placeholder.

Kết quả có `pii`: `confirmation` (`not_required`, `confirmed` hoặc `not_supported`), `masked_columns`, `detected` (số giá trị khác nhau theo loại, **không** chứa giá trị gốc) và `warning`.

### Giới hạn quan trọng

- **Không nhận dạng tên người** trong văn bản tự do: không có mô hình nhận dạng thực thể (NER) tiếng Việt đi kèm; engine NLP chỉ là spaCy rỗng để dùng bộ nhận dạng theo luật. Tên người được che **nhờ cờ `contains_pii` trong từ điển**, nên cần đánh dấu đúng các cột đó. Địa chỉ nhà và tên riêng trong cột không gắn cờ không được phát hiện.
- Xác nhận là **sự đồng ý của người dùng, không phải rào chắn bảo mật**: việc che dữ liệu luôn chạy, dù có hỏi hay không. SDK ghi chú rằng nếu client là một agent thì nó có thể tự trả lời thay người dùng. Client không hỗ trợ elicitation vẫn chạy được với dữ liệu đã che và ghi `confirmation: not_supported`.
- Số chỉ-có-chữ-số không có gợi ý từ tên cột (ví dụ CCCD nằm trong cột tên "ghi chú") không bị che nếu không giống định dạng cụ thể nào khác.
- Quyền xem dữ liệu theo người dùng Superset (row-level security, quyền dataset) **không** được áp dụng; xem giới hạn định danh ở [MCP server](../../mcp-server.md).

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
| --- | ---: | --- |
| `TEXT2SQL_QUERY_TIMEOUT_SECONDS` | 15 | `statement_timeout` của truy vấn nguồn. |
| `TEXT2SQL_QUERY_MAX_ROWS` | 200 | Trần số dòng trả về, áp cho `limit` của plan. |

Phụ thuộc mới: `presidio-analyzer`, `presidio-anonymizer` (kéo theo spaCy). Không tải mô hình ngôn ngữ nào. Thư viện nạp lười: khởi động MCP server không tốn thêm, lần che dữ liệu đầu tiên mất khoảng 1,3 giây. Vì cùng một `uv.lock`, image backend cũng cài các thư viện này dù không dùng.

## Kiểm thử

- `tests/test_text2sql_query.py`: bộ kiểm tra biểu thức (kể cả chuỗi tấn công) và bộ biên dịch plan, không cần database.
- `tests/test_text2sql_pii.py`: phát hiện và che dữ liệu cá nhân bằng Presidio thật.
- `tests/test_text2sql_query_pg.py`: tích hợp trên PostgreSQL thật, chạy khi đặt `POSTGRES_TEST_URL` (test tự tạo và xóa database tạm): kết quả chính xác, NULL, cắt dòng, che PII, chỉ đọc, timeout, không để lại kết nối, không lộ thông tin kết nối.
- `tests/test_mcp_server.py`: tool, lược đồ tham số và luồng xác nhận (đồng ý, từ chối, hủy, client không hỗ trợ).

## Việc còn lại

- `run_sql`: cho AI gửi SQL tự do. Cần phân tích SQL, danh sách bảng và hàm cho phép, chạy trên cùng bộ thực thi chỉ đọc ở trên, và che PII như trên.
- Join giữa các bảng, metric nhiều bảng, metric của dataset ảo.
- Nhận dạng tên người bằng mô hình NER, và quyền xem theo người dùng.
