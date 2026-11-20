# Biểu đồ của kết quả truy vấn

Mỗi kết quả dữ liệu của agent (`query_metric`, `run_sql`) mang một spec biểu đồ JSON. Backend sở hữu danh mục loại biểu đồ, mô hình spec và bộ kiểm tra; frontend chỉ vẽ spec đã qua kiểm tra (Recharts). Thiết kế gốc: [báo cáo thiết kế](../../../reports/2026-11-20-thiet-ke-tra-loi-stream-bieu-do.md), mục 4.

Mã nguồn dùng chung ở `backend/common/charts/` (không import `backend.modules`):

| File | Vai trò |
| --- | --- |
| `spec.py` | `ChartSpec` phiên bản 1 (pydantic, `extra="forbid"`), `ChartField`, 32 loại `CHART_TYPES`, bảng màu `PALETTE` (`series-1`…`series-8`, `muted`), `spec_json` (dạng gọn, bỏ giá trị mặc định), `spec_summary` |
| `catalog.py` | `CATALOG`: mỗi loại có nhóm, nhãn tiếng Việt, vai trò (`x`, `y`, `series`, `row`, `path`, `size`, `color`, `goal`, `compare`, `source`, `target`, `label`), kiểu cột nhận (`N` số, `C` phân loại, `T` thời gian), giới hạn điểm/nhóm/series và mô hình `options` |
| `profile.py` | Quy tắc null, khóa phân loại và thời gian, `infer_fields` (đoán kiểu từ JSON cho kết quả cũ), `ResultProfile` |
| `prepare.py` | Thuật toán chuẩn bị dữ liệu dùng chung với frontend, `chart_stats` |
| `validate.py` | `validate_chart` (quy tắc V1–V34), `ChartSpecError`, `ValidatedChart` |
| `suggest.py` | Spec mặc định cho từng loại, ma trận đề xuất, `compatible_types`, `suggest_chart`, `chart_display` |

## Spec

Khóa cấp cao: `version` (luôn 1), `type`, `title`, `subtitle`, `encoding`, `transform` (`filter`, `sort`, `top_n`, `limit`, `index_to`, `cumulative`), `orientation`, `axes` (`x`, `y`; **không có trục y thứ hai**), `format`, `reference_lines`, `reference_bands`, `annotations`, `legend`, `labels`, `colors` (`scheme`, `assign`, `highlight`), `facet`, `options` (theo loại). Màu chỉ là token của bảng màu, không nhận mã hex. Mỗi số đo (`Measure`) có `aggregate` (`auto`, `none`, `sum`, `avg`, `min`, `max`, `count`, `count_distinct`) và, riêng `combo`, `mark` (`bar`, `line`, `area`).

`GET /api/v1/text2sql/chart-types` trả danh mục cho frontend và agent: `{version, palette, enabled, types: [{type, family, label, roles: [{role, required, multiple, min, max, accepts}], min_rows, max_rows, max_series, options_schema}]}`. Setting `TEXT2SQL_CHART_TYPES_ENABLED` (danh sách cách nhau bằng dấu phẩy, rỗng là bật hết) giới hạn loại dùng được; `table` luôn bật.

`POST /api/v1/text2sql/charts/validate` nhận `{chart, fields (≤ 100), rows (≤ 1.000), rows_complete}`, trả `{chart (đã chuẩn hóa), warnings, chart_types}` hoặc 400 `text2sql_chart_invalid` với các thông báo nối bằng xuống dòng.

## Trường của kết quả (`fields`)

`FieldOut` (= `ChartField`): `name`, `label`, `type` (`number`, `date`, `datetime`, `text`, `boolean`, `other`), `unit`, `decimals`, `percent`, `additive` (`True` khi biểu thức metric ngoài cùng là `SUM`/`COUNT`), `role` (`measure`/`dimension`), `format_hint` (`plain`: năm, mã, id, cột nhóm hoặc `EXTRACT` không có dấu ngăn nghìn), `time_unit` (khi đã gom theo `time_grain` hoặc `DATE_TRUNC`), `pii`. Dựng ở `backend/modules/text2sql/services/display_format.py` (`metric_fields`, `sql_fields`); kết quả cũ không có `fields` thì `infer_fields` đoán từ giá trị.

## Quy tắc null (backend và frontend giống nhau)

- Ô số hợp lệ là số hữu hạn không phải bool; mọi giá trị khác (kể cả chuỗi `NaN`, `Infinity`, `-inf` không phân biệt hoa thường) là null.
- Giá trị phân loại null hiển thị là `(Trống)`.
- Dòng có trục `x`/`row` kiểu thời gian hoặc số bị null thì bị bỏ (đếm vào `dropped_null`); `scatter`, `bubble`, `histogram`, `box_plot` bỏ dòng thiếu số đo bắt buộc.
- Khóa phân loại: bool → `"true"`/`"false"`, số thực nguyên → chuỗi số nguyên, số thực khác → `repr`. Khóa thời gian theo `time_unit`: ngày `YYYY-MM-DD`, tuần là ngày thứ Hai đầu tuần, tháng `YYYY-MM`, quý `YYYY-Qn`, năm `YYYY`.

## Thuật toán chuẩn bị dữ liệu (`prepare`)

Frontend (`charts/data.ts`) phải làm đúng thứ tự này; `tests/fixtures/chart_cases.json` là bộ ca dùng chung (kỳ vọng `stats` = `{points, groups, series, dropped_null}`).

1. Bỏ dòng null theo quy tắc trên.
2. Áp `transform.filter` lần lượt (null chỉ qua `ne`, `not_in`; ngày so theo 10 ký tự đầu khi giá trị lọc dạng `YYYY-MM-DD`).
3. Gom theo các chiều `x`, `row`, `path`, `source`, `target`, `series`. `aggregate: "auto"` thành `none` khi khóa không lặp, ngược lại `sum` nếu `additive is True`, còn lại `avg` (kèm cảnh báo). Loại không gom (`scatter`, `bubble`, `histogram`, `box_plot`, `table`, …) giữ dòng thô.
4. `top_n` (chỉ khi `x` phân loại): xếp hạng theo tổng số đo đầu tiên, giữ `n` nhóm, phần còn lại cộng vào `Khác` (`other_label`) đặt cuối.
5. Sắp xếp ổn định: `sort.by = x` theo giá trị trục, `y` hoặc tên cột y theo tổng; không có `sort` thì trục thời gian/số tăng dần, trục phân loại giữ thứ tự dữ liệu.
6. `limit` cắt số nhóm trên trục x.

## Bộ kiểm tra (`validate_chart`)

`validate_chart(spec, fields, rows, result_id="", rows_complete=True, enabled=None) -> ValidatedChart(spec, warnings, stats)`. Pydantic chạy trước (thông báo đã dịch sang tiếng Việt, đường dẫn dạng `encoding.y[0].field`); sau đó mọi quy tắc chạy và gom lỗi (tối đa 8 câu). Mỗi câu nêu đường dẫn, lý do và cách sửa, ví dụ `encoding.y[0].field: không có cột 'luong_mua' trong kết quả 1-2. Các cột: ten_thanh_pho (văn bản), tong_luong_mua (số).`

| Nhóm | Quy tắc |
| --- | --- |
| Cấu trúc | V1 pydantic (khóa lạ, `axes.y2` có câu riêng, màu hex), V2 `version`, V3 `type` lạ (gợi ý loại gần giống), V34 loại chưa bật, V4 cột phải có, V5 số lượng vai trò, V6 kiểu cột hợp vai trò, V21 một cột hai vai trò, V22 `aggregate` số trên cột chữ, `mark` chỉ cho `combo` |
| Ngữ nghĩa | V11 xếp chồng cần số cộng dồn được, V12 một trục cần cùng đơn vị, V18 `options` theo loại, V19 `sort.by`/`filter.field`, V20/V30 `facet`, V23 `Khác`/`cumulative` cần cộng dồn được, V25 trục thời gian không sắp theo giá trị, V26 token màu trùng, V27 `time_unit`, V28 `colors.scheme`, V14/V29 trục và vùng tham chiếu, V31 dạng điều kiện lọc, V33 cột dữ liệu cá nhân không làm nhãn, lọc, tô hay chú thích |
| Theo dữ liệu | V7 khóa lặp khi `aggregate: none`, V8 số điểm tối thiểu/tối đa, V9 số nhóm/series, V10 dấu giá trị, V13 thang log, V15/V16/V17 giá trị phải có trên trục hoặc trong series (gợi ý giá trị gần giống bỏ dấu), V24 `index_to`, V32 sankey không vòng, không tự nối; sunburst/treemap mỗi lá một cha |

Khi `rows_complete=False` (kết quả bị cắt hoặc chỉ còn số dòng đã lưu) các quy tắc theo dữ liệu thành cảnh báo, kèm câu `Kiểm trên N dòng đã lưu`. Spec trả về đã chuẩn hóa: điền `label`, `time_unit`, `aggregate` cụ thể, `orientation` mặc định; `labels.show = all` với nhiều điểm đổi thành `auto`.

## Đề xuất mặc định và `display`

`suggest_chart(fields, rows, question_type, enabled, rows_complete)` trả `ValidatedChart` của loại đầu tiên qua kiểm tra theo ma trận (mục 4.5 của thiết kế); không loại nào qua thì `table`. `compatible_types` trả mọi loại có spec mặc định qua kiểm tra, sắp theo mức ưu tiên, luôn kết thúc bằng `table`. Tóm tắt ma trận:

| Hình dạng | Mặc định |
| --- | --- |
| 0 dòng, chỉ cột chữ | `table` |
| 1 dòng | `kpi` (thêm `bullet` khi có cột mục tiêu) |
| C + 1 N | 2–3 dòng `bar`, 4–50 dòng `bar_horizontal`, > 50 dòng `table` |
| T + 1 N | `bar` nếu cộng dồn được và ≤ 31 điểm, ngược lại `line` |
| T + C + 1 N | `line` với `series` |
| C + 2–4 N | cùng đơn vị `bar_grouped`, khác đơn vị `table` |
| 2 N / 3 N | `scatter` / `bubble` |
| 1 N thô (± C) | `histogram` (± C: `box_plot`) |
| C + C + N | `heatmap` |

`question_type` chỉ phá thế hòa: T7 sắp giảm dần và `top_n` 10, T10 ưu tiên `line`/`bar`, T11 `donut`, T13 `scatter`. `chart_display(spec, points, source)`: `none` cho `table`, `kpi` hoặc dưới 3 điểm; `chart` khi agent chọn; `chart_if_last` khi là đề xuất của code (frontend chỉ mở biểu đồ ở kết quả cuối).

## Agent đặt biểu đồ

- Kèm lời gọi: `query_metric(..., chart={...})`, `run_sql(..., chart={...})`. Hợp lệ → `chart_source = "agent"`; sai → dữ liệu vẫn trả, `chart` giữ đề xuất, output có `chart_error`.
- Sau khi có kết quả: công cụ `make_chart(result_id, chart)`. Hợp lệ → ghi bước `make_chart` và cập nhật bước dữ liệu (`chart`, `chart_source = "agent"`, `display`, thêm loại vào `chart_types`). Sai → `ToolError` với các thông báo V*; `result_id` lạ → liệt kê các `result_id` hiện có.
- `result_id` là `"<vị trí câu>-<thứ tự>"`, chỉ đếm bước `query_metric`/`run_sql` thành công; chạy tiếp sau hỏi lại vẫn đếm tiếp.

## Lựa chọn của người dùng

Lựa chọn biểu đồ trên từng kết quả lưu ở cột `views` của lượt hỏi đáp (module [`conversation`](../conversation/api-luot-hoi-dap.md)): `PUT`/`DELETE /api/v1/conversations/{id}/turns/{turn_id}/views/{result_id}`. Backend kiểm spec bằng cùng `validate_chart` trên các dòng đã lưu.

## Frontend

Mã ở `frontend/features/text2sql/charts/` (tab `Hỏi dữ liệu`, xem [Frontend](../../frontend/README.md#hỏi-dữ-liệu)). Frontend không tự đặt luật: mọi spec do người dùng sửa đều đi qua bộ kiểm tra của backend trước khi được lưu.

| File | Vai trò |
| --- | --- |
| `spec.ts` | Kiểu TypeScript của spec v1 (khớp `spec.py`), `CHART_TYPES`, `PALETTE`, `isChartSpec` |
| `format.ts` | Định dạng số kiểu Việt Nam (làm tròn nửa lên như `Decimal`, `format_hint`, phần trăm, rút gọn `N`/`Tr`/`Tỷ`), ngày theo `time_unit` (bỏ năm khi là năm hiện tại), tiêu đề cột kèm đơn vị, `(Trống)` cho null |
| `data.ts` | Bản port của `prepare.py` (`prepare`, `chartStats`) và các hàm dựng dữ liệu cho từng nhóm biểu đồ: pivot series, cộng dồn và `index_to`, bước thác nước, bin của histogram, tứ phân vị của box plot (Tukey), đường xu hướng tuyến tính, cây cho treemap/sunburst, nút và luồng sankey, lưới heatmap |
| `suggest.ts` | Bản port spec mặc định theo loại của `suggest.py`; `defaultSpecFor` dựng spec khi người dùng đổi loại (giữ tiêu đề) |
| `palette.ts` | Token → biến CSS: `series-1`…`series-8` → `--chart-1`…`--chart-8`, `muted` → `--chart-muted`; dải tuần tự `--chart-seq-100`…`700`; dải phân kỳ `--chart-div-neg`/`mid`/`pos` |
| `catalog.ts` | `useChartCatalog` (SWR `GET /api/v1/text2sql/chart-types`), nhãn tiếng Việt của loại, nhóm, vai trò và biểu tượng |
| `renderers/` | `cartesian.tsx` (cột, thanh ngang, nhóm, chồng, chồng 100%, kẹo mút, quả tạ, phân kỳ, thác nước, đường, vùng, vùng chồng, kết hợp, histogram, box plot, scatter, bubble), `polar.tsx` (tròn, vành khuyên, thanh tròn, mạng nhện, phễu), `hierarchy.tsx` (treemap, sunburst, sankey), `grid.tsx` (heatmap, lịch nhiệt), `figures.tsx` (thẻ số, bullet, bảng sparkline, bảng) |
| `chart-view.tsx` | Bảng `RENDERERS` (đủ 32 loại), lỗi khi vẽ thì quay về bảng (error boundary); loại chưa vẽ được thì hiện `Chưa hỗ trợ dạng «X»; đang hiện dạng «Y».` |
| `chart-switcher.tsx` | Menu đổi loại, nhóm theo họ; chỉ liệt kê `chart_types` của kết quả ∩ loại đã bật ∩ loại vẽ được, luôn có `Bảng` |
| `chart-editor.tsx` | Panel `Tùy chỉnh biểu đồ` (Sheet): tiêu đề, phụ đề; cột cho từng vai trò theo danh mục (số đo có cách gộp, màu, kiểu vẽ với `combo`); sắp xếp, top N với `Khác`, cộng dồn, quy về 100; trục (hướng, tên, nghiêng nhãn, min/max, bắt đầu từ 0, log, ẩn); định dạng số; đường tham chiếu (tối đa 5); chú giải, nhãn số, cách tô màu, nhấn mạnh (tối đa 3), màu riêng cho series; chia nhỏ; `options` của loại dựng từ `options_schema`. Lỗi và cảnh báo của backend hiện ở đầu panel |
| `chart-panel.tsx` | Thanh công cụ của một biểu đồ và luồng lưu |
| `result-table.tsx` | Bảng kết quả dùng nhãn, đơn vị và định dạng của `fields` |

**Biểu đồ nào được vẽ:** lựa chọn của người dùng (`views[result_id].chart`), rồi spec của agent, rồi spec đề xuất, cuối cùng là bảng. Vùng biểu đồ dưới câu trả lời chỉ hiện kết quả có lựa chọn của người dùng khác `table`, hoặc `display = chart`, hoặc `display = chart_if_last` ở kết quả cuối của câu đơn đã trả lời; mọi kết quả vẫn có tab `Biểu đồ` trong `Số liệu và cách tính`. Chọn `Bảng` ở vùng biểu đồ là lựa chọn lưu lại nên kết quả đó rời vùng biểu đồ (vẫn đặt lại được trong tab `Biểu đồ` của thẻ).

**Lưu lựa chọn:** đổi loại thì dựng spec mặc định của loại mới và gửi ngay; sửa trong panel thì gửi sau 600 ms không gõ. Các lần lưu của cùng một kết quả chạy nối tiếp, lần cũ bị thay bởi lần mới thì bỏ qua. Lượt đã ghi (có `conversation_id`, `turn_id`, tên người dùng) gọi `PUT /api/v1/conversations/{id}/turns/{turn_id}/views/{result_id}` với `{user_id, chart}`; lượt chưa ghi gọi `POST /api/v1/text2sql/charts/validate` với `{chart, fields, rows (≤ 1.000), rows_complete}` và chỉ giữ trong trang. Thành công thì vẽ spec đã chuẩn hóa backend trả về; 400 thì tách thông báo theo dòng và hiện trong panel, biểu đồ giữ bản hợp lệ trước đó. `Đặt lại` gọi `DELETE ...?user_id=` (204) và quay về spec của agent hoặc đề xuất.

**Quy ước vẽ:** không có trục y thứ hai; series thứ chín trở đi không sinh màu mới mà dùng `muted`; màu đi theo thực thể (thứ tự xuất hiện trong toàn bộ dữ liệu), không theo thứ hạng. Cột, thanh, kẹo mút, vùng và `combo` luôn bắt đầu từ 0 (đầu trục làm tròn tới bước dễ đọc); đường giữ trục tự động, `axes.y.zero = false` thì ôm sát dữ liệu. Chú giải chỉ hiện khi có từ 2 series; nhãn số chọn lọc (cột đơn: mọi cột; đường: điểm đầu và cuối), nhãn ở hai đầu đường nghiêng vào trong để không đè trục. Treemap một cấp dùng một màu và sắp ô theo giá trị giảm dần, ô đủ rộng hiện cả giá trị. Chữ dùng màu chữ, không dùng màu series. Mọi biểu đồ có tooltip; heatmap là bảng HTML, lịch nhiệt là lưới HTML theo tuần; mỗi ô có dữ liệu focus được và có `aria-label`. Chế độ tối dùng bộ màu riêng trong `app/globals.css`; dải tuần tự đảo chiều để giá trị nhỏ chìm vào nền tối.

**Kiểm thử:** `npm run test:charts` (`node --test`, Node 24 bỏ kiểu TypeScript khi chạy, nên `charts/package.json` khai `"type": "module"` và `tsconfig.json` bật `allowImportingTsExtensions`) chạy `data.test.ts` và `format.test.ts` trên `tests/fixtures/chart_cases.json` và `format_cases.json`, cùng bộ ca với backend.

**Chưa làm:** vân (texture) thay màu cho người mù màu hoặc in ấn.
