"""Transport-neutral pieces shared by Client and AsyncClient."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, TypeVar, Union
from uuid import UUID

import httpx

from . import models as m
from ._config import (
    API_PATH,
    check_uuid,
    env_or,
    normalize_api_key,
    normalize_max_retries,
    normalize_portal_url,
    normalize_timeout,
)
from ._version import __version__
from .errors import (
    ConnectionError,
    RateLimitError,
    ServerError,
    SqlCockpitError,
    TimeoutError,
    error_for_status,
)

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RETRY_AFTER = 30.0
USER_AGENT = f"sqlcockpit-python/{__version__}"
_SAFE_PATH = re.compile(r"^/[a-z0-9/_-]*$", re.IGNORECASE)

T = TypeVar("T")
Id = Union[str, UUID]


@dataclass(frozen=True)
class Op:
    """One API call: what to send and how to read the answer."""

    method: str
    path: str
    parse: Callable[[Any], Any]
    params: Optional[Dict[str, str]] = None
    body: Optional[Dict[str, Any]] = None

    @property
    def retryable(self) -> bool:
        return self.method == "GET"


# Errors raised while talking to the portal. They are built here and raised by the
# caller outside any ``except`` block, so no httpx exception (which holds the
# request and its Authorization header) is chained onto them.


def redirect_error(status: int) -> SqlCockpitError:
    return SqlCockpitError(
        "The portal answered with a redirect, which the SDK does not follow. Check SQL_COCKPIT_PORTAL_URL.",
        code="unexpected_redirect",
        status=status,
    )


def too_large_error(status: int) -> SqlCockpitError:
    return SqlCockpitError("The portal response was too large.", code="response_too_large", status=status)


def transport_error(exc: httpx.HTTPError) -> SqlCockpitError:
    if isinstance(exc, httpx.TimeoutException):
        return TimeoutError("The SQL Cockpit portal did not answer in time. Try again shortly.", code="timeout")
    return ConnectionError(
        "Could not reach the SQL Cockpit portal. Check SQL_COCKPIT_PORTAL_URL and your connection.",
        code="unreachable",
    )


def declared_too_large(response: httpx.Response) -> bool:
    try:
        return int(response.headers.get("content-length") or 0) > MAX_RESPONSE_BYTES
    except ValueError:
        return False


def parse_retry_after(headers: httpx.Headers) -> Optional[float]:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return max(0.0, seconds)


def retry_delay(error: SqlCockpitError, attempt: int) -> Optional[float]:
    """Seconds to wait before retrying a GET, or None when it should not be retried."""
    if not isinstance(error, (RateLimitError, ServerError)):
        return None
    if error.retry_after is not None:
        return min(error.retry_after, MAX_RETRY_AFTER)
    return min(0.5 * (2**attempt), MAX_RETRY_AFTER)


def read_payload(status: int, headers: httpx.Headers, body: bytes) -> Any:
    """Return ``data`` from a success envelope, or raise the matching error."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        payload = None

    if 200 <= status < 300:
        if isinstance(payload, dict) and payload.get("ok") is True and "data" in payload:
            return payload["data"]
        if payload is None:
            raise SqlCockpitError(
                f"The portal returned an unexpected response (HTTP {status}).",
                code="invalid_response",
                status=status,
            )

    error = payload.get("error") if isinstance(payload, dict) else None
    error = error if isinstance(error, dict) else {}
    code = error.get("code") if isinstance(error.get("code"), str) else "request_failed"
    message = (
        error.get("message") if isinstance(error.get("message"), str) else f"The portal request failed (HTTP {status})."
    )
    fields = error.get("fields") if isinstance(error.get("fields"), dict) else None
    raise error_for_status(status, code, message, fields, parse_retry_after(headers))


def _invalid(what: str) -> SqlCockpitError:
    return SqlCockpitError(f"The portal response had no {what}.", code="invalid_response")


def _model(cls: Callable[[Dict[str, Any]], T], data: Any, what: str) -> T:
    if not isinstance(data, dict):
        raise _invalid(what)
    return cls(data)


def _field(data: Any, key: str) -> Any:
    if not isinstance(data, dict) or key not in data:
        raise _invalid(key)
    return data[key]


def _models(cls: Callable[[Dict[str, Any]], T], key: str) -> Callable[[Any], List[T]]:
    def parse(data: Any) -> List[T]:
        items = _field(data, key)
        if not isinstance(items, list):
            raise _invalid(key)
        return [_model(cls, item, key) for item in items]

    return parse


def _query(**values: Optional[str]) -> Optional[Dict[str, str]]:
    query = {k: v for k, v in values.items() if v is not None and v != ""}
    return query or None


def _members_path(tenant_id: Id) -> str:
    return f"/tenants/{check_uuid(tenant_id, 'tenant_id')}/members"


def _member_path(tenant_id: Id, membership_id: Id) -> str:
    return f"{_members_path(tenant_id)}/{check_uuid(membership_id, 'membership_id')}"


def _optional_uuid(value: Optional[Id], name: str) -> Optional[str]:
    return None if value is None else check_uuid(value, name)


# Operations, one per OpenAPI operationId ---------------------------------------


def get_account() -> Op:
    return Op("GET", "/account", lambda d: _model(m.Account.from_dict, d, "account"))


def get_usage() -> Op:
    return Op("GET", "/usage", lambda d: _model(m.Usage.from_dict, d, "usage"))


def list_tenants() -> Op:
    return Op("GET", "/tenants", _models(m.Tenant.from_dict, "tenants"))


def list_team_members(tenant_id: Id) -> Op:
    return Op("GET", _members_path(tenant_id), lambda d: _model(m.Team.from_dict, d, "team"))


def add_team_member(tenant_id: Id, name: str, email: str, role: str) -> Op:
    return Op(
        "POST",
        _members_path(tenant_id),
        lambda d: _model(m.TeamMemberResult.from_dict, d, "member"),
        body={"name": name, "email": email, "role": role},
    )


def change_team_member_role(tenant_id: Id, membership_id: Id, role: str) -> Op:
    return Op(
        "PATCH",
        _member_path(tenant_id, membership_id),
        lambda d: _model(m.TeamMemberResult.from_dict, d, "member"),
        body={"role": role, "confirm": True},
    )


def remove_team_member(tenant_id: Id, membership_id: Id) -> Op:
    return Op(
        "DELETE",
        _member_path(tenant_id, membership_id),
        lambda d: _model(m.RemovedMember.from_dict, d, "result"),
        body={"confirm": True},
    )


def resend_team_member_invite(tenant_id: Id, membership_id: Id) -> Op:
    return Op(
        "POST",
        _member_path(tenant_id, membership_id) + "/resend",
        lambda d: _model(m.InviteSent.from_dict, d, "result"),
    )


def list_agents(tenant_id: Optional[Id] = None, status: Optional[str] = None) -> Op:
    return Op(
        "GET",
        "/agents",
        _models(m.Agent.from_dict, "agents"),
        params=_query(tenant_id=_optional_uuid(tenant_id, "tenant_id"), status=status),
    )


def list_instances(tenant_id: Optional[Id] = None) -> Op:
    return Op(
        "GET",
        "/instances",
        _models(m.Instance.from_dict, "instances"),
        params=_query(tenant_id=_optional_uuid(tenant_id, "tenant_id")),
    )


def list_support_tickets(status: Optional[str] = None) -> Op:
    return Op("GET", "/support-tickets", _models(m.TicketSummary.from_dict, "tickets"), params=_query(status=status))


def get_support_ticket(ticket_id: Id) -> Op:
    return Op(
        "GET",
        f"/support-tickets/{check_uuid(ticket_id, 'ticket_id')}",
        lambda d: _model(m.Ticket.from_dict, _field(d, "ticket"), "ticket"),
    )


def create_support_ticket(
    subject: str, message: str, tenant_id: Optional[Id] = None, agent_id: Optional[Id] = None
) -> Op:
    body: Dict[str, Any] = {"subject": subject, "message": message}
    if tenant_id is not None:
        body["tenant_id"] = check_uuid(tenant_id, "tenant_id")
    if agent_id is not None:
        body["agent_id"] = check_uuid(agent_id, "agent_id")
    return Op(
        "POST",
        "/support-tickets",
        lambda d: _model(m.Ticket.from_dict, _field(d, "ticket"), "ticket"),
        body=body,
    )


# Shared client state -------------------------------------------------------------


class BaseClient:
    """Configuration and request building shared by Client and AsyncClient."""

    def __init__(
        self,
        api_key: Optional[str],
        portal_url: Optional[str],
        timeout: Optional[float],
        max_retries: int,
        env: Optional[Mapping[str, str]],
    ) -> None:
        import os

        environ = os.environ if env is None else env
        # Name-mangled and never printed: see __repr__.
        self.__api_key = normalize_api_key(env_or(api_key, "SQL_COCKPIT_API_KEY", environ))
        self.portal_url: str = normalize_portal_url(env_or(portal_url, "SQL_COCKPIT_PORTAL_URL", environ))
        self.base_url: str = self.portal_url + API_PATH
        self.timeout: float = normalize_timeout(timeout, environ)
        self.max_retries: int = normalize_max_retries(max_retries)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(portal_url={self.portal_url!r})"

    def __getstate__(self) -> Any:
        raise TypeError(f"{type(self).__name__} cannot be pickled.")

    def _build_request(self, http: Union[httpx.Client, httpx.AsyncClient], op: Op) -> httpx.Request:
        if not _SAFE_PATH.match(op.path):
            raise SqlCockpitError("Refusing to call an unexpected portal path.", code="invalid_path")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.__api_key}",
            "User-Agent": USER_AGENT,
        }
        if op.body is not None:
            headers["Content-Type"] = "application/json"
            content: Optional[bytes] = json.dumps(op.body).encode("utf-8")
        else:
            content = None
        return http.build_request(
            op.method, self.base_url + op.path, params=op.params, headers=headers, content=content
        )
