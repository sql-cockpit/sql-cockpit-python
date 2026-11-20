"""Official Python SDK for the SQL Cockpit Portal API."""

from . import models
from ._async_client import AsyncClient
from ._client import Client
from ._version import __version__
from .errors import (
    AuthenticationError,
    ConfigurationError,
    ConnectionError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    SqlCockpitError,
    TimeoutError,
    ValidationError,
)

__all__ = [
    "__version__",
    "Client",
    "AsyncClient",
    "models",
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
