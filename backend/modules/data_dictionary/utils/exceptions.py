from backend.common.base_exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)


class DataDictionaryValidationError(ValidationError):
    abstract = False
    status = 422
    code = "invalid_data_dictionary"
    message = "Từ điển dữ liệu không hợp lệ."


class DictionaryAutofillUnavailableError(ServiceUnavailableError):
    abstract = False
    code = "dictionary_autofill_unavailable"
    message = "Tự động điền chưa sẵn sàng: chưa cấu hình OPENROUTER_API_KEY."


class DictionaryAutofillInProgressError(ConflictError):
    abstract = False
    code = "dictionary_autofill_in_progress"
    message = "Bảng đang được tự động điền; chờ lượt hiện tại kết thúc."


class DictionaryAutofillFailedError(AppError):
    abstract = False
    status = 502
    code = "dictionary_autofill_failed"
    message = "Mô hình không trả về gợi ý hợp lệ; thử lại sau."


class DictionaryTableNotFoundError(NotFoundError):
    abstract = False
    code = "dictionary_table_not_found"
    message = "Không tìm thấy bảng được yêu cầu."


class DictionaryConnectionNotFoundError(NotFoundError):
    abstract = False
    code = "dictionary_connection_not_found"
    message = "Không tìm thấy kết nối database được yêu cầu."
