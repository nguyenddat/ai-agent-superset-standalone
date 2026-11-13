from typing import Any, ClassVar


class AppError(Exception):
    abstract: ClassVar[bool] = True
    status: ClassVar[int] = 400
    code: ClassVar[str] = "app_error"
    message: ClassVar[str] = "Yêu cầu không hợp lệ."

    def __new__(cls, *args: Any, **kwargs: Any) -> "AppError":
        if cls.__dict__.get("abstract", False):
            raise TypeError(f"{cls.__name__} is abstract; raise a module-specific subclass")
        return super().__new__(cls)

    def __init__(self, message: str | None = None) -> None:
        super().__init__(self.message if message is None else message)


class ValidationError(AppError, ValueError):
    abstract = True
    status = 400
    code = "validation_error"
    message = "Dữ liệu gửi lên không hợp lệ."


class NotAuthenticatedError(AppError):
    abstract = True
    status = 401
    code = "not_authenticated"
    message = "Cần đăng nhập để tiếp tục."


class NotAuthorizedError(AppError):
    abstract = True
    status = 403
    code = "not_authorized"
    message = "Không có quyền thực hiện thao tác này."


class NotFoundError(AppError):
    abstract = True
    status = 404
    code = "not_found"
    message = "Không tìm thấy dữ liệu."


class ConflictError(AppError):
    abstract = True
    status = 409
    code = "conflict"
    message = "Dữ liệu đã thay đổi; tải lại rồi thử lại."


class TooManyRequestsError(AppError):
    abstract = True
    status = 429
    code = "too_many_requests"
    message = "Có quá nhiều yêu cầu đang chờ xử lý."


class ServiceUnavailableError(AppError):
    abstract = True
    status = 503
    code = "service_unavailable"
    message = "Dịch vụ tạm thời không sẵn sàng."
