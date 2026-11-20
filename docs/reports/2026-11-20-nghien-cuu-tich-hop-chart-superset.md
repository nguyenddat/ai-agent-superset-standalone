# Nghiên cứu: biểu đồ cho câu trả lời và tích hợp Superset (người dùng vẫn chọn loại biểu đồ)

**Ngày:** 2026-11-20. **Loại:** nghiên cứu, chưa sửa code. **Phạm vi:** tab `Hỏi dữ liệu` (`frontend/features/text2sql/`), route chat `POST /api/v1/text2sql/chat` và `/chat/stream`, lưu lượt ở `conversation`, đồng bộ Superset ở `metric_management`.

## 1. Tóm tắt

- Mọi dữ liệu cần để vẽ biểu đồ **đã có sẵn** trong event `tool` (`columns`, `rows`) và trong `results[]` của lượt đã lưu. Frontend đã cài `recharts` **3.8.0** và có `components/ui/chart.tsx` (shadcn) cùng `components/stat-charts.tsx`, nên vẽ tại chỗ không cần thư viện mới.
- Superset **không chạy** ở máy này lúc nghiên cứu (cổng 8089 không trả lời, không có container Superset), `.env` của standalone **không có** `SUPERSET_URL`, và database của app có **0** database Superset, **0** user Superset, 16 metric đều `origin = manual`. Nghĩa là hiện chưa có ánh xạ metric hay database nào sang Superset để dựa vào.
- Bản Superset đích là **6.1.0** (image `text-to-bi-superset:6.1.0`, `FROM apache/superset:6.1.0` trong `ai-agent-superset-extension/simulation/superset/Dockerfile`, cổng mặc định 8089). Các API và tên `viz_type` trong báo cáo được kiểm bằng cách đọc mã nguồn Superset trong image này (chạy container tạm, không mở cổng, không ghi gì vào Superset).
- **Nhúng Superset vào app không đáng làm:** guest token của 6.1.0 chỉ cấp quyền cho **dashboard** (`GuestTokenResourceType` chỉ có `DASHBOARD`), cờ `EMBEDDED_SUPERSET` mặc định tắt, Talisman mặc định gửi `X-Frame-Options: SAMEORIGIN`. Mỗi câu trả lời sẽ phải tạo dataset, chart và dashboard trong Superset.
- **Đề xuất:** làm kiểu **lai**, chia ba giai đoạn:
  1. Backend dựng `chart` spec bằng code (không dùng LLM). Frontend vẽ bằng Recharts, có bộ chọn loại biểu đồ, và lưu lựa chọn của người dùng theo lượt.
  2. Nút **"Mở trong Superset"**: tạo permalink chỉ ghi vào bảng key-value của Superset. Dùng `POST /api/v1/explore/permalink` khi metric đến từ Superset; trường hợp còn lại dùng `POST /api/v1/sqllab/permalink`.
  3. Nút **"Lưu thành chart"** (tùy chọn, chỉ khi người dùng bấm): tạo dataset ảo và chart thật qua `POST /api/v1/dataset/` và `POST /api/v1/chart/`.

## 2. Hiện trạng đã kiểm

### 2.1 App đang nói chuyện với Superset thế nào

`backend/modules/metric_management/services/superset_client.py` (`SupersetClient.fetch_snapshot`) dùng `httpx` 0.28.1 (theo `uv.lock`), timeout 20 giây và `follow_redirects=False`. Trình tự gọi:

1. `POST /api/v1/security/login` với `{"username", "password", "provider": "db", "refresh": false}`, lấy `access_token` rồi gửi header `Authorization: Bearer`.
2. Phân trang `GET /api/v1/security/users/`, `GET /api/v1/database/`, `GET /api/v1/dataset/` với `q=(page:N,page_size:100)`.
3. `GET /api/v1/dataset/{id}` cho từng dataset để lấy `metrics`.

Client này **chỉ đọc**. Nó không lấy CSRF token và không giữ token giữa các lần gọi; mỗi lần sync đăng nhập lại. Cấu hình nằm ở `backend/core/setting.py` (dòng 21 đến 23: `superset_url`, `superset_username`, `superset_password: SecretStr`). Route là `POST /api/v1/metrics/superset/sync` (`routes/router_metric.py`), mô tả ở `docs/handbook/modules/metric_management/api-dong-bo-superset.md`.

Dữ liệu đồng bộ (`MetricService.sync_superset`):

- `metrics`: `origin='superset'`, `source_url`, `source_metric_id`, `source_dataset_id`, `source_database_id` (trỏ tới `superset_databases`), `source_schema`, `source_table`, `source_sql` (với dataset ảo), `format` (`d3format`) và `table_id`. `table_id` chỉ được gắn khi dataset là bảng vật lý và database Superset đã liên kết với connection.
- `superset_databases`: `source_id` (id database trong Superset), `name`, `backend`, `connection_id`. `connection_id` được liên kết tay qua `PUT /api/v1/metrics/superset/databases/{id}/link`.
- `superset_users`: `source_id`, `username`, `email`.

Đây là cầu nối duy nhất giữa connection của app với `database_id` của Superset, và giữa metric của app với `dataset_id`, `metric_name` của Superset.

Kiểm tra trên database của app (`SELECT count(*)`, chỉ đọc qua `docker exec` vào container `postgres`):

| Bảng | Kết quả |
| --- | --- |
| `superset_databases` | 0 dòng |
| `superset_users` | 0 dòng |
| `metrics` | 16 dòng, tất cả `origin = manual` |

### 2.2 Superset đích

| Mục | Giá trị | Nguồn |
| --- | --- | --- |
| Phiên bản | `apache-superset` **6.1.0** | `importlib.metadata.version` trong image `text-to-bi-superset:6.1.0` |
| Compose | Service `superset` và `superset-init`, cổng `${SUPERSET_PORT:-8089}:8088` | `ai-agent-superset-extension/docker-compose.yml` |
| Cấu hình | Chỉ `FEATURE_FLAGS = {"ENABLE_EXTENSIONS": True}`; không bật `EMBEDDED_SUPERSET`, không đổi `TALISMAN_CONFIG` | `simulation/superset/superset_config.py` |
| Dashboard mẫu | Có sẵn: `big_number_total`, `echarts_timeseries_line`, `echarts_timeseries_bar` (cả trục X là chuỗi `ten_thanh_pho`), `table`, dataset trên `Weather Warehouse` | `simulation/superset/bootstrap_dashboard.py` |
| Đang chạy? | **Không**: `curl http://localhost:8089/health` không có phản hồi; `docker ps -a` không có container Superset | Kiểm lúc 2026-11-20 |
| Compose của standalone | Không có service Superset; `SUPERSET_*` mặc định rỗng | `compose.yaml` |
| Git history | Chỉ commit `df84216 feat(metric-management): add metric CRUD and one-way Superset sync` nhắc tới Superset | `git log` |

Từ container backend, địa chỉ Superset khác địa chỉ trình duyệt (handbook đã ghi `http://host.docker.internal:8089`). Link "Mở trong Superset" vì vậy cần một biến riêng cho URL công khai (mục 7).

### 2.3 Dữ liệu biểu đồ đang có trong luồng chat

- `AgentStepOut` (`backend/modules/text2sql/schemas/schema_text2sql.py`, dòng 157) gồm `tool`, `arguments`, `sql`, `columns`, `rows`, `row_count`, `truncated`, `notes`, `error`. **Không có kiểu cột**. `rows` đã qua `json_cell` (`agent_tools.py`), nên `date`/`datetime` thành chuỗi ISO và `Decimal` thành số, và frontend phải đoán lại kiểu (`query-result.tsx`: regex `NUMERIC`, `DATE`, `DATETIME`).
- `query_metric` có ngữ nghĩa sẵn trong `arguments` (`QueryMetricArgs` ở `services/sql_builder.py`): `metric`, `group_by`, `time_grain{column, grain ∈ day|week|month|quarter|year}`, `filters[{column, operator, value}]`, `order_by`, `limit`. `run_sql` chỉ có `sql` và `purpose`.
- Catalog (`services/agent_catalog.py`) có nhãn và kiểu: `ColumnInfo.label`, `ColumnInfo.data_type`, `MetricInfo.label`, `MetricInfo.format`. **`MetricInfo` không có `origin`, `source_dataset_id`, `source_metric_id`**, nên muốn ánh xạ sang Superset phải bổ sung các trường này.
- Lượt đã lưu (`conversation_turns.results`, JSON) giữ `position`, `kind`, `tool`, `sql`, `columns`, `rows`, `row_count`, `truncated` (thêm `metric.name` với `query_metric`) cho mỗi bước dữ liệu thành công (`stored_results` trong `chat_service.py`, `docs/handbook/modules/conversation/ghi-luot-tu-pipeline.md`). Service cắt còn tối đa `CONVERSATION_MAX_STORED_ROWS` dòng mỗi mục và đặt `stored_truncated`, nên lượt mở lại có thể có ít dòng hơn lúc trả lời. Cột `steps` giữ **mọi** bước (kể cả `get_metric`, `ask_user`) theo đúng thứ tự nhưng không có dòng; khi mở lại, `storedQuestions()` trong `use-chat.ts` ghép từng bước với mục `results` cùng `position`, `tool`, `sql` và **chỉ chép `columns`, `rows`**. Bảng chưa có cột nào cho trạng thái hiển thị. Hiện chỉ đánh giá (`PUT .../turns/{turn_id}/feedback`) là thao tác người dùng được lưu theo lượt.
- Frontend: `chat-turn.tsx` (`dataResults`) lấy mọi bước `query_metric`, `run_sql`, `get_column_values` thành công và vẽ `QueryResult` với hai tab, "Bảng"/"Số liệu" và "SQL".
- Tiền lệ trong extension (chỉ đọc): `extensions/ai-agents/frontend/src/features/chat/components/QueryResultView.tsx` có `chartPlan()`. Hàm này vẽ đường hoặc cột theo thời gian khi có một chiều thời gian (tối đa 8 series, quá thì small multiples tới 24 nhóm), vẽ cột xếp hạng khi chỉ có một chiều nhóm, còn lại giữ bảng; phép so sánh hai kỳ cũng giữ bảng. Kết quả backend của extension mang sẵn `dimensions[].temporal`, `metrics[].label/unit` và `presentation`. Extension tự vẽ SVG, **không** dùng Superset để render.

### 2.4 Hình dạng kết quả thật theo loại câu hỏi

Lấy từ `scripts/text2sql_eval/results/a2-final-x2.json` (98 lần hỏi). Với mỗi câu đơn, script đọc bước dữ liệu thành công cuối cùng và phân loại kiểu cột theo giá trị (script nháp ở thư mục scratchpad, không thuộc repo):

| Loại | Hình dạng chiếm đa số (số lần) | Ví dụ cột |
| --- | --- | --- |
| T1 Tra cứu | 1 dòng × 1 số (18/24); 2 đến 12 dòng chữ + số (2) | `nhiet_do_cao_nhat`; `ten_thanh_pho, nhiet_do_trung_binh` |
| T2, T3, T4, T9, T15 | 1 dòng × 1 số (12/13, 8/8, 4/4, 3/3, 7/7) | `tong_luong_mua`, `so_ngay_co_mua`, `ty_le_nap_thanh_cong` |
| T5 Liệt kê | 2 đến 12 dòng chữ (3); chữ + số; chữ + ngày + số (có lần trên 12 dòng) | `ten_thanh_pho, ngay_key, gio_giat_toi_da_kmh` |
| T6 Phân nhóm | 2 đến 12 dòng chữ + số (4/4) | `ten_thanh_pho, tong_luong_mua`; `vung_khi_hau, nhiet_do_trung_binh_c` |
| T7 Cực trị | 1 dòng chữ + số (9); 2 đến 12 dòng chữ + số (3) | `ten_thanh_pho, nhiet_do_cao_nhat` |
| T8 So sánh | 2 dòng chữ + số (2); 2 dòng ngày + số (1) | `ten_thanh_pho, nhiet_do_cao_nhat`; `ngay_key, tong_luong_mua` |
| T10 Xu hướng | ngày + số, 2 đến 12 dòng (4/6; chỉ 1 lần dùng `time_grain`, còn lại `group_by` cột ngày) | `ngay_key, nhiet_do_cao_nhat` |
| T11 Phân bố | 1 số (2); chữ + số đếm (2) | `ten_dieu_kien, so_lan` |
| T12 Bất thường | danh sách chữ (2/2) | `ten_thanh_pho` |
| T13 Tương quan | 1 dòng nhiều số (3); nhóm chữ + 2 số (1) | `pearson_r, ...`; `nhom_ngay, so_ngay, nhiet_do_cao_nhat_tb_c` |
| T22 Định nghĩa | không có dữ liệu (6/6) | |

Từ bảng này rút ra ba điểm:

1. Khoảng **55%** kết quả có dữ liệu (58/105 câu đơn có bước dữ liệu thành công; 49% nếu tính cả 13 câu không có dữ liệu) là **một con số**, nên biểu đồ không giúp gì; ô KPI hiện có (`single` trong `query-result.tsx`) là đủ. Lưu ý `single` chỉ nhận đúng 1 dòng × 1 cột, nên quy tắc `kpi` "1 dòng, 1 đến 3 số" ở mục 3.3 cần mở rộng thẻ số. Bảng trên phân loại theo `question_type` mà bước tiền xử lý gán cho từng câu đơn, không theo nhóm câu của bộ đánh giá.
2. Phần có ích cho biểu đồ là **chữ + số** (T6, T7 top-k, T8, T11) và **ngày + số** (T10, T8 theo ngày).
3. Chuỗi thời gian thường đến từ `group_by` trên cột ngày chứ không qua `time_grain`, nên phải nhận ra chiều thời gian theo **kiểu cột**, không chỉ theo `time_grain`.

## 3. Phương án 1: vẽ trong frontend của app

### 3.1 Thư viện

| Lựa chọn | Đánh giá |
| --- | --- |
| **Recharts 3.8.0** (đã cài, `frontend/node_modules/recharts/package.json`) | Đã dùng ở `stat-charts.tsx`, `connection-overview.tsx`, `knowledge-growth.tsx`; `components/ui/chart.tsx` (shadcn) cấp `ChartContainer`, `ChartTooltip` và màu `--chart-1..5` theo theme sáng/tối. Đã kiểm tra các export `BarChart`, `LineChart`, `AreaChart`, `PieChart`, `ScatterChart`, `ComposedChart`, `Brush`, `ReferenceLine` đều có. **Chọn phương án này.** |
| ECharts (`echarts-for-react`) | Giống họ chart của Superset (`echarts_*`), nhưng thêm khoảng 1 MB và lệch kiểu với shadcn. Không cần. |
| Vega-Lite, Observable Plot | Spec khai báo đẹp nhưng thêm phụ thuộc mới, khó đồng bộ theme. Không cần. |

### 3.2 Bộ loại biểu đồ của app và ánh xạ sang Superset 6.1.0

Tên `viz_type` được kiểm trong enum `VizType` của bundle `superset/static/assets/8115.*.entry.js` (image 6.1.0). Thời gian gom (time grain) được kiểm trong `superset/constants.py`.

| `chart_type` (app) | Khi nào hợp lý | Recharts | `viz_type` Superset 6.1.0 |
| --- | --- | --- | --- |
| `kpi` | 1 dòng, 1 đến 3 số | thẻ số (đã có) | `big_number_total` |
| `table` | Luôn có mặt; mặc định cho danh sách (T5, T12), nhiều cột, quá nhiều dòng | `DataTable` (đã có) | `table` |
| `bar_horizontal` | Chữ + số, xếp hạng, nhãn dài (T6, T7 top-k, T11 đếm) | `BarChart layout="vertical"` (như `GroupBars`) | `echarts_timeseries_bar` với trục X là cột phân loại; hướng ngang dùng control `orientation` (**cần thử trên Superset thật**) |
| `bar` | Chữ hoặc ngày + số, ít nhóm; T8 hai vế; chuỗi ngày của số cộng dồn (lượng mưa) | `BarChart` | `echarts_timeseries_bar` |
| `line` | Ngày + số, từ 3 điểm (T10), giá trị không cộng dồn (nhiệt độ) | `LineChart` | `echarts_timeseries_line` |
| `area` | Như `line`, số cộng dồn | `AreaChart` | `echarts_area` |
| `pie` | Chữ + số **cộng dồn, không âm**, từ 2 đến 6 nhóm (tỷ trọng, T11 phân bố) | `PieChart` | `pie` |
| `scatter` | Hai cột số, nhiều dòng (T13 khi trả từng cặp) | `ScatterChart` | `bubble_v2` (cần `x`, `y`, `size`, `entity`); `echarts_timeseries_scatter` chỉ dùng cho trục thời gian |

Thời gian gom: `day → P1D`, `week → P1W`, `month → P1M`, `quarter → P3M`, `year → P1Y`. Chuỗi nhiều nhóm (ngày + chữ + số) dùng `groupby: [cột chữ]` trong `echarts_timeseries_*`.

### 3.3 Gợi ý tự động: quy tắc bằng code

Đầu vào: kiểu từng cột, số dòng, `question_type` của câu đơn và tính cộng dồn của metric. Tính cộng dồn suy từ biểu thức metric: chỉ gồm `SUM` hoặc `COUNT` thì cộng dồn được; `AVG`, `MAX`, `MIN` hoặc tỷ lệ thì không. Quy tắc theo thứ tự ưu tiên:

1. Không có dòng, hoặc chỉ có cột chữ: `table` (T5, T12).
2. Một dòng: `kpi`. Không đưa ra bộ chọn biểu đồ, chỉ có tab "Bảng".
3. Có một cột thời gian và một số; tùy chọn thêm một cột chữ có không quá 8 giá trị (chuỗi):
   - Số cộng dồn: gợi ý `bar`, thay thế là `line`, `area`.
   - Còn lại: gợi ý `line`, thay thế là `bar`.
   - Ít hơn 3 điểm (T8 hai ngày): `bar`.
4. Một cột chữ và một số:
   - T7 hoặc có `order_by`/`limit`: `bar_horizontal` sắp giảm dần.
   - T8 với 2 hoặc 3 dòng: `bar`.
   - T11 hoặc T6 với số cộng dồn không âm và tối đa 6 nhóm: gợi ý `bar_horizontal`, cho phép `pie`.
   - Trên 30 nhóm: `table` (vẫn cho chọn `bar_horizontal` kèm cảnh báo "chỉ hiện 30 nhóm đầu").
5. Một cột chữ và nhiều số (T13 dạng nhóm): `bar` nhóm (grouped), thay thế là `table`.
6. Hai cột số, từ 5 dòng trở lên, không có chiều nào khác: `scatter`.
7. Còn lại: `table`.

`question_type` chỉ là **gợi ý phụ**, vì phân loại có thể sai và đã thấy T1 cũng có thể trả nhiều thành phố. Hình dạng dữ liệu luôn quyết định: loại nào không vẽ được với dữ liệu đó thì không hiện trong bộ chọn. Khi `truncated = true`, biểu đồ hiện cảnh báo "chỉ vẽ N dòng đầu".

Có nên để LLM chọn biểu đồ không? **Không ở bước đầu.** Các lý do:

- Quy tắc trên phủ được hình dạng thật đã thấy.
- Cách làm bằng code chạy tất định, kiểm thử được và không tốn thêm token.
- Agent hiện đã tối đa 12 bước công cụ cho mỗi câu.

Có thể thêm sau một trường tùy chọn `presentation` trong câu trả lời của agent, theo kiểu `presentation` của extension, nếu thấy nhu cầu.

## 4. Phương án 2: để Superset render

Các endpoint dưới đây đều có trong 6.1.0 (đã đọc mã nguồn trong image):

| Mục đích | Endpoint | Payload chính (đã kiểm schema) | Ghi vào Superset? |
| --- | --- | --- | --- |
| Link Explore từ trạng thái biểu đồ | `POST /api/v1/explore/permalink` | `ExplorePermalinkStateSchema`: `formData` (bắt buộc, phải có `datasource: "<id>__table"`), `urlParams`, `chartState`. Trả `{key, url}`; url dạng `/superset/explore/p/<key>/` | Chỉ 1 dòng key-value. `CreateExplorePermalinkCommand` gọi `check_chart_access(datasource_id, ...)`, nên **người tạo phải có quyền trên dataset** |
| Form data tạm | `POST /api/v1/explore/form_data` | `datasource_id`, `datasource_type`, `form_data` (chuỗi JSON) | Cache, có hạn |
| Link SQL Lab mang SQL | `POST /api/v1/sqllab/permalink` | `SqlLabPermalinkSchema`: `dbId`, `name`, `sql` **bắt buộc** (thiếu `name` thì 400 `Missing data for required field`, đã thử); `schema`, `catalog`, `autorun` tùy chọn | Chỉ 1 dòng key-value; response `{key, url}`, url dạng `/sqllab/p/<key>/` |
| Dataset ảo từ SQL | `POST /api/v1/dataset/` | `DatasetPostSchema`: `database` (bắt buộc), `table_name` (bắt buộc), `schema`, `sql`, `owners`, `external_url`, `is_managed_externally` | **Có**. `table_name` phải duy nhất theo `(database, catalog, schema)` (`DatasetDAO.validate_uniqueness`) |
| Chart đã lưu | `POST /api/v1/chart/` | `slice_name`, `viz_type`, `datasource_id`, `datasource_type`, `params` (chuỗi JSON form_data), `query_context`, `owners`, `dashboards` | **Có** |
| Dữ liệu theo hình dạng Superset | `POST /api/v1/chart/data` | `ChartDataQueryContextSchema`: `datasource{id,type}`, `queries[]`, `form_data`, `result_type`, `result_format` | Không ghi, nhưng chạy lại truy vấn |
| Nhúng | `POST /api/v1/security/guest_token/` + `@superset-ui/embedded-sdk` | `GuestTokenCreateSchema`: `user`, `resources[{type, id}]`, `rls[{dataset, clause}]` | **Chỉ `type = dashboard`** trong 6.1.0 |

### 4.1 Ánh xạ metric và database

**Metric `origin = superset` với kết quả từ `query_metric`** (đường tốt nhất, không cần tạo dataset). Form data dựng trên dataset gốc `source_dataset_id`:

```json
{
  "datasource": "<source_dataset_id>__table",
  "viz_type": "echarts_timeseries_line",
  "x_axis": "ngay_key",
  "time_grain_sqla": "P1D",
  "metrics": ["<metric.name>"],
  "groupby": [],
  "adhoc_filters": [
    {"expressionType": "SIMPLE", "clause": "WHERE", "subject": "ten_thanh_pho", "operator": "==", "comparator": "Ha Noi"},
    {"expressionType": "SIMPLE", "clause": "WHERE", "subject": "ngay_key", "operator": "TEMPORAL_RANGE", "comparator": "2026-11-13 : 2026-11-20"}
  ],
  "row_limit": 1000
}
```

Phạm vi thật của đường này hẹp hơn tên gọi:

- `MetricInfo.table_id` là kiểu bắt buộc, và `table_id` của metric Superset chỉ được gắn khi dataset là bảng vật lý của database đã liên kết. Metric Superset trên dataset ảo có `source_sql`, và `build_metric_query` từ chối dựng (`ToolError` yêu cầu dùng `run_sql`), nên kết quả của nó luôn đi đường `run_sql`, tức chế độ `sqllab` hoặc dataset ảo, không phải `explore`.
- Tên cột trong `QueryMetricArgs` là tên cột của bảng vật lý trong app. Dataset Superset trỏ cùng bảng nên tên trùng, nhưng `x_axis` + `time_grain_sqla` chỉ gom theo thời gian khi cột đó được đánh dấu thời gian (`is_dttm`) trong dataset Superset. Dataset mẫu của extension dùng cột thời gian `thoi_diem_quan_sat` (gom `PT1H`), còn `ngay_key` trong ví dụ trên chỉ để minh họa; phải đọc `columns[].is_dttm` của dataset khi dựng form data.
- Tên metric gửi trong `metrics` là `metric_name` của Superset; sync ghi đúng tên này vào `metrics.name` (`metric_service.py`), nên dùng được trực tiếp.

Ánh xạ toán tử (đã kiểm `FilterOperator` trong `superset/utils/core.py`):

| App | Superset |
| --- | --- |
| `equals`, `not_equals` | `==`, `!=` |
| `greater_than`, `greater_than_or_equal` | `>`, `>=` |
| `less_than`, `less_than_or_equal` | `<`, `<=` |
| `in`, `not_in` | `IN`, `NOT IN` |
| `contains`, `not_contains` | `ILIKE`, `NOT ILIKE` với `%giá trị%`; app thoát ký tự `%`, `_` (`_escape_like` trong `sql_builder.py`) còn Superset đưa nguyên chuỗi vào, nên phải tự thoát trước khi gửi |
| `is_null`, `is_not_null` | `IS NULL`, `IS NOT NULL` |
| Cặp `greater_than_or_equal` + `less_than` trên cùng một cột ngày (cách agent hiện biểu diễn khoảng ngày, đã thấy ở mọi câu T10 trong `a2-final-x2.json`; `QueryMetricArgs` không có kiểu "khoảng ngày" riêng) | Gộp thành một `TEMPORAL_RANGE` `"from : before"` (Superset hiểu là nửa mở `[from, before)`), hoặc giữ hai bộ lọc `>=`, `<` |

Quy tắc chuyên gia mà `query_metric` tự áp (ghi trong `notes`) phải được chuyển thành `adhoc_filters` dạng `{"expressionType": "SQL", "clause": "WHERE", "sqlExpression": ...}`. Thiếu bước này thì biểu đồ trong Superset ra **số khác** với câu trả lời. Đây là rủi ro lớn nhất của đường này, nên `sql_builder` cần trả ra danh sách điều kiện đã áp ở dạng có cấu trúc, không chỉ ghi chú.

**Metric `manual` hoặc kết quả từ `run_sql`:** Superset không có dataset tương ứng. Có hai cách:

- (a) **SQL Lab permalink** với `dbId` lấy từ `superset_databases.source_id` của dòng có `connection_id` bằng connection của hội thoại. Người dùng mở SQL Lab với đúng SQL đã chạy, rồi tự bấm "Create chart" của Superset. Cách này không tạo dataset. Lưu ý: lệnh tạo SQL Lab permalink **không** kiểm quyền trên database (khác Explore permalink), nhưng người **mở** link phải có quyền vào SQL Lab (vai trò `sql_lab` hoặc tương đương) và quyền trên database đó. Người dùng nghiệp vụ thường chỉ có `Gamma`, khi đó link vô dụng. Link mở ra ở trang `/sqllab/p/<key>/`.
- (b) Tạo **dataset ảo** từ SQL (mục 4.3).

Connection chưa liên kết với database Superset nào (như hiện tại) thì **ẩn** nút.

### 4.2 Xác thực và quyền

- **Tài khoản dịch vụ** (đang dùng cho sync): đơn giản, nhưng mọi link và dataset được tạo dưới tên tài khoản này. Người mở link vẫn phải đăng nhập Superset và có quyền đọc dataset hoặc database: permalink không cấp quyền, Superset kiểm quyền khi mở. Vì vậy RLS của Superset vẫn áp đúng **cho người xem**, còn câu trả lời trong app thì không qua RLS của Superset mà chạy bằng URI của connection.
- **Theo từng người dùng:** app hiện **chưa có xác thực**; `user_id` do client gửi (`docs/handbook/kien-truc.md`). Không thể đăng nhập Superset thay người dùng một cách an toàn. Có thể ánh xạ `user_id` sang `superset_users.username` để đặt `owners` cho dataset hoặc chart đã lưu, nhưng ánh xạ này không được xác thực.
- **CSRF:** `WTF_CSRF_ENABLED = True` và `WTF_CSRF_EXEMPT_LIST` của 6.1.0 chỉ miễn `chart/data`, `explore_json`, `log`, `samples`, `cache_dashboard_screenshot`. Các lời gọi POST tạo permalink, dataset, chart cần lấy `GET /api/v1/security/csrf_token/` bằng bearer token, giữ cookie phiên trong cùng `httpx.Client` và gửi header `X-CSRFToken`. Extension **không** phải tiền lệ cho cách này: nó chạy bên trong Superset và chuyển tiếp cookie phiên cùng CSRF token của chính người dùng (`post_json(path, body, cookie_header, csrf_token, ...)` trong `semantic_layer/services/client.py`), không đăng nhập bằng tài khoản dịch vụ. Kết luận CSRF ở trên rút từ cấu hình và đã thử lại trên một Superset 6.1.0 dựng tạm (xem mục "Kiểm tra lại").
- **Token:** client hiện đăng nhập lại mỗi lần gọi. Với nút bấm trong chat nên cache access token trong tiến trình theo hạn JWT, và đăng nhập lại khi nhận 401.

### 4.3 Dataset ảo và dọn dẹp

- Tên đề xuất: `ai_chat_<turn_id 8 ký tự>_<position>_<index>`, đặt `external_url` trỏ về lượt chat, `is_managed_externally = false` để người dùng vẫn sửa được, `owners` là tài khoản dịch vụ (cộng người dùng nếu ánh xạ được).
- SQL đã qua `validate_select`, nhưng Superset sẽ chạy nó bằng **kết nối của Superset** với quyền của Superset, không qua `sql_guard` của app. Bên chạy khác nên kết quả có thể khác (múi giờ: app đặt `TimeZone=Asia/Ho_Chi_Minh` cho phiên, Superset thì không).
- SQL của app có thể chứa ngày cố định (`'2026-11-19'`): dataset ảo "đóng băng" khoảng thời gian, khác với metric của Superset.
- Dọn dẹp: chỉ tạo khi người dùng bấm **"Lưu thành chart"**, không tạo tự động cho mọi câu trả lời. Ghi `superset_dataset_id`, `superset_chart_id` vào lượt để không tạo trùng. Không xóa tự động, vì xóa dataset làm hỏng chart người dùng đã lưu; nếu cần thì có job dọn dataset `ai_chat_*` không có chart sau N ngày (`DELETE /api/v1/dataset/{id}`).

### 4.4 Nhúng (iframe hoặc embedded SDK): không đề xuất

- `@superset-ui/embedded-sdk` bản mới nhất **0.4.0** (npm, 2026-06-18) chỉ có `embedDashboard`. Guest token 6.1.0 chỉ nhận `resources[].type = "dashboard"`. Muốn nhúng một biểu đồ thì phải tạo dataset, chart, dashboard, bật embedded cho dashboard (`POST /api/v1/dashboard/{id}/embedded`), bật cờ `EMBEDDED_SUPERSET`, đổi `GUEST_ROLE_NAME` (mặc định `"Public"`) và `GUEST_TOKEN_JWT_SECRET` (mặc định là chuỗi test).
- Talisman mặc định `frame_options=SAMEORIGIN` (flask_talisman). Muốn iframe trang Explore với `?standalone=1` từ origin của app thì phải nới `TALISMAN_CONFIG`/`frame-ancestors`, và người xem phải có cookie phiên Superset trong iframe khác origin (bị chặn bởi chính sách cookie bên thứ ba của trình duyệt).
- Cờ `EMBEDDABLE_CHARTS = True` chỉ bật nút "Embed code" trong Superset; cách nhúng này cũng cần phiên đăng nhập.
- `POST /api/v1/chart/data` không mang lại gì: app đã có `rows`. Gọi nó nghĩa là chạy lại truy vấn trên một nguồn khác và cần sẵn dataset.

## 5. Phương án 3: lai (đề xuất)

| Tiêu chí | 1. Vẽ tại chỗ | 2. Superset render hoặc nhúng | 3. Lai |
| --- | --- | --- | --- |
| Độ trễ | Tức thì, cùng event `tool` | Phải tạo dataset/chart, rồi iframe tải trang | Tức thì; Superset chỉ khi bấm |
| Cần Superset chạy | Không | Có | Chỉ cho nút |
| Khớp số với câu trả lời | Đúng (cùng `rows`) | Có thể lệch (RLS, múi giờ, quy tắc) | Đúng ở app; Superset có ghi chú "chạy lại trên Superset" |
| Rác trong Superset | Không | Mỗi câu một dataset/chart/dashboard | Chỉ khi "Lưu thành chart" |
| Bảo mật | Không thêm bề mặt | Guest token, frame, đổi cấu hình Superset | Permalink cần đăng nhập Superset |
| Người dùng chọn loại biểu đồ | Bộ chọn trong app | Đổi trong Explore | Cả hai; lựa chọn được mang sang Superset qua `viz_type` |

## 6. Hợp đồng dữ liệu đề xuất

### 6.1 `chart` trong mỗi bước dữ liệu (thêm trường, tương thích ngược)

Thêm hai trường tùy chọn vào `AgentStepOut`, đi cùng event `tool`, `answers[].steps[]` của `/chat` và `results[]` khi lưu:

- `column_types`: kiểu từng cột theo giá trị Python **trước** `json_cell`, nhận một trong `number`, `date`, `datetime`, `text`, `boolean`, `other`. Cách này không còn phải đoán kiểu bằng regex trên chuỗi.
- `chart`: spec biểu đồ dựng bằng code, ví dụ dưới đây.

```json
{
  "column_types": ["date", "number"],
  "chart": {
    "version": 1,
    "suggested": "line",
    "allowed": ["line", "bar", "area", "table"],
    "dimensions": [{"column": "ngay_key", "label": "Ngày", "role": "time", "time_grain": "day"}],
    "series": null,
    "measures": [{"column": "nhiet_do_cao_nhat", "label": "Nhiệt độ cao nhất (°C)", "format": ",.1f", "additive": false}],
    "sort": null,
    "superset": {"mode": "explore", "dataset_id": 12, "viz_type": "echarts_timeseries_line"}
  }
}
```

- `role` nhận `time`, `category` hoặc `series` (chiều chữ thứ hai trên chuỗi thời gian). `superset.mode` nhận `explore` (metric từ Superset), `sqllab` (connection đã liên kết) hoặc `null` (ẩn nút). Spec không chứa thông tin nhạy cảm: `dataset_id` vốn hiện trong UI Superset.
- `chart = null` với `get_column_values` và với lỗi.
- Không đổi event SSE nào và không thêm event mới. Thêm trường vào `tool` là đủ, vì spec dựng ngay khi có `rows`.
- Bản lưu (`results[]`) giữ `column_types` và `chart` (sửa `stored_results` trong `chat_service.py`). `storedQuestions()` trong `use-chat.ts` hiện chỉ chép `columns`, `rows` từ `results` sang bước, nên phải chép thêm hai trường này; nếu quên, lượt mở lại sẽ mất spec và rơi về đường lùi. Lượt cũ không có hai trường này thì frontend tự suy như hiện tại (đường lùi).
- Spec dựng trên đủ dòng (tối đa `TEXT2SQL_QUERY_MAX_ROWS`), còn bản lưu có thể bị cắt (`stored_truncated`). Biểu đồ của lượt mở lại phải hiện cảnh báo dựa trên cả `truncated` lẫn `stored_truncated`.

### 6.2 Lựa chọn của người dùng

Đề xuất **cột mới** `conversation_turns.views` (JSON, nullable) thay vì sửa `results`. `results` là đầu ra của pipeline và nên bất biến; `views` là trạng thái giao diện:

```json
{"1:0": {"chart_type": "bar", "updated_at": "2026-11-20T09:00:00+07:00"}}
```

- Khóa `"<position>:<chỉ số bước>"` dùng đúng `key` mà `chat-turn.tsx` đang tạo (`${item.position}:${index}`), trong đó `index` là chỉ số trong **toàn bộ** `steps` của câu đơn (gồm cả bước tra cứu), không phải chỉ số trong `results`. Frontend dựng lại được khóa này vì cột `steps` giữ đủ bước theo thứ tự. Backend thì cần tìm mục `results` từ khóa để kiểm `chart.allowed`, nên nên lưu thêm `step_index` vào mỗi mục `results` thay vì đếm lại từ `steps`.
- Lượt chờ hỏi lại (`needs_clarification`): lượt chạy tiếp là **lượt mới** (`continued_from`), lượt cũ không đổi. Lựa chọn người dùng đặt trên lượt đang chờ sẽ không tự sang lượt mới; nếu cần thì chép `views` khi `begin_turn` với `resume_id`, hoặc đơn giản là chấp nhận mất.
- Route mới, theo mẫu `PUT .../feedback`: `PUT /api/v1/conversations/{conversation_id}/turns/{turn_id}/views/{result_key}`. Body là `{"user_id": "...", "chart_type": "bar"}`; `chart_type` phải thuộc `chart.allowed` của kết quả đó (sai thì 422), lượt không thuộc `user_id` thì 404. `DELETE` cùng đường dẫn để trở về gợi ý.
- `TurnOut` trả thêm `views`. Không có `user_id` (chế độ không lưu) thì lựa chọn chỉ nằm trong state của `use-chat.ts`.
- Mở rộng sau: mặc định theo người dùng ("luôn mở dạng bảng") lưu trong `localStorage`, không cần backend.
- Superset: khi bấm "Mở trong Superset", backend dùng `chart_type` hiện tại để chọn `viz_type`, nên lựa chọn của người dùng đi theo sang Superset.

### 6.3 Route Superset (giai đoạn 2, 3)

- `POST /api/v1/text2sql/superset-links` với body `{conversation_id, turn_id, user_id, result_key, chart_type}` trả `{"url": "...", "mode": "explore" | "sqllab"}`. Backend đọc kết quả từ lượt đã lưu, **không** nhận SQL hay form data từ client, để client không dùng tài khoản dịch vụ chạy SQL tùy ý.
- `POST /api/v1/text2sql/superset-charts` với cùng body trả `{"chart_id", "dataset_id", "url"}` (giai đoạn 3). Ghi id vào `views[result_key].superset` để không tạo trùng.
- Lỗi: Superset chưa cấu hình hoặc không tới được thì 503 `superset_unavailable` (đã có `SupersetUnavailableError` ở `metric_management/utils/exceptions.py`). Connection chưa liên kết thì 409 `superset_database_not_linked`.

## 7. Kế hoạch làm từng bước

**Giai đoạn 1: biểu đồ tại chỗ và bộ chọn** (không cần Superset)

1. Backend `backend/modules/text2sql/services/chart_spec.py` (mới): `build_chart_spec(step, column_types, question_type, catalog) -> ChartSpec | None` theo quy tắc mục 3.3. Tính cộng dồn bằng sqlglot trên `MetricInfo.expression`; nhãn lấy từ `ColumnInfo.label` và `MetricInfo.label`.
2. `services/agent_tools.py` (`_execute`): ghi `column_types` từ giá trị thô trước `json_cell`.
3. `services/text2sql_agent_service.py`: gắn `chart` khi tạo `AgentStepOut`. Chỗ này biết `question_type` của câu đơn và gửi qua `tool_reporter`.
4. `schemas/schema_text2sql.py`: thêm `ChartSpec`, `column_types`, `chart`. `chat_service.py`: đưa vào `results` khi `complete_turn`.
5. Test: `tests/.../test_chart_spec.py` với các hình dạng ở mục 2.4 (1 số → `kpi`; chữ + số T7 → `bar_horizontal`; ngày + số AVG → `line`; ngày + số SUM → `bar`; số âm → không có `pie`; trên 30 nhóm → `table`; `truncated`). Thêm test hợp đồng cho event `tool` có `chart`.
6. Frontend:
   - `features/text2sql/types.ts`: thêm `ChartSpec`, `column_types`, `chart` vào `ToolStep` và `StoredResult`, thêm `views` vào `StoredTurn`.
   - `features/text2sql/use-chat.ts` (`storedQuestions`): chép thêm `column_types`, `chart` từ mục `results` sang bước khi mở lại lượt.
   - Tạo `features/text2sql/result-chart.tsx` vẽ bằng `ChartContainer` + Recharts; có hàm `fallbackSpec()` cho lượt cũ.
   - Tạo `features/text2sql/chart-picker.tsx` dùng `components/ui/toggle-group.tsx` (đã có), chỉ hiện các loại trong `allowed`.
   - `query-result.tsx`: thêm tab "Biểu đồ", mặc định là tab này khi `suggested` khác `kpi` và `table`.
   - Tuân theo hướng dẫn màu và trục của handbook frontend; số định dạng `vi-VN` như `query-result.tsx`.
7. Lưu lựa chọn:
   - Alembic migration thêm `conversation_turns.views`.
   - `ConversationService.set_view` và `delete_view`, route `PUT`/`DELETE .../views/{result_key}` trong `router_conversation.py`, schema trong `schema_conversation.py`.
   - `frontend/features/text2sql/api.ts` và `use-chat.ts` cập nhật lạc quan (optimistic) như `rate`.
8. Handbook: `docs/handbook/modules/text2sql/api-chat.md` (trường mới của `tool`), `docs/handbook/modules/conversation/ghi-luot-tu-pipeline.md` và `api-luot-hoi-dap.md` (`views`), `docs/handbook/frontend` (biểu đồ kết quả).

**Giai đoạn 2: "Mở trong Superset"** (cần Superset 6.1.0 chạy và đã sync, đã liên kết database)

1. `metric_management/services/superset_client.py`: thêm phiên ghi được (`login`, `csrf_token`, giữ cookie), cache token và các hàm `create_explore_permalink(form_data)`, `create_sqllab_permalink(db_id, name, sql, schema)` (`name` bắt buộc). Cân nhắc chuyển client sang `backend/common/` nếu `text2sql` dùng chung, theo quy ước import trong `quy-uoc-code.md`.
2. `agent_catalog.py`: thêm `origin`, `source_dataset_id`, `source_metric_id` vào `MetricInfo`. `sql_builder.py`: trả các điều kiện quy tắc đã áp ở dạng có cấu trúc để chuyển thành `adhoc_filters`.
3. `services/superset_form_data.py` (mới): dựng form data từ `QueryMetricArgs`, `chart_type` và điều kiện quy tắc (ánh xạ ở mục 4.1). Route `POST /api/v1/text2sql/superset-links`.
4. Cấu hình `SUPERSET_PUBLIC_URL` (địa chỉ trình duyệt, khác `SUPERSET_URL` trong container). Thay host trong `url` mà Superset trả về (`url_for(..., _external=True)` theo host của request backend).
5. Test: client giả với `httpx.MockTransport` cho trình tự login, csrf, permalink; test form data cho từng `chart_type`; test ẩn nút khi chưa liên kết. Kiểm thủ công trên Superset thật: mở link, so số với câu trả lời.

**Giai đoạn 3: "Lưu thành chart"** (tùy chọn): `POST /api/v1/dataset/` (dataset ảo hoặc dataset gốc), rồi `POST /api/v1/chart/` với `params`. Ghi id vào `views`. Viết tài liệu cho quy ước tên `ai_chat_*` và cách dọn dẹp.

## 8. Rủi ro

- **Số trong Superset lệch với câu trả lời** khi chạy lại trên Superset. Có ba nguồn lệch: quy tắc chuyên gia chưa chuyển hết thành bộ lọc, múi giờ phiên khác nhau, RLS của Superset. Cần ghi rõ trên nút: "Superset chạy lại truy vấn với quyền của bạn".
- **PII:** route chat chưa che PII và `results` lưu dòng thô. Biểu đồ chỉ hiển thị lại cùng dữ liệu nên không tăng rủi ro. Riêng dataset ảo đưa SQL sang Superset, nơi người khác có thể thấy nếu có quyền.
- **Tài khoản dịch vụ** cần quyền ghi (`can_write` trên Dataset và Chart, quyền tạo permalink Explore và SQL Lab), rộng hơn quyền đọc của sync hiện nay. Nên tách hai tài khoản.
- **Không có xác thực người dùng trong app:** ai gọi được API của app đều tạo được link hoặc chart dưới tài khoản dịch vụ. Route Superset phải sau lớp truy cập tin cậy, giống ghi chú hiện có cho endpoint sync.
- **Hình dạng bất thường** (pivot rộng, cột số dạng chuỗi, ngày dạng số nguyên `20261119`): quy tắc trả `table` thay vì vẽ sai. Test phải có các ca này.
- Hướng ngang của `echarts_timeseries_bar` (control `orientation`; bundle 6.1.0 có hằng `Horizontal="horizontal"`, `Vertical="vertical"`) và form data của `bubble_v2` **chưa thử** render trên Superset thật.
- **Người xem không có quyền SQL Lab:** link chế độ `sqllab` chỉ dùng được với người có vai trò SQL Lab. Nên hiện nút theo chế độ và ghi rõ yêu cầu quyền, hoặc chỉ bật chế độ này khi người dùng xác nhận có quyền.
- **Cột thời gian chưa đánh dấu trong dataset Superset:** form data `explore` gom thời gian sai hoặc lỗi nếu cột ngày không có `is_dttm` (mục 4.1).
- **Lựa chọn biểu đồ trên lượt chờ hỏi lại** không theo sang lượt chạy tiếp (mục 6.2).
- Chưa xét: link Explore kiểu cũ `/explore/?form_data=<JSON>` (không ghi gì vào Superset). Bundle 6.1.0 vẫn đọc tham số `form_data` nhưng trải các khóa của nó thành tham số gọi `GET /api/v1/explore/`, nên không chắc mọi control được áp; cần thử trước khi coi là phương án thay permalink.

## 9. Câu hỏi cho người dùng

1. Có đồng ý **vẽ tại chỗ bằng Recharts** làm mặc định, còn Superset chỉ là nút "Mở trong Superset" (không nhúng iframe) không?
2. Superset nào sẽ dùng thật: bản 6.1.0 trong `ai-agent-superset-extension` (hiện đang tắt) hay một instance khác? Có cần thêm Superset vào `compose.yaml` của standalone (profile `simulation`) để chạy thử không?
3. Có được phép cho app **ghi** vào Superset không: tạo permalink (ghi key-value, nhẹ), tạo dataset ảo và chart (giai đoạn 3)? Nếu có thì dùng tài khoản dịch vụ riêng nào?
4. Với kết quả `run_sql` hoặc metric `manual`: mở SQL Lab với SQL (không tạo gì trong Superset), hay tạo dataset ảo để mở thẳng Explore?
5. Lựa chọn loại biểu đồ lưu **theo từng kết quả của từng lượt** (đề xuất) là đủ, hay cần thêm mặc định theo người dùng hoặc theo metric?
6. Có cần bộ chọn cho phép đổi cả **chiều và số đo** (ví dụ đổi trục hoặc ẩn series) không, hay chỉ đổi loại biểu đồ?

## Nguồn

- Mã nguồn Superset 6.1.0 trong image `text-to-bi-superset:6.1.0` (đọc bằng container tạm, không mở cổng):
  - `superset/explore/permalink/schemas.py`, `superset/commands/explore/permalink/create.py`
  - `superset/sqllab/permalink/api.py`, `superset/datasets/schemas.py`, `superset/daos/dataset.py`
  - `superset/charts/schemas.py`, `superset/security/guest_token.py`, `superset/security/api.py`
  - `superset/config.py` (`FEATURE_FLAGS`, `TALISMAN_CONFIG`, `WTF_CSRF_EXEMPT_LIST`, `GUEST_ROLE_NAME`)
  - `superset/utils/core.py` (`FilterOperator`, `DatasourceType`), `superset/constants.py` (thời gian gom)
  - `superset/views/explore.py`, `static/assets/8115.*.entry.js` (enum `VizType`)
- npm: `@superset-ui/embedded-sdk` 0.4.0 (`npm view`), <https://www.npmjs.com/package/@superset-ui/embedded-sdk>
- Superset REST API: <https://superset.apache.org/docs/api/>; cấu hình mạng, Talisman và nhúng: <https://superset.apache.org/docs/configuration/networking-settings>
- Recharts: <https://recharts.org/en-US/api>

## Kiểm tra lại (rà soát độc lập, 2026-11-20)

Đã đối chiếu lại với mã nguồn, `uv.lock`, `frontend/node_modules`, database của app (chỉ đọc) và mã nguồn Superset trong image `text-to-bi-superset:6.1.0`. Ngoài đọc mã, đã chạy thử API trên **một Superset 6.1.0 dựng tạm** từ image này: container `--network none`, không mở cổng, metadata SQLite trong container, xóa ngay sau khi chạy; không đụng Superset hay database thật nào.

**Đúng như báo cáo:** Superset 6.1.0; `FROM apache/superset:6.1.0`; cổng `${SUPERSET_PORT:-8089}:8088`; Superset không chạy; `.env` không có `SUPERSET_*` và `compose.yaml` để rỗng; `superset_databases` 0, `superset_users` 0, `metrics` 16 dòng `manual`; luồng gọi và cấu hình của `superset_client.py` (`httpx` 0.28.1, `setting.py` dòng 21 đến 23); `GuestTokenResourceType` chỉ có `DASHBOARD`; `EMBEDDED_SUPERSET=False`, `EMBEDDABLE_CHARTS=True`, `GUEST_ROLE_NAME="Public"`, `GUEST_TOKEN_JWT_SECRET` mặc định, `WTF_CSRF_EXEMPT_LIST`; Talisman mặc định `frame_options=SAMEORIGIN`; các schema permalink, dataset, chart, form_data; `validate_uniqueness`; tên `viz_type`, thời gian gom, `FilterOperator`; `@superset-ui/embedded-sdk` 0.4.0 (2026-06-18); Recharts 3.8.0 và các export; `AgentStepOut`, `json_cell`, `MetricInfo`; số liệu ở mục 2.4 (tính lại ra cùng con số khi phân loại theo `question_type` của tiền xử lý).

**Kết quả chạy thử trên Superset tạm (bearer token từ `/api/v1/security/login`, client giữ cookie):**

| Lời gọi | Kết quả |
| --- | --- |
| `POST /api/v1/explore/permalink` không có CSRF | 400 `The CSRF token is missing` |
| `GET /api/v1/security/csrf_token/` rồi gửi `X-CSRFToken` | 201 `{key, url}`, `url` = `http://<host của request>/superset/explore/p/<key>/` |
| Explore permalink với `datasource` không tồn tại | 404 `Dataset does not exist` |
| `POST /api/v1/sqllab/permalink` thiếu `name` / có `name` | 400 / 201, `url` = `/sqllab/p/<key>/` |
| `POST /api/v1/dataset/` (dataset ảo), `POST /api/v1/chart/` | 201 / 201 |
| `POST /api/v1/chart/data` không có CSRF | 200 (đúng danh sách miễn CSRF) |
| `POST /api/v1/security/guest_token/` với `type: "chart"` | 400 `Must be one of: dashboard.` |

**Đã sửa trong báo cáo:**

1. Mục 4.2: bỏ câu nói extension "làm đúng như vậy". Extension chuyển tiếp cookie phiên và CSRF của chính người dùng, không đăng nhập bằng tài khoản dịch vụ. Kết luận CSRF giờ đã được thử, không còn là "cần thử lại".
2. Mục 4 (bảng endpoint): `POST /api/v1/sqllab/permalink` bắt buộc `dbId`, `name`, `sql`; báo cáo cũ không ghi `name` là bắt buộc. Kế hoạch giai đoạn 2 thêm tham số `name`.
3. Mục 4.1 (ánh xạ toán tử): app không có kiểu "khoảng ngày `{from, before}`"; agent biểu diễn khoảng ngày bằng cặp `greater_than_or_equal` + `less_than`. Thêm ghi chú thoát ký tự cho `ILIKE`.
4. Mục 4.1: thêm phạm vi thật của chế độ `explore` (metric Superset trên dataset ảo có `source_sql` nên luôn đi `run_sql`; cột thời gian phải có `is_dttm`; dataset mẫu dùng `thoi_diem_quan_sat`, không phải `ngay_key`). Thêm yêu cầu quyền SQL Lab cho người mở link `sqllab`.
5. Mục 2.3, 6.1, 6.2, 7: bản lưu còn có `metric.name`, `stored_truncated`; `storedQuestions()` trong `use-chat.ts` chỉ chép `columns`, `rows` nên phải sửa để giữ `column_types`, `chart`; giải thích lại khóa `position:index` (chỉ số trong toàn bộ `steps`); lượt chạy tiếp sau hỏi lại là lượt mới nên `views` không tự theo sang.
6. Mục 2.4: nói rõ 55% là trên 105 câu đơn có dữ liệu (49% trên 118), bảng phân loại theo `question_type` của tiền xử lý; `single` hiện chỉ nhận 1 × 1.
7. Mục 8: thêm rủi ro quyền SQL Lab, cột thời gian chưa đánh dấu, lựa chọn trên lượt chờ hỏi lại, và phương án `/explore/?form_data=` chưa xét.

**Chưa kiểm được:** render thật của `echarts_timeseries_bar` ngang và `bubble_v2`; quyền tối thiểu cho tài khoản dịch vụ (đã chạy thử bằng `Admin`); việc mở link permalink trong trình duyệt; RLS. Các mục này cần một Superset có dữ liệu thật.
