from backend.common.base_exceptions import ConflictError, NotFoundError, ValidationError


class ConversationValidationError(ValidationError):
    code = "conversation_invalid"
    message = "Dữ liệu hội thoại không hợp lệ."


class ConversationNotFoundError(NotFoundError):
    code = "conversation_not_found"
    message = "Không tìm thấy hội thoại."


class ConversationTurnNotFoundError(NotFoundError):
    code = "conversation_turn_not_found"
    message = "Không tìm thấy lượt hỏi đáp."


class ConversationConnectionNotFoundError(NotFoundError):
    code = "conversation_connection_not_found"
    message = "Kết nối dữ liệu không tồn tại."


class ConversationTurnNotContinuableError(ConflictError):
    code = "conversation_turn_not_continuable"
    message = "Lượt hỏi đáp này không chờ người dùng trả lời nên không tiếp tục được."


class ConversationResultNotFoundError(NotFoundError):
    code = "conversation_result_not_found"
    message = "Không tìm thấy kết quả này trong lượt hỏi đáp."


class ConversationChartInvalidError(ValidationError):
    code = "conversation_chart_invalid"
    message = "Biểu đồ không hợp lệ."
