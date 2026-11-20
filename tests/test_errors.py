import httpx
import pytest

import sqlcockpit
from conftest import API_KEY, TENANT, fail, ok
from sqlcockpit import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    SqlCockpitError,
    ValidationError,
)


@pytest.mark.parametrize(
    "status, code, cls",
    [
        (401, "unauthenticated", AuthenticationError),
        (403, "forbidden", PermissionDeniedError),
        (404, "not_found", NotFoundError),
        (422, "validation_failed", ValidationError),
        (429, "rate_limited", RateLimitError),
        (500, "server_error", ServerError),
        (503, "server_error", ServerError),
        (400, "bad_request", SqlCockpitError),
        (405, "method_not_allowed", SqlCockpitError),
    ],
)
def test_status_maps_to_exception(make_client, status, code, cls):
    client = make_client(fail(status, code, "It went wrong."), max_retries=0)
    with pytest.raises(cls) as info:
        client.account.get()
    err = info.value
    assert type(err) is cls
    assert isinstance(err, SqlCockpitError)
    assert (err.status, err.code, err.message) == (status, code, "It went wrong.")
    assert str(err) == "It went wrong."


def test_validation_fields(make_client):
    client = make_client(fail(422, "validation_failed", "Check the fields.", fields={"email": ["Taken."]}))
    with pytest.raises(ValidationError) as info:
        client.team.add(TENANT, name="Ada", email="ada@example.com", role="admin")
    assert info.value.fields == {"email": ["Taken."]}


def test_rate_limit_retry_after(make_client):
    client = make_client(fail(429, "rate_limited", headers={"Retry-After": "12"}))
    with pytest.raises(RateLimitError) as info:
        client.support.create(subject="Help me", message="Something is broken.")
    assert info.value.retry_after == 12
    assert len(client.recorder.requests) == 1  # writes are never retried
    assert client.sleeps == []


def test_non_json_error_maps_by_status(make_client):
    client = make_client(httpx.Response(502, text="<html>Bad gateway</html>"), max_retries=0)
    with pytest.raises(ServerError) as info:
        client.account.get()
    assert info.value.status == 502 and info.value.code == "request_failed"


def test_non_json_success_is_invalid_response(make_client):
    client = make_client(httpx.Response(200, text="hello"))
    with pytest.raises(SqlCockpitError) as info:
        client.account.get()
    assert info.value.code == "invalid_response"


def test_ok_false_with_200_is_error(make_client):
    client = make_client(fail(200, "server_error", "Odd."))
    with pytest.raises(SqlCockpitError) as info:
        client.account.get()
    assert info.value.message == "Odd."


def test_get_retries_429_honouring_retry_after_capped(make_client):
    client = make_client(
        fail(429, "rate_limited", headers={"Retry-After": "5"}),
        fail(429, "rate_limited", headers={"Retry-After": "120"}),
        ok({"name": "Ada"}),
    )
    assert client.account.get().name == "Ada"
    assert client.sleeps == [5, 30]
    assert len(client.recorder.requests) == 3


def test_get_retries_5xx_then_gives_up(make_client):
    client = make_client(fail(500, "server_error"))
    with pytest.raises(ServerError):
        client.tenants.list()
    assert len(client.recorder.requests) == 3
    assert client.sleeps == [0.5, 1.0]


def test_retries_can_be_disabled(make_client):
    client = make_client(fail(503, "server_error"), max_retries=0)
    with pytest.raises(ServerError):
        client.tenants.list()
    assert len(client.recorder.requests) == 1


def test_get_does_not_retry_4xx(make_client):
    client = make_client(fail(404, "not_found"))
    with pytest.raises(NotFoundError):
        client.team.list(TENANT)
    assert len(client.recorder.requests) == 1


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.team.add(TENANT, name="Ada", email="a@example.com", role="admin"),
        lambda c: c.team.change_role(TENANT, TENANT, role="admin"),
        lambda c: c.team.remove(TENANT, TENANT),
        lambda c: c.team.resend_invite(TENANT, TENANT),
    ],
)
def test_writes_never_retried_on_5xx(make_client, call):
    client = make_client(fail(500, "server_error"))
    with pytest.raises(ServerError):
        call(client)
    assert len(client.recorder.requests) == 1


def test_timeout_maps_to_timeout_error(make_client):
    client = make_client(httpx.ReadTimeout("slow"))
    with pytest.raises(sqlcockpit.TimeoutError) as info:
        client.account.get()
    err = info.value
    assert isinstance(err, sqlcockpit.ConnectionError)
    assert isinstance(err, TimeoutError)  # builtin
    assert err.code == "timeout"
    assert err.__context__ is None and err.__cause__ is None


def test_connect_error_maps_to_connection_error(make_client):
    client = make_client(httpx.ConnectError("refused"))
    with pytest.raises(sqlcockpit.ConnectionError) as info:
        client.account.get()
    assert info.value.code == "unreachable"
    assert API_KEY not in repr(info.value) and API_KEY not in str(info.value)
    assert info.value.__context__ is None
