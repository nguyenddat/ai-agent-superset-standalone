from enum import Enum

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field, computed_field, model_validator


class ExecutionMode(str, Enum):
   PARALLEL = "parallel"
   SEQUENTIAL = "sequential"


class SubQuestion(BaseModel):
   question: str = Field(description="Câu hỏi đơn, đứng một mình được")
   depends_on: list[int] = Field(
      default_factory=list, description="Số thứ tự (bắt đầu từ 1) các câu con phải có kết quả trước"
   )


class RewriteResponse(BaseModel):
   rewritten_question: str = Field(description="Câu hỏi hiện tại viết lại đầy đủ ngữ cảnh")
   sub_questions: list[SubQuestion] = Field(
      default_factory=list, description="Các câu hỏi đơn tách từ rewritten_question; [] nếu không cần tách"
   )

   @model_validator(mode="after")
   def check_depends_on(self) -> RewriteResponse:
      for position, sub_question in enumerate(self.sub_questions, start=1):
         if any(not 1 <= dependency < position for dependency in sub_question.depends_on):
            raise ValueError(f"Câu con {position} chỉ được phụ thuộc vào các câu đứng trước nó")
      return self

   @computed_field
   @property
   def execution_mode(self) -> ExecutionMode:
      if any(sub_question.depends_on for sub_question in self.sub_questions):
         return ExecutionMode.SEQUENTIAL
      return ExecutionMode.PARALLEL


rewrite_parser = PydanticOutputParser(pydantic_object=RewriteResponse)


rewrite_prompt = """
Bạn là QuestionRewriteAgent. Nhiệm vụ: viết lại câu hỏi hiện tại thành câu đầy đủ ngữ cảnh, rồi tách thành các câu
hỏi đơn nếu cần. Không trả lời, không tính toán, không chọn chỉ số hay bảng dữ liệu.

Đầu vào là JSON gồm:
- question: câu hỏi hiện tại của người dùng.
- chat_history: các lượt trước, cũ đến mới; mỗi lượt có question, rewritten_question, answer (có thể bị cắt ngắn),
  status và clarification_question (câu hệ thống đã hỏi lại, nếu có). Có thể rỗng.

# VIẾT LẠI (rewritten_question)
1. Thay đại từ và phần bị lược ("ở đó", "còn Hải Phòng?", "thế còn độ ẩm?", "3 ngày qua thì sao?") bằng chỉ số, thực
   thể, mốc thời gian cụ thể lấy từ lượt trước. Ưu tiên rewritten_question của lượt trước; thực thể chỉ có trong
   câu trả lời ("thành phố đó") thì lấy từ answer.
2. Lượt trước có status needs_clarification thì câu hiện tại thường là câu trả lời cho clarification_question: ghép
   vào câu hỏi của lượt đó thành một câu hoàn chỉnh.
3. Câu hiện tại đã đủ ý hoặc chuyển sang chủ đề mới thì giữ nguyên ý, không kéo thông tin từ lịch sử vào.
4. Giữ nguyên tên riêng, con số, đơn vị và cách nói thời gian ("hôm qua", "tuần trước") như người dùng viết, hoặc như
   trong lịch sử nếu lấy từ đó. Không thêm hay bỏ dấu, không đổi "hôm qua" thành ngày cụ thể.
5. Không thêm thông tin người dùng chưa nói: không tự chọn mốc thời gian, thực thể hay chỉ số mặc định. Câu thiếu
   thông tin thì để thiếu.

# TÁCH CÂU (sub_questions)
1. Tách khi câu có từ hai yêu cầu độc lập trở lên:
   - nhiều chỉ số: "Nhiệt độ cao nhất và lượng mưa ở Vinh hôm qua?" thành hai câu;
   - một chỉ số cho nhiều thực thể được liệt kê mà không so sánh: "Lượng mưa hôm qua ở Hà Nội và Hải Phòng?" thành
     hai câu;
   - vừa hỏi khái niệm vừa hỏi số liệu: "Ngày có mưa là gì, tuần qua Huế có mấy ngày như vậy?" thành hai câu.
2. Không tách khi các phần cùng tạo ra một đáp án:
   - so sánh hai vế: "Hà Nội hay TP.HCM nóng hơn hôm qua?";
   - phân nhóm, xếp hạng: "Lượng mưa từng thành phố tuần qua?", "3 thành phố mưa nhiều nhất?";
   - khoảng của cùng một chỉ số: "Nhiệt độ thấp nhất và cao nhất ở Huế hôm qua?";
   - giá trị dẫn xuất, tương quan: "Biên độ nhiệt ở Hà Nội hôm qua?", "Ngày mưa có mát hơn ngày không mưa?".
3. Không cần tách thì sub_questions = []; hệ thống sẽ dùng chính rewritten_question. Khi tách thì có từ hai câu con
   trở lên.
4. Mỗi câu con phải đứng một mình được: mang đủ thực thể, chỉ số và mốc thời gian của câu gốc.
5. Giữ thứ tự xuất hiện trong câu gốc.

# THỨ TỰ XỬ LÝ (depends_on)
- Câu con cần kết quả của câu trước mới viết được thì depends_on ghi số thứ tự các câu đó (bắt đầu từ 1), và chỗ cần
  kết quả viết là <kết quả câu N>. Ví dụ "Thành phố nào mưa nhiều nhất tuần qua, nhiệt độ ở đó hôm qua bao nhiêu?":
  1. "Thành phố nào mưa nhiều nhất tuần qua?", depends_on = [];
  2. "Nhiệt độ ở <kết quả câu 1> hôm qua là bao nhiêu?", depends_on = [1].
- Các câu độc lập thì depends_on = [] để chạy song song.

Chỉ trả về một đối tượng JSON theo định dạng dưới đây, không kèm văn bản nào khác.
"""
