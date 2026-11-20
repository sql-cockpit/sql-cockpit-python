import pickle

import httpx
import pytest

import sqlcockpit
from conftest import API_KEY, MEMBER, TENANT, fail, ok
from sqlcockpit import ConfigurationError, SqlCockpitError
from sqlcockpit._core import MAX_RESPONSE_BYTES

# Redirects ----------------------------------------------------------------------


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirect_is_refused(make_client, status):
    client = make_client(httpx.Response(status, headers={"Location": "https://evil.example/steal"}))
    with pytest.raises(SqlCockpitError) as info:
        client.account.get()
    assert info.value.code == "unexpected_redirect"
    assert info.value.status == status
    assert len(client.recorder.requests) == 1
    assert client.recorder.last.url.host == "portal.sql-cockpit.com"


# Response size cap ----------------------------------------------------------------


def test_declared_oversize_response_is_refused(make_client):
    client = make_client(httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(SqlCockpitError) as info:
        client.account.get()
    assert info.value.code == "response_too_large"


def test_streamed_oversize_response_is_refused(make_client):
    def chunks():
        for _ in range(3):
            yield b"x" * (1024 * 1024)

    client = make_client(lambda request: httpx.Response(200, content=chunks()))
    with pytest.raises(SqlCockpitError) as info:
        client.account.get()
    assert info.value.code == "response_too_large"


def test_response_at_cap_is_accepted(make_client):
    body = b'{"ok": true, "data": {"name": "Ada"}}'
    body = body + b" " * (MAX_RESPONSE_BYTES - len(body))
    client = make_client(httpx.Response(200, content=body))
    assert client.account.get().name == "Ada"


# Ids -------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "abc", "../account", f"{TENANT}/../x", f"{TENANT}?x=1", 123, None])
def test_path_ids_must_be_uuids(make_client, bad):
    client = make_client(ok({}))
    with pytest.raises(ValueError):
        client.team.list(bad)
    with pytest.raises(ValueError):
        client.team.remove(TENANT, bad)
    with pytest.raises(ValueError):
        client.support.get(bad)
    assert client.recorder.requests == []


def test_query_and_body_ids_must_be_uuids(make_client):
    client = make_client(ok({}))
    with pytest.raises(ValueError):
        client.agents.list(tenant_id="nope")
    with pytest.raises(ValueError):
        client.instances.list(tenant_id="nope")
    with pytest.raises(ValueError):
        client.support.create(subject="Help me", message="Something broke.", agent_id="nope")
    assert client.recorder.requests == []


def test_uppercase_uuid_is_normalised(make_client):
    client = make_client(ok({"sent": True}))
    client.team.resend_invite(TENANT.upper(), MEMBER.upper())
    assert TENANT in str(client.recorder.last.url)


# Portal URL -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, base",
    [
        (None, "https://portal.sql-cockpit.com/api/portal/v1"),
        ("https://portal.example.com/", "https://portal.example.com/api/portal/v1"),
        ("http://localhost:8000", "http://localhost:8000/api/portal/v1"),
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000/api/portal/v1"),
        ("http://[::1]:8000", "http://[::1]:8000/api/portal/v1"),
    ],
)
def test_portal_url_accepted(url, base):
    with sqlcockpit.Client(API_KEY, portal_url=url, env={}) as client:
        assert client.base_url == base


@pytest.mark.parametrize(
    "url",
    [
        "http://portal.sql-cockpit.com",
        "http://localhost.evil.com",
        "ftp://portal.sql-cockpit.com",
        "https://user:pass@portal.sql-cockpit.com",
        "https://portal.sql-cockpit.com?x=1",
        "https://portal.sql-cockpit.com#frag",
        "not a url",
        "https://portal.sql-cockpit.com:99999",
    ],
)
def test_portal_url_refused(url):
    with pytest.raises(ConfigurationError):
        sqlcockpit.Client(API_KEY, portal_url=url, env={})


# Configuration --------------------------------------------------------------------


def test_config_from_env():
    env = {
        "SQL_COCKPIT_API_KEY": API_KEY,
        "SQL_COCKPIT_PORTAL_URL": "http://localhost:8000",
        "SQL_COCKPIT_TIMEOUT_MS": "5000",
    }
    with sqlcockpit.Client(env=env) as client:
        assert client.portal_url == "http://localhost:8000"
        assert client.timeout == 5.0


def test_args_override_env():
    env = {"SQL_COCKPIT_API_KEY": "x" * 30, "SQL_COCKPIT_PORTAL_URL": "http://localhost:8000"}
    with sqlcockpit.Client(API_KEY, portal_url="https://p.example.com", timeout=7, env=env) as client:
        assert client.portal_url == "https://p.example.com"
        assert client.timeout == 7.0


def test_reads_os_environ(monkeypatch):
    monkeypatch.setenv("SQL_COCKPIT_API_KEY", API_KEY)
    monkeypatch.delenv("SQL_COCKPIT_PORTAL_URL", raising=False)
    monkeypatch.delenv("SQL_COCKPIT_TIMEOUT_MS", raising=False)
    with sqlcockpit.Client() as client:
        assert client.portal_url == "https://portal.sql-cockpit.com"
        assert client.timeout == 20.0


@pytest.mark.parametrize("key", [None, "", "   ", "short", "has a space in it 1234567890", "x" * 201])
def test_api_key_required_and_checked(key):
    with pytest.raises(ConfigurationError) as info:
        sqlcockpit.Client(key, env={})
    if key and key.strip():
        assert key not in str(info.value)


@pytest.mark.parametrize("timeout", [0, 0.5, 121, "10", True])
def test_timeout_range(timeout):
    with pytest.raises(ConfigurationError):
        sqlcockpit.Client(API_KEY, timeout=timeout, env={})


@pytest.mark.parametrize("value", ["abc", "500", "999999"])
def test_timeout_env_range(value):
    with pytest.raises(ConfigurationError):
        sqlcockpit.Client(API_KEY, env={"SQL_COCKPIT_TIMEOUT_MS": value})


@pytest.mark.parametrize("retries", [-1, 3, True, 1.5])
def test_max_retries_range(retries):
    with pytest.raises(ConfigurationError):
        sqlcockpit.Client(API_KEY, max_retries=retries, env={})


# Key never leaks ---------------------------------------------------------------------


def test_key_not_in_repr_or_str_or_vars():
    for cls in (sqlcockpit.Client, sqlcockpit.AsyncClient):
        client = cls(API_KEY, env={})
        assert API_KEY not in repr(client)
        assert API_KEY not in str(client)
        assert API_KEY not in repr(client.account)
        assert all(API_KEY not in repr(v) for k, v in vars(client).items() if not k.startswith("_BaseClient"))
        with pytest.raises(TypeError):
            pickle.dumps(client)


def test_key_not_in_error(make_client):
    client = make_client(fail(401, "unauthenticated", "The API key is not valid."), max_retries=0)
    with pytest.raises(sqlcockpit.AuthenticationError) as info:
        client.account.get()
    assert API_KEY not in repr(info.value)
    assert API_KEY not in str(info.value)
    assert API_KEY not in repr(vars(info.value))
