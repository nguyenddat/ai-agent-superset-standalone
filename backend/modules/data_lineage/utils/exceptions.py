from backend.common.base_exceptions import ConflictError, NotFoundError, ValidationError


class LineageValidationError(ValidationError):
    abstract = False
    status = 422
    code = "data_lineage_invalid"
    message = "Khai báo data lineage không hợp lệ."


class LineageNotFoundError(NotFoundError):
    abstract = False
    code = "data_lineage_not_found"
    message = "Không tìm thấy dữ liệu lineage được yêu cầu."


class LineageConflictError(ConflictError):
    abstract = False
    code = "data_lineage_conflict"
    message = "Tên phép biến đổi đã tồn tại cho bảng đích."
