# 10. DeepSpace memory moderation lifecycle

**Status:** available locally. Memory is tenant-scoped; candidates never
auto-activate; destructive operations are explicit and auditable.

## 1. What it covers

The memory workspace is the user-visible moderation surface for everything
the agent remembers: durable user facts and preferences, session memory,
inferred candidates, retention reports, and clearing. It is the backend
contract behind `MemoryPanel`, the composer memory controls, and the
`/documentation/memory-workspace` guide. Recall shaping (what the agent
retrieves) stays in `08-selective-context-retrieval.md`; this document covers
the moderation lifecycle (what gets kept, approved, edited, or removed).

## 2. Scopes and states

- **User memory** holds durable facts, preferences, and workflow rules.
- **Session memory** is temporary, can attach to a conversation, and expires
  automatically (7-day session window in the v2 service).
- **Candidates** are inferred suggestions (`pending`): bounded (≤3 per pass),
  never auto-saved, and sensitive information is never auto-captured.
- Facts carry confidence, entities, related-memory links, and history:
  repeated facts reinforce one record instead of duplicating; changed
  explicit facts supersede the older record while preserving its history.

## 3. Moderation routes (`/api/v1/deepspace/chats/...`)

| Operation | Route |
|---|---|
| Search memory | `GET /memory/search` |
| List facts | `GET /memory` |
| Save explicit fact | `POST /memory` (active only after the save succeeds) |
| Edit fact | `PATCH /memory/{memory_id}` |
| Approve candidate | `POST /memory/{memory_id}/approve` |
| Discard candidate | `DELETE /memory/{memory_id}/candidate` |
| Forget one key | `DELETE /memory/{key}` |
| Clear personal memory | `DELETE /memory/clear` |
| Duplicate cleanup | `POST /memory/cleanup` |
| Stale cleanup | `POST /memory/cleanup-stale` |
| Retention report | `GET /memory/retention` |
| Health evaluation | `GET /memory/evaluation` |
| Preferences | `GET/PATCH /memory/preferences` |

Every route is authenticated and tenant-scoped; cross-tenant reads and
writes fail closed. Memory never copies whole conversations, and MCP
connections stay in their own runtime — they are not mixed into memory
storage.

## 4. Retention and evaluation

- Retention reports expose duplicate counts, stale records, embedding
  health, and personal-memory clearing from inside DeepSpace.
- Cleanup endpoints are explicit operator/member actions, never background
  purges: duplicates merge, stale records expire, and clearing removes
  personal memory on request.
- Conversation history is separate from memory and survives page reloads
  independently of retention runs.

## 5. What must not change

1. Candidates must remain approval-gated; no path may auto-activate an
   inferred fact.
2. Sensitive auto-capture stays forbidden; explicit `remember` requests are
   the only write path that creates durable facts without review.
3. Memory reads and writes stay tenant-scoped and permission-checked.
4. Recall answers may cite used memories, but raw storage internals and
   other tenants' records are never exposed.

## 6. Verification

Backend regression coverage exercises memory CRUD, candidate
approve/discard, cleanup, retention reporting, and tenant isolation.
Frontend coverage renders the memory panel scopes, candidate approval,
search, edit, forget, and export flows.
