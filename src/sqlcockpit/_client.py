from __future__ import annotations

import time
from types import TracebackType
from typing import Any, List, Mapping, Optional, Type

import httpx

from . import _core as core
from ._core import Id, Op
from .errors import SqlCockpitError
from .models import (
    Account,
    Agent,
    AgentStatus,
    AssignableRole,
    Instance,
    InviteSent,
    RemovedMember,
    Team,
    TeamMemberResult,
    Tenant,
    Ticket,
    TicketStatus,
    TicketSummary,
    Usage,
)


class Client(core.BaseClient):
    """Synchronous client for the SQL Cockpit Portal API.

    Reads ``SQL_COCKPIT_API_KEY``, ``SQL_COCKPIT_PORTAL_URL`` and
    ``SQL_COCKPIT_TIMEOUT_MS`` from the environment when the matching argument is
    not given. ``timeout`` is in seconds. ``max_retries`` (0-2) applies to GET
    requests that end in 429 or 5xx; writes are never retried.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        portal_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 2,
        transport: Optional[httpx.BaseTransport] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(api_key, portal_url, timeout, max_retries, env)
        self._http = httpx.Client(transport=transport, timeout=self.timeout, follow_redirects=False)
        self._sleep = time.sleep
        self.account = AccountResource(self)
        self.tenants = TenantsResource(self)
        self.team = TeamResource(self)
        self.agents = AgentsResource(self)
        self.instances = InstancesResource(self)
        self.support = SupportResource(self)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def _call(self, op: Op) -> Any:
        attempt = 0
        while True:
            try:
                data = self._send(op)
            except SqlCockpitError as error:
                delay = core.retry_delay(error, attempt) if op.retryable and attempt < self.max_retries else None
                if delay is None:
                    raise
                attempt += 1
                self._sleep(delay)
                continue
            return op.parse(data)

    def _send(self, op: Op) -> Any:
        request = self._build_request(self._http, op)
        failure: Optional[SqlCockpitError] = None
        try:
            response = self._http.send(request, stream=True, follow_redirects=False)
        except httpx.HTTPError as exc:
            failure = core.transport_error(exc)
        if failure is not None:
            raise failure

        try:
            if 300 <= response.status_code < 400:
                raise core.redirect_error(response.status_code)
            if core.declared_too_large(response):
                raise core.too_large_error(response.status_code)
            body = bytearray()
            try:
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > core.MAX_RESPONSE_BYTES:
                        failure = core.too_large_error(response.status_code)
                        break
            except httpx.HTTPError as exc:
                failure = core.transport_error(exc)
            if failure is not None:
                raise failure
        finally:
            response.close()
        return core.read_payload(response.status_code, response.headers, bytes(body))


class _Resource:
    def __init__(self, client: Client) -> None:
        self._client = client


class AccountResource(_Resource):
    def get(self) -> Account:
        """GET /account: your name, email, plan, subscription and the credential in use."""
        return self._client._call(core.get_account())

    def usage(self) -> Usage:
        """GET /usage: what your plan includes this billing period and how much is used."""
        return self._client._call(core.get_usage())


class TenantsResource(_Resource):
    def list(self) -> List[Tenant]:
        """GET /tenants: every tenant you own or belong to."""
        return self._client._call(core.list_tenants())


class TeamResource(_Resource):
    def list(self, tenant_id: Id) -> Team:
        """GET /tenants/{tenant_id}/members: the tenant's owner and members."""
        return self._client._call(core.list_team_members(tenant_id))

    def add(self, tenant_id: Id, *, name: str, email: str, role: AssignableRole) -> TeamMemberResult:
        """POST /tenants/{tenant_id}/members: add someone to the tenant."""
        return self._client._call(core.add_team_member(tenant_id, name, email, role))

    def change_role(self, tenant_id: Id, membership_id: Id, *, role: AssignableRole) -> TeamMemberResult:
        """PATCH /tenants/{tenant_id}/members/{membership_id}: give a member another role (sends confirm: true)."""
        return self._client._call(core.change_team_member_role(tenant_id, membership_id, role))

    def remove(self, tenant_id: Id, membership_id: Id) -> RemovedMember:
        """DELETE /tenants/{tenant_id}/members/{membership_id}: remove a member (sends confirm: true)."""
        return self._client._call(core.remove_team_member(tenant_id, membership_id))

    def resend_invite(self, tenant_id: Id, membership_id: Id) -> InviteSent:
        """POST /tenants/{tenant_id}/members/{membership_id}/resend: send the set-password email again."""
        return self._client._call(core.resend_team_member_invite(tenant_id, membership_id))


class AgentsResource(_Resource):
    def list(self, tenant_id: Optional[Id] = None, status: Optional[AgentStatus] = None) -> List[Agent]:
        """GET /agents: the Agents paired with the tenants you can reach."""
        return self._client._call(core.list_agents(tenant_id, status))


class InstancesResource(_Resource):
    def list(self, tenant_id: Optional[Id] = None) -> List[Instance]:
        """GET /instances: the SQL Cockpit Server instances of the tenants you can reach."""
        return self._client._call(core.list_instances(tenant_id))


class SupportResource(_Resource):
    def list(self, status: Optional[TicketStatus] = None) -> List[TicketSummary]:
        """GET /support-tickets: the tickets you have opened, newest first."""
        return self._client._call(core.list_support_tickets(status))

    def get(self, ticket_id: Id) -> Ticket:
        """GET /support-tickets/{ticket_id}: a ticket with its message and replies."""
        return self._client._call(core.get_support_ticket(ticket_id))

    def create(
        self,
        *,
        subject: str,
        message: str,
        tenant_id: Optional[Id] = None,
        agent_id: Optional[Id] = None,
    ) -> Ticket:
        """POST /support-tickets: open a ticket. Naming an Agent raises it as high priority."""
        return self._client._call(core.create_support_ticket(subject, message, tenant_id, agent_id))
