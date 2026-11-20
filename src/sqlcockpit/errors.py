"""Exceptions raised by the SQL Cockpit SDK.

Every exception carries ``code``, ``status``, ``message`` and ``fields``. None of
them ever contains your API key.
"""

from __future__ import annotations

import builtins
from typing import Dict, List, Optional

__all__ = [
    "SqlCockpitError",
    "ConfigurationError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
    "RateLimitError",
    "ServerError",
    "ConnectionError",
    "TimeoutError",
]


class SqlCockpitError(Exception):
    """Base class for every error the SDK raises.

    ``code`` is the portal's error code (for example ``"not_found"``) or one the
    SDK sets itself (``"unexpected_redirect"``, ``"response_too_large"``,
    ``"invalid_response"``, ``"unreachable"``, ``"timeout"``, ``"invalid_config"``).
    ``status`` is the HTTP status, or 0 when no response arrived.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "request_failed",
        status: int = 0,
        fields: Optional[Dict[str, List[str]]] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.fields = fields
        self.retry_after = retry_after

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, status={self.status!r}, message={self.message!r})"


class ConfigurationError(SqlCockpitError, ValueError):
    """The API key, portal URL or timeout is missing or not usable."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="invalid_config")


class AuthenticationError(SqlCockpitError):
    """HTTP 401: the API key is missing, invalid, revoked or expired."""


class PermissionDeniedError(SqlCockpitError):
    """HTTP 403: the key lacks the scope, or your role cannot do this."""


class NotFoundError(SqlCockpitError):
    """HTTP 404: not found, or not something your account can reach."""


class ValidationError(SqlCockpitError):
    """HTTP 422: a value was refused. ``fields`` maps each field to its messages."""


class RateLimitError(SqlCockpitError):
    """HTTP 429: too many requests. ``retry_after`` is the wait in seconds, if sent."""


class ServerError(SqlCockpitError):
    """HTTP 5xx: the portal failed. Try again shortly."""


class ConnectionError(SqlCockpitError, builtins.ConnectionError):
    """The portal could not be reached."""


class TimeoutError(ConnectionError, builtins.TimeoutError):
    """The portal did not answer within the timeout."""


def error_for_status(
    status: int,
    code: str,
    message: str,
    fields: Optional[Dict[str, List[str]]] = None,
    retry_after: Optional[float] = None,
) -> SqlCockpitError:
    cls: type
    if status == 401:
        cls = AuthenticationError
    elif status == 403:
        cls = PermissionDeniedError
    elif status == 404:
        cls = NotFoundError
    elif status == 422:
        cls = ValidationError
    elif status == 429:
        cls = RateLimitError
    elif status >= 500:
        cls = ServerError
    else:
        cls = SqlCockpitError
    return cls(message, code=code, status=status, fields=fields, retry_after=retry_after)
