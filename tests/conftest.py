import json
from typing import Any, Callable, List

import httpx
import pytest

import sqlcockpit

API_KEY = "sco_test_0123456789abcdefghijklmnop"
BASE = "https://portal.sql-cockpit.com/api/portal/v1"
TENANT = "11111111-1111-4111-8111-111111111111"
MEMBER = "22222222-2222-4222-8222-222222222222"
AGENT = "33333333-3333-4333-8333-333333333333"
TICKET = "44444444-4444-4444-8444-444444444444"


def ok(data: Any, status: int = 200, **kwargs: Any) -> httpx.Response:
    return httpx.Response(status, json={"ok": True, "data": data}, **kwargs)


def fail(status: int, code: str, message: str = "Nope.", fields: Any = None, **kwargs: Any) -> httpx.Response:
    error = {"code": code, "message": message}
    if fields is not None:
        error["fields"] = fields
    return httpx.Response(status, json={"ok": False, "error": error}, **kwargs)


class Recorder:
    """A MockTransport handler that answers from a queue and records every request."""

    def __init__(self, *responses: Any) -> None:
        self.responses: List[Any] = list(responses)
        self.requests: List[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        nxt = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(nxt, Exception):
            raise nxt
        if callable(nxt):
            return nxt(request)
        return nxt

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def body(self, index: int = -1) -> Any:
        return json.loads(self.requests[index].content)


@pytest.fixture
def make_client() -> Callable[..., Any]:
    created = []

    def factory(*responses: Any, **kwargs: Any) -> Any:
        rec = Recorder(*responses)
        kwargs.setdefault("api_key", API_KEY)
        client = sqlcockpit.Client(transport=httpx.MockTransport(rec), env={}, **kwargs)
        sleeps: List[float] = []
        client._sleep = sleeps.append
        client.recorder = rec
        client.sleeps = sleeps
        created.append(client)
        return client

    yield factory
    for c in created:
        c.close()
