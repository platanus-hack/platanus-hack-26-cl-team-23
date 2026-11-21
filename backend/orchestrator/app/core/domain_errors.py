from collections.abc import Mapping


class DomainError(Exception):
    """Error de dominio. Cada subclase define su código HTTP."""

    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.headers = dict(headers or {})


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class ValidationDomainError(DomainError):
    status_code = 422


class AuthenticationError(DomainError):
    status_code = 401


class AuthorizationError(DomainError):
    status_code = 403


class ExternalServiceError(DomainError):
    status_code = 502


class DatabaseUnavailableError(DomainError):
    status_code = 503


class RateLimitError(DomainError):
    status_code = 429
