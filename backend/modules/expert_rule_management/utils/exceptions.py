from backend.common.base_exceptions import ConflictError, NotFoundError, ValidationError


class ExpertRuleNotFoundError(NotFoundError):
    code = "expert_rule_not_found"
    message = "Không tìm thấy expert rule."


class ExpertRuleValidationError(ValidationError):
    code = "expert_rule_invalid"
    message = "Expert rule không hợp lệ."


class ExpertRuleConflictError(ConflictError):
    code = "expert_rule_conflict"
    message = "Expert rule đã thay đổi; hãy tải lại trước khi lưu."
