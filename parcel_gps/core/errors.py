from __future__ import annotations

from typing import Any

QUOTA_EXHAUSTED_CODE = "KEY_AUTH_004"
AMBIGUOUS_CODE = "CNV_AMBIGUOUS"
COVERAGE_CODE = "CNV_COVERAGE"
PLACE_NAME_CODE = "CNV_PLACE_NAME"
HTTP_AMBIGUOUS = 300
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500
HTTP_SERVICE_UNAVAILABLE = 503


class ParcelGpsError(Exception):
    kind = "generic"

    def __init__(
        self,
        message: str,
        status: int | None = None,
        code: str | None = None,
        details: Any = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details
        self.retry_after = retry_after


class AuthenticationError(ParcelGpsError):
    kind = "auth"


class ForbiddenError(ParcelGpsError):
    kind = "forbidden"


class NotFoundError(ParcelGpsError):
    kind = "not_found"


class ValidationError(ParcelGpsError):
    kind = "validation"


class PlaceNameError(ParcelGpsError):
    kind = "place_name"


class CoverageError(ParcelGpsError):
    kind = "coverage"

    @property
    def country(self) -> str | None:
        return self.details.get("country") if isinstance(self.details, dict) else None


class AmbiguousReferenceError(ParcelGpsError):
    kind = "ambiguous"

    @property
    def candidate_countries(self) -> list[str]:
        if not isinstance(self.details, dict):
            return []
        countries = []
        for candidate in self.details.get("candidates") or []:
            code = candidate.get("country") if isinstance(candidate, dict) else None
            if isinstance(code, str) and code not in countries:
                countries.append(code)
        return countries


class QuotaExceededError(ParcelGpsError):
    kind = "quota"


class RateLimitError(ParcelGpsError):
    kind = "rate_limit"


class ServerError(ParcelGpsError):
    kind = "server"


class ServiceUnavailableError(ServerError):
    kind = "unavailable"


class RequestTimeoutError(ParcelGpsError):
    kind = "timeout"


class NetworkError(ParcelGpsError):
    kind = "network"


class NoOutlineError(ParcelGpsError):
    kind = "no_outline"


def error_from_response(status: int, body: dict[str, Any], retry_after: float | None = None) -> ParcelGpsError:
    code = body.get("code") if isinstance(body.get("code"), str) else None
    message = body.get("error") or body.get("message") or f"HTTP {status}"
    if not isinstance(message, str):
        message = f"HTTP {status}"
    details = body.get("data")
    kwargs: dict[str, Any] = {"status": status, "code": code, "details": details, "retry_after": retry_after}

    if code == AMBIGUOUS_CODE or status == HTTP_AMBIGUOUS:
        return AmbiguousReferenceError(message, **kwargs)
    if code == COVERAGE_CODE:
        return CoverageError(message, **kwargs)
    if code == PLACE_NAME_CODE:
        return PlaceNameError(message, **kwargs)
    if code == QUOTA_EXHAUSTED_CODE:
        return QuotaExceededError(message, **kwargs)
    if status == HTTP_TOO_MANY_REQUESTS:
        return RateLimitError(message, **kwargs)
    if status == HTTP_UNAUTHORIZED:
        return AuthenticationError(message, **kwargs)
    if status == HTTP_FORBIDDEN:
        return ForbiddenError(message, **kwargs)
    if status == HTTP_NOT_FOUND:
        return NotFoundError(message, **kwargs)
    if status in (HTTP_BAD_REQUEST, HTTP_UNPROCESSABLE):
        return ValidationError(message, **kwargs)
    if status == HTTP_SERVICE_UNAVAILABLE:
        return ServiceUnavailableError(message, **kwargs)
    if status >= HTTP_SERVER_ERROR:
        return ServerError(message, **kwargs)
    return ParcelGpsError(message, **kwargs)
