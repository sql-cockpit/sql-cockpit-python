from __future__ import annotations

import asyncio
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


class AsyncClient(core.BaseClient):
    """Asynchronous client for the SQL Cockpit Portal API. Same options as ``Client``."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        portal_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 2,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(api_key, portal_url, timeout, max_retries, env)
        self._http = httpx.AsyncClient(transport=transport, timeout=self.timeout, follow_redirects=False)
        self._sleep = asyncio.sleep
        self.account = AsyncAccountResource(self)
        self.tenants = AsyncTenantsResource(self)
        self.team = AsyncTeamResource(self)
        self.agents = AsyncAgentsResource(self)
        self.instances = AsyncInstancesResource(self)
        self.support = AsyncSupportResource(self)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.aclose()

    async def _call(self, op: Op) -> Any:
        attempt = 0
        while True:
            try:
                data = await self._send(op)
            except SqlCockpitError as error:
                delay = core.retry_delay(error, attempt) if op.retryable and attempt < self.max_retries else None
                if delay is None:
                    raise
                attempt += 1
                await self._sleep(delay)
                continue
            return op.parse(data)

    async def _send(self, op: Op) -> Any:
        request = self._build_request(self._http, op)
        failure: Optional[SqlCockpitError] = None
        try:
            response = await self._http.send(request, stream=True, follow_redirects=False)
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
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > core.MAX_RESPONSE_BYTES:
                        failure = core.too_large_error(response.status_code)
                        break
            except httpx.HTTPError as exc:
                failure = core.transport_error(exc)
            if failure is not None:
                raise failure
        finally:
            await response.aclose()
        return core.read_payload(response.status_code, response.headers, bytes(body))


class _AsyncResource:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client


class AsyncAccountResource(_AsyncResource):
    async def get(self) -> Account:
        """GET /account"""
        return await self._client._call(core.get_account())

    async def usage(self) -> Usage:
        """GET /usage"""
        return await self._client._call(core.get_usage())


class AsyncTenantsResource(_AsyncResource):
    async def list(self) -> List[Tenant]:
        """GET /tenants"""
        return await self._client._call(core.list_tenants())


class AsyncTeamResource(_AsyncResource):
    async def list(self, tenant_id: Id) -> Team:
        """GET /tenants/{tenant_id}/members"""
        return await self._client._call(core.list_team_members(tenant_id))

    async def add(self, tenant_id: Id, *, name: str, email: str, role: AssignableRole) -> TeamMemberResult:
        """POST /tenants/{tenant_id}/members"""
        return await self._client._call(core.add_team_member(tenant_id, name, email, role))

    async def change_role(self, tenant_id: Id, membership_id: Id, *, role: AssignableRole) -> TeamMemberResult:
        """PATCH /tenants/{tenant_id}/members/{membership_id} (sends confirm: true)"""
        return await self._client._call(core.change_team_member_role(tenant_id, membership_id, role))

    async def remove(self, tenant_id: Id, membership_id: Id) -> RemovedMember:
        """DELETE /tenants/{tenant_id}/members/{membership_id} (sends confirm: true)"""
        return await self._client._call(core.remove_team_member(tenant_id, membership_id))

    async def resend_invite(self, tenant_id: Id, membership_id: Id) -> InviteSent:
        """POST /tenants/{tenant_id}/members/{membership_id}/resend"""
        return await self._client._call(core.resend_team_member_invite(tenant_id, membership_id))


class AsyncAgentsResource(_AsyncResource):
    async def list(self, tenant_id: Optional[Id] = None, status: Optional[AgentStatus] = None) -> List[Agent]:
        """GET /agents"""
        return await self._client._call(core.list_agents(tenant_id, status))


class AsyncInstancesResource(_AsyncResource):
    async def list(self, tenant_id: Optional[Id] = None) -> List[Instance]:
        """GET /instances"""
        return await self._client._call(core.list_instances(tenant_id))


class AsyncSupportResource(_AsyncResource):
    async def list(self, status: Optional[TicketStatus] = None) -> List[TicketSummary]:
        """GET /support-tickets"""
        return await self._client._call(core.list_support_tickets(status))

    async def get(self, ticket_id: Id) -> Ticket:
        """GET /support-tickets/{ticket_id}"""
        return await self._client._call(core.get_support_ticket(ticket_id))

    async def create(
        self,
        *,
        subject: str,
        message: str,
        tenant_id: Optional[Id] = None,
        agent_id: Optional[Id] = None,
    ) -> Ticket:
        """POST /support-tickets"""
        return await self._client._call(core.create_support_ticket(subject, message, tenant_id, agent_id))
