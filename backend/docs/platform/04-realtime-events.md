# 04. Shared realtime events

AverQel uses an authenticated, user-scoped realtime channel for durable UI
state changes. The migrated surfaces are the DeepSpace conversation list,
document status refreshes, and storage lifecycle/usage refreshes; existing
DeepSpace response SSE and collection WebSockets remain unchanged.

## Contract

The gateway is:

- `WS /api/v1/realtime/ws`
- authorized with the existing `queries:run` permission;
- scoped to the authenticated tenant and user;
- backed by a bounded Redis Stream at
  `averqel:realtime:v1:{tenant_id}:{user_id}`.

Browser clients call `POST /api/v1/realtime/ticket` with their normal
authenticated API session. The endpoint returns an opaque ticket that expires
after 60 seconds. The WebSocket consumes it once from Redis before accepting
the connection. The authenticated API client refreshes a near-expiry access
token before requesting a ticket, so reconnects do not reuse stale JWTs and
access JWTs do not appear in browser WebSocket URLs. Direct JWT/API-key
WebSocket authentication remains available for compatibility with existing
non-browser clients.

Each event contains `event_id`, `type`, `resource`, `data`, and
`occurred_at`. The Redis Stream ID is the replay cursor. The browser stores the
last received cursor, reconnects with it, and automatically receives missed
events still inside the bounded replay window. REST remains authoritative: a
client must re-fetch the affected resource after an event rather than treating
event payloads as permission-bearing state.

## Implemented event publishers and consumers

Conversation create, update, append-content, delete, and bulk delete emit
user-scoped `conversations` events. The
DeepSpace sidebar subscribes to those events and refreshes its authoritative
conversation list without the old ten-second polling loop.

Document ingestion publishes the shared stream alongside its existing
document-status Pub/Sub/SSE path. The documents page uses the shared stream as
an authoritative refresh trigger while retaining its existing SSE status
rendering. Storage retention/archive mutations publish storage events, and the
storage page refreshes from those events instead of a five-second polling loop.

DeepSpace queue transitions and run metrics publish user-scoped events. The
DeepSpace queue view and operational summary use those events for authoritative
snapshot refreshes and no longer use their former visible polling loops. Admin
system metrics use a separate platform-admin-only SSE endpoint backed by the
service-wide Redis metrics counters described below. MCP API actions and
background catalog/lifecycle workers publish `mcp` events; both the MCP
dashboard and inspector consume them.
Document detail status also uses the shared `documents` event stream instead
of a short polling loop.

DeepSpace answer-token streams are intentionally still dedicated per-run SSE
channels. This prevents a high-volume model response from competing with
low-volume application state events.

## Reconnect and failure behavior

The frontend reconnects with exponential backoff up to ten seconds and obtains
a fresh one-use ticket for each attempt. The affected REST snapshot handles a
missed or trimmed cursor; the application does not delete local state or
display an empty list during a transient connection failure. A browser refresh
remains an emergency recovery action, not a normal synchronization step.

## Admin service metrics stream

`GET /api/v1/metrics/summary/stream` is restricted to allowlisted platform
administrators. API and instrumented worker processes atomically update a fixed
set of low-cardinality counters in Redis and publish a change signal. The stream
sends an initial snapshot, then checks for updated totals at one-second
intervals; it sends a heartbeat while idle and closes after five minutes so the
browser can reconnect and reauthenticate. It is separate from the user-scoped
workspace event gateway.

The JSON summary endpoint reads the same counters. Totals are service-wide and
cumulative from `metrics_started_at`; they reset if the Redis metrics hash is
lost or cleared. `metrics_complete=false` means a process observed a failed
counter write, so the UI labels the snapshot as partial. A Redis read or
invalid stored value is reported as unavailable; it must never be displayed as
a successful zero snapshot. The database count covers explicitly instrumented
repository operations, not every SQL statement. Detailed per-process samples
remain available through the internal Prometheus scrape endpoint.

## Admin service metrics stream

`GET /api/v1/metrics/summary/stream` is restricted to allowlisted platform
administrators. API and instrumented worker processes atomically update a fixed
set of low-cardinality counters in Redis and publish a change signal. The stream
sends an initial snapshot, then checks for updated totals at one-second
intervals; it sends a heartbeat while idle and closes after five minutes so the
browser can reconnect and reauthenticate. It is separate from the user-scoped
workspace event gateway.

The JSON summary endpoint reads the same counters. Totals are service-wide and
cumulative from `metrics_started_at`; they reset if the Redis metrics hash is
lost or cleared. `metrics_complete=false` means a process observed a failed
counter write, so the UI labels the snapshot as partial. A Redis read or
invalid stored value is reported as unavailable; it must never be displayed as
a successful zero snapshot. The database count covers explicitly instrumented
repository operations, not every SQL statement. Detailed per-process samples
remain available through the internal Prometheus scrape endpoint.

## Security requirements

The gateway never accepts tenant or user identity as authority from event
payloads or query parameters. The server derives both from the authenticated
session used to mint the ticket and subscribes only to that exact stream. Event
payloads are invalidated data, not commands, and must not contain access
tokens, encrypted secrets, raw provider content, or cross-tenant identifiers.

## Scope note

The shared gateway covers the workspace surfaces that have durable mutation
publishers: conversations, documents, storage, queues, DeepSpace run metrics,
MCP state, and dashboard invalidation. Dedicated high-volume DeepSpace answer
SSE and collection chat WebSockets remain unchanged. Decorative UI timers and
visibility-triggered recovery loads are not data synchronization channels.
