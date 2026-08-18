# DeepSpace universal tools

DeepSpace exposes a small, target-aware workspace tool surface to new model
requests. The target is always explicit so the model can choose the correct
resource without giving the backend ambiguous or host-filesystem access.

## Operations

| Operation | Targets | Purpose |
| --- | --- | --- |
| `read` | `note`, `library`, `memory`, `chat`, `tasks` | Read authorized data without changing it |
| `find` | `library`, `memory`, `chat` | Search an authorized source |
| `write` | `note`, `library`, `memory` | Create or replace/append content |
| `edit` | `note`, `library` | Replace, append, or rename content |
| `delete` | `library`, `memory` | Destructive removal with explicit user intent |

The existing `todo_*`, `observe`, `analyze`, `web_search`, `url_read`,
`image_read`, `ask_user`, and `final` tools remain the specialized tools for
their distinct lifecycle or external-provider contracts. The former
note-specific, memory-specific, and `workspace_write` tools have been removed;
new runs must use the universal operations above.

## Target boundaries

- `note` is the active DeepSpace note for the current conversation.
- `library` is the tenant/user/conversation-owned DeepSpace Library.
- `memory` is the tenant-scoped durable memory store.
- `chat` is the current conversation history and is read-only through this
  interface.
- `tasks` is the persisted DeepSpace task ledger and is read-only through
  `read`; task mutations continue through the validated `todo_*` lifecycle.

Every operation is checked by the DeepSpace tool policy and storage layer for
tenant, user, and conversation ownership. Library operations use file IDs or
validated exact names and never access the host operating system.

Library targets can address folders with `folder_id`/`folder_name`. The
universal dispatcher supports listing and reading entries, creating text files
or folders, replacing/appending text, renaming or moving files, and deleting
authorized files. Binary import, archive inspection, version restore, and
authenticated content streaming are exposed by the Library API and preview;
the agent receives bounded extracted text/metadata rather than unsafe binary
execution.

## Streaming

The dispatcher is inside the existing chat service. Existing SSE event types
and the frontend timeline are unchanged. New calls appear as ordinary real
tool events with their operation, target, arguments, result, and status.

## MCP routing boundary

Connected MCP catalogs are discovered through the authenticated bridge, but
their schemas are exposed to the model only when the user explicitly names the
corresponding connected service (for example, Gmail, Drive, Calendar, GitHub,
Slack, or Notion). General research, drafting, Library, note, and workspace
requests use the native DeepSpace tools such as `web_search` and `write` and do
not receive unrelated MCP tools.

This is a model-routing boundary, not a security boundary. Every selected MCP
call still passes the existing tenant/user ownership, connection status,
catalog revision, allowlist, read-only, risk ceiling, approval, and audit
checks. A printed `<function-call>`, DSML, XML, or JSON fragment is never
executed as a tool; it is treated as invalid provider output and retried only
within the bounded chat recovery policy.
