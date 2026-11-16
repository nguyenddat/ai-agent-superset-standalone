# Dựng truy vấn nhiều bảng (dataset query)

**Trạng thái: đã triển khai** ở tầng service (`backend/modules/text2sql/dataset/`: `schemas.py`, `expression.py`, `compiler.py`, `service.py`). Việc lưu dataset nằm ở [query-datasets.md](query-datasets.md); MCP tool `query_dataset` gọi tầng này (xem [find-fields-join.md](find-fields-join.md#chạy-truy-vấn-nhiều-bảng-query_dataset) và [MCP server](../../mcp-server.md)).

Bộ dựng nhận một **phương án nối** (`JoinOption`) do server tự tính bằng `JoinGraph.plan` (xem [find-fields-join.md](find-fields-join.md)) và một **plan có cấu trúc** (`DatasetQueryPlan`), rồi sinh một câu `SELECT` chỉ đọc. Client không bao giờ gửi `from_sql`; mọi định danh lấy từ catalog và được quote, mọi giá trị do người dùng hoặc LLM đưa vào đều được bind tham số.

## Plan

| Trường | Ý nghĩa |
| --- | --- |
| `select` | 1 đến 20 mục. Mỗi mục có **đúng một** trong `column_id` hoặc `expression`; `aggregation` (`sum`, `avg`, `min`, `max`, `count`, `count_distinct`) chỉ đi với `column_id`; `alias` tùy chọn. |
| `group_by` | Tối đa 5 ID cột (kiểu văn bản, số, boolean, ngày, ngày giờ, UUID), không trùng. Cột nhóm chưa có trong `select` vẫn được trả về, đặt trước các mục `select`. |
| `time` | `QueryTime` như [query-metric.md](query-metric.md): khoảng `[start, end)`, `granularity` nhóm theo `date_trunc` và trả cột `time_bucket`. Điều kiện thời gian luôn nằm trong `WHERE`. |
| `filters` | Tối đa 10 điều kiện AND, cùng toán tử và quy tắc kiểu của `QueryFilter`, thêm `placement` (`where` mặc định hoặc `join`). |
| `order_by` | Tối đa 3 khóa; `by` là alias một cột kết quả, `"time"` (khi có `granularity`) hoặc `column_id` của một mục `select` không tổng hợp. NULL xếp cuối. |
| `limit` | Mặc định 100, bị cắt bởi `TEXT2SQL_QUERY_MAX_ROWS`. Server lấy thêm một dòng để báo `truncated`. |

Mọi model đặt `extra="forbid"`. Kết quả `DatasetResult` gồm `columns`, `rows`, `row_count`, `truncated`, `limit`, `sql`, `parameters`, `pii`, `elapsed_ms`, `warnings`.

### Hai chế độ

- **Có nhóm**: khi có ít nhất một phép tổng hợp, có `group_by` hoặc có `time.granularity`. Mọi mục `select` dạng cột thường phải nằm trong `group_by`, nếu không bị từ chối. Biểu thức theo dòng (không có hàm tổng hợp) bị từ chối ở chế độ này.
- **Dòng thô**: không có các yếu tố trên. Trả từng dòng của kết quả nối, giới hạn bởi `LIMIT`; cho phép biểu thức theo dòng (vẫn qua allowlist). Không có thứ tự mặc định.

### Alias

Alias người dùng đặt được chuẩn hóa: bỏ dấu tiếng Việt, mọi ký tự ngoài `[A-Za-z0-9_]` thành `_`, bỏ `_` ở đầu và cuối, chữ thường, tối đa 48 ký tự; trùng thì thêm `_2`, `_3`. Rỗng thì dùng tên mặc định (`bang_cot`, `sum_bang_cot`, `expr_1`). `time_bucket` được giữ cho cột kỳ. Alias luôn được quote khi đưa vào SQL.

## Quy tắc nối: WHERE và ON

Mọi bước nối là `LEFT JOIN` từ bảng gốc (`t1`) ra ngoài theo `JoinOption.steps`; server dựng lại mệnh đề `FROM` từ catalog và `steps[].on`.

- `placement="where"` (mặc định): điều kiện vào `WHERE`. Lọc theo cột của bảng nối sẽ **loại** các dòng gốc không khớp.
- `placement="join"`: điều kiện vào `ON` của chính bước `LEFT JOIN` tới bảng chứa cột, nên dòng gốc không khớp **được giữ** với giá trị NULL. Chỉ hợp lệ cho cột của bảng không phải gốc; dùng cho cột bảng gốc bị từ chối.

Ví dụ "mỗi khách có bao nhiêu đơn từ 2026, kể cả 0": bảng gốc `customers`, `select` có `{column_id: orders.id, aggregation: "count"}` (đếm cột của bảng nối, không dùng `COUNT(*)`), lọc `orders.created_at >= 2026-01-01` với `placement="join"`. Khách không có đơn trả về 0; với `placement="where"` khách đó biến mất.

## Nhân dòng và khử trùng lặp

Khi một bước nối `multiplies_rows` (1→n), mỗi dòng của các bảng phía trước bị lặp lại, nên `SUM`, `AVG`, `COUNT` trên cột của chúng sẽ bị cộng trùng. Bộ dựng **không trả số sai âm thầm**:

1. Với mỗi hàm tổng hợp, xác định tập bảng mà đối số tham chiếu (`COUNT(*)` và đối số không có cột được gán cho bảng gốc).
2. Kiểm tra nhân dòng **bên trong** tập bảng được tham chiếu: với mỗi bảng tham chiếu, lấy các bước `multiplies_rows` trên đường từ gốc tới nó mà không nằm trên đường tới các bảng tham chiếu còn lại.
   - Hai bảng trở lên có bước như vậy (hai nhánh nhân dòng khác nhau, ví dụ gốc `customers`, `SUM(orders.total + tickets.fee)`): **từ chối** với mọi hàm tổng hợp, vì kết quả là tích chéo giữa các nhánh. Gợi ý tách thành `SUM(orders.total) + SUM(tickets.fee)`.
   - Đúng một bảng có bước như vậy (cột của bảng tổ tiên đi cùng cột của bảng phía sau bước nhân dòng, ví dụ gốc `orders`, `SUM(CASE WHEN items.qty >= 1 THEN orders.total END)`): **từ chối** trừ khi hàm là `MIN`, `MAX` hoặc có `DISTINCT`; mỗi giá trị của bảng tổ tiên bị lặp theo số dòng của bảng sau nên không có cách khử trùng lặp nào đúng cho mọi ý định. Gợi ý chọn bảng chi tiết nhất làm gốc (ví dụ `items`), tách hàm tổng hợp hoặc dùng `MIN`/`MAX`/`COUNT(DISTINCT ...)`.
3. Lấy đường đi từ bảng gốc tới các bảng tham chiếu trên cây nối. Nếu có bước `multiplies_rows` **nằm ngoài** đường đi này thì hàm tổng hợp bị nhân dòng và được khử trùng lặp như dưới đây.
4. Hàm `MIN`, `MAX` và mọi hàm có `DISTINCT` không bị ảnh hưởng nên giữ nguyên. `SUM`, `AVG`, `COUNT` bị nhân dòng thì được **tổng hợp trước trong CTE**: truy vấn được dựng thành `WITH "base" AS (...)`, trong đó mỗi khóa khử trùng lặp có một cột

   ```sql
   CASE WHEN <khóa chính của bảng nguồn> IS NOT NULL
        THEN ROW_NUMBER() OVER (PARTITION BY <các cột nhóm>, <khóa chính các bảng trên đường đi từ gốc>) END
   ```

   và hàm tổng hợp ngoài chỉ lấy dòng có số thứ tự 1, ví dụ `SUM(CASE WHEN "_r1" = 1 THEN "_v1" END)`. Mỗi dòng của bảng nguồn được tính đúng một lần trong mỗi nhóm; phần `IS NOT NULL` bỏ các dòng không khớp của `LEFT JOIN`.
5. Kết quả kèm cảnh báo `đã khử trùng lặp theo khóa chính ...` trong `warnings`.

Khóa lấy từ data dictionary: các cột `is_primary_key` (coi là NOT NULL), nếu không có thì một cột `is_unique` mà metadata nguồn xác nhận NOT NULL (`DatabaseColumn.is_nullable = false`). Cột duy nhất cho phép NULL **không** dùng làm khóa: điều kiện `IS NOT NULL` sẽ bỏ các dòng có khóa NULL (đếm thiếu) và `PARTITION BY NULL` gộp các dòng khác nhau. **Từ chối** bằng `Text2SqlInvalidRequest` khi cần khử trùng lặp mà một bảng trên đường đi chưa khai báo khóa; thông báo gợi ý chọn bảng chứa cột cần tổng hợp làm bảng gốc, bỏ bảng gây nhân dòng, dùng `count_distinct`/`min`/`max` hoặc khai báo khóa chính.

Ngữ nghĩa theo **hạt của bảng gốc**: cột của bảng nối kiểu n→1 (không nhân dòng, ví dụ gốc `orders` nối `customers`) được tính một lần cho mỗi dòng gốc, nên `SUM(customers.credit)` với gốc `orders` cộng hạn mức theo từng đơn. Trường hợp này hợp lệ nhưng có cảnh báo; muốn mỗi khách tính một lần thì chọn `customers` làm gốc. Ở chế độ dòng thô, cảnh báo nhân dòng của `JoinOption` được trả lại nguyên văn.

Ví dụ (gốc `orders`, nối `items` nhân dòng):

```sql
WITH "base" AS (
  SELECT t1."status" AS "_g1", t1."total" AS "_v1",
         CASE WHEN t1."id" IS NOT NULL THEN ROW_NUMBER() OVER (PARTITION BY t1."status", t1."id") END AS "_r1",
         t2."qty" AS "_v2"
  FROM "public"."orders" AS t1 LEFT JOIN "public"."items" AS t2 ON t2."order_id" = t1."id")
SELECT "_g1" AS "orders_status", SUM(CASE WHEN "_r1" = 1 THEN "_v1" END) AS "doanh_thu", SUM("_v2") AS "so_luong"
FROM "base" GROUP BY "_g1" ORDER BY "doanh_thu" DESC NULLS LAST LIMIT :p0
```

## Biểu thức

`dataset/expression.py` tái dùng `ALLOWED_NODES`, `ALLOWED_CAST_TYPES`, giới hạn độ dài và số nút của `query/expression.py`:

- Cột viết dạng `bang.cot` (tên bảng không kèm schema); thiếu tên bảng, có schema, bảng không thuộc phương án nối, cột không tồn tại hoặc tên bảng trùng giữa các bảng đã nối (khác schema) đều bị từ chối. Cột được viết lại thành `tN."cot"` theo catalog.
- Từ chối: hàm ngoài allowlist (ví dụ `pg_sleep`, `version`), subquery, window, nhiều câu lệnh, `*` ngoài `COUNT(*)`, `bang.*`, kiểu ép lạ (kể cả `CHAR`, vì Postgres hiểu là `char(1)`), lồng ngoặc/hàm quá sâu, hàm tổng hợp lồng nhau, `DISTINCT` ngoài hàm tổng hợp hoặc nhiều cột, hàm tổng hợp nhiều đối số.
- Biểu thức có hàm tổng hợp: mọi cột phải nằm bên trong hàm tổng hợp. Biểu thức không có hàm tổng hợp là biểu thức theo dòng, chỉ dùng ở chế độ dòng thô.
- Mọi hằng (chuỗi, số) trong biểu thức được thay bằng tham số bind (`:pN`); SQL sinh ra không chứa giá trị do LLM viết.

## Dữ liệu cá nhân (PII)

- Cột `contains_pii` được chọn hoặc nhóm (sẽ bị che), `count`/`count_distinct` được phép; `min`/`max` trả giá trị thật nên cột kết quả được đánh dấu và che.
- Từ chối: lọc theo cột PII, dùng cột PII làm cột thời gian, `sum`/`avg` trên cột PII, tham chiếu cột PII trong `expression`.
- `execute` che kết quả bằng `PiiMasker` như `query_metric`: cột đánh dấu PII thay toàn bộ, các cột còn lại (trừ `count`, `count_distinct`, `sum`, `avg` qua `column_id` và cột kỳ) được quét bằng Presidio.

## Thực thi

`DatasetQueryService.prepare(connection_id, join, plan)` kiểm tra connection, nạp catalog và gọi `compile_dataset_query`. `execute(compiled, source_url, confirmation)` chạy qua `run_read_only` (transaction `REPEATABLE READ` chỉ đọc, `statement_timeout`, `lock_timeout`, TimeZone UTC), định dạng ô bằng `format_cell`, che PII và trả `DatasetResult`. `resolve_source` dùng lại cách giải mã URI của `QueryService`.

Server kiểm tra `JoinOption` trước khi dùng: alias dạng `tN`, mỗi bước nối từ một alias đã có, `table_ids` khớp các bảng trong bước nối và thuộc connection; sai thì yêu cầu gọi lại `plan_join`.

## Giới hạn hiện tại

- Chỉ PostgreSQL. `time` luôn lọc trong `WHERE`; muốn giữ dòng gốc không khớp theo khoảng thời gian thì dùng `filters` với `placement="join"`.
- Không nhóm theo biểu thức; không `HAVING`. Một hàm tổng hợp dùng cột của hai nhánh nhân dòng khác nhau **bị từ chối** (kể cả `MIN`/`MAX`/`DISTINCT`); một hàm `SUM`/`AVG`/`COUNT` trộn cột của bảng tổ tiên với cột của bảng phía sau bước nhân dòng **bị từ chối** (kể cả biểu thức có nghĩa theo từng dòng như `SUM(orders.total * items.qty)` với gốc `orders`; hãy chọn `items` làm gốc).
- Khử trùng lặp cần khóa chính hoặc cột duy nhất NOT NULL khai báo trong data dictionary.

## Kiểm thử

`tests/test_text2sql_dataset_compiler.py`: phần đơn vị chạy trên SQLite in-memory (catalog tổng hợp, `JoinGraph`); lớp `DatasetPostgresTests` chỉ chạy khi đặt `POSTGRES_TEST_URL` và kiểm tra trên PostgreSQL thật: không cộng trùng khi nối 1→n, `placement=join` giữ khách không có đơn còn `where` loại đi, `LEFT JOIN` giữ dòng không khớp, nhóm theo kỳ khi có nhân dòng, che PII, từ chối khóa duy nhất cho phép NULL, từ chối hàm tổng hợp trộn bảng tổ tiên với bảng nhân dòng hoặc trộn hai nhánh nhân dòng.
