# DeepSpace durable runs

DeepSpace chat generation is owned by the backend worker, not by the browser's
HTTP connection. The existing `/api/v1/deepspace/chats/stream` SSE contract is
unchanged for clients.

When a prompt is submitted, the API schedules the `deepspace.run` Celery task.
The worker executes the existing `DeepSpaceChatService`, commits every SSE
frame to `deepspace_run_events`, and publishes the same frame on the scoped
Redis channel `deepspace:run:{client_request_id}`. A connected browser receives
frames immediately. A later browser reconnect first replays committed frames
from PostgreSQL and then follows Redis until `done` or `error`.

The event table is tenant-, user-, conversation-, and request-scoped. The
frontend sends `reconnect: true` when history contains a still-streaming
assistant message; this attaches to the existing run and never queues a second
one. The Stop action writes a tenant/user-scoped Redis cancellation marker and
requests cancellation of any existing runtime row. The worker checks the
marker before starting and the runtime cancellation flag during provider and
tool work.

Deployments must run `alembic upgrade head` before restarting the worker. The
worker command consumes the `deepspace` queue in addition to the existing
queues. Event rows are retained using the existing transient-record retention
period and removed by the scheduled maintenance cleanup.
