# DeepSpace selective context retrieval

## Purpose

DeepSpace uses a short-context default and retrieves older material only when
the user asks for earlier decisions, memories, task history, or project status.
The full transcript remains durable, but it is never copied wholesale into a
model request.

## Request behavior

```text
ordinary request
  -> recent bounded context only
  -> no history search

explicit retrospective request
  -> read-only retrieval tools
  -> tenant/user/conversation-scoped hybrid search
  -> bounded evidence snippets
  -> model answer marked by evidence, not by guessed history
```

The retrospective profile can use `find`, `read`, `ask_user`, and `final`. It
cannot use write, edit, delete, analyze, sandbox, or external side-effect
tools merely because the user asked for history.

## Chat index

`deepspace_conversation_retrieval_chunks` is derived search data. Visible user
and assistant message content is indexed against the active message version.
The authoritative records remain `messages` and `message_versions`.

The index uses:

- PostgreSQL full-text search for lexical matches;
- pgvector embeddings for semantic candidates;
- bounded candidate and answer limits;
- content hashes and active-version IDs for idempotent reindexing;
- tenant, user, conversation, and message foreign-key boundaries;
- RLS and cascade deletion;
- asynchronous `deepspace.index_conversation` work on the dataset-indexing queue.

Large messages are split into bounded chunks. The model receives only selected
snippets, never the entire index. Retrieved text is reference-only and cannot
override current user instructions or authorize a tool call.

## Memory behavior

Memory remains a separate durable system. It uses embeddings, lexical overlap,
importance, confidence, freshness, entity overlap, deduplication, and explicit
user/tenant scope. Its structured types now include facts, preferences,
workflow rules, decisions, commitments, project goals, and artifact references.
Automatic capture remains consent-controlled and inferred memories may remain
pending for review. Credentials and other sensitive values are blocked.

Assistant output is not automatically trusted as memory. Durable assistant-
derived facts require explicit user confirmation or a verified tool/evidence
source; otherwise they remain ordinary response text.

Memory retrieval is allowed only when the user explicitly asks to recall or
inspect memory and `memory_retrieval_enabled` is true. Sensitive values,
credentials, and cross-tenant records are not automatically retrieved.

## Operational guarantees

- Normal chat latency does not wait for indexing.
- Indexing failure cannot fail a completed chat response.
- Search failure falls back safely or returns no evidence; it never invents history.
- During rollout, a worker without the retrieval migration uses a bounded,
  tenant-scoped lexical fallback for explicit history requests only.
- A retrospective request may also read the bounded `project` view, which
  combines the persisted conversation summary with the authorized task ledger;
  it is reference-only and cannot authorize actions.
- Message edits create a new active version and obsolete index rows are removed.
- Conversation deletion cascades to derived retrieval rows.
- The current queue, approval, MCP, provider, cancellation, and SSE contracts
  are not changed by the retrieval index.

## Verification requirements

Before release, verify:

1. ordinary prompts do not call retrieval;
2. retrospective prompts receive only read-only retrieval tools;
3. semantic and lexical matches return bounded results;
4. one user cannot retrieve another user’s messages or memories;
5. tenant isolation remains enforced by application scope and RLS;
6. message edits and deletion remove stale derived rows;
7. indexing failure does not block chat;
8. old retrieved text is treated as reference-only prompt data;
9. local and staging providers report retrieval fallback honestly;
10. latency remains within the DeepSpace interactive budget.

The additive database migration is
`20260929_0001_deepspace_conversation_retrieval_index`, after
`20260928_0001`. Deploy the code and migration together. Until the migration is
applied, normal chat remains unchanged and explicit history lookup uses the
bounded rollout fallback.
