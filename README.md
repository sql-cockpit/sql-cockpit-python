# SQL Cockpit Python SDK

The official Python client for the SQL Cockpit Portal API. It covers your account, tenants, team, Agents, instances and support tickets.

Python 3.9 or later. The only dependency is [httpx](https://www.python-httpx.org/).

## Install

Until there is a PyPI release, install from GitHub:

```
pip install git+https://github.com/sql-cockpit/sql-cockpit-python
```

## Create an API key

Sign in to the portal and go to **Settings > Developer access**. Create a key and set it in your environment:

```
export SQL_COCKPIT_API_KEY=...
```

The key works like a password. Keep it out of source control.

## First program

```python
import sqlcockpit

with sqlcockpit.Client() as client:
    account = client.account.get()
    print(account.name, account.email)
    print("Plan:", account.plan.name if account.plan else "none")
```

## Methods

Every method returns a typed model from `sqlcockpit.models`. List methods return a plain list.

| Method | HTTP | Returns |
| --- | --- | --- |
| `client.account.get()` | `GET /account` | `Account` |
| `client.account.usage()` | `GET /usage` | `Usage` |
| `client.tenants.list()` | `GET /tenants` | `list[Tenant]` |
| `client.team.list(tenant_id)` | `GET /tenants/{tenant_id}/members` | `Team` |
| `client.team.add(tenant_id, name=, email=, role=)` | `POST /tenants/{tenant_id}/members` | `TeamMemberResult` |
| `client.team.change_role(tenant_id, membership_id, role=)` | `PATCH /tenants/{tenant_id}/members/{membership_id}` | `TeamMemberResult` |
| `client.team.remove(tenant_id, membership_id)` | `DELETE /tenants/{tenant_id}/members/{membership_id}` | `RemovedMember` |
| `client.team.resend_invite(tenant_id, membership_id)` | `POST /tenants/{tenant_id}/members/{membership_id}/resend` | `InviteSent` |
| `client.agents.list(tenant_id=None, status=None)` | `GET /agents` | `list[Agent]` |
| `client.instances.list(tenant_id=None)` | `GET /instances` | `list[Instance]` |
| `client.support.list(status=None)` | `GET /support-tickets` | `list[TicketSummary]` |
| `client.support.get(ticket_id)` | `GET /support-tickets/{ticket_id}` | `Ticket` |
| `client.support.create(subject=, message=, tenant_id=None, agent_id=None)` | `POST /support-tickets` | `Ticket` |

`change_role` and `remove` send `confirm: true` for you. Calling them is the confirmation, so check the ids first.

IDs are UUIDs, as strings or `uuid.UUID`. Anything else raises `ValueError` before a request is sent.

Timestamps are ISO 8601 strings, as the API sends them. Each model also has `raw`, the dict it was built from, which keeps any field this version of the SDK does not know about yet.

Plans, billing and deleting anything other than a team membership stay in the portal.

## Errors

Every error is a `sqlcockpit.SqlCockpitError` with `code`, `status`, `message` and `fields`.

| Exception | When |
| --- | --- |
| `AuthenticationError` | 401. The key is missing, invalid, revoked or expired. |
| `PermissionDeniedError` | 403. The key lacks the scope, or your role cannot do this. |
| `NotFoundError` | 404. Not found, or not something your account can reach. |
| `ValidationError` | 422. A value was refused. `fields` maps each field to its messages. |
| `RateLimitError` | 429. `retry_after` is the wait in seconds, when the portal sends it. |
| `ServerError` | 5xx. |
| `ConnectionError` | The portal could not be reached. |
| `TimeoutError` | The portal did not answer in time. A subclass of `ConnectionError`. |
| `ConfigurationError` | The key, portal URL or timeout is missing or not usable. |

```python
import sqlcockpit

with sqlcockpit.Client() as client:
    try:
        client.team.add(tenant_id, name="Ada Lovelace", email="ada@example.com", role="developer")
    except sqlcockpit.ValidationError as error:
        for field, messages in (error.fields or {}).items():
            print(field, messages)
    except sqlcockpit.SqlCockpitError as error:
        print(error.status, error.code, error.message)
```

### Retries

GET requests that end in 429 or a 5xx are retried up to twice. The SDK waits for the `Retry-After` header when there is one (at most 30 seconds), and otherwise for 0.5 then 1 second. Writes are never retried. Pass `max_retries=0` to turn retries off.

## Async

`AsyncClient` has the same methods. Await them.

```python
import asyncio
import sqlcockpit


async def main():
    async with sqlcockpit.AsyncClient() as client:
        for agent in await client.agents.list(status="active"):
            print(agent.name, agent.connection)


asyncio.run(main())
```

## Configuration

| Argument | Environment variable | Default |
| --- | --- | --- |
| `api_key` | `SQL_COCKPIT_API_KEY` | Required |
| `portal_url` | `SQL_COCKPIT_PORTAL_URL` | `https://portal.sql-cockpit.com` |
| `timeout` (seconds) | `SQL_COCKPIT_TIMEOUT_MS` (milliseconds) | 20 seconds |
| `max_retries` | | 2 |

Arguments win over environment variables. The timeout must be between 1 and 120 seconds. The environment variables are the same ones the SQL Cockpit MCP server reads.

```python
client = sqlcockpit.Client(api_key="...", timeout=10, max_retries=0)
```

## Safety

- The portal URL must use `https://`. `http://` is allowed only for `localhost`, `127.0.0.1` and `[::1]`.
- Redirects are never followed. A redirect raises `SqlCockpitError` with code `unexpected_redirect`.
- Responses larger than 2 MiB are refused with code `response_too_large`.
- The API key never appears in `repr()`, in exceptions or in logs, and clients cannot be pickled.

## Testing your code

Pass an httpx transport to answer requests without the network:

```python
import httpx
import sqlcockpit


def handler(request):
    return httpx.Response(200, json={"ok": True, "data": {"name": "Ada"}})


client = sqlcockpit.Client(api_key="sco_test_0123456789abcdef", transport=httpx.MockTransport(handler))
```

## Development

```
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT. See [LICENSE](LICENSE).
