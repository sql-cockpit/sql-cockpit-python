from __future__ import annotations

import os
import re
import uuid
from typing import Mapping, Optional, Union
from urllib.parse import urlsplit, urlunsplit

from .errors import ConfigurationError

DEFAULT_PORTAL_URL = "https://portal.sql-cockpit.com"
API_PATH = "/api/portal/v1"
DEFAULT_TIMEOUT = 20.0
MIN_TIMEOUT = 1.0
MAX_TIMEOUT = 120.0
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def normalize_portal_url(value: Optional[str]) -> str:
    """HTTPS only, except loopback hosts for local development. No credentials, query or fragment."""
    raw = (value or "").strip() or DEFAULT_PORTAL_URL
    try:
        parts = urlsplit(raw)
        _ = parts.port  # raises ValueError for a bad port
    except ValueError:
        raise ConfigurationError("SQL_COCKPIT_PORTAL_URL is not a valid URL.") from None
    if not parts.scheme or not parts.hostname:
        raise ConfigurationError("SQL_COCKPIT_PORTAL_URL is not a valid URL.")
    if "@" in parts.netloc or parts.query or parts.fragment or "?" in raw or "#" in raw:
        raise ConfigurationError("SQL_COCKPIT_PORTAL_URL must not contain credentials, a query string or a fragment.")
    scheme = parts.scheme.lower()
    if not (scheme == "https" or (scheme == "http" and parts.hostname in LOOPBACK_HOSTS)):
        raise ConfigurationError("SQL_COCKPIT_PORTAL_URL must use https:// (http:// is only allowed for localhost).")
    return urlunsplit((scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def normalize_api_key(value: Optional[str]) -> str:
    key = (value or "").strip()
    if not key:
        raise ConfigurationError(
            "SQL_COCKPIT_API_KEY is required. Create a key in the portal under Settings > Developer access."
        )
    if len(key) < 20 or len(key) > 200 or re.search(r"\s", key):
        raise ConfigurationError("SQL_COCKPIT_API_KEY does not look like a SQL Cockpit API key.")
    return key


def normalize_timeout(value: Optional[float], env: Mapping[str, str]) -> float:
    if value is None:
        raw = env.get("SQL_COCKPIT_TIMEOUT_MS", "").strip()
        if not raw:
            return DEFAULT_TIMEOUT
        try:
            value = int(raw) / 1000
        except ValueError:
            raise ConfigurationError(
                "SQL_COCKPIT_TIMEOUT_MS must be a whole number of milliseconds between 1000 and 120000."
            ) from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError("timeout must be a number of seconds.")
    if not MIN_TIMEOUT <= float(value) <= MAX_TIMEOUT:
        raise ConfigurationError("timeout must be between 1 and 120 seconds.")
    return float(value)


def normalize_max_retries(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2:
        raise ConfigurationError("max_retries must be 0, 1 or 2.")
    return value


def env_or(value: Optional[str], name: str, env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    if value is not None:
        return value
    return (os.environ if env is None else env).get(name)


def check_uuid(value: Union[str, uuid.UUID], name: str) -> str:
    """Refuse anything that is not a UUID before it reaches a URL."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if not isinstance(value, str) or not _UUID_RE.match(value):
        raise ValueError(f"{name} must be a UUID.")
    return value.lower()
