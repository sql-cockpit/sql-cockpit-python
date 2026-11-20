# Changelog

## 0.1.0 - 2026-11-20

First release.

- `Client` and `AsyncClient` for the SQL Cockpit Portal API v1.
- Account, tenants, team members, Agents, instances and support tickets: one method per operation.
- Typed models for every response.
- Exceptions for each error status, with `fields` on validation errors and `retry_after` on rate limits.
- GET requests retry 429 and 5xx up to twice. Writes are never retried.
- HTTPS only (except localhost), no redirects, 2 MiB response cap, UUID checks on ids, and the API key kept out of `repr()` and exceptions.
