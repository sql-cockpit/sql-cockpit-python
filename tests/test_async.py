import asyncio
import json

import httpx
import pytest

import sqlcockpit
from conftest import AGENT, API_KEY, BASE, MEMBER, TENANT, TICKET, Recorder, fail, ok


def make(*responses, **kwargs):
    rec = Recorder(*responses)
    client = sqlcockpit.AsyncClient(API_KEY, transport=httpx.MockTransport(rec), env={}, **kwargs)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    client._sleep = fake_sleep
    return client, rec, sleeps


def run(coro):
    return asyncio.run(coro)


def test_every_operation():
    responses = [
        ok({"name": "Ada"}),
        ok({"allowances": []}),
        ok({"tenants": [{"id": TENANT}]}),
        ok({"members": []}),
        ok({"member": {"id": MEMBER}, "message": "Added."}, status=201),
        ok({"member": {"id": MEMBER, "role": "admin"}}),
        ok({"removed": True}),
        ok({"sent": True}),
        ok({"agents": [{"id": AGENT}]}),
        ok({"instances": []}),
        ok({"tickets": []}),
        ok({"ticket": {"id": TICKET}}),
        ok({"ticket": {"id": TICKET}}, status=201),
    ]
    client, rec, _ = make(*responses)

    async def main():
        async with client as c:
            assert (await c.account.get()).name == "Ada"
            assert (await c.account.usage()).allowances == []
            assert (await c.tenants.list())[0].id == TENANT
            assert (await c.team.list(TENANT)).members == []
            assert (await c.team.add(TENANT, name="Ada", email="a@example.com", role="admin")).message == "Added."
            assert (await c.team.change_role(TENANT, MEMBER, role="admin")).member.role == "admin"
            assert (await c.team.remove(TENANT, MEMBER)).removed is True
            assert (await c.team.resend_invite(TENANT, MEMBER)).sent is True
            assert (await c.agents.list(tenant_id=TENANT, status="active"))[0].id == AGENT
            assert await c.instances.list() == []
            assert await c.support.list(status="open") == []
            assert (await c.support.get(TICKET)).id == TICKET
            assert (await c.support.create(subject="Help me", message="Something broke.")).id == TICKET
        assert client._http.is_closed

    run(main())
    calls = [(r.method, str(r.url).replace(BASE, "")) for r in rec.requests]
    assert calls == [
        ("GET", "/account"),
        ("GET", "/usage"),
        ("GET", "/tenants"),
        ("GET", f"/tenants/{TENANT}/members"),
        ("POST", f"/tenants/{TENANT}/members"),
        ("PATCH", f"/tenants/{TENANT}/members/{MEMBER}"),
        ("DELETE", f"/tenants/{TENANT}/members/{MEMBER}"),
        ("POST", f"/tenants/{TENANT}/members/{MEMBER}/resend"),
        ("GET", f"/agents?tenant_id={TENANT}&status=active"),
        ("GET", "/instances"),
        ("GET", "/support-tickets?status=open"),
        ("GET", f"/support-tickets/{TICKET}"),
        ("POST", "/support-tickets"),
    ]
    assert json.loads(rec.requests[5].content) == {"role": "admin", "confirm": True}
    assert json.loads(rec.requests[6].content) == {"confirm": True}
    assert all(r.headers["authorization"] == f"Bearer {API_KEY}" for r in rec.requests)


def test_async_retry_and_errors():
    client, rec, sleeps = make(fail(429, "rate_limited", headers={"Retry-After": "2"}), ok({"name": "Ada"}))

    async def main():
        async with client as c:
            return await c.account.get()

    assert run(main()).name == "Ada"
    assert sleeps == [2]

    client, rec, sleeps = make(fail(500, "server_error"))

    async def write():
        async with client as c:
            await c.support.create(subject="Help me", message="Something broke.")

    with pytest.raises(sqlcockpit.ServerError):
        run(write())
    assert len(rec.requests) == 1


def test_async_redirect_and_size_cap():
    client, _, _ = make(httpx.Response(302, headers={"Location": "https://evil.example"}))

    async def main():
        async with client as c:
            await c.account.get()

    with pytest.raises(sqlcockpit.SqlCockpitError) as info:
        run(main())
    assert info.value.code == "unexpected_redirect"

    async def chunks():
        for _ in range(3):
            yield b"x" * (1024 * 1024)

    client, _, _ = make(lambda request: httpx.Response(200, content=chunks()))
    with pytest.raises(sqlcockpit.SqlCockpitError) as info:
        run(main())
    assert info.value.code == "response_too_large"


def test_async_timeout():
    client, _, _ = make(httpx.ConnectTimeout("slow"))

    async def main():
        async with client as c:
            await c.tenants.list()

    with pytest.raises(sqlcockpit.TimeoutError):
        run(main())
