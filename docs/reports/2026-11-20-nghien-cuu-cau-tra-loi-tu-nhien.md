# Nghiên cứu: câu trả lời tự nhiên hơn cho tab "Hỏi dữ liệu"

Ngày: 2026-11-20. Phạm vi: nghiên cứu, chưa sửa code. Dữ liệu chẩn đoán lấy từ các lần chạy thật trong `scripts/text2sql_eval/results/` (mô hình `openai/gpt-6-luna` qua OpenRouter, `today = 2026-11-20`).

## 1. Tóm tắt

- Câu trả lời hiện **đúng số** nhưng đọc như log: 78% câu trả lời cuối (75/96) kết thúc bằng một câu "cách tính" (bản ghi dự báo theo ngày, quy tắc đã áp). 90% ghi năm đầy đủ dù là năm hiện tại. 24% nhắc chữ "quy tắc". Một số câu lộ mã kỹ thuật (`tong_luong_mua_mm`, `DU_BAO_GIO`, `THAT_BAI`) hoặc tên không dấu (Ho Chi Minh, Buon Ma Thuot).
- Nguyên nhân chính nằm ở **prompt** và **dữ liệu đưa vào prompt**, không phải ở mô hình. Prompt agent yêu cầu "Nêu ngắn gọn các giả định đã chọn, quy tắc chuyên gia đã áp hoặc bỏ qua, và lưu ý của metric nếu có". Ghi chú của công cụ thì viết theo giọng kỹ thuật ("điều kiện trên cột loai_quan_sat đã nằm trong biểu thức metric nên không lọc thêm"). Giao diện cũng góp phần: thẻ kết quả nằm **trên** câu trả lời, tiêu đề cột là tên cột thô, chân thẻ in nguyên ghi chú kỹ thuật.
- **Đề xuất:** tách "phân tích" khỏi "viết". Agent trả **bản nháp sự thật**. Một bước viết (`compose`) thay cho `synthesize` hiện tại, chạy cho **mọi** lượt (kể cả câu không tách) và stream từng token. Bước này viết theo hướng dẫn văn phong theo loại câu hỏi. Phần "cách tính" (quy tắc đã áp, khớp giá trị, khoảng dữ liệu) do **code** dựng từ `steps`, hiển thị riêng thành khối thu gọn, không để LLM viết vào câu trả lời.
- **A/B offline** trên 10 bản ghi thật (chỉ gọi lại bước viết với dữ liệu đã lưu, không chạm database nguồn): cả 10/10 vẫn qua bộ chấm của `run_eval.py`. Bước viết không thêm con số nào ngoài bản nháp. Độ dài giảm khoảng 32% (2.704 xuống 1.849 ký tự). Trung vị thời gian tới token đầu là 1,1 giây, tổng 1,8 giây, khoảng 2.100 đến 3.100 token vào mỗi lần. **Lưu ý:** con số 1,1 giây đo khi bộ nhớ đệm prompt của nhà cung cấp đã nóng (9/10 lần gần như toàn bộ token vào là `cache_read`). Ở vòng v1, khi chỉ phần prompt hệ thống được đệm, trung vị là 3,2 giây tới token đầu và 3,6 giây tổng. Nên ước lượng thực tế là khoảng 1 đến 4 giây. Bản nháp trong A/B là câu trả lời cũ của agent, chưa phải bản nháp theo prompt mới ở mục 5.1.

## 2. Chẩn đoán có bằng chứng

### 2.1. Số liệu trên 96 câu trả lời cuối của `a2-final-x2.json`

Cách đếm: script `scratchpad/stats.py`, regex trên `output.answer` của các lượt `answered`.

| Dấu hiệu "debug" | Số câu | Tỷ lệ |
| --- | ---: | ---: |
| Câu cuối là câu nói cách tính hoặc nguồn ("Dùng bản ghi dự báo theo ngày", "Áp dụng quy tắc...") | 75/96 | 78% |
| Nhắc "bản ghi", "dự báo theo ngày/giờ" | 74/96 | 77% |
| Ghi năm đầy đủ `/2026` dù là năm hiện tại | 86/96 | 90% |
| In đậm (thường in đậm cả ngày tháng) | 77/96 | 80% |
| Nhắc "quy tắc" | 23/96 | 24% |
| Chữ "áp dụng" | 18/96 | 19% |
| "chỉ số" hoặc "metric" | 11/96 | 11% |
| Tên thành phố không dấu như trong dữ liệu | 8/96 | 8% |
| Số có 2 chữ số thập phân (77,56%, 26,69 °C, 29,95 giây) | 7/96 | 7% |
| Mã hoặc tên cột trong dấu \` | 3/96 | 3% |

Trên toàn bộ 692 câu trả lời khác nhau của mọi file kết quả (gồm câu trả lời con), "bản ghi" xuất hiện ở 404 câu, tên không dấu ở 65 câu, dấu \` ở 24 câu, mã `DU_BAO_*` ở 11 câu.

### 2.2. Phân loại và ví dụ trích nguyên văn

1. **Đuôi "cách tính" lặp lại ở mọi câu.** Đây là loại nặng nhất.
   - T1-1: "Nhiệt độ cao nhất ở Hà Nội hôm qua là **22 °C** (ngày **19/11/2026**). Dùng số liệu dự báo theo ngày theo quy tắc áp dụng cho chỉ số nhiệt độ cao nhất."
   - T6-1: bảng 12 thành phố, rồi "Tổng hợp từ các bản ghi dự báo theo ngày; quy tắc chỉ số theo ngày đã được áp dụng."
   - T3-2: "Đã áp dụng quy tắc chỉ tính các thành phố đang hoạt động; con số này phản ánh trạng thái hiện tại."
2. **Lộ tên cột, mã giá trị, cách khớp dữ liệu.**
   - T22-1: "tổng lượng mưa ngày (`tong_luong_mua_mm`) lớn hơn 0 mm trên bản ghi dự báo theo ngày".
   - C-2: "đã áp dụng quy tắc dùng bản ghi `DU_BAO_GIO` cho chỉ số trung bình."
   - T15-1: "lỗi được tính theo trạng thái `THAT_BAI`".
   - S-3: "“Hà Nội” được khớp với tên “Ha Noi” trong dữ liệu."
   - T13-1: "giá trị Huế trong dữ liệu là “Hue”."
   - Bản `a2-smoke`: "metric này không tính theo tháng nên không lọc theo tháng 11/2026."
3. **Giá trị thô không dấu.** T15-3: "Buon Ma Thuot, Can Tho, Da Nang, Ha Long, Ha Noi, ..., Ho Chi Minh". T7-1 và D-2: "**Ho Chi Minh**". Có lần thì mô hình tự thêm dấu, có lần không, nên cùng một câu hỏi lại ra hai kiểu.
4. **Ngày tháng nặng nề.** "từ **13/11/2026 đến hết ngày 19/11/2026**", "lúc **20/11/2026 01:00**". In đậm cả ngày, luôn có năm, không có thứ.
5. **Số chưa làm tròn, thuật ngữ thống kê.** "**77,56%**", "**26,69°C** so với **24,05°C**, chênh **2,64°C**", "hệ số tương quan Pearson là **0,035**". Cách viết đơn vị cũng không thống nhất: có câu "34,7°C", có câu "34,7 °C".
6. **Diễn đạt máy móc.**
   - T4-1: "Có, Hà Nội có mưa hôm qua (19/11/2026): ghi nhận **1 ngày có mưa**." Số đếm của metric bị đọc nguyên.
   - T5-2: "**không có thành phố miền Bắc nào không mưa**", tức phủ định kép.
   - T1-2: "Đây là bản ghi quan sát hiện tại mới nhất".
7. **Lặp thông tin khi ghép câu tách.** Ở D-1, bước `synthesize` giữ nguyên hai đuôi nguồn: "...tính theo tổng lượng mưa ngày trên các bản ghi dự báo theo ngày. Nhiệt độ cao nhất ở Phú Quốc hôm qua (19/11/2026) là 31,2 °C, theo bản ghi dự báo theo ngày." Prompt `synthesize` dặn "Giữ các giả định, quy tắc đã áp và lưu ý quan trọng", nên đuôi nguồn không bị lược.
8. **Câu hỏi lại.** Lời hỏi khá tốt ("Bạn muốn so sánh tổng lượng mưa của các thành phố trong khoảng thời gian nào?"). Nhưng `options` lấy thẳng giá trị cột: M-3 có `['Buon Ma Thuot', 'Can Tho', 'Da Nang', ...]` và chỉ có 8/12 thành phố.
9. **Phần làm tốt, cần giữ:** câu đầu đi thẳng vào kết quả, số dùng dấu phẩy thập phân, bảng Markdown cho T6. Câu thiếu thông tin có nêu giả định ("Bạn chưa nêu thành phố nên mình liệt kê theo từng thành phố"), nhưng xưng hô lẫn lộn giữa "mình", "tôi" và câu không chủ ngữ.

### 2.3. Nguyên nhân gốc trong code

| Nguyên nhân | Vị trí |
| --- | --- |
| Prompt yêu cầu nêu quy tắc đã áp hoặc bỏ qua và lưu ý metric trong câu trả lời | `backend/agent_package/prompts/prompt_text2sql_agent.py`, mục `# CÂU TRẢ LỜI`, gạch 2; mục `# CÁCH LÀM` bước 3: "tự áp điều kiện ... và nêu ra trong câu trả lời" |
| Prompt ghép yêu cầu giữ giả định, quy tắc, lưu ý | `prompt_synthesize.py`, mục `# CÁCH VIẾT` điểm 3 |
| `query_metric` trả `notes` theo giọng kỹ thuật, nhắc tên cột và mã, kể cả ngoại lệ không liên quan ("khi Người dùng hỏi lượng mưa trong từng giờ thì Dùng luong_mua_mm trên dòng DU_BAO_GIO") | `services/agent_tools.py`, `_resolve_filter_values` và phần ghi chú quy tắc trong `sql_builder.py` |
| Agent chỉ thấy tên cột, chưa thấy đơn vị. `ColumnInfo` có `label` nhưng không có `unit`, `format`, dù `column_dictionaries` có hai cột này | `services/agent_catalog.py` (`ColumnInfo.describe`), `data_dictionary/models/column_dictionary.py` |
| Giá trị văn bản trong database nguồn không dấu, không có nhãn hiển thị | dữ liệu nguồn (`ten_thanh_pho = 'Ha Noi'`) |
| Không có hướng dẫn văn phong theo loại câu (`question_type`) và không có ví dụ | cả hai prompt; `docs/handbook/modules/agent_package.md` ghi "Không có few-shot" |
| Câu không tách thì dùng thẳng câu của agent, không có bước viết chung | `services/chat_graph.py`, `_synthesize` |

### 2.4. Giao diện đang làm cảm giác "debug" nặng thêm

Đọc `frontend/features/text2sql/chat-turn.tsx`, `query-result.tsx`, `labels.ts`:

- `AssistantTurn` hiển thị theo thứ tự: `ThinkingTrace`, `RewriteNote`, **mọi thẻ `QueryResult`**, rồi mới đến câu trả lời. Người dùng thấy bảng kỹ thuật trước câu trả lời.
- `QueryResult` dùng `step.columns` làm tiêu đề cột. Với kết quả một ô, nhãn là tên cột thô, ví dụ `so_thanh_pho_hoat_dong`, `nhiet_do_cao_nhat`. Tab SQL in kèm JSON "Tham số của công cụ".
- Chân thẻ in nguyên `step.notes`, ví dụ "Quy tắc 'Chỉ số theo ngày dùng bản ghi dự báo ngày': điều kiện trên cột loai_quan_sat đã nằm trong biểu thức metric nên không lọc thêm."
- `TOOL_LABELS` có chữ tiếng Anh "metric" ("Đọc định nghĩa metric", "Truy vấn metric"). Bước trong `ThinkingTrace` có dạng "Đọc định nghĩa metric: nhiet_do_cao_nhat".
- Điểm tốt: `query-result.tsx` đã định dạng số bằng `Intl.NumberFormat("vi-VN")` và ngày bằng `Intl.DateTimeFormat("vi-VN")`. `answer-markdown.tsx` (react-markdown 10.1.0, remark-gfm 4.0.1) đã hiển thị được bảng, danh sách và in đậm.

## 3. Hướng dẫn văn phong đề xuất

### 3.1. Nguyên tắc chung

1. **Câu đầu là đáp án.** Kết quả, đối tượng và thời gian nằm trong một câu.
2. **Chỉ một ý phụ, và chỉ khi nó đổi cách hiểu con số:** giả định do câu hỏi thiếu thông tin, định nghĩa nghiệp vụ người dùng có thể hiểu khác, kết quả chỉ là một phần. Ý phụ viết thành mệnh đề ngắn. Mọi thứ khác đưa sang khối "Cách tính" do hệ thống dựng (mục 4.3).
3. **Không nhắc nội bộ:** bản ghi, metric, chỉ số, bảng, cột, truy vấn, quy tắc chuyên gia, mã viết hoa, tên có dấu gạch dưới, dấu \`.
4. **Tên hiển thị:** nhãn metric và cột lấy từ catalog. Địa danh viết tiếng Việt có dấu, không viết tắt (bộ chấm so khớp tên đầy đủ, xem mục 9).
5. **Không xưng "tôi".** Khi cần thì dùng "Bạn chưa nêu ... nên ...". Không kết bằng lời mời hỏi tiếp. In đậm 1 đến 3 số hoặc kết luận chính, không in đậm ngày.

### 3.2. Số, ngày và đơn vị theo vi-VN

Đã kiểm bằng Node 24.19.0, API `Intl` (ICU):

| Thứ cần viết | Cách viết | `Intl` cho ra |
| --- | --- | --- |
| Số thập phân, hàng nghìn | `1.234,5`; `41.250.000` | `new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(1234.5)` → `1.234,5` |
| Phần trăm | `97,1%` (không cách) | `style:'percent'` → `97,1%` |
| Nhiệt độ, lượng, tốc độ | `34,7 °C`, `46,9 mm`, `77,8 km/h` | `style:'unit'` → `34,7°C`, `46,9 mm`, `77,8 km/h` (ICU viết °C liền số) |
| Ngày có thứ | `thứ Năm, 19/11` | `{weekday:'long',day:'2-digit',month:'2-digit'}` → `Thứ Năm, 19/11` |
| Khoảng ngày | `13–19/11` | `formatRange` → `13/11 – 19/11` |
| Số rút gọn | `1,2 triệu` | `notation:'compact'` → `1,2 Tr` (viết tắt, không nên dùng trong câu) |

Quy ước đề xuất:

- Số đo (°C, mm, %, km/h, giây) làm tròn **tối đa 1 chữ số** thập phân. Số đếm giữ nguyên. Hệ số tương quan giữ 2 đến 3 chữ số có nghĩa.
- Đơn vị cách số một khoảng trắng (`22 °C`), riêng `%` viết liền.
- Không ghi năm nếu trùng năm của `today`. Mốc tương đối viết như người dùng hỏi, kèm ngày trong ngoặc: "hôm qua (thứ Năm, 19/11)", "tuần trước (9–15/11)".

Python không có sẵn bộ định dạng vi-VN (`babel` không có trong `uv.lock`). Một hàm nhỏ là đủ; đã chạy thử trong scratchpad:

```python
def vi_number(value, digits=1):
    q = Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    text = f"{q:,.{digits}f}".rstrip("0").rstrip(".") if digits else f"{q:,.0f}"
    return text.translate(str.maketrans({",": ".", ".": ","}))
# 1234.5 -> "1.234,5"; 77.56 -> "77,6"; 41250000 -> "41.250.000"; 0.035 (digits=3) -> "0,035"
```

Lỗi biên đã kiểm lại: số âm làm tròn về 0 (ví dụ `-0.04`) cho ra `"-0"`. Sửa bằng cách cộng thêm `+ 0` sau `quantize(...)`; đã chạy lại, `-0.04` thành `"0"` và `-1.25` thành `"-1,3"`.

`MetricInfo.format` (ví dụ `",.1f"` của Superset) đã có trong catalog, dùng được để chọn số chữ số thập phân theo metric. Chuỗi này là định dạng d3 của Superset, có thể là `".1%"` (giá trị là tỷ lệ 0 đến 1, phải nhân 100) hoặc `"SMART_NUMBER"`. Vì vậy cần một hàm đọc riêng, không truyền thẳng vào format của Python.

### 3.3. Khuôn câu theo loại câu hỏi

| Loại | Khuôn | Ví dụ (viết lại từ dữ liệu thật) |
| --- | --- | --- |
| T1, T2, T3, T9, T15 | 1 câu: kết quả, đối tượng, thời gian; tối đa 2 câu | "Tổng lượng mưa ở Huế 7 ngày qua (13–19/11) là **8,6 mm**." |
| T4 | Mở đầu "Có," hoặc "Không,", sau đó là căn cứ | "Có, hôm qua (thứ Năm, 19/11) Hà Nội có mưa, khoảng **0,9 mm**." |
| T5, T12 | Số lượng, sau đó liệt kê (trong câu nếu ≤ 8 mục, gạch đầu dòng nếu nhiều hơn) | "Có, tuần trước (9–15/11) gió giật vượt 40 km/h ở **cả 12 thành phố**: ..." |
| Câu phủ định | Trả lời khẳng định, tránh phủ định kép | "Không có nơi nào; cả 4 thành phố miền Bắc đều có mưa." |
| T6, T10 | Câu dẫn, rồi bảng (≥ 5 dòng) hoặc danh sách; kết bằng 1 câu nêu điểm nổi bật | "... Cao nhất là Phú Quốc (**46,9 mm**), thấp nhất là Huế (**8,6 mm**)." |
| T7 | Tên trước, giá trị sau; top-k theo thứ hạng | "Hôm qua (thứ Năm, 19/11), **TP. Hồ Chí Minh** nóng nhất, **34,7 °C**." |
| T8 | Kết luận trước, hai giá trị sau. Chỉ nói mức chênh khi bản nháp hoặc `data` đã có số đó; nếu không có thì chỉ nói bên nào hơn | "TP. Hồ Chí Minh nóng hơn Hà Nội **12,7 °C** (34,7 °C so với 22 °C)." (chỉ đúng khi 12,7 có sẵn trong bản nháp) |
| T11 | "dao động từ X đến Y" | |
| T13 | Kết luận bằng lời thường; hệ số và cỡ mẫu trong ngoặc | "...**hầu như không liên quan** (hệ số tương quan 0,035 trên 168 giờ)." |
| T22 | 1 đến 2 câu, lời thường, không tên cột | "Một ngày được tính là có mưa khi tổng lượng mưa trong ngày trên 0 mm." |
| Câu tách | Liền mạch theo thứ tự ý, có từ nối; mốc thời gian chung nói một lần | "Phú Quốc mưa nhiều nhất 7 ngày qua (13–19/11), **46,9 mm**; còn nhiệt độ cao nhất ở đó hôm qua là **31,2 °C**." |
| Câu phụ thuộc | Dùng "ở đó", "thành phố này" thay vì nhắc lại cả câu trước | như trên |
| Thiếu thông tin, đã tự giả định | Giả định ở câu dẫn | "Bạn chưa nêu thành phố nên đây là nhiệt độ trung bình hôm qua của từng nơi:" |
| Không có dữ liệu | "Chưa có số liệu ... cho ..." kèm lý do ngắn, không đoán | |
| Trả lời được một phần | Phần có kết quả trước; phần thiếu 1 câu kèm lý do | |
| Kết quả bị cắt | "Danh sách dưới đây là N dòng đầu." | |

**Độ dài:** T1 đến T4, T7 đến T9 nên dưới khoảng 200 ký tự. Bảng không tính vào độ dài. Câu tách nên dưới khoảng 350 ký tự. Prompt nêu "tối đa N câu" vì mô hình tuân theo số câu tốt hơn số ký tự. `max_tokens` của mô hình (4096) không cần đổi.

## 4. Phương án kiến trúc

### 4.1. Các lựa chọn

| Phương án | Mô tả | Ưu | Nhược |
| --- | --- | --- | --- |
| A. Chỉ sửa prompt | Viết lại mục `# CÂU TRẢ LỜI` của agent và prompt `synthesize` theo mục 3 | Không thêm lời gọi LLM, sửa nhanh | Agent viết câu trả lời trong ngữ cảnh 6.000+ token đầy kết quả công cụ và ghi chú quy tắc, nên dễ tái phạm. Câu không tách vẫn không có bước viết chung. Khó stream token: câu cuối của agent nằm trong vòng gọi công cụ, và các câu con chạy song song nên token đan xen. Chưa A/B offline được vì phải chạy lại agent, tức chạm database nguồn. |
| B. Tách phân tích và viết (**đề xuất**) | Agent trả bản nháp sự thật. Nút `compose` (thay `synthesize`) chạy cho mọi lượt có câu trả lời và stream token | Một chỗ duy nhất quyết định văn phong cho câu đơn, câu tách và câu phụ thuộc. Ngữ cảnh viết nhỏ (khoảng 2.000 đến 3.000 token). Stream token tự nhiên ở nút cuối. A/B offline cho kết quả tốt (mục 6). | Thêm 1 lời gọi cho câu không tách: token đầu sau khoảng 1,1 giây khi bộ đệm prompt đã nóng, khoảng 3,2 giây khi chưa (trung vị, mục 6). Có rủi ro mô hình viết sai số, nên cần chốt kiểm tra số (mục 4.4). |
| A+. Sửa prompt và hậu xử lý bằng code | Phương án A, thêm một bước code sửa các lỗi máy móc (bỏ `/2026` khi trùng năm, thay tên không dấu bằng nhãn, bỏ dấu \`) | Không thêm độ trễ, sửa được ngay các lỗi đếm được ở mục 2.1 | Không sửa được giọng văn hay việc lặp ý khi ghép câu. Sửa chuỗi bằng regex dễ làm hỏng câu. Nên coi là bước đệm trước B. |
| C. Agent trả JSON có cấu trúc | Agent gọi công cụ `submit_answer(facts, assumptions, caveats)`, code dựng câu bằng template | Kiểm soát chặt, không lo bịa | 22 loại câu, nhiều dạng bảng: template cứng sẽ lại thành "robot". Stream token của tham số công cụ cần parse JSON dở dang. Tốn công nhất. |

### 4.2. Thiết kế đề xuất (B)

```text
preprocess ─► dispatch ─► answer_question (agent: draft + steps) ─► ... ─► compose (stream) ─► END
```

1. **Agent** (`prompt_text2sql_agent.py`): mục cuối đổi thành "BẢN NHÁP" (mục 5.1). Bản nháp gồm sự thật, khoảng thời gian đã lọc, và các dòng `Giả định:`, `Định nghĩa:`, `Hạn chế:` khi có. Agent không cần nêu quy tắc mặc định hay nguồn, vì hệ thống đã ghi trong `steps`. `QuestionAnswerOut.answer` vẫn giữ tên trường, nhưng nghĩa đổi thành bản nháp (ghi rõ trong handbook).
2. **`compose`** (thay `_synthesize` trong `services/chat_graph.py`). Nút này chạy cả khi chỉ có một câu. Đầu vào do code dựng, gồm:
   - `question` (câu đã viết lại), `today` kèm thứ;
   - `parts[]`, mỗi phần có `question`, `question_type`, `business_concepts`, `draft`;
   - `data`: tối đa khoảng 30 dòng của bước truy vấn thành công cuối. Tiêu đề cột lấy **nhãn** (nhãn metric, `ColumnInfo.label`), có `unit`. Giá trị số nên được **định dạng sẵn** theo `MetricInfo.format` và đơn vị bằng `vi_number`, để mô hình chỉ chép chứ không tự làm tròn.
   
   Đầu ra là văn bản Markdown, không JSON, để stream được. Bỏ `SynthesizeResponse` và `SynthesizeParser`.
3. **Stream:** trong nút `compose`, gọi `get_chat_model().stream(messages)` (`ChatOpenAI.stream` của langchain-openai 1.7.4, đã chạy thử) và đẩy từng phần qua `get_stream_writer()` thành event mới `answer_delta {"text": ...}`. Chế độ `custom` đã dùng sẵn cho event `tool`, nên sự kiện ra ngay trong lúc nút chạy. Khi xong, update `answer` vẫn sinh event `answer` với toàn văn như hiện nay, nên client cũ không vỡ. Việc này chồng với hướng nghiên cứu "Streaming quá trình trả lời". Báo cáo đó (`docs/reports/2026-11-20-nghien-cuu-streaming-cau-tra-loi.md`, mục hợp đồng event) đã định nghĩa `answer_delta` với các trường `position`, `round`, `final`, `text`, kèm `answer_reset` và `synthesize_started`. Báo cáo đó cũng stream thẳng câu trả lời của agent làm bản chính (`final: true`) với câu không tách. Nếu chọn B thì phải thống nhất lại: chữ của agent chỉ là bản nháp (`final: false`, hoặc không gửi). Chỉ chữ của `compose` được gửi với `position: null, final: true`. Hai báo cáo cần dùng chung một hợp đồng event.
   - Sự kiện `answer` hiện được sinh trong `chat_events.update_events` khi `node == "synthesize"`. Đổi tên nút thì phải sửa chỗ này. Cách an toàn hơn là giữ tên nút `synthesize`, chỉ đổi phần bên trong. Như vậy không phải sửa ánh xạ event, và các snapshot hỏi lại đang chờ (checkpoint đã xuất, lưu trong hội thoại) khi chạy tiếp vẫn gặp đúng tên nút cũ. Nếu vẫn đổi tên thì cần test chạy tiếp một snapshot tạo trước khi đổi.
   - Writer của `_emitter` đã kiểm tra `should_stop()` ở mỗi lần gửi. Nên dùng `_emitter` cho từng đoạn chữ, để người dùng ngắt kết nối thì dừng luôn việc gọi LLM.
4. **Dự phòng:** đây là hành vi **mới**. Hiện nay `ChatService._complete` ném `Text2SqlAgentUnavailable` khi `synthesize` lỗi, nên cả lượt thất bại. Đề xuất: `compose` lỗi (`OpenAIError`, timeout) thì dùng bản nháp như cách hiện tại làm với câu không tách: một câu thì lấy nguyên bản nháp, nhiều câu thì nối các bản nháp. Lỗi ở bước viết không làm mất câu trả lời. `get_chat_model()` đang đặt `timeout=60, max_retries=2`, nên trường hợp xấu nhất có thể chờ vài phút trước khi dùng dự phòng. Nên đặt timeout riêng ngắn hơn cho `compose`. Nếu lỗi xảy ra giữa lúc stream, client đã nhận một phần chữ, nên event `answer` cuối (bản nháp) phải thay toàn bộ, hoặc gửi `answer_reset` trước. `use-chat.ts` hiện gán thẳng `answer` khi nhận event `answer`, nên cách thay toàn bộ dùng được.

### 4.3. Phần "cách tính" và lưu ý: tách khỏi câu trả lời

Không để LLM viết khối này. Code dựng từ `steps`, có cấu trúc, và giao diện hiển thị thành một dòng thu gọn "Cách tính (3)" dưới câu trả lời. Mở ra thì thấy các chip hoặc dòng:

| `kind` | Nguồn | Ví dụ hiển thị |
| --- | --- | --- |
| `rule` | Quy tắc chuyên gia đã áp hoặc đã nhường (`query_metric`) | "Chỉ số theo ngày dùng bản ghi dự báo ngày" |
| `value_match` | `_resolve_filter_values` | "Hà Nội → Ha Noi" |
| `period` | Bộ lọc thời gian, hoặc khoảng gộp MIN/MAX | "13/11 – 19/11/2026" |
| `assumption` | Dòng `Giả định:` trong bản nháp | "Chưa nêu thành phố: liệt kê từng thành phố" |
| `truncated` | `step.truncated` | "Chỉ lấy 1.000 dòng đầu" |

Không nên parse chuỗi `notes` hiện tại. Nên thêm trường có cấu trúc vào `AgentStepOut`, ví dụ `rules: list[{name, status: "applied"|"yielded"|"skipped"}]`. Ngoại lệ của quy tắc không khớp câu hỏi thì không hiển thị. Ghi chú gửi cho agent có thể giữ như cũ, vì đó là kênh làm việc của agent.

Lưu ý: giả định **vẫn phải nằm trong câu trả lời** (mệnh đề ngắn). Người dùng cần thấy nó mà không phải mở khối thu gọn, và bộ chấm `clarify_or_assume` hiện chỉ đọc `answer` (mục 9).

### 4.4. Chốt kiểm tra số sau bước viết

Sau `compose`, code trích mọi số trong câu trả lời và so với tập số của bản nháp, `data`, và ngày tháng của `today`/`dates`. Cách so dùng cùng logic và ngưỡng với `run_eval.has_number`: lệch tối đa `max(0,051; 0,5%)`. Gặp số lạ thì ghi log và, tùy chọn, gửi lại event `answer` bằng bản nháp. Trong A/B, số lạ là 0/10.

Khi kiểm lại, tập số cho phép phải gồm thêm **số dòng** của kết quả ("cả 12 thành phố"), các ngày đã quy đổi trong `dates`, và các số đã định dạng sẵn. Nếu thiếu, chốt kiểm tra sẽ báo nhầm. Bộ trích số phải hiểu dấu chấm ngăn hàng nghìn (mục 9). `ab_writer.py` không có bước kiểm tra số lạ. Kết quả 0/10 ở trên được kiểm lại bằng script riêng (`scratchpad/rv_nums.py`), với tập số gồm bản nháp, các dòng dữ liệu và các mốc ngày, số dòng.

## 5. Nội dung prompt đề xuất

### 5.1. `prompt_text2sql_agent.py`: thay mục `# CÂU TRẢ LỜI`

Với phương án B, đồng thời bỏ cụm "và nêu ra trong câu trả lời" ở bước 3 của `# CÁCH LÀM`.

```text
# BẢN NHÁP TRẢ LỜI
Bước sau sẽ viết lại bản nháp cho người dùng; bản nháp cần đủ và đúng, không cần hay.
- Viết tiếng Việt. Dòng đầu: kết quả chính với số liệu, đơn vị, đối tượng và khoảng thời gian đã lọc (ngày cụ thể).
  Danh sách hoặc bảng nhiều dòng thì nói ngắn kết quả chính; bảng đầy đủ đã có ở kết quả công cụ.
- Thêm một dòng cho mỗi điều sau, nếu có:
  - "Giả định: ..." khi đã tự chọn cách hiểu vì câu hỏi thiếu thông tin (không nêu đối tượng, không nêu thời gian).
  - "Định nghĩa: ..." khi câu hỏi dùng thuật ngữ trong business_concepts: nói định nghĩa đã dùng bằng lời thường.
  - "Hạn chế: ..." khi kết quả bị cắt, không có dữ liệu, hoặc một phần câu hỏi chưa trả lời được, kèm lý do.
- Không nêu quy tắc mặc định đã áp, loại bản ghi, bảng nguồn hay cách khớp tên giá trị: hệ thống tự ghi lại từ công cụ.
- Không có dữ liệu hoặc không trả lời được thì nói thẳng; không bịa, không đoán. Không chép SQL hay tên công cụ.
```

Nếu chọn phương án A (chỉ sửa prompt, không có bước viết), thay mục đó bằng bản rút gọn của mục 3 (mục 3.1, khuôn ở 3.3 và quy ước 3.2), kèm hai ví dụ ở mục 5.2.

Thêm vào bước 7 (`ask_user`) một câu: "options viết ở dạng người dùng đọc được: tên tiếng Việt có dấu, nhãn metric, khoảng thời gian dạng 13–19/11; nếu nhiều hơn 8 lựa chọn thì chọn các lựa chọn phổ biến và để người dùng tự gõ."

### 5.2. Prompt `compose`, thay `prompt_synthesize.py`

Đây là bản v2 đã chạy A/B (mục 6), có ba chỗ sửa sau A/B, nên cần chạy lại A/B trước khi dùng:

- Bỏ "gấp ba Quận 1" trong ví dụ, vì đó là phép tính mới.
- Mục giả định đọc các dòng `Giả định:`, `Định nghĩa:`, `Hạn chế:` của bản nháp mới (5.1).
- Bỏ trường `notes` khỏi đầu vào.

Ví dụ trong prompt dùng lĩnh vực thư viện và bán lẻ, không liên quan dữ liệu thời tiết, theo quy định "few-shot dùng lĩnh vực không liên quan dữ liệu thật" của `docs/handbook/modules/agent_package.md`.

```text
Bạn là AnswerWriter. Nhiệm vụ: viết câu trả lời cuối cùng cho người dùng từ kết quả phân tích đã có, như một
chuyên viên số liệu trả lời đồng nghiệp: đúng, gọn, tự nhiên. Không phân tích lại, không truy vấn, không tính thêm.

Đầu vào là JSON gồm:
- question: câu hỏi của người dùng, đã đủ ngữ cảnh.
- today: ngày hiện tại kèm thứ.
- parts: các phần đã phân tích, theo thứ tự ý trong question. Mỗi phần có question, question_type,
  business_concepts, draft (bản nháp của bước phân tích: số liệu đúng nhưng có thể khô, lặp, lộ chi tiết kỹ thuật)
  và data (các bảng kết quả: title, columns, rows).

# SỐ LIỆU
1. Chỉ dùng số, tên, mốc thời gian có trong draft hoặc data. Không thêm phép tính mới.
2. Số đo (°C, mm, %, km/h, giây) làm tròn tối đa 1 chữ số thập phân; số đếm giữ nguyên; hệ số (tương quan) giữ như
   draft. Viết số kiểu Việt Nam: dấu phẩy thập phân (24,4), dấu chấm ngăn hàng nghìn (1.250).
3. Đơn vị đi sau số, cách một khoảng trắng, trừ %: 22 °C, 8,6 mm, 40 km/h, 66,1%.

# THỜI GIAN
1. Nói mốc thời gian theo cách người dùng hỏi, kèm ngày ngắn trong ngoặc: "hôm qua (thứ Năm, 19/11)", "7 ngày qua
   (13–19/11)", "tuần trước (9–15/11)". Không ghi năm nếu là năm của today. Không dùng dạng 2026-11-19.
2. Giờ viết "1 giờ sáng nay" hoặc "01:00 ngày 20/11".

# TÊN GỌI
1. Gọi chỉ số và cột bằng tên thường ngày (nhiệt độ cao nhất, lượng mưa), không dùng tên kỹ thuật (chữ có dấu gạch
   dưới, mã viết hoa), không dùng dấu `.
2. Tên địa danh lưu không dấu thì viết đủ tên tiếng Việt có dấu; không viết tắt.
3. Không nhắc đến hệ thống bên trong: "bản ghi", "metric", "truy vấn", "cột", "quy tắc chuyên gia",
   "trong dữ liệu ghi là".

# CẤU TRÚC THEO LOẠI CÂU (question_type)
- T1, T2, T3, T9, T15: một câu chứa kết quả, đối tượng, thời gian. Tối đa 2 câu.
- T4: mở đầu bằng "Có," hoặc "Không," rồi đưa con số làm căn cứ nếu có; không nói số đếm vô nghĩa như "ghi nhận
  1 ngày có mưa" cho một ngày.
- Câu hỏi phủ định ("nơi nào không mưa"): trả lời khẳng định, tránh phủ định kép: "Không có nơi nào; cả 4 nơi đều
  có mưa."
- T5, T12: nói số lượng rồi liệt kê. Từ 8 mục trở xuống thì liệt kê trong câu; nhiều hơn thì gạch đầu dòng. Mọi đối
  tượng đều thỏa thì nói "cả N ..." rồi vẫn liệt kê.
- T6, T10: một câu dẫn, rồi bảng (từ 5 dòng) hoặc gạch đầu dòng (dưới 5 dòng). T6 xếp giảm dần theo giá trị, T10
  theo thời gian. Kết bằng một câu nêu điểm nổi bật (cao nhất, thấp nhất, tăng hay giảm) chỉ dùng số đã có.
- T7: tên trước, giá trị sau; top-k thì liệt kê theo thứ hạng.
- T8: kết luận trước (A hơn B, kèm mức chênh nếu draft hoặc data đã có), hai giá trị sau.
- T11: "dao động từ X đến Y".
- T13: kết luận bằng lời thường ("gần như không liên quan"); hệ số và số mẫu để trong ngoặc.
- T22: định nghĩa trong 1 đến 2 câu bằng lời thường.
- Nhiều phần: viết liền mạch theo thứ tự ý, dùng từ nối ("còn", "ở đó"); mốc thời gian chung chỉ nói một lần.
  Phần chưa trả lời được thì nói thẳng phần đó và lý do trong một câu.
- Không có dữ liệu: nói "Chưa có số liệu ..." kèm lý do ngắn.

# GIẢ ĐỊNH VÀ LƯU Ý
1. Draft có "Giả định:" (hệ thống tự chọn cách hiểu vì câu hỏi thiếu thông tin) thì bắt buộc giữ ý đó, viết thành
   mệnh đề ngắn ở câu dẫn, ví dụ "Bạn chưa nêu thành phố nên đây là số liệu từng thành phố:".
2. Draft có "Định nghĩa:" hoặc phần có business_concepts thì nói định nghĩa đã dùng trong một mệnh đề ngắn, bằng
   lời thường. Không có thì không nhắc quy tắc nào.
3. Draft có "Hạn chế:" thì nói ngắn trong một câu.
4. Không thêm lưu ý nào khác: không nói nguồn, loại số liệu, bảng, quy tắc mặc định, cách khớp tên. Những điều đó
   hệ thống hiển thị riêng.

# ĐỊNH DẠNG
- Markdown ngắn, không tiêu đề. In đậm 1 đến 3 con số hoặc kết luận chính, không in đậm ngày tháng.
- Không lặp lại nguyên câu hỏi, không xưng "tôi", không kết bằng lời mời hỏi tiếp.

# ĐẦU RA
Chỉ viết câu trả lời (Markdown), không kèm phần nào khác.

# VÍ DỤ (lĩnh vực khác, chỉ để thấy cách viết)
Đầu vào: question "Số sách mượn tuần trước của từng chi nhánh?", today "2031-03-14 (thứ Sáu)", business_concepts
["lượt mượn hoàn tất"], draft "Tổng số lượt mượn (so_luot_muon) theo chi_nhanh từ 2031-03-03 đến 2031-03-09:
Quan 1 412; Thu Duc 1288; Go Vap 97. Áp dụng quy tắc chuyên gia 'Chỉ tính lượt mượn hoàn tất' trên bản ghi
TRANG_THAI = HOAN_TAT."
Đầu ra:
Tuần trước (3–9/3), Thủ Đức có nhiều lượt mượn sách nhất với **1.288 lượt** (chỉ tính lượt mượn đã trả sách).

- Thủ Đức: 1.288 lượt
- Quận 1: 412 lượt
- Gò Vấp: 97 lượt

Đầu vào: question "Hôm qua cửa hàng nào bán chạy nhất, doanh thu ở đó bao nhiêu?", hai phần, draft 1 "Cửa hàng
bán chạy nhất ngày 2031-03-13 là Ben Thanh (so_don = 86). Dùng bản ghi đơn đã thanh toán.", draft 2 "Doanh thu cửa
hàng Ben Thanh ngày 13/03/2031 là 41250000 VND, tính trên đơn đã thanh toán, không gồm đơn hoàn."
Đầu ra:
Hôm qua (thứ Năm, 13/3), cửa hàng Bến Thành bán chạy nhất với **86 đơn**, doanh thu **41.250.000 đồng**.
```

## 6. A/B offline

**Cách làm** (`scratchpad/ab_writer.py`):

- Lấy 10 bản ghi `#1` của `a2-final-x2.json`. Dựng đầu vào `compose` từ dữ liệu đã lưu: câu viết lại, `question_type`, `business_concepts`, câu trả lời của agent làm `draft`, tối đa 30 dòng của 2 bước truy vấn cuối. Nhãn chỉ có nhãn metric lấy từ `preprocess`; tên cột khác vẫn để thô, tức là trường hợp xấu hơn thực tế.
- Gọi `get_chat_model().stream(...)` với mô hình đang cấu hình. Không chạm database nguồn.
- Chấm lại bằng chính `run_eval.evaluate` với gold đã lưu.

**Vòng 1 (v1).** 7/8 qua chấm. Phát hiện hai lỗi prompt:

- Mô hình tự thêm lưu ý mới ("Đây là số liệu dự báo, không phải số đo thực tế") ở 4/8 câu.
- Mô hình bỏ mất giả định ở M-2, nên bộ chấm `clarify_or_assume` trượt.

Bản v2 sửa hai chỗ: bắt buộc giữ "Giả định", cấm thêm lưu ý khác. v2 cũng bỏ phần ghi chú do LLM viết.

**Vòng 2 (v2), 10 câu: 10/10 qua chấm.** Số lạ không có trong bản nháp: 0. Tổng độ dài giảm từ 2.704 xuống 1.849 ký tự (giảm 32%). Thời gian tới token đầu: trung vị 1,1 giây, dài nhất 5,3 giây ở M-2 (492 token ra, trong đó 327 token suy luận). Tổng thời gian: trung vị 1,8 giây. Token vào: 2.073 đến 3.093.

**Giới hạn của A/B (kiểm lại):**

- **Độ trễ đo khi bộ đệm đã nóng.** Ở v2, `usage_metadata.input_token_details.cache_read` gần bằng toàn bộ token vào ở 9/10 câu, vì cùng đầu vào đã được gửi ở lần chạy trước. Ở v1, khi chỉ phần prompt hệ thống được đệm (1.771 token), thời gian tới token đầu có trung vị **3,2 giây** (cao nhất 8,2 giây) và tổng thời gian có trung vị 3,6 giây. Mô hình có sinh token suy luận (0 đến 327 token) trước chữ đầu tiên, nên thời gian tới token đầu thay đổi theo câu.
- **Bản nháp là câu trả lời cũ của agent**, đã viết khá hoàn chỉnh, chưa phải bản nháp theo prompt mới ở mục 5.1. Đầu vào v2 vẫn có trường `notes`. Mỗi câu chỉ chạy một lần, và v1 chỉ có 8 câu. Kết quả 10/10 cho thấy hướng đi đúng, nhưng chưa phải bằng chứng cho thiết kế cuối cùng.

| Câu | Trước | Sau (v2) |
| --- | --- | --- |
| T4-1 Hôm qua Hà Nội có mưa không? | Có, Hà Nội có mưa hôm qua (19/11/2026): ghi nhận **1 ngày có mưa**. Theo quy tắc nghiệp vụ, ngày có mưa là ngày có tổng lượng mưa ngày lớn hơn 0 mm. | Có, Hà Nội có mưa hôm qua (thứ Năm, 19/11), với lượng mưa ngày lớn hơn 0 mm. |
| T7-1 Thành phố nào nóng nhất hôm qua? | Thành phố **Ho Chi Minh** nóng nhất hôm qua, với nhiệt độ cao nhất **34,7°C** vào ngày **19/11/2026**. Dữ liệu lấy từ bản ghi dự báo theo ngày. | Hôm qua (thứ Năm, 19/11), **TP. Hồ Chí Minh** nóng nhất, với nhiệt độ cao nhất **34,7 °C**. |
| T15-3 Đang theo dõi những thành phố nào? | Hiện đang theo dõi 12 thành phố: Buon Ma Thuot, Can Tho, ..., Thai Binh và Vinh. Đã áp dụng quy tắc chỉ liệt kê thành phố đang hoạt động; không giới hạn theo thời gian. | Đang theo dõi **12 thành phố**: Buôn Ma Thuột, Cần Thơ, Đà Nẵng, Hạ Long, Hà Nội, Hải Phòng, TP. Hồ Chí Minh, Huế, Nha Trang, Phú Quốc, Thái Bình và Vinh. |
| T13-1 Độ ẩm và xác suất mưa ở Huế tuần trước tương quan thế nào? | ...**hầu như không có tương quan tuyến tính**: hệ số tương quan Pearson là **0,035** trên **168 giờ** có đủ dữ liệu, từ **09/11/2026 đến 15/11/2026**. ... Đã dùng các bản ghi dự báo theo giờ; giá trị Huế trong dữ liệu là “Hue”. | Tuần trước (9–15/11), độ ẩm và xác suất mưa theo giờ ở Huế **hầu như không liên quan** (hệ số tương quan 0,035 trên 168 giờ). Độ ẩm trung bình là 87,2%, còn xác suất mưa trung bình là 60,9%. |
| T6-1 Tổng lượng mưa 7 ngày qua từng thành phố? | Bảng, rồi "Tổng hợp từ các bản ghi dự báo theo ngày; quy tắc chỉ số theo ngày đã được áp dụng." | Bảng có đơn vị mm, rồi "Cao nhất là Phú Quốc (**46,9 mm**), thấp nhất là Huế (**8,6 mm**)." |
| T9-2 Tỷ lệ nạp dữ liệu thành công? | ...**97,06%**, tính trên toàn bộ dữ liệu từ **13/11/2026 đến 20/11/2026**. Các lần đang chạy được loại khỏi mẫu số; tỷ lệ được tính trên các lần nạp đã kết thúc. | Tỷ lệ nạp dữ liệu thành công là **97,1%** trên toàn bộ dữ liệu từ 13–20/11; các lần nạp đang chạy không tính vào mẫu số. |
| M-2 Nhiệt độ hôm qua là bao nhiêu? | Danh sách 12 dòng, rồi "Bạn không nêu thành phố nên mình liệt kê ... Áp dụng quy tắc nhiệt độ trung bình dùng các bản ghi dự báo theo giờ." | "Bạn chưa nêu thành phố nên đây là **nhiệt độ trung bình** hôm qua (thứ Năm, 19/11) theo từng nơi: Buôn Ma Thuột 25,1 °C; ...; Vinh 22,5 °C." |
| D-1 (câu phụ thuộc) | Phú Quốc mưa nhiều nhất trong 7 ngày qua, với tổng lượng mưa 46,9 mm từ ngày 13/11/2026 đến hết ngày 19/11/2026, tính theo ... bản ghi dự báo theo ngày. Nhiệt độ cao nhất ở Phú Quốc hôm qua (19/11/2026) là 31,2 °C, theo bản ghi dự báo theo ngày. | Phú Quốc mưa nhiều nhất 7 ngày qua (13–19/11), với **46,9 mm**; còn nhiệt độ cao nhất ở đó hôm qua (thứ Năm, 19/11) là **31,2 °C**. |
| T12-2 Có nơi nào gió giật trên 40 km/h? | Có. Trong tuần trước (09/11–15/11/2026), gió giật tối đa vượt 40 km/h tại **12 địa điểm**: ... Đối chiếu theo gió giật tối đa trong các bản ghi dự báo ngày. | Có, tuần trước (9–15/11), gió giật vượt 40 km/h tại **12 địa điểm**: Buôn Ma Thuột, ..., Vinh. |

**Điểm v2 còn chưa đạt:**

- M-2 liệt kê 12 mục trong một câu, trái quy tắc "hơn 8 mục thì gạch đầu dòng". Câu như vậy khó đọc.
- T5-2 vẫn in đậm phủ định kép "không có thành phố miền Bắc nào không mưa", dù vế sau đã nói rõ.
- T4-1 "với lượng mưa ngày lớn hơn 0 mm" là câu đúng nhưng hơi thừa. Bản nháp có lượng mưa cụ thể (0,9 mm) thì nên dùng số đó; việc này phụ thuộc agent có truy vấn lượng mưa hay không.

Hai điểm đầu có thể sửa bằng một ví dụ thêm hoặc bằng cách để code gợi ý dạng hiển thị (`"layout": "list"` khi số dòng > 8). Một lần chạy cho mỗi câu chưa đủ để kết luận độ ổn định. Cần chạy lại toàn bộ `run_eval.py --repeat 2` sau khi cài đặt.

## 7. Kế hoạch triển khai từng bước

| Bước | Việc | File | Hợp đồng | Kiểm thử |
| --- | --- | --- | --- | --- |
| 1 | Giao diện: đưa câu trả lời lên trước; gộp các thẻ `QueryResult` vào khối thu gọn "Số liệu và cách tính (N)"; tiêu đề cột và nhãn ô đơn dùng nhãn; đổi `TOOL_LABELS` sang tiếng Việt ("Đọc định nghĩa chỉ số", "Tính chỉ số") | `frontend/features/text2sql/chat-turn.tsx`, `query-result.tsx`, `labels.ts`; `docs/handbook/frontend` | Cần nhãn cột từ backend (bước 2) | Test giao diện hiện có, xem bằng trình duyệt |
| 2 | Backend gửi nhãn và đơn vị: `ColumnInfo` thêm `unit`, `format`; `AgentStepOut` thêm `column_labels: list[str]` (nhãn metric cho cột giá trị, `ColumnInfo.label` cho cột nhóm; `run_sql` thì khớp alias với tên cột trong catalog, không khớp thì giữ alias) | `services/agent_catalog.py`, `agent_tools.py`, `schemas`, `chat_events.py`, `frontend/.../types.ts`; `api-chat.md` | Thêm trường, không phá client cũ | `tests/` cho `query_metric` (nhãn đúng), cho `step_event` |
| 3 | Prompt agent: thay mục câu trả lời bằng "BẢN NHÁP" (5.1); sửa bước 3 và bước 7 (`options` dễ đọc) | `prompt_text2sql_agent.py`; `agent_package.md` | Nghĩa của `answers[].answer` đổi thành bản nháp | Chạy `run_eval.py` |
| 4 | Nút `compose` thay `synthesize`: chạy cho mọi lượt có câu trả lời, đầu vào có cấu trúc, dữ liệu định dạng sẵn bằng `vi_number`, đầu ra văn bản; dự phòng bằng bản nháp; chốt kiểm tra số | `services/chat_graph.py` (thân `_synthesize`; nên giữ tên nút `synthesize`, xem 4.2), `chat_events.py` (`update_events` nếu đổi tên nút), `chat_service.py` (`_synthesize`, `_complete` không còn ném `Text2SqlAgentUnavailable` cho bước này), `agent_package/prompts/prompt_compose.py` (mới, thay `prompt_synthesize.py`), `get_chat_completion.py` (bỏ task `synthesize`); `tests/test_text2sql_chat.py`, `tests/test_text2sql_agent.py` đang dùng `synthesize`; hàm định dạng chung đặt ở `backend/common/` | Không đổi request/response; `answer` là văn bản đã viết | Test graph với mô hình giả: câu đơn cũng đi qua `compose`; lỗi LLM thì trả bản nháp; số lạ thì trả bản nháp; chạy tiếp từ snapshot hỏi lại tạo bằng graph cũ; test `vi_number` (kể cả số âm làm tròn về 0) |
| 5 | Stream token: `compose` đẩy `answer_delta` qua `get_stream_writer()`; client ghép dần, event `answer` cuối vẫn là toàn văn | `chat_graph.py`, `chat_events.py`, `frontend/.../use-chat.ts`, `types.ts`; `api-chat.md` | Thêm event `answer_delta` (cùng làm với nghiên cứu streaming) | Test SSE thứ tự event; client cũ bỏ qua event lạ |
| 6 | Khối "Cách tính": `AgentStepOut.rules` có cấu trúc; `done` hoặc response thêm `explanations: [{kind, text}]` do code dựng; giao diện hiển thị khối thu gọn | `sql_builder.py`, `agent_tools.py`, `chat_service.py`, `schemas`, `chat-turn.tsx`; lưu kèm lượt trong `conversation` (`ghi-luot-tu-pipeline.md`) | Thêm trường | Test dựng `explanations` từ steps mẫu |
| 7 | Cập nhật bộ chấm: regex số hiểu dấu chấm ngăn hàng nghìn; `clarify_or_assume` đọc cả `explanations` nếu có; thêm kiểm tra văn phong tự động (không có `_`, \`, `/2026` khi cùng năm, "bản ghi", "metric") làm chỉ số phụ, không làm trượt câu | `scripts/text2sql_eval/run_eval.py`; `danh-gia-chay-that.md` | Không | Chạy lại toàn bộ, so với `a2-final-x2.json` |

Bước 1 và 3 làm độc lập được ngay, ít rủi ro. Bước 4 và 5 nên làm cùng nhóm việc streaming.

## 8. Tương tác với streaming và các bước khác

- **Streaming:** hiện `answer` đến một lần ở cuối. Có `compose` thì token đầu đến khoảng 1 giây sau khi câu con cuối xong. Trong lúc chờ, giao diện vẫn có `ThinkingTrace` theo từng công cụ. `StreamingText` (`frontend/components/streaming-answer.tsx`) đã hỗ trợ nhận Markdown làm `children` khi nội dung tăng dần.
- **Markdown dở dang khi stream:** bảng hoặc `**` chưa đóng sẽ hiện tạm thành ký tự thô trong vài trăm mili giây. Chấp nhận được; nếu cần thì chỉ render lại khi gặp xuống dòng.
- **Lịch sử hội thoại:** `rewrite` dùng `answer` của lượt trước, cắt còn 500 ký tự. Câu trả lời ngắn và không có tên kỹ thuật thì ít bị cắt mất thực thể hơn. Tên có dấu như "Hồ Chí Minh" vẫn khớp được, vì `_resolve_filter_values` so khớp sau khi bỏ dấu và chữ hoa. Riêng tên có tiền tố như "TP. Hồ Chí Minh" thì **không** khớp với `ho chi minh`. Với toán tử `eq`/`in`, code chỉ so `normalized(text)` bằng đúng khóa, nên công cụ báo lỗi "không có giá trị" và agent phải gọi thêm một vòng. Vì vậy hoặc không thêm tiền tố "TP." trong câu trả lời, hoặc cần bảng nhãn giá trị (câu hỏi 5 ở mục 10) để ánh xạ ngược.
- **Hỏi lại:** câu `clarification_question` do agent viết qua `ask_user`, không đi qua `compose`. Chỉ cần sửa prompt bước 7 cho `options`. Nhiều câu cùng hỏi lại thì `clarification_request` đang ghép bằng số thứ tự "1. ...\n2. ...", vẫn đọc được.
- **Chi phí:** thêm 1 lời gọi cho mỗi lượt không tách, khoảng 2.000 đến 3.000 token vào và 50 đến 500 token ra. Với lượt tách, `compose` thay hẳn `synthesize` nên không thêm lời gọi.

## 9. Rủi ro

1. **Bộ chấm đọc sai số có dấu chấm hàng nghìn.** `NUMBER` trong `run_eval.py` đọc "1.288" thành 1,288 và "41.250.000" thành 41,25 (đã chạy thử). Dữ liệu thời tiết hiện ít số từ 1.000 trở lên, nhưng phải sửa trước khi bật quy ước này. Regex thay thế đã thử chạy đúng: `-?\d{1,3}(?:\.\d{3})+(?:,\d+)?` xét trước dạng thường. Cần sửa cả `answer_numbers`: hiện chỉ đổi `,` thành `.`, nên phải bỏ dấu chấm ngăn hàng nghìn trước khi đổi. Regex mới làm số viết kiểu tiếng Anh có đúng 3 chữ số sau dấu chấm (ví dụ "0.035") bị đọc thành 35. Vì vậy prompt phải bắt buộc dùng dấu phẩy thập phân, hoặc số có phần nguyên bằng 0 phải luôn được đọc là số thập phân.
2. **So khớp thực thể.** `check_gold` so tên sau khi bỏ dấu. "TP. Hồ Chí Minh" chứa "ho chi minh" nên qua, nhưng "TP.HCM" sẽ trượt. Prompt đã cấm viết tắt; nên thêm bảng nhãn giá trị (mục 10) để khỏi phụ thuộc mô hình.
3. **Mô hình tự thêm dấu cho tên lạ** có thể sai (tên riêng ít gặp). Cần nhãn giá trị từ data dictionary hoặc bảng danh mục, không để mô hình đoán.
4. **Làm tròn khác bản nháp.** Ngưỡng của bộ chấm là `max(0,051; 0,5%)`: 29,95 thành 30 lệch 0,05, vẫn qua sát nút. Định dạng sẵn trong code (bước 4) loại bỏ rủi ro này.
5. **Bước viết làm mất giả định** (đã gặp ở v1). Chặn bằng prompt v2 và bằng `explanations` có cấu trúc. Có thể thêm kiểm tra: bản nháp có "Giả định:" mà câu trả lời không có cụm nào trong `ASSUMPTION_CUES` thì ghi log.
6. **Độ trễ:** câu đơn chậm thêm khoảng 1 đến 2 giây khi bộ đệm prompt đã nóng, khoảng 3 đến 4 giây khi chưa (v1). Trường hợp chậm nhất đã đo là 6,5 giây (v2) đến 8,9 giây (v1) khi danh sách dài. Bộ đệm prompt của OpenRouter tùy nhà cung cấp và mô hình, nên không thể coi là luôn có.
8. **Hai báo cáo stream lệch nhau:** báo cáo streaming đề xuất stream thẳng câu trả lời của agent cho câu không tách. Phương án B ở đây biến câu đó thành bản nháp. Cần chọn một hợp đồng `answer_delta` chung trước khi làm (mục 4.2).
7. **Đổi nghĩa `answers[].answer`** thành bản nháp: giao diện lịch sử và `StoredQuestion.answer` cần ghi rõ, kẻo có nơi hiển thị bản nháp cho người dùng.

## 10. Câu hỏi cần người dùng quyết

1. Chấp nhận thêm 1 lời gọi LLM (khoảng 1 đến 4 giây tới chữ đầu tùy bộ đệm, có stream) cho câu không tách để có văn phong thống nhất (phương án B)? Hay làm phương án A trước (chỉ sửa prompt, không thêm độ trễ)?
2. Giao diện: câu trả lời lên đầu, bảng số liệu và SQL thu gọn vào "Số liệu và cách tính"? Hay giữ thẻ kết quả mở sẵn như hiện nay?
3. Xưng hô: không chủ ngữ ("Bạn chưa nêu thành phố nên ..."), hay xưng "mình", hay xưng "tôi"?
4. Năm trong ngày tháng: bỏ năm khi trùng năm hiện tại? Có thêm thứ ("thứ Năm, 19/11") cho mốc một ngày không?
5. Tên giá trị không dấu (Ha Noi): thêm "nhãn hiển thị cho giá trị" vào data dictionary (ví dụ khai báo cột nhãn ở bảng danh mục, hoặc bảng ánh xạ giá trị sang nhãn)? Hay chấp nhận để mô hình tự thêm dấu?
6. Câu trả lời dùng dữ liệu dự báo cho ngày đã qua (cách dữ liệu nguồn đang lưu): có cần nói "theo dự báo" trong câu trả lời không? Hiện đề xuất chỉ để trong khối "Cách tính".
7. Có thêm kiểm tra văn phong tự động vào `run_eval.py` làm chỉ số theo dõi (không làm trượt câu) không?

## Phụ lục: phiên bản và cách kiểm chứng

- Thư viện theo `uv.lock`: `langchain-core` 1.8.0, `langchain-openai` 1.7.4, `langgraph` 1.2.23, `openai` 3.50.0, `pydantic` 2.14.3.
- Frontend theo `frontend/node_modules`: `react-markdown` 10.1.0, `remark-gfm` 4.0.1, `next` 16.4.6, `react` 19.3.0.
- `Intl` vi-VN kiểm bằng Node v24.19.0. Hàm `vi_number` và regex số mới kiểm bằng Python trong scratchpad.
- `ChatOpenAI.stream(messages, stream_usage=True)` trả chunk dần và có `usage_metadata` ở chunk cuối, đã chạy thật trong A/B.
- Script và kết quả (scratchpad, không thuộc repo):
  - `C:\Users\dat\AppData\Local\Temp\claude\d--Code-Superset-AI\3428e385-9db2-46b6-835b-611b745f0661\scratchpad\ab_writer.py`
  - `...\scratchpad\writer_prompt.py` (v2), `...\scratchpad\writer_prompt_v1.py`
  - `...\scratchpad\ab_results_v1.json`, `...\scratchpad\ab_results_v2.json`
  - `...\scratchpad\stats.py`, `...\scratchpad\scan.py`, `...\scratchpad\scan.txt`
- Tài liệu tham khảo:
  - LangGraph streaming (chế độ `custom`, `get_stream_writer`): https://docs.langchain.com/oss/python/langgraph/streaming
  - `Intl.NumberFormat`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
  - Hành vi thực tế đã kiểm bằng code cài sẵn như trên, không chỉ dựa vào tài liệu.

## Kiểm tra lại

Người rà soát đã đối chiếu từng khẳng định với code, thư viện đã cài và kết quả trong scratchpad, ngày 2026-11-20.

**Khớp, giữ nguyên:**

- Phiên bản: `uv.lock` (langchain-core 1.8.0, langchain-openai 1.7.4, langgraph 1.2.23, openai 3.50.0, pydantic 2.14.3, không có babel), `frontend/node_modules` (react-markdown 10.1.0, remark-gfm 4.0.1, next 16.4.6, react 19.3.0) và Node v24.19.0.
- Chạy lại `stats.py` trên `a2-final-x2.json`: 96 câu; 74 (77%) nhắc bản ghi hoặc dự báo; 75 câu có câu cuối nói cách tính; 86 câu ghi `/2026`; 23 câu nhắc quy tắc; 8 câu có tên không dấu; 3 câu có dấu \`. Regex đếm câu cuối khá rộng (có cả "Dùng", "Tính theo"), nên 78% là ước lượng.
- Trích dẫn prompt (`prompt_text2sql_agent.py` dòng 24–25 và 58; `prompt_synthesize.py` điểm 3), `ColumnInfo.describe` không có `unit` và `format`, `MetricInfo.format`, chuỗi ghi chú ở `sql_builder.py` dòng 200–215, thứ tự hiển thị trong `chat-turn.tsx`, `TOOL_LABELS`, `step.columns`, `step.notes`, "Tham số của công cụ" trong `query-result.tsx`, `HISTORY_ANSWER_LENGTH = 500`, quy định few-shot trong `agent_package.md`.
- `Intl` vi-VN cho kết quả đúng như bảng 3.2. Regex `NUMBER` hiện tại đọc "41.250.000" thành 41,25 và regex mới đọc đúng.
- Số liệu A/B tính lại từ `ab_results_v1.json` và `ab_results_v2.json`: v1 qua 7/8, v2 qua 10/10; độ dài 2.704 xuống 1.849; v2 có trung vị thời gian tới token đầu 1,115 giây, tổng 1,8 giây, token vào 2.073 đến 3.093. Kiểm lại số lạ bằng `scratchpad/rv_nums.py`: 0/10.

**Đã sửa trong báo cáo:**

1. Độ trễ 1,1 giây đo khi bộ đệm prompt đã nóng (v2 có `cache_read` gần bằng toàn bộ token vào). Khi chưa nóng (v1), trung vị là 3,2 giây tới token đầu và 3,6 giây tổng. Đã ghi rõ ở mục 1, 4.1, 6, rủi ro 6 và câu hỏi 1.
2. A/B dùng câu trả lời cũ của agent làm bản nháp, chưa phải bản nháp theo prompt mới; `ab_writer.py` không kiểm số lạ. Đã ghi ở mục 6 và 4.4.
3. Mục 8: "TP. Hồ Chí Minh" **không** khớp được với `Ho Chi Minh` trong `_resolve_filter_values`, vì code so cả chuỗi sau khi bỏ dấu.
4. Mục 4.2: phần dự phòng là hành vi mới (hiện `synthesize` lỗi thì ném `Text2SqlAgentUnavailable`). Đã thêm timeout 60 giây × 2 lần thử lại và trường hợp lỗi giữa lúc stream.
5. Mục 4.2 và bước 4: event `answer` gắn với tên nút `synthesize` trong `chat_events.update_events`. Khuyên giữ tên nút để không ảnh hưởng snapshot hỏi lại. Đã thêm các file test đang dùng `synthesize`.
6. Mục 4.2 và rủi ro 8: báo cáo streaming đã định nghĩa `answer_delta` với `position`, `round`, `final`, và stream câu trả lời của agent làm bản chính. Hai báo cáo phải thống nhất.
7. `vi_number` cho ra `"-0"` với số âm làm tròn về 0. Đã thêm cách sửa và chạy lại (`scratchpad/rv_fix.py`).
8. Rủi ro 1: `answer_numbers` cũng phải bỏ dấu chấm ngăn hàng nghìn. Regex mới đọc "0.035" kiểu tiếng Anh thành 35.
9. T8: ví dụ "chênh 12,7 °C" là phép tính mới nếu bản nháp chưa có số này, trái quy tắc "không tính thêm". Đã thêm điều kiện ở bảng 3.3 và trong prompt.
10. Thêm phương án A+ (sửa prompt và hậu xử lý bằng code) vào bảng 4.1. Thêm lưu ý `MetricInfo.format` là định dạng d3 (`.1%`, `SMART_NUMBER`).

**Chưa kiểm được:** chạy tiếp từ snapshot hỏi lại sau khi đổi tên nút (cần test thật), và độ ổn định khi chạy lặp bước viết, vì A/B chỉ chạy mỗi câu một lần.
