from backend.common.base_exceptions import ConflictError, NotFoundError, ValidationError


class BusinessModelValidationError(ValidationError):
    abstract = False
    status = 422
    code = "business_model_invalid"
    message = "Dữ liệu mô hình nghiệp vụ không hợp lệ."


class BusinessModelNotFoundError(NotFoundError):
    abstract = False
    code = "business_model_not_found"
    message = "Không tìm thấy dữ liệu mô hình nghiệp vụ được yêu cầu."


class BusinessModelConflictError(ConflictError):
    abstract = False
    code = "business_model_conflict"
    message = "Tên tầng dữ liệu hoặc miền nghiệp vụ đã tồn tại."
