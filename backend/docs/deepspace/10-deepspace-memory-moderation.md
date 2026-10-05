# 10. DeepSpace memory moderation lifecycle

**Status:** available locally. Memory is tenant-scoped; automatic capture is
off by default; users control review and retrieval preferences.

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
- **Automatic capture** is off by default. When enabled, the user can keep
  inferred memories pending for approval or turn off review so inferred
  memories can become active without a separate approval. Explicit user
  requests can save a matching fact as active after the save succeeds.
- Inferred suggestions are bounded (≤3 per pass). A keyword guard blocks a
  limited set of credential and sensitive-data terms; it is not a complete
  sensitive-data detector or a privacy guarantee. Users should not store
  passwords, tokens, or highly sensitive personal information in memory.
- **Memory retrieval** has its own preference. Turning it off prevents active
  memories from being used as chat context without deleting those memories.
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

## 5. Safety invariants and limits

1. Automatic capture remains opt-in and is disabled for a new preference
   record. The user can separately choose whether inferred memories require
   approval and whether active memories may be retrieved in chat.
2. The sensitive-content check is a limited keyword guard. It must not be
   described as comprehensive detection, data-loss prevention, or a guarantee
   that sensitive content cannot enter memory.
3. Memory reads and writes stay tenant-scoped and permission-checked.
4. Recall answers may cite used memories, but raw storage internals and other
   tenants' records are never exposed.

## 6. Verification

Backend regression coverage exercises memory CRUD, candidate
approve/discard, cleanup, retention reporting, and tenant isolation.
Frontend coverage renders the memory panel scopes, candidate approval,
search, edit, forget, and export flows.
