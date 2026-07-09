# Approval Service

A backend service that handles content approval workflows: creating approval
requests for publications, scenarios, edits, or external items, and recording
the final decision (approved / rejected / cancelled).

This service does not implement publications, scenarios, edits, users, or
workspaces — those are external systems. This service only tracks the
approval workflow around content that lives elsewhere, referenced by id.

## Tech stack

- Python 3.12 + FastAPI
- PostgreSQL (SQLAlchemy 2.0 ORM, sync)
- Alembic for migrations
- Pytest for tests (in-memory SQLite)
- Docker + Docker Compose

## Running locally (without Docker)

Prerequisites: Python 3.12+, a local PostgreSQL instance.

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

createdb approval_service
```

Create a `.env` file in the project root:

```
DATABASE_URL=postgresql+psycopg2://YOUR_USER:YOUR_PASSWORD@localhost:5432/approval_service
```

Apply migrations:

```bash
alembic upgrade head
```

Run the server:

```bash
uvicorn app.main:app --reload --port 8000
```

Check it's up:

```bash
curl http://localhost:8000/healthz
# {"status":"ok"}
```

## Running with Docker

```bash
docker compose up --build
```

This starts Postgres, waits for it to become healthy, runs
`alembic upgrade head` automatically, then starts the API on
`http://localhost:8000`. No manual migration step is required.

To stop and wipe the database volume:

```bash
docker compose down -v
```

> **Note:** the Postgres credentials in `docker-compose.yml` are placeholder
> dev-only values for a container that is not exposed beyond your machine by
> default. They are not real secrets and are safe to keep in version control
> for local development. Do not reuse them in any real deployment.

## Running tests

```bash
pytest -v
```

Tests run against an isolated in-memory SQLite database (see
`tests/conftest.py`) and do not touch your local or Docker Postgres
instance. 23 tests cover creation, reads, workspace isolation, idempotency,
and decision/final-state transitions.

## Authentication (mock)

There is no real identity provider in this assignment. The caller identifies
itself via three headers, which a real deployment would replace with values
derived from a validated JWT / session, without changing any downstream code:

| Header            | Description                                             |
|--------------------|---------------------------------------------------------|
| `X-Workspace-Id`   | The workspace the request applies to                    |
| `X-User-Id`        | The acting user's id                                     |
| `X-Permissions`    | Comma-separated list of permissions the caller holds     |

Valid permissions:

| Permission         | Required for                          |
|--------------------|----------------------------------------|
| `approval:read`    | Listing/getting requests               |
| `approval:create`  | Creating a request                     |
| `approval:decide`  | Approving or rejecting a request       |
| `approval:cancel`  | Cancelling a request                   |

All three headers are required on every request; missing or empty
`X-Workspace-Id`/`X-User-Id` returns `401`. Every DB query is scoped by
`workspace_id` taken from this header — never from the request body or URL —
which is what enforces workspace isolation.

## API

Base path: `/v1/approval-requests`

### Create a request

```
POST /v1/approval-requests
Idempotency-Key: <required, any client-generated unique string>
```

```json
{
  "sourceType": "publication",
  "sourceId": "pub_123",
  "reviewerUserIds": ["user_bob"],
  "title": "New homepage banner",
  "description": "Please review before it goes live",
  "metadata": { "any": "extra context, no secrets" }
}
```

`sourceType` is one of: `publication`, `scenario`, `edit`, `external`.
`sourceId` and `reviewerUserIds` are opaque external identifiers — this
service does not validate them against the neighboring services.

`Idempotency-Key` is **required** on create. Repeating an identical request
with the same key returns the original response and does not create a
duplicate row. Reusing the same key with a different body returns `409`.

Returns `201` with the created request (status `pending`).

### List requests in a workspace

```
GET /v1/approval-requests?status=pending&sourceType=publication&sourceId=pub_123&limit=50&offset=0
```

All filters are optional. Results are always scoped to the caller's
workspace. Returns `{ items, total, limit, offset }`.

### Get a single request

```
GET /v1/approval-requests/{id}
```

Returns `404` if the request doesn't exist **or** belongs to another
workspace — the two cases are indistinguishable to the caller by design.

### Approve

```
POST /v1/approval-requests/{id}/approve
Idempotency-Key: <optional>
```

```json
{ "reason": "looks good" }
```

`reason` is optional.

### Reject

```
POST /v1/approval-requests/{id}/reject
Idempotency-Key: <optional>
```

```json
{ "reason": "does not meet brand guidelines" }
```

`reason` is **required**.

### Cancel

```
POST /v1/approval-requests/{id}/cancel
Idempotency-Key: <optional>
```

```json
{ "reason": "no longer needed" }
```

`reason` is optional. Requires `approval:cancel` (distinct from
`approval:decide`).

### Common error responses

| Status | Meaning                                                        |
|--------|-----------------------------------------------------------------|
| 400    | Bad request (e.g. missing required `Idempotency-Key` on create) |
| 401    | Missing/invalid auth headers                                    |
| 403    | Caller lacks the required permission                             |
| 404    | Request not found (or belongs to another workspace)              |
| 409    | Request already in a final state, or idempotency key conflict    |
| 422    | Request body failed validation (e.g. missing `reason` on reject) |

## Further reading

See `DESIGN.md` for the data model, service boundaries, idempotency design,
event/integration approach, and known trade-offs.

