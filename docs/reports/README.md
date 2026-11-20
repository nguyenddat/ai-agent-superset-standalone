# Báo cáo

Thư mục này dành cho các báo cáo theo yêu cầu về thiết kế, triển khai, kiểm thử và bàn giao. Handbook là nơi giữ quy ước lâu dài; báo cáo ghi kết quả tại một thời điểm, kèm phạm vi và bằng chứng.

Khi tạo báo cáo, dùng tiếng Việt có dấu và UTF-8 cho Markdown. Đặt tên theo `YYYY-MM-DD-chu-de.md`; nếu xuất Word/PDF, giữ cùng tên gốc. Ghi rõ ngày, phiên bản hoặc commit được đánh giá, các bước đã kiểm tra, kết quả và giới hạn còn lại. Không đưa secret hoặc URI chứa mật khẩu vào báo cáo.

## Tài liệu thiết kế

- [2026-11-20-thiet-ke-tra-loi-stream-bieu-do.md](2026-11-20-thiet-ke-tra-loi-stream-bieu-do.md): thiết kế văn phong câu trả lời, mục "Cách tính", stream chữ câu trả lời và bộ biểu đồ mở rộng (32 loại, spec, bộ kiểm tra, lưu lựa chọn của người dùng); chia việc BE1, BE2, FE. Phần backend biểu đồ và văn phong đã triển khai, xem [biểu đồ](../handbook/modules/text2sql/bieu-do.md).
