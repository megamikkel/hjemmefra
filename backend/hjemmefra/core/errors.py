class HjemmefraError(Exception):
    code = "ERROR"


class NotFound(HjemmefraError):
    code = "NOT_FOUND"


class Forbidden(HjemmefraError):
    code = "FORBIDDEN"


class ValidationFailed(HjemmefraError):
    code = "VALIDATION_FAILED"


class ConflictError(HjemmefraError):
    code = "CONFLICT"
