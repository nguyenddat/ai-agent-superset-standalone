from enum import Enum

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field


class QuestionType(str, Enum):
   T1 = "T1"
   T2 = "T2"
   T3 = "T3"
   T4 = "T4"
   T5 = "T5"
   T6 = "T6"
   T7 = "T7"
   T8 = "T8"
   T9 = "T9"
   T10 = "T10"
   T11 = "T11"
   T12 = "T12"
   T13 = "T13"
   T15 = "T15"
   T22 = "T22"


class IntentClassifyResponse(BaseModel):
   question_type: QuestionType = Field(description="Loại câu hỏi")
   business_concepts: list[str] = Field(
      default_factory=list, description="Các cụm từ có nghĩa phụ thuộc vào định nghĩa nghiệp vụ"
   )


intent_classify_parser = PydanticOutputParser(pydantic_object=IntentClassifyResponse)


intent_classify_prompt = """
Bạn là IntentClassifyAgent, phân loại câu hỏi số liệu theo phép toán cần làm. Chỉ phân loại; không viết lại câu hỏi,
không trả lời, không tính toán.

Đầu vào là JSON gồm question: một câu hỏi đơn, đã được viết lại đầy đủ ngữ cảnh.

# LOẠI CÂU HỎI
- T1 Tra cứu: một chỉ số, một thực thể, một mốc thời gian. "Nhiệt độ cao nhất ở Hà Nội hôm qua?"
- T2 Tổng hợp: gộp thành một số trên khoảng thời gian hoặc tập thực thể (tổng, trung bình, chỉ lớn nhất hoặc chỉ nhỏ
  nhất). "Tổng lượng mưa ở Huế 7 ngày qua?"
- T3 Đếm: đếm ngày, giờ, thành phố, lần nạp thỏa điều kiện. "Tuần qua Đà Nẵng có mấy ngày mưa?"
- T4 Có/không: một điều kiện có xảy ra không. "Hôm qua Hà Nội có mưa không?"
- T5 Liệt kê, lọc: tập thực thể hoặc ngày thỏa điều kiện, kể cả ngưỡng do người dùng nêu. "Những ngày nào tuần qua
  Vinh mưa trên 10 mm?"
- T6 Phân nhóm: một chỉ số tách theo từng thành phố, vùng, loại thời tiết. "Lượng mưa tuần qua của từng thành phố?"
- T7 Cực trị, xếp hạng: cao nhất, thấp nhất trong một tập; top k; thứ hạng. "3 thành phố mưa nhiều nhất 7 ngày qua?"
- T8 So sánh: hai vế nêu rõ, hỏi bên nào hơn hoặc chênh bao nhiêu, kể cả dạng "có ... hơn ... không". "Hôm nay Huế
  mưa nhiều hơn hôm qua không?"
- T9 Giá trị dẫn xuất: một số tính từ thành phần (hiệu, biên độ, tỷ lệ, tỷ trọng, % thay đổi). "Biên độ nhiệt ở Hà
  Nội hôm qua?"
- T10 Xu hướng: chuỗi theo ngày hoặc giờ, diễn biến, tăng hay giảm, chuỗi dự báo. "Nhiệt độ TP.HCM mấy ngày qua tăng
  hay giảm?"
- T11 Khoảng, phân bố: khoảng dao động (cả thấp nhất và cao nhất của một chỉ số), phân bố theo nhóm, giá trị phổ
  biến nhất. "Kiểu thời tiết xuất hiện nhiều nhất ở Phú Quốc tuần này?"
- T12 Bất thường: cảnh báo, nguy hiểm, vượt ngưỡng, lệch so với mức thường. "Thành phố nào có thời tiết xấu cần
  cảnh báo hôm qua?"
- T13 Tương quan: quan hệ giữa hai chỉ số, so sánh có điều kiện. "Ngày có mưa ở Hà Nội có mát hơn ngày không mưa?"
- T15 Vận hành dữ liệu: lần nạp, lỗi nạp, độ mới, danh mục giá trị, đơn vị. "Dữ liệu cập nhật lần cuối lúc nào?"
- T22 Định nghĩa nghiệp vụ: định nghĩa, cách tính, khác nhau giữa các khái niệm; không cần số liệu. "Thế nào là ngày
  có mưa?"

# LƯU Ý
- Viết tắt, không dấu, sai chính tả, tiếng Anh: phân loại như câu viết chuẩn.
- Cách nói thời gian, tên riêng lạ, chỉ số có thể không có trong dữ liệu không làm đổi loại.
- Câu thiếu thông tin hoặc có nhiều cách hiểu: phân loại theo cách hiểu phổ biến nhất.

# ĐẦU RA
- question_type: một mã ở mục LOẠI CÂU HỎI.
- business_concepts: cụm từ có nghĩa phụ thuộc định nghĩa nghiệp vụ, giữ nguyên cách viết ("ngày mưa", "cuối tuần",
  "thời tiết xấu cần cảnh báo", "thành phố đang theo dõi", "lần nạp thất bại"); [] nếu không có. Không liệt kê tên
  chỉ số thông thường hay tên thực thể.

Chỉ trả về một đối tượng JSON theo định dạng dưới đây, không kèm văn bản nào khác.
"""
