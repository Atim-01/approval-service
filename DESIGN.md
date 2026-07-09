# DESIGN.md

## Data model

Four tables, all scoped by `workspace_id`:

**`approval_requests`** — the core entity. Tracks `source_type`/`source_id`
(opaque references to publications/scenarios/edits/external items owned by
other services), `reviewer_user_ids` (JSON array of external user ids),
`requested_by_user_id`, and `status` (`pending` → one of
`approved`/`rejected`/`cancelled`, which are terminal). `request_metadata`
is a free-form JSON bag for future extensibility, validated at the API
layer to reject a denylist of sensitive-looking keys (`token`, `secret`,
`password`, `email`, `signed_url`, `storage_key`, `provider_url`, ...)
before it ever reaches the database.

**`audit_logs`** — append-only history of every state-changing action:
who (`actor_user_id`), what (`action`, `from_status` → `to_status`), when
(`created_at`), and sanitized context (`details`, e.g. a rejection reason).
Rows are never updated or deleted.

**`outbox_events`** — see "Events/integrations" below.

**`idempotency_records`** — see "Idempotency" below.

Enums (`source_type`, `status`) use SQLAlchemy's `native_enum=False`,
storing them as `VARCHAR` with a `CHECK` constraint rather than a Postgres
native `ENUM` type. This keeps the schema portable across Postgres (real
usage) and SQLite (fast, isolated tests) without maintaining two schema
definitions.

## Service boundaries

This service owns only the approval workflow. It has no knowledge of what a
"publication" or "scenario" actually is beyond an id and a type tag — it
does not call out to those services, validate that the ids exist, or fetch
any of their data. All identifiers from other domains (`sourceId`,
`reviewerUserIds`, `workspace_id`, `user_id`) are treated as opaque strings.

**Workspace isolation** is enforced at a single chokepoint:
`services.get_approval_request()` filters by `(id, workspace_id)` in one
query, and every other read/write path (list, approve, reject, cancel) goes
through it. A request that exists but belongs to another workspace returns
`404`, not `403` — this avoids leaking whether a given id exists at all in
a workspace the caller can't see into.

**Permissions** are resolved from a `Principal` (workspace_id + user_id +
permission set) built once per request from headers (see README's auth
section), and never trusted from the request body or URL path.

## Idempotency

Every mutating endpoint (create, approve, reject, cancel) accepts an
`Idempotency-Key` header. It's required on create (since that's the
operation the "no duplicate requests" constraint is primarily concerned
with) and optional-but-supported on the decision endpoints.

Records are keyed on `(workspace_id, endpoint, idempotency_key)` with a
unique DB constraint, plus a hash of the canonicalized request body:

- **Same key, same body** → the original response is replayed verbatim.
  This is a safe retry (e.g. after a client-side timeout where the first
  request actually succeeded).
- **Same key, different body** → `409 Conflict`. This is treated as a
  client bug (reusing a key for a genuinely different request), not
  silently reprocessed.

The idempotency record is written in the *same transaction* as the
underlying state change, so a crash between "do the work" and "record the
idempotency key" can't happen — either both commit or neither does.
A narrow concurrent-duplicate race (two identical requests both pass the
initial lookup before either commits) is handled by catching the resulting
`IntegrityError` on the second insert and treating it as a no-op, since the
first request's response is already the source of truth.

This is deliberately a *different* mechanism from the final-state check
below: idempotency guards against retries of the *same* request; the
final-state check guards against a *second, different* decision being made
on an already-decided request.

## Events/integrations

The service writes to an `outbox_events` table as part of the same
transaction as every state change (create, approve, reject, cancel) —
the **transactional outbox pattern**. Each row records `event_type`
(e.g. `approval_request.created`, `approval_request.approved`),
`aggregate_id`, `workspace_id`, a sanitized `payload` (ids and status only,
no free text — so it structurally cannot leak `description`/`metadata`/
`decision_reason` content even if API-layer validation were ever bypassed),
and a `published_at` timestamp that starts `NULL`.

This assignment does not include a message broker or publisher process —
that's out of scope — but the integration point is exactly this table: a
separate worker would poll rows where `published_at IS NULL`, publish each
to whatever broker/webhook the consuming services use, and mark it
published. Because the event row commits atomically with the state change,
no event is ever lost (crash before commit → neither happened) or silently
skipped (crash after commit, before publish → the row is still there for
the poller to find).

## Known trade-offs or compromises

- **No real authentication.** Per the assignment, mock header-based auth is
  used. Swapping in real JWT validation only requires replacing
  `app.auth.get_principal`; no route or service code would need to change.
- **No reviewer-identity enforcement.** `reviewerUserIds` is stored and
  returned, but the service does not currently check that the user calling
  `/approve` or `/reject` is actually one of the listed reviewers — it only
  checks the `approval:decide` permission. Enforcing that would need a
  product decision (e.g. is `approval:decide` scoped per-user upstream, or
  should this service enforce reviewer membership itself?). Documented here
  as a straightforward addition, not implemented to keep the mock-auth
  boundary clean.
- **No outbox publisher included.** As noted above, the outbox table is
  ready for consumption but no polling/publishing worker exists in this
  submission — implementing one would mean picking a real broker, which is
  outside this assignment's scope ("you do not need to implement the
  neighboring services").
- **Sync SQLAlchemy, not async.** Chosen for simplicity and to keep Alembic
  configuration straightforward; FastAPI still serves requests concurrently
  via its threadpool for sync route handlers. For much higher throughput,
  an async SQLAlchemy engine + async routes would be the next step.
- **`datetime.utcnow()` deprecation warnings.** Python 3.12 flags
  `datetime.utcnow()` as deprecated in favor of timezone-aware
  `datetime.now(datetime.UTC)`. Functionally harmless today (values are
  still correct, naive UTC timestamps), left as-is to avoid touching every
  timestamp call site under time pressure; would switch to timezone-aware
  datetimes in a follow-up pass.
- **Idempotency key retention has no expiry.** `idempotency_records` grows
  unboundedly today. A production version would add a TTL/cleanup job
  (e.g. drop records older than 24–48 hours), since idempotency keys are
  typically only meaningful for retry windows measured in minutes, not
  forever.