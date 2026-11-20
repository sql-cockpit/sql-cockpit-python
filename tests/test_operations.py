import uuid

import pytest

import sqlcockpit
from conftest import AGENT, API_KEY, BASE, MEMBER, TENANT, TICKET, ok
from sqlcockpit.models import (
    Account,
    Agent,
    Instance,
    InviteSent,
    RemovedMember,
    Team,
    TeamMemberResult,
    Tenant,
    Ticket,
    TicketSummary,
    Usage,
)

MEMBER_DATA = {
    "id": MEMBER,
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "role": "developer",
    "role_label": "Developer",
    "status": "pending_password",
    "joined_at": None,
    "added_at": "2026-11-20T10:00:00Z",
}

TICKET_DATA = {
    "id": TICKET,
    "subject": "Agent offline",
    "status": "open",
    "status_label": "Open",
    "priority": "high",
    "tenant": {"id": TENANT, "name": "Acme"},
    "created_at": "2026-11-20T10:00:00Z",
    "updated_at": "2026-11-20T10:00:00Z",
    "portal_url": "https://portal.sql-cockpit.com/support/x",
    "message": "The Agent stopped reporting.",
    "agent": {"id": AGENT, "name": "sql-01", "hostname": None},
    "team_response": None,
    "replies": [{"from": "sql_cockpit_team", "body": "Looking now.", "created_at": "2026-11-20T11:00:00Z"}],
}


def test_account_get(make_client):
    client = make_client(
        ok(
            {
                "name": "Ada",
                "email": "ada@example.com",
                "email_verified": True,
                "plan": {"name": "Team", "description": None},
                "subscription": {"status": "active", "cycle": "month"},
                "connected_via": {"type": "api_key", "name": "ci", "scopes": ["portal:read"], "expires_at": None},
                "something_new": 1,
            }
        )
    )
    account = client.account.get()
    assert isinstance(account, Account)
    assert account.name == "Ada"
    assert account.plan.name == "Team"
    assert account.subscription.cycle == "month"
    assert account.connected_via.scopes == ["portal:read"]
    assert account.raw["something_new"] == 1
    req = client.recorder.last
    assert req.method == "GET"
    assert str(req.url) == f"{BASE}/account"
    assert req.headers["authorization"] == f"Bearer {API_KEY}"
    assert req.headers["accept"] == "application/json"
    assert req.headers["user-agent"] == f"sqlcockpit-python/{sqlcockpit.__version__}"
    assert req.content == b""


def test_account_usage(make_client):
    client = make_client(
        ok(
            {
                "billing_account": True,
                "plan": "Team",
                "period": {"start": "2026-11-01T00:00:00Z", "end": "2026-12-01T00:00:00Z"},
                "allowances": [{"key": "agents", "label": "Agents", "used": 2, "limit": 5, "at_limit": False}],
            }
        )
    )
    usage = client.account.usage()
    assert isinstance(usage, Usage)
    assert usage.period.start == "2026-11-01T00:00:00Z"
    assert usage.allowances[0].limit == 5
    assert str(client.recorder.last.url) == f"{BASE}/usage"


def test_tenants_list(make_client):
    client = make_client(ok({"tenants": [{"id": TENANT, "name": "Acme", "your_role": "owner", "abilities": ["x"]}]}))
    tenants = client.tenants.list()
    assert isinstance(tenants, list) and isinstance(tenants[0], Tenant)
    assert tenants[0].your_role == "owner"
    assert str(client.recorder.last.url) == f"{BASE}/tenants"


def test_team_list(make_client):
    client = make_client(
        ok(
            {
                "tenant": {"id": TENANT, "name": "Acme"},
                "owner": {"name": "Ada", "email": "ada@example.com"},
                "members": [MEMBER_DATA],
                "you_can_manage": True,
                "assignable_roles": ["admin", "developer"],
                "role_summaries": {"admin": "Everything"},
                "seats": {"used": 2, "limit": None},
            }
        )
    )
    team = client.team.list(TENANT)
    assert isinstance(team, Team)
    assert team.members[0].email == "ada@example.com"
    assert team.seats.limit is None
    assert team.assignable_roles == ["admin", "developer"]
    assert str(client.recorder.last.url) == f"{BASE}/tenants/{TENANT}/members"


def test_team_add(make_client):
    client = make_client(ok({"member": MEMBER_DATA, "message": "Added."}, status=201))
    result = client.team.add(TENANT, name="Ada Lovelace", email="ada@example.com", role="developer")
    assert isinstance(result, TeamMemberResult)
    assert result.member.status == "pending_password"
    req = client.recorder.last
    assert req.method == "POST"
    assert str(req.url) == f"{BASE}/tenants/{TENANT}/members"
    assert req.headers["content-type"] == "application/json"
    assert client.recorder.body() == {"name": "Ada Lovelace", "email": "ada@example.com", "role": "developer"}


def test_team_change_role_sends_confirm(make_client):
    client = make_client(ok({"member": dict(MEMBER_DATA, role="admin"), "message": "Updated."}))
    result = client.team.change_role(TENANT, MEMBER, role="admin")
    assert result.member.role == "admin"
    req = client.recorder.last
    assert req.method == "PATCH"
    assert str(req.url) == f"{BASE}/tenants/{TENANT}/members/{MEMBER}"
    assert client.recorder.body() == {"role": "admin", "confirm": True}


def test_team_remove_sends_confirm(make_client):
    client = make_client(ok({"removed": True, "email": "ada@example.com", "tenant_id": TENANT}))
    result = client.team.remove(TENANT, uuid.UUID(MEMBER))
    assert isinstance(result, RemovedMember) and result.removed is True
    req = client.recorder.last
    assert req.method == "DELETE"
    assert str(req.url) == f"{BASE}/tenants/{TENANT}/members/{MEMBER}"
    assert client.recorder.body() == {"confirm": True}


def test_team_resend_invite(make_client):
    client = make_client(ok({"sent": True, "email": "ada@example.com"}))
    result = client.team.resend_invite(TENANT, MEMBER)
    assert isinstance(result, InviteSent) and result.sent is True
    req = client.recorder.last
    assert req.method == "POST"
    assert str(req.url) == f"{BASE}/tenants/{TENANT}/members/{MEMBER}/resend"
    assert req.content == b""


def test_agents_list(make_client):
    client = make_client(
        ok({"agents": [{"id": AGENT, "status": "active", "latest_command": {"type": "update", "status": "done"}}]})
    )
    agents = client.agents.list()
    assert isinstance(agents[0], Agent)
    assert agents[0].latest_command.type == "update"
    assert str(client.recorder.last.url) == f"{BASE}/agents"

    client.agents.list(tenant_id=TENANT, status="active")
    params = client.recorder.last.url.params
    assert params["tenant_id"] == TENANT and params["status"] == "active"


def test_instances_list(make_client):
    client = make_client(ok({"instances": [{"id": "i", "revision": 3, "applied_revision": None}]}))
    instances = client.instances.list(tenant_id=TENANT)
    assert isinstance(instances[0], Instance) and instances[0].revision == 3
    assert client.recorder.last.url.params["tenant_id"] == TENANT


def test_support_list(make_client):
    client = make_client(ok({"tickets": [TICKET_DATA]}))
    tickets = client.support.list(status="open")
    assert isinstance(tickets[0], TicketSummary)
    assert tickets[0].tenant.name == "Acme"
    assert str(client.recorder.last.url) == f"{BASE}/support-tickets?status=open"


def test_support_get(make_client):
    client = make_client(ok({"ticket": TICKET_DATA}))
    ticket = client.support.get(TICKET)
    assert isinstance(ticket, Ticket)
    assert ticket.agent.name == "sql-01"
    assert ticket.replies[0].from_ == "sql_cockpit_team"
    assert str(client.recorder.last.url) == f"{BASE}/support-tickets/{TICKET}"


def test_support_create(make_client):
    client = make_client(ok({"ticket": TICKET_DATA}, status=201))
    ticket = client.support.create(subject="Agent offline", message="The Agent stopped reporting.")
    assert ticket.id == TICKET
    assert client.recorder.body() == {"subject": "Agent offline", "message": "The Agent stopped reporting."}

    client.support.create(
        subject="Agent offline", message="The Agent stopped reporting.", tenant_id=TENANT, agent_id=AGENT
    )
    req = client.recorder.last
    assert req.method == "POST" and str(req.url) == f"{BASE}/support-tickets"
    assert client.recorder.body() == {
        "subject": "Agent offline",
        "message": "The Agent stopped reporting.",
        "tenant_id": TENANT,
        "agent_id": AGENT,
    }


def test_missing_envelope_key_is_invalid_response(make_client):
    client = make_client(ok({"nothing": []}))
    with pytest.raises(sqlcockpit.SqlCockpitError) as info:
        client.tenants.list()
    assert info.value.code == "invalid_response"


def test_context_manager_closes(make_client):
    client = make_client(ok({"tenants": []}))
    with client as c:
        assert c.tenants.list() == []
    assert client._http.is_closed
