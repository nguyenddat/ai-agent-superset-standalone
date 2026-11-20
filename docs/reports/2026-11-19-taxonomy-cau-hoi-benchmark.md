# Taxonomy câu hỏi cho benchmark hỏi đáp số liệu (kho thời tiết)

**Ngày:** 19/11/2026. **Trạng thái:** đề xuất. Tài liệu này đi kèm [đề xuất benchmark](2026-11-19-de-xuat-benchmark-text2sql.md) và thay cho bảng nhóm câu hỏi ở mục 4 của đề xuất đó.

## 1. Cách xây taxonomy

### 1.1. Nguồn tham khảo và phần lấy từ mỗi nguồn

| Nguồn | Lấy gì |
|---|---|
| Amar, Eagan, Stasko (InfoVis 2005): 10 tác vụ phân tích mức thấp | Trục chính theo **ý định**: tra giá trị, lọc, tính giá trị dẫn xuất, tìm cực trị, sắp xếp, xác định khoảng, mô tả phân bố, tìm bất thường, gom cụm, tương quan |
| WikiTableQuestions (Pasupat & Liang 2015) | Nhóm theo **phép toán**: tra cứu, tổng hợp, so sánh hơn và so sánh nhất, số học |
| BIRD (NeurIPS 2023) | Bốn loại **tri thức** cần để viết SQL: suy luận số, tri thức miền, từ đồng nghĩa, minh họa giá trị (chiếm 70% câu của BIRD). Đây chính là lỗi "Hà Nội" / "Ha Noi" |
| Dr.Spider (ICLR 2023) | **Biến thể có cặp**: đổi từ khóa, tên cột, giá trị nhưng giữ nguyên nghĩa. Biến thể giá trị là loại khó nhất |
| EHRSQL (2023), ChronoQA (2025) | **Biểu thức thời gian** tuyệt đối, tương đối, ngầm; cố định "thời điểm hiện tại" để đáp án ổn định. ChronoQA ghi nhận câu thời gian tương đối chiếm 69% lỗi |
| SParC, CoSQL (2019) | **Hội thoại nhiều lượt** theo bốn quan hệ: tinh chỉnh, cùng thực thể, cùng thuộc tính, dựa trên câu trả lời trước |
| AMBROSIA (2024), Text2Analysis (AAAI 2024) | **Mơ hồ**: phạm vi, gắn kết, mơ hồ nghĩa; thiếu tham số (loại mơ hồ phổ biến nhất trong Text2Analysis) |
| TriageSQL (2020), Wang và cộng sự (ACL Findings 2023), PremiseSQL (2026) | **Không trả lời được**: ngoài miền, thiếu cột, thiếu giá trị, phép tính không làm được, phi SQL, tiền đề sai |
| InsightBench (ICLR 2025) | Mức phân tích mô tả, chẩn đoán, dự đoán, đề xuất. Chỉ dùng để xác định ranh giới: câu chẩn đoán và đề xuất nằm ngoài khả năng của luồng hiện tại |

### 1.2. Nguyên tắc

- **Một trục chính.** Mỗi câu thuộc đúng một loại, xác định theo **ý định và dạng đáp án**. Loại quyết định cách chấm.
- **Các trục phụ là tag**, không tách thành loại riêng: đường đi (metric hay nhiều bảng), quy tắc chuyên gia, loại bản ghi, kiểu thời gian, phạm vi thực thể, loại tri thức BIRD, độ khó. Tag dùng để phân tầng khi lấy mẫu và cắt điểm khi báo cáo.
- **Loại nào cũng trả lời được bằng dữ liệu thật trong `data_wh`.** Ví dụ trong tài liệu đã đối chiếu với các cột hiện có. Generator phải kiểm tra lại đáp án trên snapshot: không rỗng ngoài chủ ý, không hòa ở câu so sánh nhất, không toàn `NULL`.
- **Mỗi loại 20 đến 30 câu**, phân bổ đều qua các loại con và tag để điểm từng loại có ý nghĩa thống kê. Với 25 câu, sai số chuẩn của tỷ lệ đúng khoảng ±10 điểm phần trăm, nên chỉ kết luận khi hai lần chạy chênh nhau lớn hơn mức này.

### 1.3. Dữ liệu dùng để ra đề

- **Bảng sự kiện `fact_tong_hop_thoi_tiet`:** gồm 3 loại bản ghi `HIEN_TAI`, `DU_BAO_NGAY` (06/11 đến 25/11) và `DU_BAO_GIO`. Các chỉ số: nhiệt độ, cảm nhận, độ ẩm, lượng mưa, mưa rào, xác suất mưa, áp suất, mây, gió, gió giật, tầm nhìn, số giờ có mưa, thời lượng nắng, thời lượng ban ngày.
- **Các chiều:**
  - 12 thành phố;
  - 7 vùng (`vung`) và 4 vùng khí hậu (`vung_khi_hau`);
  - 21 điều kiện thời tiết thuộc 7 nhóm mức độ (Mua, Mua lon, Dong, Tuyet, Nguy hiem, Han che tam nhin, Binh thuong);
  - lịch `dim_ngay` có thứ và cờ cuối tuần.
- **Vận hành ETL `tb_lan_nap_du_lieu`:** 28 lần nạp (27 thành công, 1 thất bại), thời điểm, số thành phố, số quan sát.
- **Tri thức đã khai báo:** 16 metric, 21 thuật ngữ, 8 quy tắc.
- **Lưu ý:** tên thành phố, vùng và điều kiện lưu **không dấu**.

## 2. Dạng đáp án chuẩn (gold) và cách so

| Dạng | Ví dụ | Cách so |
|---|---|---|
| `scalar` | `29.5` | Sai số tuyệt đối theo đơn vị (nhiệt 0,05 °C; mưa 0,05 mm; tỷ lệ 0,1 điểm %) |
| `boolean` | `true` kèm số làm căn cứ | Đúng giá trị logic; căn cứ so như `scalar` |
| `entity` | `Ho Chi Minh` | So sau khi bỏ dấu, chuẩn hóa chữ hoa, chữ thường và bí danh (TP.HCM, Sài Gòn) |
| `set` | `{Hue, Vinh}` | Bằng tập; báo thêm precision và recall để chẩn đoán |
| `ordered_list` | top 3 có thứ tự | Đúng thứ tự; chấp nhận hoán vị trong nhóm hòa |
| `table` | thành phố → giá trị | Khớp tập dòng, không xét thứ tự; cho phép thừa cột |
| `series` | ngày → giá trị | Khớp từng mốc thời gian |
| `tuple` | (bên thắng, chênh lệch) | Khớp từng thành phần |
| `text` | định nghĩa (T22) | Có đủ các ý chính bắt buộc (so khớp sau khi bỏ dấu) |
| `status` | `needs_clarification`, `no_metric` | Trạng thái nằm trong danh sách chấp nhận và **không có số liệu bịa** |

Mỗi câu khai báo `answer_type` và `gold_sql`. Đáp án tính lại trên snapshot khi chạy, không lưu số cứng. Câu có thể diễn giải nhiều cách (loại T19) có `gold_sql` là một danh sách các cách hiểu được chấp nhận.

## 3. Taxonomy: 22 loại, 5 nhóm, khoảng 540 câu

Tổng quan:

| Nhóm | Loại | Dạng gold | Số câu | Ưu tiên |
|---|---|---|---|---|
| A. Truy xuất và tổng hợp | T1 Tra cứu giá trị | scalar | 25 | P0 |
| | T2 Tổng hợp theo khoảng hoặc tập | scalar | 30 | P0 |
| | T3 Đếm theo điều kiện | scalar (số nguyên) | 25 | P1 |
| | T4 Câu hỏi có/không | boolean | 20 | P1 |
| | T5 Liệt kê, lọc | set | 25 | P1 |
| | T6 Phân nhóm theo chiều | table | 25 | P1 |
| B. So sánh và quan hệ | T7 Cực trị, xếp hạng | entity, ordered_list | 30 | P0 |
| | T8 So sánh | tuple | 30 | P0 |
| | T9 Giá trị dẫn xuất | scalar | 25 | P1 |
| | T10 Xu hướng, chuỗi thời gian | series | 25 | P1 |
| | T11 Khoảng và phân bố | tuple, table | 20 | P2 |
| | T12 Bất thường, vượt ngưỡng | set | 20 | P2 |
| | T13 Tương quan | scalar, tuple | 20 | P2 |
| C. Tri thức nghiệp vụ | T22 Hỏi định nghĩa nghiệp vụ (không cần số liệu) | text có ý chính | 20 | P1 |
| | T14 Áp dụng định nghĩa nghiệp vụ trên số liệu | theo câu | 24 | P0 |
| | T15 Dữ liệu và vận hành | theo câu | 20 | P2 |
| D. Ngôn ngữ và ngữ cảnh | T16 Biến thể diễn đạt | như câu gốc | 30 | P1 |
| | T17 Biểu thức thời gian | theo câu | 30 | P0 |
| | T18 Hội thoại nhiều lượt | theo lượt | 20 hội thoại | P2 |
| | T21 Câu ghép nhiều ý | tuple | 20 | P0 |
| E. Không trả lời thẳng được | T19 Mơ hồ | status hoặc nhiều cách hiểu | 25 | P1 |
| | T20 Không trả lời được | status | 30 | P0 |

**Ưu tiên:** P0 là bản tối thiểu (khoảng 220 câu). P1 làm tiếp theo. P2 làm khi hai mức đầu ổn định.

Mã loại giữ cố định để báo cáo so sánh được qua các phiên bản. T21 và T22 được thêm sau nên không đánh số lại các loại cũ.

---

### Nhóm A. Truy xuất và tổng hợp (mô tả "điều gì đã xảy ra")

#### T1. Tra cứu giá trị (Retrieve Value): 25 câu
Một chỉ số, một thực thể, một mốc thời gian; đáp án là một con số có đơn vị. Đây là loại đơn giản nhất, dùng để tách lỗi chọn metric, lọc giá trị và áp quy tắc khỏi các lỗi suy luận phức tạp.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Chỉ số theo ngày (bản ghi `DU_BAO_NGAY`) | 10 | "Nhiệt độ cao nhất ở Hà Nội hôm qua là bao nhiêu?" · "Tổng lượng mưa ở Vinh ngày 15/11?" |
| Thời tiết hiện tại (quy tắc lấy bản ghi mới nhất) | 6 | "Bây giờ ở Đà Nẵng bao nhiêu độ?" · "Độ ẩm hiện tại ở Cần Thơ?" |
| Chỉ số theo giờ | 5 | "Lúc 14 giờ hôm qua ở Huế gió bao nhiêu km/h?" |
| Dự báo tương lai | 4 | "Ngày mai Hải Phòng nhiệt độ thấp nhất bao nhiêu?" |

Tag cần phủ: mỗi thành phố xuất hiện ít nhất 1 lần, ít nhất 8 chỉ số khác nhau. Gold: `scalar`.

#### T2. Tổng hợp theo khoảng hoặc tập (Aggregation): 30 câu
Gộp nhiều bản ghi bằng tổng, trung bình, lớn nhất, nhỏ nhất. Kiểm tra chọn đúng phép gộp, đúng loại bản ghi (chỉ số ngày hay giờ) và đúng phạm vi.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Tổng theo khoảng thời gian | 8 | "Tổng lượng mưa ở Huế 7 ngày qua?" |
| Trung bình (quy tắc dùng bản ghi giờ) | 8 | "Độ ẩm trung bình ở Hà Nội tuần này?" |
| Lớn nhất, nhỏ nhất trên khoảng | 7 | "Nhiệt độ thấp nhất ở Buôn Ma Thuột trong 5 ngày qua?" |
| Gộp trên tập thực thể (vùng, cả nước) | 7 | "Lượng mưa trung bình các thành phố miền Trung hôm qua?" |

Bẫy cần có: trung bình của trung bình ngày khác trung bình theo giờ; tổng lượng mưa cộng theo ngày, không cộng theo giờ. Gold: `scalar`.

#### T3. Đếm theo điều kiện (Count): 25 câu
Đếm ngày, giờ, thành phố hoặc lần nạp thỏa điều kiện. Thường dựa vào định nghĩa nghiệp vụ.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Đếm ngày | 10 | "Tuần qua Đà Nẵng có mấy ngày mưa?" (ngày có mưa: tổng lượng mưa ngày > 0) |
| Đếm giờ | 5 | "Hôm qua Hà Nội có bao nhiêu giờ có mưa?" |
| Đếm thực thể | 6 | "Có bao nhiêu thành phố có dông hôm qua?" · "Bao nhiêu thành phố đang được theo dõi?" |
| Đếm distinct, tránh đếm trùng | 4 | "Có bao nhiêu điều kiện thời tiết khác nhau xuất hiện ở Phú Quốc tuần này?" |

Gold: `scalar`, số nguyên, so tuyệt đối.

#### T4. Câu hỏi có/không (Boolean): 20 câu
Kiểm tra một điều kiện. Câu trả lời phải đúng giá trị logic và có số làm căn cứ. Loại này dễ bị trả lời "có" theo cảm tính mà không truy vấn.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Sự kiện xảy ra | 8 | "Hôm qua Hà Nội có mưa không?" · "Ngày mai Huế có dông không?" |
| Vượt ngưỡng | 6 | "Hôm qua TP.HCM có nóng trên 33 độ không?" |
| Tồn tại trong tập | 6 | "Tuần này có thành phố nào bị thời tiết nguy hiểm không?" |

Cân bằng 50% câu đúng và 50% câu sai. Gold: `boolean` kèm căn cứ.

#### T5. Liệt kê, lọc (Filter): 25 câu
Trả về tập thực thể (thành phố, ngày, điều kiện) thỏa điều kiện.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Lọc thành phố theo chỉ số | 8 | "Những thành phố nào có mưa hôm qua?" |
| Lọc ngày | 7 | "Những ngày nào trong tuần qua Vinh có mưa trên 10 mm?" |
| Lọc theo điều kiện thời tiết (nhiều bảng) | 5 | "Thành phố nào có dông trong 3 ngày qua?" |
| Lọc kết hợp (AND, OR, NOT) | 5 | "Thành phố miền Bắc nào không mưa hôm qua?" |

Cần có 2 hoặc 3 câu cố ý cho tập rỗng, để kiểm tra hệ thống trả "không có" chứ không bịa. Gold: `set`.

#### T6. Phân nhóm theo chiều (Breakdown): 25 câu
Một chỉ số tách theo một hoặc hai chiều. Kiểm tra `group_by` và cách nối chiều.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Theo thành phố | 8 | "Lượng mưa tuần qua của từng thành phố?" |
| Theo vùng, vùng khí hậu | 7 | "Nhiệt độ trung bình hôm qua theo vùng khí hậu?" |
| Theo nhóm mức độ, điều kiện thời tiết | 5 | "Số giờ theo từng loại thời tiết ở Hà Nội hôm qua?" |
| Hai chiều | 5 | "Lượng mưa theo thành phố và theo ngày trong 3 ngày qua?" |

Gold: `table`.

### Nhóm B. So sánh và quan hệ

#### T7. Cực trị, xếp hạng (Find Extremum, Sort, Top-k): 30 câu
Loại xuất hiện nhiều trong cả WikiTableQuestions và BIRD. Kiểm tra hướng sắp xếp, `limit`, xử lý hòa và trả đúng thực thể kèm giá trị.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Thực thể cao nhất, thấp nhất | 10 | "Thành phố nào nóng nhất hôm qua?" · "Nơi nào gió mạnh nhất tuần này?" |
| Ngày, giờ cực trị | 7 | "Ngày nào trong tuần qua Hà Nội mưa nhiều nhất?" · "Mấy giờ hôm qua Huế nóng nhất?" |
| Top k, bottom k | 8 | "3 thành phố mưa nhiều nhất 7 ngày qua?" |
| Xếp hạng đầy đủ, thứ hạng của một thực thể | 5 | "Đà Nẵng đứng thứ mấy về lượng mưa tuần qua?" |

Generator loại bỏ câu có hòa ở vị trí được hỏi, hoặc ghi rõ trong gold là chấp nhận cả hai. Gold: `entity` hoặc `ordered_list`.

#### T8. So sánh (Comparison): 30 câu
Phép so sánh hai vế. Đáp án gồm bên lớn hơn hoặc nhỏ hơn và mức chênh.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Thực thể với thực thể | 8 | "Hôm qua Hà Nội hay TP.HCM nóng hơn, chênh bao nhiêu độ?" |
| Kỳ với kỳ | 8 | "Hôm nay Huế mưa nhiều hơn hôm qua không?" · "Tuần này so với tuần trước?" |
| Thực thể với mức chung | 6 | "Lượng mưa Vinh hôm qua cao hơn trung bình cả nước bao nhiêu?" |
| Quá khứ với dự báo | 4 | "Ngày mai Đà Nẵng có mát hơn hôm nay không?" |
| Nhóm với nhóm | 4 | "Miền Bắc hay miền Nam mưa nhiều hơn tuần qua?" |

Gold: `tuple` (bên thắng, chênh lệch tuyệt đối; thêm chênh lệch % nếu được hỏi).

#### T9. Giá trị dẫn xuất (Compute Derived Value): 25 câu
Phép tính không có sẵn thành metric, tương ứng loại "suy luận số" của BIRD.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Hiệu, biên độ | 8 | "Biên độ nhiệt ở Hà Nội hôm qua là bao nhiêu?" (cao nhất trừ thấp nhất) |
| Tỷ lệ, phần trăm | 7 | "Tỷ lệ ngày có mưa ở Huế trong tuần qua?" · "Tỷ lệ nạp dữ liệu thành công?" |
| Tỷ trọng | 5 | "Hà Nội chiếm bao nhiêu % tổng lượng mưa miền Bắc tuần qua?" |
| Mức thay đổi | 5 | "Nhiệt độ cao nhất ở Đà Nẵng tăng bao nhiêu % so với hôm kia?" |

Gold: `scalar`; so sai số tương đối với phần trăm.

#### T10. Xu hướng, chuỗi thời gian (Trend): 25 câu

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Chuỗi theo ngày | 10 | "Nhiệt độ cao nhất ở Hà Nội từng ngày trong tuần qua?" |
| Chuỗi theo giờ | 5 | "Diễn biến nhiệt độ theo giờ ở Huế hôm qua?" |
| Hướng xu hướng | 6 | "Nhiệt độ ở TP.HCM mấy ngày qua đang tăng hay giảm?" |
| Chuỗi dự báo | 4 | "Dự báo lượng mưa 5 ngày tới ở Đà Nẵng?" |

Câu hỏi về hướng xu hướng cần định nghĩa rõ trong gold (độ dốc hồi quy tuyến tính hoặc so đầu kỳ với cuối kỳ) và chỉ chọn trường hợp rõ ràng. Gold: `series`, hoặc `entity` (tăng / giảm / đi ngang) kèm chuỗi.

#### T11. Khoảng và phân bố (Determine Range, Characterize Distribution): 20 câu

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Khoảng dao động | 8 | "Nhiệt độ ở Buôn Ma Thuột hôm qua dao động trong khoảng nào?" · "Độ ẩm ở Cần Thơ tuần qua thấp nhất và cao nhất bao nhiêu?" |
| Phân bố theo nhóm | 7 | "Phân bố các loại thời tiết ở Hà Nội tuần qua?" |
| Giá trị phổ biến nhất (mode) | 5 | "Kiểu thời tiết xuất hiện nhiều nhất ở Phú Quốc tuần này?" |

Phần lớn câu loại này đi nhánh nhiều bảng (`query_dataset`). Gold: `tuple` (min, max) hoặc `table`.

#### T12. Bất thường, vượt ngưỡng (Find Anomalies): 20 câu

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Theo quy tắc cảnh báo | 7 | "Thành phố nào có thời tiết xấu cần cảnh báo hôm qua?" |
| Vượt ngưỡng tuyệt đối | 7 | "Có nơi nào gió giật trên 40 km/h tuần này không, ở đâu?" |
| Lệch so với mức thường | 6 | "Ngày nào nhiệt độ Hà Nội cao bất thường so với trung bình 7 ngày?" (gold định nghĩa lệch ≥ 2 độ lệch chuẩn) |

Gold: `set`.

#### T13. Tương quan (Correlate): 20 câu
Mức khó nhất trong nhóm B. Có thể làm bằng SQL (`corr()`), nhưng hệ thống có thể chưa hỗ trợ biểu thức này. Loại này đo **giới hạn hiện tại**; khi chưa hỗ trợ, kết quả chấp nhận được là báo rõ không làm được.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Hệ số tương quan | 8 | "Độ ẩm và lượng mưa theo giờ ở Huế tuần qua tương quan thế nào?" |
| So sánh có điều kiện | 8 | "Ngày có mưa ở Hà Nội có mát hơn ngày không mưa không, chênh bao nhiêu?" |
| Đồng xuất hiện | 4 | "Khi có dông thì gió giật trung bình bao nhiêu?" |

Gold: `scalar` (hệ số, sai số 0,02) hoặc `tuple`. `accept_status` gồm cả `no_metric` có thông điệp rõ.

### Nhóm C. Tri thức nghiệp vụ

Nhóm này tách hai trường hợp khác hẳn nhau về luồng xử lý:
- **T22:** người dùng hỏi về **chính định nghĩa**. Câu trả lời nằm trong tầng tri thức (thuật ngữ, quy tắc, mô tả metric), không cần truy vấn database.
- **T14:** người dùng hỏi **số liệu**, và số liệu chỉ đúng khi áp đúng định nghĩa.

#### T22. Hỏi định nghĩa nghiệp vụ (không cần số liệu): 20 câu
Trả lời thẳng từ thuật ngữ, quy tắc chuyên gia và mô tả metric đã truy hồi. **Không truy vấn database.** Nếu hệ thống vẫn chạy truy vấn, câu vẫn tính đúng nếu nội dung đúng, nhưng bị ghi nhận là thừa bước (tốn thời gian, có rủi ro kéo số liệu không cần thiết vào câu trả lời).

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Định nghĩa của quy tắc | 8 | "Thế nào thì được tính là ngày có mưa?" · "Thời tiết xấu cần cảnh báo gồm những loại nào?" · "Cuối tuần tính những ngày nào?" |
| Cách tính của metric | 6 | "Nhiệt độ trung bình được tính trên dữ liệu gì?" · "Tỷ lệ ngày có mưa tính thế nào?" |
| Phân biệt khái niệm | 6 | "Nhiệt độ hiện tại khác nhiệt độ trung bình thế nào?" · "Tổng lượng mưa và xác suất mưa khác nhau ra sao?" |

Gold:
- `answer_type: text`, kèm danh sách **ý chính bắt buộc** lấy từ nội dung quy tắc hoặc metric đã khai báo (ví dụ: "tổng lượng mưa ngày > 0 mm", "dùng bản ghi dự báo theo ngày").
- Chấm bằng cách kiểm tra từng ý chính có trong câu trả lời: bỏ dấu, so khớp từ khóa, chấp nhận vài cách diễn đạt.
- Chấm thêm cờ `queried_db` (có truy vấn database hay không) và danh sách tri thức đã truy hồi (đúng quy tắc, đúng metric).

#### T14. Áp dụng định nghĩa nghiệp vụ trên số liệu: 24 câu, 3 câu cho mỗi quy tắc
Đáp án chỉ đúng nếu áp đúng định nghĩa đã khai báo. Đây là loại kiểm tra trực tiếp thiết kế "quy tắc áp dụng tự động".

| Quy tắc | Ba câu: dùng thẳng, câu hỏi tự ghi đè, metric không liên quan |
|---|---|
| Chỉ số theo ngày dùng bản ghi dự báo ngày | "Nhiệt độ cao nhất Hà Nội hôm qua" · "Nhiệt độ cao nhất **theo giờ** hôm qua" · câu về độ ẩm (không được áp quy tắc này) |
| Chỉ số trung bình dùng bản ghi giờ | tương tự |
| Thời tiết hiện tại lấy bản ghi mới nhất | "Bây giờ…" · "Lúc 9 giờ sáng nay…" · … |
| Ngày có mưa tính trên tổng lượng mưa ngày | "Mấy ngày mưa…" · "Mấy ngày mưa **trên 5 mm**…" · … |
| Cuối tuần là thứ Bảy và Chủ nhật | "Cuối tuần qua…" · "Chủ nhật vừa rồi…" · … |
| Thời tiết xấu cần cảnh báo | … |
| Chỉ tính thành phố đang theo dõi | "Bao nhiêu thành phố…" · "Kể cả thành phố đã ngừng theo dõi…" · … |
| Lần nạp thất bại | … |

Ngoài kết quả, chấm thêm: điều kiện quy tắc có trong SQL, `overridden` đúng khi câu hỏi tự lọc cùng cột, và quy tắc không bị áp sang metric khác.

#### T15. Dữ liệu và vận hành (Meta, ETL): 20 câu

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Vận hành ETL | 8 | "Hôm qua nạp dữ liệu mấy lần, có lần nào lỗi không?" · "Thời gian nạp trung bình?" |
| Độ mới của dữ liệu | 4 | "Dữ liệu cập nhật lần cuối lúc nào?" |
| Danh mục | 8 | "Đang theo dõi những thành phố nào?" · "Đơn vị của tốc độ gió là gì?" · "Có những loại thời tiết nào được coi là nguy hiểm?" |

Câu danh mục kiểm tra hệ thống có trả lời từ bảng danh mục hay từ chối. Gold: theo câu.

### Nhóm D. Ngôn ngữ và ngữ cảnh

#### T16. Biến thể diễn đạt (Perturbation, theo Dr.Spider): 30 câu
Mỗi câu là **bản biến thể của một câu ở T1, T2, T7 hoặc T8** và dùng chung gold với câu gốc. Chỉ số chính là **độ bền**: tỷ lệ cặp mà câu gốc và biến thể cùng đúng.

| Loại con (tên Dr.Spider) | Số câu | Ví dụ biến thể |
|---|---|---|
| Đồng nghĩa giá trị | 8 | Hà Nội → "HN", "Ha Noi", "thủ đô"; TP.HCM → "Sài Gòn", "SG"; Huế → "cố đô" |
| Đồng nghĩa cột, chỉ số | 6 | "nhiệt độ cao nhất" → "nóng nhất mấy độ", "nhiệt độ max"; "lượng mưa" → "mưa bao nhiêu mm" |
| Đồng nghĩa từ khóa | 4 | "nhiều nhất" → "dẫn đầu"; "ít nhất 10" → "không dưới 10" |
| Không dấu, sai chính tả | 6 | "nhiet do cao nhat o ha noi hom qua"; "nhiệt đọ" |
| Tiếng Anh, trộn ngôn ngữ | 3 | "Max temperature in Hanoi yesterday?" |
| Diễn đạt dài, vòng vo | 3 | câu có thêm ngữ cảnh không liên quan |

Gold: như câu gốc. Báo cáo cả độ chính xác tuyệt đối lẫn độ bền theo cặp.

#### T17. Biểu thức thời gian (Temporal, theo EHRSQL và ChronoQA): 30 câu
Tách riêng vì lỗi thời gian tương đối là nhóm lỗi lớn nhất trong ChronoQA, và `today` có thể cố định được. Chỉ số và thực thể giữ đơn giản để cô lập lỗi thời gian.

| Loại con | Số câu | Ví dụ (today = 2026-11-19, thứ Năm) |
|---|---|---|
| Tuyệt đối | 5 | "ngày 12/11", "từ 10 đến 15/11", "18-11-2026" |
| Tương đối theo ngày | 6 | "hôm qua", "hôm kia", "3 ngày qua", "7 ngày tới" |
| Tương đối theo tuần | 6 | "tuần này", "tuần trước", "đầu tuần", "cuối tuần qua" |
| Theo thứ trong tuần | 4 | "thứ Bảy vừa rồi", "Chủ nhật tới" |
| Trong ngày (theo giờ) | 5 | "sáng nay", "chiều qua", "đêm qua", "từ 6 đến 9 giờ sáng nay" |
| Ngầm định | 4 | "Hà Nội có mưa không?" (không nêu thời gian) |

Gold: theo `gold_sql`. Chấm riêng khoảng thời gian trong plan, so với khoảng kỳ vọng ghi trong YAML (`expect.time_range`), và ghi rõ quy ước "tuần" (bắt đầu thứ Hai) cùng giờ địa phương. Thời điểm lưu trong dữ liệu đang theo UTC hay giờ Việt Nam phải xác nhận trước khi viết câu theo giờ.

#### T18. Hội thoại nhiều lượt (theo SParC và CoSQL): 20 hội thoại, khoảng 60 lượt
Chạy qua route chat `POST /api/v1/text2sql/chat` có lịch sử. Mỗi hội thoại có 2 đến 4 lượt.

| Quan hệ | Số hội thoại | Ví dụ |
|---|---|---|
| Tinh chỉnh | 6 | "Lượng mưa hôm qua ở Huế?" → "Còn 3 ngày qua?" |
| Cùng thực thể, đổi thuộc tính | 5 | "Nhiệt độ cao nhất ở Vinh hôm qua?" → "Thế còn độ ẩm?" |
| Cùng thuộc tính, đổi thực thể | 5 | "Hà Nội mưa bao nhiêu?" → "Hải Phòng thì sao?" |
| Dựa trên câu trả lời trước | 4 | "Thành phố nào mưa nhiều nhất tuần qua?" → "Nhiệt độ ở đó hôm qua?" |

Chấm từng lượt như câu độc lập (gold đã thay đại từ bằng giá trị thật), cùng tỷ lệ hội thoại đúng trọn vẹn.

#### T21. Câu ghép nhiều ý (Multi-intent): 20 câu
Lỗi đã gặp: quy tắc của metric này bị áp sang metric khác dưới dạng bộ lọc tường minh.

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Nhiều chỉ số, một phạm vi | 8 | "Nhiệt độ cao nhất, thấp nhất và lượng mưa ở Vinh hôm qua?" |
| Chỉ số khác loại bản ghi | 6 | "Nhiệt độ cao nhất (theo ngày) và độ ẩm trung bình (theo giờ) ở Huế hôm qua?" |
| Một chỉ số, nhiều phạm vi | 6 | "Lượng mưa hôm qua ở Hà Nội và Hải Phòng?" |

Gold: `tuple`, chấm từng thành phần; câu chỉ đúng khi mọi thành phần đúng.

### Nhóm E. Không trả lời thẳng được

#### T19. Mơ hồ (theo AMBROSIA và Text2Analysis): 25 câu

| Loại con | Số câu | Ví dụ | Hành vi chấp nhận |
|---|---|---|---|
| Thiếu chỉ số | 7 | "Thời tiết Hà Nội hôm qua thế nào?" | Hỏi lại, **hoặc** trả bộ chỉ số mặc định đúng số liệu, kèm giả định |
| Thiếu phạm vi | 6 | "Thành phố nào mưa nhiều nhất?" (không nói khi nào) | Hỏi lại, hoặc nêu giả định thời gian rồi trả đúng theo giả định đó |
| Mơ hồ nghĩa | 5 | "Hôm qua có nóng không?" (nóng là bao nhiêu? ở đâu?) | Hỏi lại |
| Mơ hồ phạm vi | 4 | "Nhiệt độ cao nhất của các thành phố miền Bắc hôm qua?" (giá trị lớn nhất chung hay từng thành phố?) | Một trong các cách hiểu trong danh sách gold |
| Mơ hồ gắn kết | 3 | "Thành phố miền Trung và Tây Nguyên có mưa trên 10 mm" | Một trong các cách hiểu |

Câu "Thời tiết Hà Nội hôm qua thế nào?" thuộc loại con "Thiếu chỉ số", và trong lần thử ngày 19/11 nó lúc trả `answered`, lúc trả `needs_clarification`; độ ổn định của loại này đo bằng `--repeat`. Gold: `status` hoặc danh sách cách hiểu.

#### T20. Không trả lời được (theo TriageSQL, Wang và cộng sự, PremiseSQL): 30 câu

| Loại con | Số câu | Ví dụ |
|---|---|---|
| Ngoài miền | 5 | "Giá vàng hôm nay?" · "Tỷ giá USD?" |
| Thiếu cột, chỉ số | 6 | "Chỉ số UV ở Đà Nẵng?" · "Chất lượng không khí AQI ở Hà Nội?" |
| Thiếu giá trị | 6 | "Nhiệt độ ở Bangkok?" · "Thời tiết Sa Pa hôm qua?" |
| Ngoài khoảng dữ liệu | 5 | "Lượng mưa tháng 7/2025 ở Huế?" · "Dự báo ngày 20/12/2026?" |
| Phi SQL, chẩn đoán, đề xuất | 4 | "Vì sao Vinh mưa nhiều?" · "Có nên đi Đà Nẵng cuối tuần này?" |
| Tiền đề sai | 4 | "Vì sao hôm qua Cần Thơ có tuyết?" · "Thành phố thứ 13 là gì?" |

Hành vi chấp nhận: `no_metric` hoặc thông điệp nêu rõ không có dữ liệu hay không hỗ trợ. **Lỗi nặng** là trả về một con số; báo cáo ghi riêng chỉ số "tỷ lệ bịa".

Ranh giới cần ghi rõ trong gold: câu dự đoán **có** dữ liệu dự báo (trong 7 ngày tới) thuộc T1, T8 hoặc T10, không thuộc T20. Hệ thống phải dùng bản ghi dự báo chứ không từ chối.

## 4. Tag dùng chung cho mọi câu

| Tag | Giá trị |
|---|---|
| `path` | `metric` (ask_data), `dataset` (find_fields → plan_join → query_dataset), `none` |
| `rules` | tên quy tắc kỳ vọng (0 đến n) |
| `record_kind` | `HIEN_TAI`, `DU_BAO_NGAY`, `DU_BAO_GIO` |
| `time_kind` | `absolute`, `relative`, `implicit`, `intraday`, `future` |
| `entity_scope` | `city`, `region`, `climate_zone`, `all`, `condition` |
| `bird_knowledge` | `numeric`, `domain`, `synonym`, `value_illustration` |
| `difficulty` | `easy`, `medium`, `hard`, `extra`, theo số thành phần SQL như cách phân độ khó của Spider |
| `base_id` | với T16 và T18: câu gốc dùng chung gold |

Ràng buộc phân bổ trên toàn bộ ≈ 540 câu:
- mỗi thành phố xuất hiện ≥ 15 lần;
- mỗi quy tắc ≥ 6 lần ngoài T14;
- `path=dataset` ≥ 15%;
- `time_kind=relative` ≥ 30%;
- ≥ 25% câu có tên riêng cần đổi giá trị (`value_illustration`), vì đây là điểm yếu đã biết.

## 5. Quy trình tạo câu

1. **Sinh theo mẫu** (T1, T2, T3, T4, T7, T8, T9, T17, T16): mẫu câu × tham số (thành phố, chỉ số, cách nói thời gian) sinh kèm `gold_sql`. Seed cố định.
2. **Viết tay** (T5, T6, T10 đến T15, T18 đến T21): dùng bảng loại con ở trên làm khung.
3. **Kiểm tra tự động trên snapshot:**
   - `gold_sql` chạy được;
   - kết quả không rỗng hoặc rỗng đúng chủ ý;
   - không hòa ở câu so sánh nhất;
   - không trùng câu gần giống (so sau khi bỏ dấu).
4. **Duyệt bởi người:** đọc câu, đọc gold, sửa chỗ diễn đạt máy móc. Câu sinh theo mẫu cần viết lại tự nhiên ít nhất 30%, để không mô hình nào học thuộc được mẫu.
5. **Chia `dev` / `test` theo tỷ lệ 30/70, phân tầng theo loại.** Với T16 và T18, câu gốc và biến thể nằm cùng một phần.

## 6. Thay đổi so với đề xuất trước

- Bảng 11 nhóm (A đến K) ở đề xuất cũ được tách thành 21 loại. Ví dụ "quy tắc chuyên gia" trước là một nhóm, nay tách thành T14 và gắn tag `rules` vào mọi loại khác; "biến thể cách viết" trở thành T16 có cặp với câu gốc.
- Quy mô tăng từ 120 lên khoảng 540 câu (22 loại, thêm T22 "hỏi định nghĩa nghiệp vụ" tách khỏi T14). Một lần chạy đủ `test` (≈ 365 câu, 1 lượt) mất khoảng 1.000 lần gọi LLM và 20 đến 30 phút ở 4 luồng. Chạy `--repeat 3` chỉ khi đánh giá phiên bản phát hành.
- Bản tối thiểu dùng các loại P0 (T1, T2, T7, T8, T14, T17, T20, T21; ≈ 220 câu).

## 7. Luồng xử lý theo loại câu hỏi

Mục này mô tả **luồng xử lý nên có** cho từng loại câu hỏi, ở mức thiết kế, không phụ thuộc vào code hiện tại. Mức độ hệ thống hiện tại đã đáp ứng được ghi ở [Phụ lục A](#phụ-lục-a-đối-chiếu-với-hệ-thống-hiện-tại). Benchmark dùng mục này để biết cần chấm **từng bước trung gian** nào cho từng loại, chứ không chỉ chấm con số cuối cùng.

### 7.1. Khung chung

Sơ đồ đầy đủ, ghi Input/Output của từng bước: [2026-11-19-pipeline-hoi-dap-so-lieu.drawio](2026-11-19-pipeline-hoi-dap-so-lieu.drawio). Mở bằng draw.io / diagrams.net hoặc extension Draw.io của VS Code.

Mọi câu hỏi đi qua cùng phần đầu (bước 1 đến 3), rồi tách ra theo nhánh. Phần đầu gồm hai khối, mỗi khối có hai bước **chạy song song**; khối sau chỉ bắt đầu khi cả hai bước của khối trước đã xong:

```text
 Yêu cầu (câu hỏi + lịch sử hội thoại)
        │
        ├──────────────────────────────┐                     khối 1, song song
        ▼                              ▼
 [1a] Ghép ngữ cảnh &           [1b] Phân loại câu hỏi /
      viết lại câu hỏi               intent (T1 đến T22)
        └──────────────┬───────────────┘
                       ├──────────────────────────────┐      khối 2, song song
                       ▼                              ▼
 [2a] Retrieve top-k tri thức:         [2b] Chuẩn hóa + trích thực thể:
      thuật ngữ, quy tắc, metric            giá trị, thời gian
                       └──────────────┬───────────────┘
                                      ▼
                         [3] Định tuyến: intent + kết quả 2a, 2b
                                      │
   ┌──────────────┬───────────────┬──────┴────────┬────────────────┬───────────────┐
   ▼              ▼               ▼               ▼                ▼
 R1 Tri thức   R2 Số liệu      R3 Ghép         R4 Mơ hồ         R5 Không trả lời được
 trả từ tri    [4] truy xuất   tách câu con,   hỏi lại hoặc     từ chối có lý do,
 thức, không   [5] tính sau    mỗi câu con     dùng mặc định    gợi ý thứ có sẵn
 query DB      [6] kiểm tra    chạy R2, rồi    có ghi giả định
               [7] trả lời     ghép kết quả
```

**[1a] Ghép ngữ cảnh và viết lại câu hỏi.** Viết câu hiện tại thành câu hỏi đầy đủ, đứng một mình được, diễn đạt theo thuật ngữ nghiệp vụ. Khi có lượt trước thì thay đại từ ("ở đó", "còn Hải Phòng?") bằng thực thể cụ thể lấy từ câu hỏi hoặc câu trả lời trước. Đây là bước viết lại duy nhất; không có bước viết lại nào sau đó.

**[1b] Phân loại câu hỏi / intent.** Chạy song song với 1a, trên câu gốc và lịch sử. Xác định loại câu (T1 đến T22) dựa vào dấu hiệu phép toán: "nhiều nhất", "so với", "có… không", "bao nhiêu ngày", "xu hướng", "vì sao"… Kết quả chưa phải nhánh cuối cùng; bước 3 mới chốt nhánh.

**[2a] Retrieve top-k tri thức.** Chạy song song với 2b, trên câu đã viết lại ở 1a: thuật ngữ, quy tắc chuyên gia, tri thức riêng của người dùng, và top-k metric. Cột và bảng **chưa** cần lấy ở bước này; chỉ lấy khi nhánh số liệu không tìm được metric phù hợp (bước 4b).

**[2b] Chuẩn hóa và trích thực thể.** Chạy song song với 2a, trên câu đã viết lại ở 1a, và làm bằng code càng nhiều càng tốt. Vì chạy sau 1a, bước này cũng sửa được giá trị mà LLM viết lại sai dạng (ví dụ "Hà Nội" có dấu):
- **Giá trị (entity linking):** đối chiếu tên trong câu với danh sách giá trị thật của các cột chiều, có bí danh và so sánh khi đã bỏ dấu. Ví dụ "Hà Nội", "HN", "thủ đô" đều thành `Ha Noi`; "Sài Gòn", "TP.HCM" thành `Ho Chi Minh`. Không khớp được (Bangkok) thì bật cờ **thiếu giá trị**.
- **Thời gian:** đổi biểu thức thời gian ("hôm qua", "tuần trước", "sáng nay") thành khoảng `[bắt đầu, kết thúc)` cùng độ chi tiết (ngày hoặc giờ) theo `today`, bằng bộ quy đổi tất định. Khoảng nằm ngoài vùng có dữ liệu thì bật cờ **ngoài vùng dữ liệu**.

**[3] Định tuyến.** Chốt nhánh R1 đến R5 từ ba nguồn: loại câu ở bước 1b, các cờ thiếu giá trị và ngoài vùng dữ liệu ở bước 2b, và kết quả retrieve ở bước 2a. Phần này là luật cố định, làm bằng code.

**Các bước của nhánh số liệu (R2):**

| Bước | Nội dung |
|---|---|
| [4a] Dùng metric | Trong top-k có metric **phù hợp**: đúng đại lượng, đúng phép gộp, và bảng của metric có đủ chiều để lọc và nhóm theo yêu cầu. Khi đó dùng luôn metric, quy tắc gắn với metric được áp tự động |
| [4b] Dùng cột | Không có metric phù hợp: retrieve top-k cột và bảng, nối bảng theo quan hệ đã khai báo, tự dựng phép tính (cột, phép gộp, biểu thức), **ánh xạ quy tắc vào cột** rồi áp như ở 4a |
| [4c] Không có dữ liệu | Không có cột phù hợp: chuyển sang R5 với lý do "thiếu chỉ số" |
| [5] Tính sau truy vấn | So sánh, hiệu, tỷ lệ, thứ hạng, xu hướng, tương quan, đối chiếu ngưỡng. **Làm bằng code tất định, không để LLM tự tính** |
| [6] Kiểm tra kết quả | Rỗng, `NULL`, hòa, bị cắt bớt, ngoài vùng dữ liệu. Không bao giờ biến `NULL` thành 0 |
| [7] Viết câu trả lời | Kết luận trước; mọi con số lấy từ kết quả của bước 4 và 5; nêu quy tắc đã áp và giả định đã dùng |

Nguyên tắc chung của mọi nhánh:
- Cái gì xác định được bằng code (giá trị thực thể, khoảng thời gian, phép tính, áp quy tắc) thì làm bằng code.
- LLM chỉ dùng cho những việc cần hiểu ngôn ngữ: hiểu ý định, chọn metric hoặc cột, diễn đạt câu trả lời.

### 7.2. Bảng định tuyến

| Loại | Nhánh | Bước 4: truy xuất | Bước 5: tính sau truy vấn | Đặc thù |
|---|---|---|---|---|
| T1 Tra cứu giá trị | R2 | 4a; theo giờ hoặc chỉ số không có metric thì 4b | Không | Giá trị thực thể và mốc thời gian phải đúng tuyệt đối |
| T2 Tổng hợp | R2 | 4a; gộp theo vùng khí hậu thì 4b | Không | Chọn đúng phép gộp và đúng loại bản ghi |
| T3 Đếm | R2 | 4a nếu có metric đếm; đếm theo điều kiện thời tiết thì 4b | Không | Chọn đúng đơn vị đếm |
| T4 Có/không | R2 | 4a hoặc 4b, lấy **số làm căn cứ** | So với ngưỡng, ra có/không | Ngưỡng lấy từ quy tắc nếu có |
| T5 Liệt kê, lọc | R2 | 4a có nhóm và lọc theo dòng; điều kiện ở bảng chiều thì 4b | Lọc theo giá trị đã gộp (nếu truy vấn không tự làm được) | Tập rỗng là kết quả hợp lệ |
| T6 Phân nhóm | R2 | 4a nếu chiều có trong bảng của metric, ngược lại 4b | Không | Đúng chiều nhóm |
| T7 Cực trị, top-k | R2 | 4a có sắp xếp và giới hạn | Thứ hạng, kiểm tra hòa | |
| T8 So sánh | R3 (hai vế) hoặc R2 (một truy vấn có nhóm) | Mỗi vế một truy vấn | Bên thắng, hiệu, % chênh | |
| T9 Giá trị dẫn xuất | R2 nếu có metric sẵn, ngược lại R3 | Các thành phần | Hiệu, tỷ lệ, tỷ trọng, % thay đổi | |
| T10 Xu hướng | R2 | Chuỗi theo ngày hoặc giờ | Hướng xu hướng (độ dốc) | |
| T11 Khoảng, phân bố | R2 | Nhỏ nhất và lớn nhất, hoặc đếm theo nhóm (thường 4b) | Mode, tỷ lệ từng nhóm | |
| T12 Bất thường | R2 | Lọc theo ngưỡng hoặc quy tắc; lệch thống kê thì lấy chuỗi | Trung bình, độ lệch chuẩn, đánh dấu điểm lệch | |
| T13 Tương quan | R2 | Lấy dữ liệu theo cặp | Hệ số tương quan, so sánh có điều kiện | |
| T14 Áp dụng định nghĩa | R2 | 4a (quy tắc theo metric) hoặc 4b (quy tắc ánh xạ vào cột) | Theo loại phép toán | Quy tắc **bắt buộc**, chỉ nhường khi câu hỏi tự nêu điều kiện cùng cột |
| T15 Dữ liệu, vận hành | R1 (danh mục, mô tả) hoặc R2 (ETL, độ mới) | 4a hoặc 4b | Không | Danh mục lấy từ tầng tri thức, không cần query |
| T16 Biến thể diễn đạt | Như câu gốc | Như câu gốc | Như câu gốc | Xử lý dứt điểm ở bước 2b và 2a |
| T17 Biểu thức thời gian | Như câu gốc | Như câu gốc | Như câu gốc | Xử lý dứt điểm ở bước 2b |
| T18 Hội thoại | Như câu sau bước 1a | | | Xử lý dứt điểm ở bước 1a |
| T19 Mơ hồ | R4 | Chỉ chạy nếu dùng mặc định | | |
| T20 Không trả lời được | R5 (riêng tiền đề sai thì R2 để kiểm chứng) | Không, hoặc chỉ để kiểm chứng | | Không bịa số |
| T21 Câu ghép nhiều ý | R3 | Mỗi câu con | Ghép kết quả | |
| T22 Hỏi định nghĩa | R1 | **Không truy vấn database** | Không | Trả từ thuật ngữ, quy tắc, mô tả metric |

### 7.3. Luồng chi tiết theo nhóm

#### Nhóm C trước tiên: T22, T14, T15 (vì tri thức quyết định có cần query hay không)

**T22 Hỏi định nghĩa nghiệp vụ** ("Thế nào là ngày có mưa?")
1. Bước 1b nhận ra câu hỏi về **khái niệm**, không có thực thể hay mốc thời gian cần số liệu; song song đó, bước 2a retrieve top-k thuật ngữ, quy tắc, mô tả metric.
2. Bước 3 chọn R1.
3. **Có** tri thức khớp (điểm đủ cao) thì trả lời thẳng từ nội dung quy tắc hoặc thuật ngữ: diễn đạt lại bằng lời thường, nêu tên quy tắc làm nguồn.
4. **Không** có tri thức khớp thì không tự định nghĩa bằng kiến thức chung. Hệ thống nói rõ là chưa có định nghĩa nghiệp vụ được khai báo; nếu cần thì đưa thêm định nghĩa thông thường và ghi rõ đó không phải định nghĩa của hệ thống.
5. **Không query database.**

Câu nửa khái niệm, nửa số liệu ("Ngày có mưa là gì, tuần qua Huế có mấy ngày như vậy?") là câu ghép T21: một câu con đi R1, một câu con đi R2.

**T14 Áp dụng định nghĩa trên số liệu** ("Tuần qua Huế có mấy ngày mưa?")
1. Bước 2a retrieve: quy tắc "ngày có mưa" cùng metric `so_ngay_co_mua` liên kết với quy tắc đó.
2. Có metric gắn quy tắc (4a): dùng metric, quy tắc được áp tự động.
3. Không có metric (4b): lấy cột và **ánh xạ định nghĩa của quy tắc vào điều kiện trên cột** (`tong_luong_mua_mm > 0` trên bản ghi ngày). Điều kiện này phải được áp bắt buộc như ở 4a, không chỉ đưa cho LLM tham khảo.
4. Câu hỏi tự nêu điều kiện trên cùng cột ("mưa **trên 5 mm**") thì điều kiện của câu hỏi thắng, và câu trả lời ghi rõ đã thay quy tắc.
5. Câu trả lời nêu quy tắc đã áp ("tính ngày có tổng lượng mưa > 0 mm").

**T15 Dữ liệu và vận hành**
- Danh mục và mô tả ("Đơn vị tốc độ gió là gì?", "Hệ thống có những chỉ số nào?"): R1, trả từ từ điển dữ liệu và danh mục metric, không query.
- Danh sách giá trị ("Đang theo dõi những thành phố nào?"): lấy được ngay từ danh sách giá trị đã dùng ở bước 2b. Nếu cần kèm điều kiện (đang hoạt động) thì R2 trên bảng chiều.
- Vận hành, độ mới ("Hôm qua nạp lỗi mấy lần?", "Dữ liệu cập nhật lần cuối khi nào?"): R2, 4a với metric ETL hoặc 4b trên bảng nhật ký nạp.

#### Nhóm A: T1 đến T6 (truy xuất và tổng hợp)

Cả 6 loại đi chung một đường: **retrieve top-k metric ở bước 2a → dùng được thì lấy luôn (4a), không dùng được thì retrieve top-k cột (4b)**. Các loại khác nhau ở cách quyết định "dùng được" và ở phần cấu hình truy vấn:

| Loại | Metric "dùng được" khi | Cấu hình truy vấn | Sau truy vấn |
|---|---|---|---|
| T1 Tra cứu | Đúng đại lượng, đúng mức thời gian (hiện tại, theo ngày hay theo giờ) | Lọc thực thể (giá trị đã chuẩn hóa ở bước 2b), một mốc thời gian, không nhóm | Một số và đơn vị |
| T2 Tổng hợp | Phép gộp của metric khớp ý câu hỏi (tổng, trung bình, lớn nhất, nhỏ nhất) | Khoảng thời gian; lọc theo tập thực thể (vùng) | Một số |
| T3 Đếm | Có metric đếm đúng đơn vị (ngày, thành phố, lần nạp) | Như T2; điều kiện đếm lấy từ quy tắc hoặc câu hỏi | Số nguyên |
| T4 Có/không | Có metric cho **đại lượng làm căn cứ** | Như T1 hoặc T2 | **So với ngưỡng** (của quy tắc hoặc câu hỏi), ra có/không kèm số |
| T5 Liệt kê | Bảng của metric có chiều cần liệt kê | Nhóm theo chiều, lọc theo dòng | Lọc theo giá trị đã gộp nếu cần; tập rỗng thì nói rõ |
| T6 Phân nhóm | Bảng của metric có chiều cần nhóm | Nhóm theo 1 đến 2 chiều | Bảng |

Ví dụ hai đường của cùng một loại:
- "Lượng mưa trung bình các thành phố **Đồng bằng sông Hồng** hôm qua": bảng của metric có cột `vung`, nên đi **4a**.
- "Lượng mưa trung bình các thành phố **miền Bắc** hôm qua": "miền Bắc" là vùng khí hậu, chỉ có ở bảng chiều thành phố, nên đi **4b**: retrieve cột `vung_khi_hau`, nối bảng, gộp.

#### Nhóm B: T7 đến T13 (so sánh và quan hệ)

Truy xuất giống nhóm A (4a, không được thì 4b). Khác biệt nằm ở **bước 5, tính sau truy vấn**, và đôi khi phải tách câu (R3):

| Loại | Luồng |
|---|---|
| T7 Cực trị, top-k | Một truy vấn nhóm theo thực thể hoặc ngày, sắp xếp, giới hạn k. Bước 5 kiểm tra hòa ở ranh giới k; hỏi "đứng thứ mấy" thì lấy cả danh sách đã sắp rồi tính thứ hạng bằng code |
| T8 So sánh | Thực thể với thực thể: một truy vấn có nhóm và lọc hai thực thể. Kỳ với kỳ, hoặc thực thể với mức chung: **R3**, tách thành hai truy vấn. Bước 5 tính bên thắng, hiệu tuyệt đối, % chênh **bằng code** |
| T9 Giá trị dẫn xuất | Có metric sẵn (tỷ lệ ngày mưa) thì dùng luôn. Không có thì R3: lấy từng thành phần (cao nhất và thấp nhất; phần và tổng), bước 5 tính biên độ, tỷ lệ, tỷ trọng, % thay đổi |
| T10 Xu hướng | Một truy vấn theo chuỗi thời gian (ngày hoặc giờ). Bước 5 tính hướng bằng độ dốc hồi quy hoặc so đầu kỳ với cuối kỳ; chuỗi đi ngang thì nói đi ngang |
| T11 Khoảng, phân bố | Khoảng: lấy nhỏ nhất và lớn nhất. Phân bố: đếm theo nhóm (điều kiện thời tiết ở bảng chiều nên thường đi 4b). Bước 5 tính tỷ lệ từng nhóm và nhóm phổ biến nhất |
| T12 Bất thường | Theo ngưỡng hoặc quy tắc: lọc thẳng trong truy vấn (quy tắc "thời tiết xấu" ánh xạ vào nhóm mức độ). Lệch thống kê: lấy chuỗi, bước 5 tính trung bình và độ lệch chuẩn rồi đánh dấu điểm lệch |
| T13 Tương quan | Lấy dữ liệu theo cặp (độ ẩm và lượng mưa cùng giờ, cùng thành phố). Bước 5 tính hệ số tương quan. So sánh có điều kiện ("ngày mưa có mát hơn không") thì chia hai nhóm theo quy tắc ngày mưa rồi so trung bình |

Nguyên tắc riêng của nhóm B: **LLM không tự làm phép tính.** Mọi con số dẫn xuất đi qua bước 5 và được ghi lại (thành phần, công thức, kết quả) để benchmark chấm được.

#### Nhóm D: T16, T17, T18, T21 (ngôn ngữ và ngữ cảnh)

Các loại này **không có luồng riêng ở bước 4**. Chúng là các trường hợp mà bước 1a hoặc bước 2b phải xử lý dứt điểm trước khi câu đi theo luồng của loại gốc:

| Loại | Xử lý ở | Đầu ra của bước đó |
|---|---|---|
| T16 Biến thể diễn đạt | [2b] entity linking theo bí danh và so khớp không dấu; [2a] retrieve dùng cả bản có dấu và không dấu, cùng từ đồng nghĩa | Đúng giá trị thực thể, đúng metric như câu gốc |
| T17 Biểu thức thời gian | [2b] bộ quy đổi thời gian tất định theo `today`, quy ước tuần (bắt đầu thứ Hai) và múi giờ | Khoảng `[bắt đầu, kết thúc)` và độ chi tiết; câu không nêu thời gian thì dùng mặc định và ghi thành giả định |
| T18 Hội thoại | [1a] viết lại thành câu đứng một mình được, dựa trên câu hỏi, thực thể và kết quả của lượt trước | Câu hỏi đầy đủ, sau đó chạy như câu đơn |
| T21 Câu ghép nhiều ý | [1b] nhận ra câu ghép, [3] chọn R3: tách câu con, mỗi câu con tự định tuyến (có thể R1 lẫn R2), chạy riêng, quy tắc áp **riêng cho từng câu con** | Kết quả từng phần, ghép thành một câu trả lời |

#### Nhóm E: T19, T20 (không trả lời thẳng được)

**T19 Mơ hồ (R4).** Sau bước 2a và 2b, kiểm tra các "ô" bắt buộc của câu hỏi số liệu: đại lượng, phạm vi thực thể, thời gian.
- Ô bị thiếu mà **có mặc định đã khai báo** thì dùng mặc định, chạy R2 và ghi giả định. Ví dụ: thiếu thời gian thì lấy hôm nay; "thời tiết thế nào" thì dùng bộ chỉ số mặc định gồm nhiệt độ cao nhất, thấp nhất, lượng mưa và điều kiện thời tiết.
- Ô bị thiếu mà **không có mặc định**, hoặc câu có nhiều cách hiểu thật sự (phạm vi, gắn kết), thì hỏi lại, kèm tối đa 4 lựa chọn lấy từ các ứng viên đã retrieve.
- Cùng một câu phải luôn cho **cùng một hành vi**. Muốn vậy, quyết định "hỏi lại hay dùng mặc định" phải dựa trên bảng mặc định cố định, không để LLM quyết định mỗi lần một khác.

**T20 Không trả lời được (R5).** Mỗi loại con dừng ở một bước khác nhau:

| Loại con | Phát hiện ở | Câu trả lời |
|---|---|---|
| Ngoài miền (giá vàng) | [2a] không có tri thức hay metric nào khớp | Nói hệ thống chỉ có dữ liệu thời tiết |
| Thiếu chỉ số (UV, AQI) | [4c] không có metric lẫn cột | Nói chưa có chỉ số này; liệt kê các chỉ số gần nhất đang có |
| Thiếu giá trị (Bangkok) | [2b] cờ thiếu giá trị | Nói thành phố này không được theo dõi; liệt kê các thành phố đang có |
| Ngoài vùng dữ liệu (2020) | [2b] cờ ngoài vùng dữ liệu | Nói rõ dữ liệu có từ ngày nào đến ngày nào |
| Chẩn đoán, đề xuất ("vì sao", "có nên") | [1b] nhận loại câu, [3] chọn R5 | Nói hệ thống chỉ trả lời được số liệu; gợi ý câu số liệu liên quan |
| Tiền đề sai ("vì sao Cần Thơ có tuyết") | [1b] nhận ra câu có tiền đề kiểm chứng được, [3], chạy R2 để kiểm chứng | Bác tiền đề bằng số liệu ("không có tuyết, lượng tuyết rơi = 0") |

Nguyên tắc: phát hiện **càng sớm càng tốt** (các bước 1b, 2a, 2b rẻ hơn bước 4), và **không bao giờ trả về một con số không đến từ truy vấn**.

### 7.4. Benchmark chấm gì theo luồng

Mỗi câu trong bộ đề ghi thêm luồng kỳ vọng:

```yaml
expect:
  route: R2                    # R1..R5
  entities: {ten_thanh_pho: "Ha Noi"}
  time_range: ["2026-11-18", "2026-11-19"]
  retrieval: {rules: ["Ngày có mưa tính trên tổng lượng mưa ngày"], metrics: [so_ngay_co_mua]}
  access: metric               # metric (4a) | columns (4b) | none
  post_compute: none           # none | threshold | diff | ratio | rank | trend | corr | ...
  queried_db: true
```

Các chỉ số chấm theo bước:

| Bước | Chỉ số |
|---|---|
| [1a] Ghép ngữ cảnh, viết lại | Câu viết lại có đủ thực thể của lượt trước (T18); không mất thực thể hay mốc thời gian |
| [1b] Phân loại | Độ chính xác loại câu T1 đến T22 |
| [2a] Retrieve | Recall@k của quy tắc, thuật ngữ, metric kỳ vọng |
| [2b] Chuẩn hóa | Độ chính xác của giá trị thực thể; độ chính xác của khoảng thời gian; cờ thiếu giá trị và ngoài vùng bật đúng lúc |
| [3] Định tuyến | Độ chính xác nhánh R1 đến R5 (ma trận nhầm lẫn giữa các nhánh) |
| [4] Truy xuất | Đúng lựa chọn 4a hay 4b; đúng metric hoặc đúng cột; quy tắc có được áp |
| [5] Tính sau | Đúng phép tính và đúng kết quả |
| [6], [7] Trả lời | Khớp gold; không bịa số; nêu đủ giả định |
| Hiệu quả | Có truy vấn thừa không (`queried_db` ở câu R1); số lần gọi LLM; thời gian xử lý |

Với cách chấm này, một câu sai sẽ chỉ ra được bước sai đầu tiên. Ví dụ, lỗi ngày 19/11 ("Hà Nội" thay vì "Ha Noi") sẽ được ghi nhận là **sai ở bước 2b** chứ không chỉ là "kết quả NULL".

## 8. Nguồn

- Amar, Eagan, Stasko. [Low-Level Components of Analytic Activity in Information Visualization](https://faculty.cc.gatech.edu/~stasko/papers/infovis05.pdf), InfoVis 2005.
- Pasupat, Liang. [Compositional Semantic Parsing on Semi-Structured Tables](https://arxiv.org/pdf/1508.00305) (WikiTableQuestions), ACL 2015.
- Li và cộng sự. [Can LLM Already Serve as A Database Interface? (BIRD)](https://proceedings.neurips.cc/paper_files/paper/2023/file/83fc8fab1710363050bbd1d4b8cc0021-Paper-Datasets_and_Benchmarks.pdf), NeurIPS 2023.
- Chang và cộng sự. [Dr.Spider: A Diagnostic Evaluation Benchmark towards Text-to-SQL Robustness](https://arxiv.org/abs/2301.08881), ICLR 2023.
- Lee và cộng sự. [EHRSQL: A Practical Text-to-SQL Benchmark for Electronic Health Records](https://arxiv.org/pdf/2301.07695), 2023.
- [ChronoQA: A Question Answering Dataset for Temporal-Sensitive Retrieval-Augmented Generation](https://arxiv.org/abs/2508.12282), 2025.
- Yu và cộng sự. [SParC: Cross-Domain Semantic Parsing in Context](https://aclanthology.org/P19-1443.pdf), ACL 2019; [CoSQL](https://arxiv.org/abs/1909.05378), EMNLP 2019.
- Saparina, Lapata. [AMBROSIA: A Benchmark for Parsing Ambiguous Questions into Database Queries](https://arxiv.org/abs/2406.19073), 2024.
- He và cộng sự. [Text2Analysis: A Benchmark of Table Question Answering with Advanced Data Analysis and Unclear Queries](https://arxiv.org/abs/2312.13671), AAAI 2024.
- Zhang và cộng sự. [Did You Ask a Good Question? (TriageSQL)](https://arxiv.org/abs/2010.12634), 2020.
- Wang và cộng sự. [Know What I don't Know: Handling Ambiguous and Unanswerable Questions for Text-to-SQL](https://aclanthology.org/2023.findings-acl.352.pdf), ACL Findings 2023.
- [PremiseSQL: Evaluating Premise Critique and Abstention in Text-to-SQL Systems](https://arxiv.org/html/2610.22158v1), 2026.
- Sahu và cộng sự. [InsightBench: Evaluating Business Analytics Agents Through Multi-Step Insight Generation](https://arxiv.org/abs/2407.06423), ICLR 2025.
- Nguyen, Dao, Nguyen. [A Pilot Study of Text-to-SQL Semantic Parsing for Vietnamese (ViText2SQL)](https://aclanthology.org/2020.findings-emnlp.364/), Findings of EMNLP 2020.

## Phụ lục A. Đối chiếu với hệ thống hiện tại

Phụ lục này đối chiếu luồng đề xuất ở [mục 7](#7-luồng-xử-lý-theo-loại-câu-hỏi) với hệ thống đang chạy, để benchmark gắn nhãn `capability` cho từng câu và tách "mô hình sai" khỏi "hệ thống chưa hỗ trợ". Thông tin đối chiếu với code ngày 19/11/2026.

### A.1. Luồng chung

```text
Câu hỏi (+ 6 lượt lịch sử nếu qua route chat có user_id)
 │
 ├─[1] Truy hồi: embed câu hỏi một lần, tìm thuật ngữ, quy tắc, tri thức riêng (Qdrant hybrid)
 ├─[2] Viết lại (LLM QuestionRewriteAgent): diễn đạt theo thuật ngữ chuẩn, giữ thực thể và mốc thời gian
 ├─[3] Tìm metric: metric liên kết với thuật ngữ, quy tắc + top 5 theo câu viết lại, lọc bằng Jev ≥ 0,6
 │      └─ không còn ứng viên ─────────────────────────────┐
 ├─[4] Lập plan metric (LLM QueryPlanAgent):                   │
 │      ok / no_metric / needs_clarification                  │
 ├─[5] Dựng SQL bằng code, ÁP QUY TẮC BẰNG CODE                │
 ├─[6] Chạy chỉ đọc, che PII                                   │
 │                                                             ▼
 │                        NHÁNH NHIỀU BẢNG (route chat tự đi; ask_data dừng ở no_metric
 │                        và gợi ý agent gọi find_fields → plan_join → query_dataset)
 │                        [4'] find_fields (Jev, ngưỡng riêng)
 │                        [5'] Lập plan dataset (LLM DatasetPlanAgent): quy tắc chỉ là VĂN BẢN
 │                        [6'] plan_join theo quan hệ đã khai báo
 │                        [7'] Dựng SQL, chạy chỉ đọc, lưu dataset
 │
 └─[9] Viết câu trả lời (LLM AnalysisAgent, chỉ ở route chat; ask_data trả JSON cho agent gọi nó)
```

Hai điểm vào có hành vi khác nhau, và benchmark phải ghi rõ đang đo điểm vào nào:

| | MCP `ask_data` | Route chat `POST /api/v1/text2sql/chat` |
|---|---|---|
| Khi `no_metric` | Dừng, trả bảng gợi ý; agent bên ngoài tự gọi nhánh nhiều bảng | Tự chuyển sang nhánh nhiều bảng |
| Lịch sử hội thoại | Không có | 6 lượt gần nhất (câu hỏi, câu viết lại, trạng thái, câu trả lời rút gọn 500 ký tự) |
| Đầu ra | JSON có cấu trúc: plan, SQL, rows | Event SSE `data` (rows) và câu trả lời bằng lời (`token`) |
| Ai tính phần số học giữa các truy vấn | Agent gọi tool | `AnalysisAgent`, bị prompt giới hạn "không tự tính thêm con số không suy ra trực tiếp từ rows" |

**Khuyến nghị:** dùng route chat (`ChatPipeline`) làm điểm vào chính cho benchmark, vì đó là đường đi đầy đủ nhất (có nhánh nhiều bảng, lịch sử, câu trả lời cuối). Dùng `ask_data` cho các loại chỉ đi nhánh metric để chấm plan có cấu trúc. Với cả hai điểm vào, chấm trước hết trên `rows`. Chỉ chấm câu trả lời bằng lời khi đáp án phải suy ra từ rows (T4, T8, T9, T10 hướng xu hướng).

### A.2. Năng lực của bộ dựng truy vấn quyết định đường đi

| Năng lực | Nhánh metric | Nhánh nhiều bảng |
|---|---|---|
| Số truy vấn mỗi câu | Tối đa 3; mỗi truy vấn đúng **một metric trên một bảng, không join** | Một truy vấn, tối đa 8 bảng, 20 cột kết quả |
| Nhóm | Cột của bảng chứa metric (`fact_tong_hop_thoi_tiet` có `ten_thanh_pho`, `vung`, `ngay_key`, `thoi_diem_quan_sat`; **không có** `vung_khi_hau`, tên điều kiện, cờ cuối tuần) | Cột của mọi bảng đã nối |
| Thời gian | `start`/`end` dạng **ngày** (YYYY-MM-DD); `granularity` từ ngày đến năm, **không có giờ** | Như nhánh metric |
| Lọc | Lọc theo **dòng** (WHERE); **không có HAVING** để lọc theo giá trị đã gộp | WHERE hoặc điều kiện trong JOIN; không có HAVING |
| Biểu thức | Biểu thức của metric do quản trị viên khai báo | Danh sách cho phép: `+ - * / %`, so sánh, `CASE`, `COALESCE`, `NULLIF`, `ROUND`, `ABS`, `GREATEST`, `LEAST`, `CAST`, `SUM/AVG/MIN/MAX/COUNT(DISTINCT)`. **Không có** hàm cửa sổ (`RANK`, `LAG`), truy vấn con, `CORR`, `STDDEV`, hàm ngày giờ (`EXTRACT`, `DATE_TRUNC` tự viết) |
| Quy tắc chuyên gia | **Áp bằng code**, không bỏ được; nhường khi câu hỏi tự lọc cùng cột (`overridden`) | Chỉ đưa cho LLM dưới dạng **văn bản**; mô hình có thể bỏ qua |
| Hỏi lại | `needs_clarification`, tối đa 4 lựa chọn | `needs_clarification` hoặc `cannot_answer` |

Hệ quả cho benchmark: mỗi câu cần ghi thêm `expect.path` (`metric`, `dataset`, `none`) và `capability`:
- `supported`: bộ dựng làm được trong một lượt;
- `composed`: phải ghép nhiều truy vấn hoặc nhờ tầng trả lời tính tiếp;
- `unsupported`: bộ dựng hiện chưa làm được; khi đó hành vi đúng là báo không làm được.

Báo cáo tách điểm theo `capability` để không lẫn "mô hình sai" với "hệ thống chưa hỗ trợ".

### A.3. Từng loại

Ký hiệu bước: [1] truy hồi, [2] viết lại, [3] tìm metric, [4] lập plan metric, [5] áp quy tắc, [4'] đến [7'] nhánh nhiều bảng, [9] câu trả lời.

#### Nhóm A. Truy xuất và tổng hợp

**T1. Tra cứu giá trị**
- **Đường đi:** nhánh metric, một truy vấn.
- **Plan kỳ vọng:** lọc `ten_thanh_pho` bằng **giá trị thật** (`Ha Noi`), khoảng thời gian `[ngày, ngày+1)`, không nhóm. Quy tắc gắn với metric tự thêm điều kiện loại bản ghi.
- **Bước quyết định:**
  - [3] chọn đúng metric trong nhóm gần nghĩa: `nhiet_do_hien_tai`, `nhiet_do_trung_binh`, `nhiet_do_cao_nhat`.
  - [4] ghi đúng giá trị lọc. Đây là lỗi đã gặp ngày 19/11: bước [2] tự đổi "Ha Noi" thành "Hà Nội", rồi [4] lọc theo "Hà Nội" nên ra `NULL`.
- **Giới hạn:**
  - Câu tra theo giờ ("lúc 14 giờ") không biểu diễn được bằng trường `time`, vì trường này chỉ nhận ngày; mô hình phải tự lọc trên `thoi_diem_quan_sat`.
  - Prompt lập plan chưa hướng dẫn cách làm việc này, nên các câu theo giờ được gắn `capability: composed`.
- **Chấm:** tầng 3 (đúng metric, đúng giá trị lọc) và tầng 5 (khớp số).

**T2. Tổng hợp theo khoảng hoặc tập**
- **Đường đi:** nhánh metric; phép gộp nằm sẵn trong biểu thức metric (`SUM`, `AVG`, `MAX`, `MIN`).
- **Plan kỳ vọng:** khoảng thời gian nhiều ngày, không nhóm.
- **Bước quyết định:**
  - [3] chọn metric có đúng phép gộp, ví dụ tổng lượng mưa chứ không phải xác suất mưa.
  - [5] quy tắc chọn loại bản ghi: chỉ số ngày dùng `DU_BAO_NGAY`, chỉ số trung bình dùng `DU_BAO_GIO`.
- **Rẽ nhánh theo cách gọi vùng:**
  - "Miền Trung", "miền Bắc" là giá trị của `vung_khi_hau`, cột này nằm ở `dim_thanh_pho` chứ không có trong bảng sự kiện. Câu dùng cách gọi này phải đi **nhánh nhiều bảng**, hoặc mô hình phải tự đổi thành `vung IN ('Bac Trung Bo', 'Nam Trung Bo')`.
  - "Đồng bằng sông Hồng" có sẵn ở cột `vung` của bảng sự kiện nên đi nhánh metric được.
  - Đây là ví dụ rõ của loại tri thức "minh họa giá trị" trong BIRD.
- **Chấm:** tầng 5; gắn tag `path` theo cách gọi vùng.

**T3. Đếm theo điều kiện**
- **Đường đi theo loại con:**
  - Đếm ngày có mưa: nhánh metric `so_ngay_co_mua`. Quy tắc "ngày có mưa" nằm sẵn trong định nghĩa metric.
  - "Ngày mưa trên 10 mm": vẫn nhánh metric, thêm lọc theo dòng `tong_luong_mua_mm > 10`. Đây là câu kiểm tra quy tắc nhường (`overridden`).
  - Đếm thành phố: `so_thanh_pho_quan_sat` hoặc `so_thanh_pho_hoat_dong`, là cặp dễ nhầm.
  - Đếm thành phố có dông: **nhánh nhiều bảng**, nối `dim_dieu_kien_thoi_tiet` rồi `COUNT(DISTINCT ...)`.
  - Đếm giờ có mưa: hoặc đọc cột `so_gio_co_mua` của bản ghi ngày, hoặc `SUM(CASE WHEN ... THEN 1 END)` trên bản ghi giờ ở nhánh nhiều bảng. Hai cách phải ra cùng một số; nếu không bằng nhau thì đó là phát hiện về dữ liệu.
- **Bước quyết định:** [3] và [4'] chọn đơn vị đếm (ngày × thành phố, thành phố hay giờ).

**T4. Có/không**
- **Đường đi:** hệ thống **không có kiểu đầu ra logic**. Plan truy vấn ra con số làm căn cứ (lượng mưa, nhiệt độ), rồi tầng [9] (hoặc agent gọi `ask_data`) chuyển số đó thành có hoặc không.
- **Bước quyết định:**
  - [4]: hỏi đúng đại lượng làm căn cứ.
  - [9]: diễn giải đúng ngưỡng. Với "có mưa không", ngưỡng phải theo quy tắc "ngày có mưa" (tổng lượng mưa > 0), không phải xác suất mưa.
- **Chấm:**
  - Tầng 5 chấm con số căn cứ.
  - Với route chat, giá trị logic lấy từ câu trả lời bằng lời. Câu trả lời mở đầu bằng kết luận (theo quy tắc 2 của prompt phân tích), nên nhận diện "có" hoặc "không" ở câu đầu bằng luật là đủ, chưa cần LLM làm giám khảo.
- **Capability:** `composed`.

**T5. Liệt kê, lọc**
- **Đường đi:**
  - Lọc theo giá trị từng dòng ("ngày nào mưa trên 10 mm"): nhánh metric, nhóm theo `ngay_key`, kèm lọc theo dòng.
  - Lọc theo giá trị **đã gộp** ("thành phố nào tổng mưa tuần qua trên 50 mm") **không làm được** vì thiếu HAVING. Plan chỉ trả tổng của mọi thành phố, phần lọc rơi xuống tầng [9].
  - Lọc theo điều kiện thời tiết: nhánh nhiều bảng.
  - "Thành phố nào **không** mưa": nhóm theo thành phố rồi tìm dòng có tổng bằng 0. Câu này cũng phụ thuộc tầng [9].
- **Capability:**
  - `supported` cho lọc theo dòng;
  - `composed` cho lọc theo giá trị gộp và phủ định.
- **Chấm:** tập kết quả ở `rows` sau khi lọc theo quy ước của gold. Báo cáo cả precision và recall để thấy hệ thống trả thừa hay thiếu.

**T6. Phân nhóm theo chiều**
- **Đường đi:**
  - Nhánh metric khi chiều có trong bảng sự kiện (`ten_thanh_pho`, `vung`, `ngay_key`).
  - Nhánh nhiều bảng khi chiều nằm ở bảng chiều (`vung_khi_hau`, `nhom_muc_do`, `ten_dieu_kien`, `la_cuoi_tuan`).
- **Bước quyết định:**
  - [4] và [4'] chọn đúng cột nhóm.
  - [6'] tìm được đường nối đã khai báo. Khi đường nối có nhiều cách hoặc chưa khai báo, route chat trả `join_ambiguous` hoặc `join_not_declared`. Gold ghi nhận đó là hành vi đúng nếu đồ thị quan hệ thật sự như vậy.
- **Chấm:** khớp bảng kết quả; báo cảnh báo nhân dòng nếu bộ dựng phát ra.

#### Nhóm B. So sánh và quan hệ

**T7. Cực trị, xếp hạng**
- **Đường đi:** nhánh metric.
- **Plan kỳ vọng:** nhóm theo thành phố, hoặc `granularity=day` khi hỏi theo ngày; `order_by metric desc/asc` và `limit k`.
- **Bước quyết định:** [4] chọn đúng hướng sắp xếp và đúng `limit`. Câu "ít mưa nhất" hay bị đảo chiều.
- **Giới hạn:**
  - "Đứng thứ mấy" không tính được trong SQL vì không có `RANK`. Plan phải trả cả danh sách đã sắp xếp và tầng [9] tự đếm vị trí, nên câu này là `composed`.
  - `limit 1` che mất trường hợp hòa. Vì vậy generator loại các câu có hòa ở vị trí được hỏi.
- **Chấm:** thực thể ở dòng đầu tiên, hoặc danh sách có thứ tự.

**T8. So sánh**
- **Đường đi theo loại con:**
  - Thực thể với thực thể: **một truy vấn** nhóm theo thành phố với lọc `IN (A, B)` (cách tốt nhất), hoặc hai truy vấn.
  - Kỳ với kỳ: hai truy vấn, hoặc một truy vấn có `granularity=day` phủ cả hai kỳ.
  - Thực thể với mức chung: hai truy vấn, một có lọc và một không.
  - Nhóm với nhóm (miền Bắc và miền Nam): nhánh nhiều bảng có nhóm theo `vung_khi_hau`.
- **Phần chênh lệch:** nhánh metric không tính được hiệu giữa hai truy vấn; tầng [9] phải tính. Nhánh nhiều bảng làm được trong một biểu thức: `SUM(CASE WHEN ten_thanh_pho='Ha Noi' THEN ... END) - SUM(CASE WHEN ... 'Ho Chi Minh' ...)`.
- **Rủi ro đã thấy trong prompt:** `AnalysisAgent` bị cấm "tự tính thêm con số không suy ra trực tiếp từ rows". Phép trừ hai số có thể bị mô hình coi là vi phạm và bỏ qua. Benchmark sẽ đo đúng chỗ này.
- **Chấm:**
  - Thành phần (giá trị từng vế) chấm từ `rows`.
  - Bên thắng và chênh lệch chấm từ câu trả lời.
  - Câu chỉ đúng khi cả hai phần đều đúng.

**T9. Giá trị dẫn xuất**
- **Đường đi theo loại con:**
  - Biên độ: hai metric (cao nhất, thấp nhất) rồi tầng [9] trừ; hoặc nhánh nhiều bảng với `MAX(nhiet_do_cao_nhat_c) - MIN(nhiet_do_thap_nhat_c)`.
  - Tỷ lệ có sẵn thành metric (`ty_le_ngay_co_mua`, `ty_le_nap_thanh_cong`): nhánh metric, `supported`.
  - Tỷ trọng (Hà Nội trên tổng miền Bắc): cần hai mức gộp khác nhau. Không có hàm cửa sổ nên phải chạy hai truy vấn rồi chia ở tầng [9]; `composed`.
  - Phần trăm thay đổi giữa hai ngày: hai truy vấn, hoặc `granularity=day` rồi tính ở tầng [9].
- **Bước quyết định:** [4] chọn giữa metric có sẵn và cách ghép; [9] làm đúng phép tính.

**T10. Xu hướng, chuỗi thời gian**
- **Đường đi:**
  - Chuỗi theo ngày: nhánh metric, `granularity=day`, sắp theo thời gian tăng dần.
  - Chuỗi theo giờ: **không có `granularity=hour`**; phải nhóm theo cột `thoi_diem_quan_sat`. Cột này được phép nhóm vì kiểu ngày giờ, nhưng prompt chưa hướng dẫn.
  - Chuỗi dự báo: khoảng thời gian ở tương lai; quy tắc chỉ số ngày vẫn áp vì bản ghi dự báo nằm cùng loại `DU_BAO_NGAY`.
- **Hướng xu hướng:** SQL không tính độ dốc; tầng [9] đọc chuỗi rồi kết luận. Vì vậy gold chỉ chọn các chuỗi có xu hướng rõ.
- **Chấm:**
  - Chuỗi chấm từ `rows`, so từng mốc thời gian.
  - Hướng chấm từ câu trả lời.

**T11. Khoảng và phân bố**
- **Đường đi:**
  - Khoảng dao động: hai metric (nhỏ nhất, lớn nhất), hoặc nhánh nhiều bảng với `MIN` và `MAX` trên bản ghi giờ.
  - Phân bố điều kiện thời tiết và giá trị phổ biến nhất: **nhánh nhiều bảng**, nhóm theo `ten_dieu_kien` với `COUNT`, sắp xếp rồi `limit 1`.
- **Bước quyết định:**
  - [4'] find_fields phải tìm ra bảng điều kiện thời tiết.
  - [6'] phải nối được với bảng sự kiện.

**T12. Bất thường, vượt ngưỡng**
- **Đường đi theo loại con:**
  - Vượt ngưỡng tuyệt đối: lọc theo dòng, nhánh metric hoặc nhánh nhiều bảng; `supported`.
  - Theo quy tắc "thời tiết xấu cần cảnh báo": điều kiện nằm ở `nhom_muc_do` của bảng điều kiện, nên phải đi **nhánh nhiều bảng**. Ở nhánh này quy tắc **chỉ là văn bản**, nên câu này kiểm tra mô hình có tự áp đúng định nghĩa hay không.
  - Lệch so với mức thường (≥ 2 độ lệch chuẩn): **không làm được** vì không có `STDDEV` hay hàm cửa sổ; `unsupported`. Hành vi đúng là báo không tính được, hoặc chia thành hai bước rõ ràng và nêu giả định.

**T13. Tương quan**
- **Đường đi theo loại con:**
  - Hệ số tương quan: **không làm được** (không có `CORR`); `unsupported`. Đáp án chấp nhận là `cannot_answer`, `no_metric` hoặc thông điệp rõ ràng; trả về một hệ số tự bịa là lỗi nặng.
  - So sánh có điều kiện ("ngày mưa có mát hơn ngày không mưa"): nhánh nhiều bảng với `AVG(CASE WHEN tong_luong_mua_mm > 0 THEN nhiet_do_cao_nhat_c END)`, so với biểu thức ngược điều kiện; `supported`.
  - Đồng xuất hiện: nối bảng điều kiện rồi lấy `AVG(gio_giat_kmh)`; `supported`.

#### Nhóm C. Tri thức nghiệp vụ

**T14. Định nghĩa nghiệp vụ.** Đây là loại mà **đường đi quyết định độ tin cậy**.
- **Nhánh metric:** quy tắc gắn với metric được **code** thêm vào SQL, mô hình không bỏ được. Khi câu hỏi tự lọc cùng cột, quy tắc nhường và được ghi vào `overridden`.
  - Kiểm tra quy tắc nhường: "nhiệt độ cao nhất theo giờ" phải làm quy tắc chỉ số ngày nhường.
  - Kiểm tra quy tắc không lan: với câu ghép nhiều ý, quy tắc của metric này không được xuất hiện thành bộ lọc tường minh trên metric khác. Đây là lỗi đã gặp ở bộ thử nghiệm cũ.
- **Nhánh nhiều bảng:** quy tắc chỉ là văn bản trong `expert_rules`. Quy tắc cuối tuần (`la_cuoi_tuan`), thời tiết xấu (`nhom_muc_do`) và thành phố đang theo dõi (`hoat_dong`) đều nằm ở bảng chiều, nên thường rơi vào nhánh này.
- **Đề xuất:** mỗi quy tắc có ít nhất một câu đi nhánh metric và một câu đi nhánh nhiều bảng, để đo chênh lệch giữa "quy tắc áp bằng code" và "quy tắc nhờ mô hình nhớ".
- **Chấm:** tầng 4 (điều kiện có trong SQL, `overridden` đúng, không lan sang metric khác) và tầng 5.

**T15. Dữ liệu và vận hành**
- **Đường đi theo loại con:**
  - Vận hành ETL: nhánh metric (`so_lan_nap`, `so_lan_nap_that_bai`, `ty_le_nap_thanh_cong`, `thoi_gian_nap_trung_binh` trên `tb_lan_nap_du_lieu`); quy tắc "lần nạp thất bại" áp bằng code.
  - Độ mới dữ liệu ("cập nhật lần cuối"): không có metric, nên đi nhánh nhiều bảng với `MAX(ket_thuc_luc)`.
  - Danh mục có trong dữ liệu (đơn vị của chỉ số, danh sách thành phố, loại thời tiết nguy hiểm): nhánh nhiều bảng trên `dim_chi_so_thoi_tiet`, `dim_thanh_pho`, `dim_dieu_kien_thoi_tiet`.
  - Câu hỏi về **chính hệ thống** ("có những metric nào"): `ask_data` và route chat **không** trả lời loại này; agent MCP phải dùng `search_metrics`. Gold là `no_metric` hoặc `cannot_answer` ở route chat, ghi `capability: unsupported`.

#### Nhóm D. Ngôn ngữ và ngữ cảnh

**T16. Biến thể diễn đạt.** Luồng giống câu gốc; khác nhau ở **bước bị ảnh hưởng**:

| Biến thể | Bước bị ảnh hưởng | Vì sao |
|---|---|---|
| Đồng nghĩa giá trị (HN, Sài Gòn, thủ đô) | [2] viết lại và [4] ghi giá trị lọc | Mô hình phải đổi về giá trị thật (`Ha Noi`, `Ho Chi Minh`); bước [2] hiện đang chuẩn hóa ngược thành có dấu |
| Đồng nghĩa cột, chỉ số | [1] truy hồi, [3] tìm metric | Phụ thuộc từ đồng nghĩa khai báo trong thuật ngữ và cột |
| Không dấu, sai chính tả | [1] và [3] | Embedding và BM25 trên văn bản không dấu có thể không ra thuật ngữ; Jev có thể chấm thấp hơn ngưỡng 0,6 |
| Tiếng Anh | [1] đến [3] | Thuật ngữ khai báo bằng tiếng Việt |
| Câu dài, vòng vo | [2] | Bước viết lại phải bỏ phần thừa mà không mất thực thể |

Chấm từng cặp: câu gốc đúng nhưng biến thể sai thì ghi lỗi vào bước tương ứng (dựa vào kết quả trung gian của [1], [3], [4]).

**T17. Biểu thức thời gian**
- **Ai quy đổi:** quy đổi diễn ra ở [4] và [4'], do LLM làm với đầu vào `today`. Bước [2] giữ nguyên cụm thời gian, không có bộ phân tích thời gian bằng code.
- **Theo loại con:**
  - Ngày, tuần, thứ trong tuần: đặt vào `start`/`end`.
  - **Quy ước tuần** (bắt đầu thứ Hai hay Chủ nhật, "tuần này" có tính hôm nay không) chưa ghi trong prompt. Gold phải nêu quy ước, và benchmark chấp nhận `assumptions` nếu hệ thống ghi rõ cách đã hiểu.
  - **Trong ngày** ("sáng nay", "đêm qua", "6 đến 9 giờ"): trường `time` chỉ nhận ngày, nên phải lọc trên `thoi_diem_quan_sat`; `composed`.
  - Bộ chạy đặt `TimeZone=UTC` cho phiên truy vấn. Phải xác nhận dữ liệu lưu theo giờ nào trước khi viết gold, nếu không "đêm qua" sẽ lệch 7 tiếng.
  - **Ngầm định:** prompt lập plan nói thiếu kỳ thì "dùng kỳ gần nhất đã kết thúc" và ghi giả định. Với thời tiết, kỳ gần nhất có thể là hôm qua hoặc hôm nay. Gold liệt kê các cách hiểu chấp nhận, và bắt buộc có giả định trong `assumptions`.
- **Chấm:** tầng 3, so khoảng thời gian trong plan với `expect.time_range`; tầng 5 kết quả.

**T18. Hội thoại nhiều lượt**
- **Điểm vào:** chỉ chạy được qua **route chat** có `user_id` và `conversation_id`; `ask_data` không có lịch sử.
- **Cơ chế:** bước [2] nhận 6 lượt gần nhất. Bước [1] truy hồi bằng câu viết lại của lượt trước nối với câu hiện tại, để câu ngắn như "còn Hải Phòng?" vẫn kéo đúng thuật ngữ.
- **Bước quyết định theo quan hệ:**
  - Tinh chỉnh, cùng thực thể, cùng thuộc tính: [2] phải viết lại thành câu đầy đủ.
  - Dựa trên câu trả lời trước ("nhiệt độ ở **đó**"): thực thể chỉ có trong `answer` của lượt trước, mà `answer` bị rút còn **500 ký tự**. Câu trả lời dài có bảng thì thực thể có thể bị cắt mất. Đây là rủi ro cụ thể benchmark cần đo.
  - Trả lời câu hỏi làm rõ: câu trả lời được gửi như một câu hỏi mới trong cùng hội thoại, nên các câu T19 có thể kéo dài thành hội thoại T18.
- **Chấm:** từng lượt, gold đã thay đại từ bằng giá trị thật; cộng tỷ lệ hội thoại đúng trọn vẹn.

**T21. Câu ghép nhiều ý**
- **Đường đi:** nhánh metric với **tối đa 3 truy vấn**.
  - Câu có 4 đại lượng trở lên không thể trả đủ trong một lượt; hành vi đúng là trả 3 đại lượng và nói rõ phần còn thiếu, hoặc hỏi lại.
  - Câu một chỉ số, nhiều thành phố: một truy vấn có nhóm và lọc `IN`.
- **Bước quyết định:**
  - [4] tách đúng các truy vấn.
  - [5] mỗi metric chỉ nhận quy tắc của chính nó.
  - Với chỉ số khác loại bản ghi (nhiệt độ cao nhất theo ngày và độ ẩm trung bình theo giờ), hai quy tắc khác nhau phải áp đúng chỗ.
- **Chấm:** từng thành phần; câu chỉ đúng khi mọi thành phần đúng. Thêm số câu bị lan quy tắc.

#### Nhóm E. Không trả lời thẳng được

**T19. Mơ hồ.** Có ba chỗ có thể dừng:
- [2] viết lại có thể tự thêm giả định.
- [4] lập plan trả `needs_clarification` kèm tối đa 4 lựa chọn. Đây là chỗ quan sát được hành vi lúc `answered`, lúc `needs_clarification`.
- [4'] lập plan dataset cũng có thể hỏi lại.

Gold liệt kê các hành vi chấp nhận cho từng câu. Benchmark đo thêm **độ ổn định** qua `--repeat`: một câu mơ hồ trả hai trạng thái khác nhau giữa các lượt là lỗi về trải nghiệm, kể cả khi trạng thái nào cũng chấp nhận được.

**T20. Không trả lời được.** Điểm dừng **khác nhau theo loại con**, và benchmark nên ghi lại bước dừng thực tế:

| Loại con | Điểm dừng mong đợi | Rủi ro |
|---|---|---|
| Ngoài miền (giá vàng) | [3] không có metric ≥ 0,6, sau đó [4'] find_fields `match=none` thì `cannot_answer` | Jev chấm nhầm cao, plan cố trả lời bằng metric không liên quan |
| Thiếu cột (UV, AQI) | [3], sau đó [4'] | find_fields trả cột gần nghĩa (bức xạ, tầm nhìn) và plan dùng nhầm |
| Thiếu giá trị (Bangkok, Sa Pa) | **Không dừng ở [3]**: metric vẫn đúng, plan lọc `ten_thanh_pho='Bangkok'`, truy vấn ra rỗng hoặc `NULL`, [9] phải nói không có dữ liệu | Tầng trả lời diễn giải `NULL` thành 0, hoặc mô hình thay bằng thành phố gần nhất |
| Ngoài khoảng dữ liệu | Như trên: truy vấn chạy, ra rỗng | Như trên |
| Phi SQL, chẩn đoán, đề xuất | [4] trả `no_metric`, hoặc [4'] trả `cannot_answer` | Mô hình trả lời "vì sao" bằng kiến thức chung, không dựa trên dữ liệu |
| Tiền đề sai (tuyết ở Cần Thơ) | Truy vấn chạy, ra 0; [9] phải **bác tiền đề** | Câu trả lời đi theo tiền đề sai |

Điểm chính của T20 là **tỷ lệ bịa số**: số câu có một con số không đến từ `rows`. Với `ask_data`, kiểm tra không có `answered` kèm kết quả khác rỗng mà gold là rỗng. Với route chat, kiểm tra câu trả lời không chứa số liệu khi `rows` rỗng.

### A.4. Tổng hợp: đường đi và mức hỗ trợ theo loại

| Loại | Đường đi chính | Bước quyết định | Capability hiện tại |
|---|---|---|---|
| T1 | metric | [3] chọn metric, [4] giá trị lọc | supported (theo giờ: composed) |
| T2 | metric; dataset nếu gọi theo vùng khí hậu | [3] phép gộp, [5] loại bản ghi | supported |
| T3 | metric hoặc dataset | [3], [4'] đơn vị đếm | supported |
| T4 | metric + [9] | [9] diễn giải ngưỡng | composed |
| T5 | metric (lọc dòng) hoặc dataset | thiếu HAVING | supported / composed |
| T6 | metric hoặc dataset | [4] cột nhóm, [6'] đường nối | supported |
| T7 | metric | [4] hướng sắp xếp, `limit` | supported (thứ hạng: composed) |
| T8 | metric nhiều truy vấn + [9], hoặc dataset với `CASE` | [9] phép trừ | composed |
| T9 | metric có sẵn hoặc ghép | [4], [9] | supported / composed |
| T10 | metric `granularity=day` | không có `hour` | supported (theo giờ, hướng: composed) |
| T11 | dataset | [4'], [6'] | supported |
| T12 | metric hoặc dataset | quy tắc dạng văn bản; thiếu `STDDEV` | supported / unsupported |
| T13 | dataset | thiếu `CORR` | supported (có điều kiện) / unsupported (hệ số) |
| T14 | metric (code) hoặc dataset (văn bản) | [5] hoặc [4'] | supported |
| T15 | metric hoặc dataset; câu về hệ thống: không | | supported / unsupported |
| T16 | như câu gốc | [1], [2], [3], [4] tùy biến thể | như câu gốc |
| T17 | như câu gốc | [4] quy đổi theo `today` | supported (trong ngày: composed) |
| T18 | chỉ route chat | [2] với lịch sử, `answer` rút còn 500 ký tự | supported |
| T19 | dừng ở [2], [4] hoặc [4'] | độ ổn định | supported |
| T20 | dừng ở [3], [4'], hoặc chạy ra rỗng rồi [9] | không bịa số | supported |
| T21 | metric ≤ 3 truy vấn | [4] tách truy vấn, [5] không lan quy tắc | supported (≤ 3 đại lượng) |

Các ô `composed` và `unsupported` cũng là **danh sách cải tiến tiềm năng** cho bộ dựng truy vấn:
- `granularity=hour`;
- HAVING;
- hàm cửa sổ cho thứ hạng và tỷ trọng;
- `CORR` và `STDDEV`;
- quy tắc áp bằng code ở nhánh nhiều bảng.

Benchmark cho biết mỗi cải tiến tác động tới bao nhiêu câu, để chọn thứ tự làm.
