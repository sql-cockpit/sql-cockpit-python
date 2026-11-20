"""Typed models for the SQL Cockpit Portal API (v1).

Each model mirrors a schema in the OpenAPI document. Every field is optional so a
response that leaves something out still parses. Timestamps are ISO 8601 strings,
as the API sends them. ``raw`` holds the dict the model was built from, including
any field this version of the SDK does not know yet.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Literal, Optional, Union, get_args, get_origin, get_type_hints

__all__ = [
    "AgentStatus",
    "AssignableRole",
    "TicketStatus",
    "Plan",
    "Subscription",
    "ConnectedVia",
    "Account",
    "Allowance",
    "Period",
    "Usage",
    "Tenant",
    "Member",
    "TeamTenant",
    "TeamOwner",
    "Seats",
    "Team",
    "TeamMemberResult",
    "RemovedMember",
    "InviteSent",
    "LatestCommand",
    "Agent",
    "Instance",
    "TicketTenant",
    "TicketSummary",
    "TicketAgent",
    "TicketReply",
    "Ticket",
]

AssignableRole = Literal["admin", "developer", "operator", "read-only"]
AgentStatus = Literal["pending", "active", "revoked", "suspended"]
TicketStatus = Literal["open", "pending", "sent", "waiting_on_customer", "resolved", "closed"]

_HINTS: Dict[type, Dict[str, Any]] = {}


def _convert(hint: Any, value: Any) -> Any:
    origin = get_origin(hint)
    if origin is Union:
        if value is None:
            return None
        options = [a for a in get_args(hint) if a is not type(None)]
        return _convert(options[0], value) if len(options) == 1 else value
    if origin in (list, List):
        if isinstance(value, list):
            (item,) = get_args(hint) or (Any,)
            return [_convert(item, v) for v in value]
        return value
    if isinstance(hint, type) and issubclass(hint, _Model) and isinstance(value, dict):
        return hint.from_dict(value)
    return value


class _Model:
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):  # type: ignore[no-untyped-def]
        """Build the model from a response dict. Unknown keys are kept in ``raw``."""
        if not isinstance(data, dict):
            raise TypeError(f"{cls.__name__}.from_dict expects a dict")
        hints = _HINTS.get(cls)
        if hints is None:
            hints = _HINTS[cls] = get_type_hints(cls)
        values: Dict[str, Any] = {}
        for f in dataclasses.fields(cls):  # type: ignore[arg-type]
            if f.name == "raw":
                continue
            key = f.metadata.get("key", f.name)
            if key in data:
                values[f.name] = _convert(hints[f.name], data[key])
        return cls(**values, raw=dict(data))


def _raw() -> Any:
    return dataclasses.field(default_factory=dict, repr=False, compare=False)


def _list() -> Any:
    return dataclasses.field(default_factory=list)


_dataclass = dataclasses.dataclass(frozen=True)


# Account ----------------------------------------------------------------------


@_dataclass
class Plan(_Model):
    name: Optional[str] = None
    description: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Subscription(_Model):
    status: Optional[str] = None
    cycle: Optional[str] = None
    started_at: Optional[str] = None
    trial_ends_at: Optional[str] = None
    ends_at: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class ConnectedVia(_Model):
    type: Optional[str] = None
    name: Optional[str] = None
    scopes: List[str] = _list()
    expires_at: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Account(_Model):
    name: Optional[str] = None
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    billing_account: Optional[bool] = None
    team_member: Optional[bool] = None
    plan: Optional[Plan] = None
    subscription: Optional[Subscription] = None
    connected_via: Optional[ConnectedVia] = None
    api_key_name: Optional[str] = None
    portal_url: Optional[str] = None
    billing_note: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Allowance(_Model):
    key: Optional[str] = None
    label: Optional[str] = None
    metered: Optional[bool] = None
    used: Optional[int] = None
    limit: Optional[int] = None
    unlimited: Optional[bool] = None
    included: Optional[bool] = None
    remaining: Optional[int] = None
    at_limit: Optional[bool] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Period(_Model):
    start: Optional[str] = None
    end: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Usage(_Model):
    billing_account: Optional[bool] = None
    team_member_only: Optional[bool] = None
    message: Optional[str] = None
    plan: Optional[str] = None
    period: Optional[Period] = None
    allowances: List[Allowance] = _list()
    raw: Dict[str, Any] = _raw()


# Tenants and team ---------------------------------------------------------------


@_dataclass
class Tenant(_Model):
    id: Optional[str] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    subdomain: Optional[str] = None
    domain: Optional[str] = None
    status: Optional[str] = None
    your_role: Optional[str] = None
    is_owner: Optional[bool] = None
    abilities: List[str] = _list()
    agents_count: Optional[int] = None
    created_at: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Member(_Model):
    id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    role_label: Optional[str] = None
    status: Optional[str] = None
    joined_at: Optional[str] = None
    added_at: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class TeamTenant(_Model):
    id: Optional[str] = None
    name: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class TeamOwner(_Model):
    name: Optional[str] = None
    email: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Seats(_Model):
    used: Optional[int] = None
    limit: Optional[int] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Team(_Model):
    tenant: Optional[TeamTenant] = None
    owner: Optional[TeamOwner] = None
    members: List[Member] = _list()
    you_can_manage: Optional[bool] = None
    assignable_roles: Optional[List[str]] = None
    role_summaries: Dict[str, str] = dataclasses.field(default_factory=dict)
    seats: Optional[Seats] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class TeamMemberResult(_Model):
    """Returned by ``team.add`` and ``team.change_role``."""

    member: Optional[Member] = None
    message: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class RemovedMember(_Model):
    """Returned by ``team.remove``."""

    removed: Optional[bool] = None
    email: Optional[str] = None
    tenant_id: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class InviteSent(_Model):
    """Returned by ``team.resend_invite``."""

    sent: Optional[bool] = None
    email: Optional[str] = None
    raw: Dict[str, Any] = _raw()


# Agents and instances -----------------------------------------------------------


@_dataclass
class LatestCommand(_Model):
    type: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Agent(_Model):
    id: Optional[str] = None
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None
    name: Optional[str] = None
    hostname: Optional[str] = None
    status: Optional[str] = None
    connection: Optional[str] = None
    update_channel: Optional[str] = None
    desired_role: Optional[str] = None
    last_seen_at: Optional[str] = None
    registered_at: Optional[str] = None
    revoked_at: Optional[str] = None
    latest_command: Optional[LatestCommand] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Instance(_Model):
    id: Optional[str] = None
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None
    hostname: Optional[str] = None
    public_url: Optional[str] = None
    hosting_mode: Optional[str] = None
    status: Optional[str] = None
    revision: Optional[int] = None
    applied_revision: Optional[int] = None
    last_seen_at: Optional[str] = None
    created_at: Optional[str] = None
    raw: Dict[str, Any] = _raw()


# Support tickets -----------------------------------------------------------------


@_dataclass
class TicketTenant(_Model):
    id: Optional[str] = None
    name: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class TicketSummary(_Model):
    id: Optional[str] = None
    subject: Optional[str] = None
    status: Optional[str] = None
    status_label: Optional[str] = None
    priority: Optional[str] = None
    tenant: Optional[TicketTenant] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    portal_url: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class TicketAgent(_Model):
    id: Optional[str] = None
    name: Optional[str] = None
    hostname: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class TicketReply(_Model):
    from_: Optional[str] = dataclasses.field(default=None, metadata={"key": "from"})
    """Who wrote the reply: ``"you"`` or ``"sql_cockpit_team"`` (the API's ``from`` field)."""
    body: Optional[str] = None
    created_at: Optional[str] = None
    raw: Dict[str, Any] = _raw()


@_dataclass
class Ticket(TicketSummary):
    message: Optional[str] = None
    agent: Optional[TicketAgent] = None
    team_response: Optional[str] = None
    responded_at: Optional[str] = None
    resolved_at: Optional[str] = None
    closed_at: Optional[str] = None
    replies: List[TicketReply] = _list()
