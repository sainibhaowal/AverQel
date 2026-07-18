# AverQel DeepSpace System Inventory

Complete listing of all agentic components, tools, workflows, and MCP integrations.

---

## 1️⃣ ALL 57 AGENT TOOLS (By Category)

### 📂 Filesystem Operations (IDE-style, DEPRECATED for Web)
- `BASH` - Shell command execution (TIER3_APPROVE)
- `BASH_OUTPUT` - Read background shell output (TIER1_AUTO)
- `GLOB` - File pattern matching (TIER1_AUTO)
- `GREP` - Content search in files (TIER1_AUTO)
- `READ_FILE` - Read file contents (TIER1_AUTO)
- `EDIT_FILE` - Surgical string replacement (TIER2_CONFIRM)
- `WRITE_FILE` - Create/overwrite files (TIER2_CONFIRM)
- `KILL_SHELL` - Terminate shell session (TIER3_APPROVE)

### 📔 Data & Notebooks
- `NOTEBOOK_EDIT` - Edit Jupyter notebooks (TIER2_CONFIRM)
- `DATA_ANALYZE` - Analyze CSV/JSON/Excel (TIER1_AUTO)
- `DOCUMENT_CONVERT` - Convert between formats (TIER2_CONFIRM)

### 🔍 Search & Research
- `WEB_SEARCH` - Search the web (TIER1_AUTO)
- `WEB_FETCH` - Fetch & extract web content (TIER1_AUTO)
- `SEARCH_ECOSYSTEM_DOCS` - Search tenant docs (TIER1_AUTO)
- `CRAWL_URL` - Create web-crawler sources (TIER2_CONFIRM)

### 📧 Google Workspace (Gmail)
- `GMAIL_SEARCH` - Search emails (TIER1_AUTO)
- `GMAIL_READ` - Read specific email (TIER1_AUTO)
- `GMAIL_SEND` - Send email (TIER2_CONFIRM)
- `GMAIL_MANAGE` - Archive/trash/star (TIER2_CONFIRM)
- `GMAIL_DELETE_MESSAGE` - Permanently delete (TIER2_CONFIRM)

### 📅 Google Workspace (Calendar)
- `CALENDAR_LIST_EVENTS` - List upcoming events (TIER1_AUTO)
- `CALENDAR_FIND_FREE_SLOTS` - Find availability (TIER1_AUTO)
- `CALENDAR_CREATE_EVENT` - Create event (TIER2_CONFIRM)
- `CALENDAR_UPDATE_EVENT` - Update event (TIER2_CONFIRM)
- `CALENDAR_DELETE_EVENT` - Delete event (TIER2_CONFIRM)

### 💾 Google Workspace (Drive)
- `DRIVE_SEARCH` - Search Drive (TIER1_AUTO)
- `DRIVE_READ_FILE` - Read file (TIER1_AUTO)
- `DRIVE_UPLOAD_FILE` - Upload file (TIER2_CONFIRM)
- `DRIVE_UPDATE_FILE` - Update file (TIER2_CONFIRM)
- `DRIVE_DELETE_FILE` - Delete file (TIER2_CONFIRM)

### 💬 Slack
- `SLACK_POST_MESSAGE` - Post message to channel (TIER2_CONFIRM)
- `SLACK_UPDATE_MESSAGE` - Update message (TIER2_CONFIRM)
- `SLACK_DELETE_MESSAGE` - Delete message (TIER2_CONFIRM)

### 🐙 GitHub
- `GITHUB_SEARCH` - Search repo (TIER1_AUTO)
- `GITHUB_READ_FILE` - Read file from repo (TIER1_AUTO)
- `GITHUB_CREATE_FILE` - Create file (TIER2_CONFIRM)
- `GITHUB_UPDATE_FILE` - Update file (TIER2_CONFIRM)
- `GITHUB_DELETE_FILE` - Delete file (TIER2_CONFIRM)
- `GITHUB_CREATE_ISSUE` - Open issue (TIER2_CONFIRM)
- `GITHUB_COMMENT_ISSUE` - Comment on issue (TIER2_CONFIRM)
- `GITHUB_UPDATE_ISSUE` - Update issue (TIER2_CONFIRM)

### 📝 Notion
- `NOTION_CREATE_PAGE` - Create page (TIER2_CONFIRM)
- `NOTION_APPEND_CONTENT` - Append to block (TIER2_CONFIRM)

### 🧠 Memory & Tasks
- `MEMORY_READ` - Retrieve stored fact (TIER1_AUTO)
- `MEMORY_WRITE` - Store fact persistently (TIER2_CONFIRM)
- `MEMORY_SEARCH` - Semantic search memories (TIER1_AUTO)
- `TODO_READ` - View tasks (TIER1_AUTO)
- `TODO_WRITE` - Create/manage tasks (TIER2_CONFIRM)

### 🎯 Orchestration & Control
- `TASK` - Spawn subagent (TIER5_SPAWN)
- `ASK_USER_QUESTION` - Interactive prompts (TIER1_AUTO)
- `SKILL` - Invoke reusable prompts (TIER1_AUTO)
- `SLASH_COMMAND` - Execute custom commands (TIER1_AUTO)
- `ENTER_PLAN_MODE` - Read-only planning (TIER1_AUTO)
- `EXIT_PLAN_MODE` - Exit plan mode (TIER1_AUTO)

### 🔌 Connector Management
- `LIST_CONNECTORS` - List available connectors (TIER1_AUTO)
- `GET_CONNECTOR_STATUS` - Check connector health (TIER1_AUTO)
- `SYNC_CONNECTOR` - Trigger sync (TIER2_CONFIRM)

---

## 2️⃣ PERMISSION TIERS (5 Levels)

```
TIER1_AUTO        → Read-only, no side effects (auto-approve)
TIER2_CONFIRM     → Writes, edits, messages (user confirms)
TIER3_APPROVE     → Shell execution, dangerous ops (explicit approval)
TIER4_WARN        → Destructive ops (rm, drop) - NOT USED YET
TIER5_SPAWN       → Subagent spawning (explicit approval)
```

### Tier 1 Auto-Approve (24 tools)
`read_file, glob, grep, web_search, web_fetch, memory_read, todo_read, ask_user_question, search_ecosystem_docs, get_connector_status, list_connectors, gmail_search, gmail_read, calendar_list_events, calendar_find_free_slots, github_search, github_read_file, drive_search, drive_read_file, bash_output, enter_plan_mode, exit_plan_mode, skill, slash_command`

### Tier 2 Confirm (22 tools)
`write_file, edit_file, notebook_edit, memory_write, todo_write, gmail_send, gmail_manage, gmail_delete_message, calendar_create_event, calendar_update_event, calendar_delete_event, github_create_file, github_update_file, github_delete_file, github_create_issue, github_comment_issue, github_update_issue, drive_upload_file, drive_update_file, drive_delete_file, slack_post_message, slack_update_message, slack_delete_message, notion_create_page, notion_append_content, sync_connector, crawl_url, document_convert`

### Tier 3 Approve (2 tools)
`bash, kill_shell`

### Tier 5 Spawn (1 tool)
`task`

---

## 3️⃣ SUBAGENT TYPES (13 Specialized Agents)

When calling `TASK` tool, you can spawn one of these types:

1. **general-purpose** - Default all-rounder
2. **research** - Web research, fact-finding
3. **writer** - Document creation, content generation
4. **analyst** - Data analysis, reporting
5. **executor** - Task execution, automation
6. **explorer** - Codebase exploration, discovery
7. **planner** - Mission planning, strategy
8. **email-agent** - Gmail management
9. **research-agent** - Deep research
10. **data-agent** - Data processing
11. **document-agent** - Document handling
12. **media-agent** - Media processing
13. **scheduler-agent** - Calendar/scheduling

**Subagent spawning config:**
```json
{
  "subagent_type": "research|writer|analyst|...",
  "prompt": "Detailed task description",
  "description": "3-5 word summary",
  "model": "haiku|sonnet|opus",
  "resume": "optional_agent_id_to_resume"
}
```

**Max Concurrency:** 4 subagents per user (Redis-backed registry)

---

## 4️⃣ MISSION LANE TYPES (10 Execution Paths)

Mission planner can create parallel lanes with these types:

1. **main_chat** - Primary conversation lane
2. **research** - Parallel research execution
3. **analysis** - Data/content analysis
4. **writer** - Document generation
5. **executor** - Task execution (bash, integrations)
6. **memory** - Memory operations
7. **proactive** - Background triggers
8. **connector** - Integration syncs
9. **support** - User support/approval
10. **approval** - Permission gating

**Example mission structure:**
```
main_chat (primary)
  ├─ research (depends_on: main_chat)
  ├─ analysis (depends_on: research)
  ├─ writer (depends_on: analysis)
  └─ approval (depends_on: writer)
```

---

## 5️⃣ AGENTIC LOOP (Agent Executor)

The **Golden Agent Reasoning Loop** - implements PLAN→EXECUTE→OBSERVE→EVALUATE cycle:

### Loop Phases
1. **PLAN** - LLM reasons about user query
2. **EXECUTE** - Call tools via function-calling
3. **OBSERVE** - Collect tool outputs
4. **EVALUATE** - LLM decides next step
5. **REPEAT** - Continue if more steps needed
6. **ANSWER** - Stream final response to user

### Agent Step Events (Frontend Rendering)
- `agent_plan` - Initial reasoning step
- `tool_start` - Tool invocation begins
- `tool_delta` - Streaming tool output
- `tool_result` - Tool completed successfully
- `tool_error` - Tool execution failed
- `permission_request` - Awaiting user approval
- `answer_start` - Final answer streaming
- `answer_delta` - Streaming response text
- `answer_done` - Response complete
- `agent_thinking` - Internal reasoning
- `observing` - Processing observations
- `step_summary` - Step recap

### Execution Limits
- **MAX_STEPS:** 12 steps per conversation
- **MAX_TIMEOUT:** Configurable per tool (default 120s)
- **RETRY_BUDGET:** Conservative per tool category

### Execution Modes
1. **auto_review** - Review before execution (default)
2. **full_access** - Bypass permission gates (admin only)

---

## 6️⃣ PROACTIVE AGENTS & TRIGGERS

Durable proactive work triggered by external events:

### Active Triggers (1 Registered)
- **GMAIL_URGENT**
  - Source: `gmail`
  - Event: Unread emails matching pattern
  - Query: `is:unread (urgent OR recruiter OR 'action required')`
  - Cooldown: 14 days (idempotency)
  - Uses: Proactive intervention with user approval

### Proactive Trigger Lifecycle
1. **Match** - Trigger condition met
2. **Draft** - Agent generates response
3. **Notify** - User sees notification
4. **Approval** - User approves action
5. **Execute** - Action runs

### Trigger Registry Components
- Idempotency key generation (SHA256)
- Cooldown enforcement
- Activity logging (match/draft/notify)
- Metadata persistence

---

## 7️⃣ ORCHESTRATION COMPONENTS

### Master Orchestrator
Federated coordinator for:
- OpenChat (main conversation)
- Subagents (parallel specialized work)
- Memory (embedding-backed retrieval)
- Proactive agents (background tasks)
- Connector syncs (integration updates)

### Mission Registry
- Redis-backed state storage
- DB-backed execution mode preferences
- Durable mission tracking (TTL: 24 hours)
- Cancellation support
- Heartbeat monitoring

### Subagent Registry
- Concurrency limiting (4 slots)
- Slot management (acquire/release)
- Stale slot reaping
- Run state persistence
- Heartbeat tracking

---

## 8️⃣ MCP INTEGRATION (Model Context Protocol)

### MCP Runtime Architecture
- OAuth2 token management
- HTTP-based communication
- Streaming response handling
- Result serialization

### MCP Connectors Available
Located in `/backend/app/services/integrations/`:

1. **Google** (OAuth2-enabled)
   - Gmail
   - Calendar
   - Google Drive

2. **GitHub** (Token-based)
   - Repository access
   - Issue management
   - File operations

3. **Slack** (Bot token)
   - Channel messaging
   - Thread operations

4. **Notion** (Integration tokens)
   - Page creation
   - Block updates

5. **Web** (Public URLs)
   - Web scraping
   - URL crawling

### MCP Tool Lifecycle
```
build_mcp_runtime(config)
  → OAuthClientProvider
  → ClientSession
  → list_tools()
  → call_tool(name, args)
  → render_mcp_result_text()
  → serialize_mcp_result()
```

### MCP Failure Handling
- Graceful degradation (MCP_SDK optional)
- Error taxonomy: `unknown_tool`, `invalid_arguments`, `execution_error`
- Redaction of sensitive payloads
- Result caching for deterministic operations

---

## 9️⃣ AGENT ACTIVITY TRACKING

### Activity Types Logged
- `match` - Proactive trigger matched
- `draft` - Agent generated response
- `notify` - User notification sent
- `execute` - Action executed
- `error` - Failure occurred

### Audit Trail Data
```python
AgentAuditLog:
  - tenant_id, user_id, conversation_id
  - tool_name, tool_args (redacted)
  - tool_result (first 10k chars)
  - status (success/failed)
  - execution_time_ms
  - created_at
```

### Agent Activity Models
- `AgentActivity` - Persistent activity records
- `AgentAuditLog` - Tool execution audits
- `AgentRuntimePreference` - User execution mode prefs

---

## 🔟 MEMORY SYSTEM

### Memory Types
1. **Session Memory** - Temporary (current conversation)
2. **Persistent Memory** - Durable (cross-session)

### Memory Features
- Embedding-backed semantic search
- Deduplication & scoring
- Access telemetry
- Quality evaluation
- Tenant/user isolation
- Decay policies (future)

### Memory Operations
```
memory_write(key, value, scope=['session'|'persistent'], tags=[])
memory_read(key)
memory_search(query)  → semantic retrieval
```

### Memory Roadmap (Phase 2)
- pgvector/HNSW migration
- Real embedding generation
- Memory decay jobs
- User-visible provenance UI

---

## 1️⃣1️⃣ TOOL CONTRACT SYSTEM

### Tool Definition Structure
```python
AgentToolDef(
  name: str,
  description: str,
  parameters: JSONSchema,
  permission_level: PermissionLevel
)
```

### Validation Pipeline
1. **Unknown Tool Check** → Error: `unknown_tool`
2. **JSON Schema Validation** → Error: `invalid_arguments`
3. **Permission Check** → Error: `plan_mode_blocked` or approval request
4. **Timeout Enforcement** → Error: `timeout`
5. **Execution** → Success or `execution_error`
6. **Redaction** → Remove secrets before logging
7. **Audit** → Write to AgentAuditLog

### Error Taxonomy
- `unknown_tool` - Tool not registered
- `invalid_arguments` - Schema validation failed
- `plan_mode_blocked` - Blocked in plan mode
- `timeout` - Exceeded max runtime
- `cancelled` - User cancellation
- `execution_error` - Runtime failure
- `permission_denied` - Tier check failed

---

## 1️⃣2️⃣ EXECUTION POLICIES

### Plan Mode (`ENTER_PLAN_MODE`)
- Read-only operation (blocks TIER2+)
- For architectural design
- Prevents accidental side effects

### Permission Modes (ToolExecutor)
```
DEFAULT       → Use base permission tier
ACCEPT_EDITS  → Auto-approve TIER2 writes
PLAN_ONLY     → Block all writes
DONT_ASK      → Auto-approve TIER3 bash
BYPASS        → Skip all permissions (admin)
```

---

## 1️⃣3️⃣ MODEL SELECTION LOGIC

### Provider Registry
Supports multiple LLM providers:
- Anthropic Claude (default)
- OpenAI GPT
- Local models (via LMStudio)

### Model Selection for Agent
- Default: `claude-3-5-sonnet`
- Research: `claude-3-opus` (for complex tasks)
- Fast: `claude-3-haiku` (for quick tasks)

### Reasoning Capabilities Detection
- Checks extended thinking
- Validates context limits
- Adjusts for provider features

---

## 1️⃣4️⃣ CONFIGURATION & SETTINGS

### Environment Variables (Critical)
```
DEEPSPACE_SUBAGENT_MAX_CONCURRENCY=4
DEEPSPACE_SUBAGENT_RUN_TTL_SECONDS=86400
DEEPSPACE_PROACTIVE_DAEMON_INTERVAL_SECONDS=300
DEEPSPACE_SUBAGENT_STALE_HEARTBEAT_SECONDS=900
LLM_MODEL=claude-3-5-sonnet
LLM_PROVIDER=anthropic
```

### Redis Keys Used
```
averqel:subagents:run:{run_id}
averqel:subagents:slot:{tenant}:{user}:{slot}
averqel:subagents:cancel:{run_id}
averqel:orchestration:run:{mission_id}
averqel:daemon:heartbeat
```

---

## 1️⃣5️⃣ CURRENT PRODUCTION ROADMAP (9/10 Plan)

### ✅ Phase 1: Tool Safety (IN PROGRESS)
- [x] JSON schema validation
- [x] Permission tiers
- [x] Error taxonomy
- [x] Redaction
- [x] Timeout enforcement
- [x] Audit logging

### 🔄 Phase 2: Memory Plane (PARTIAL)
- [x] Embedding retrieval
- [x] Deduplication
- [ ] pgvector migration
- [ ] Memory decay jobs
- [ ] UI provenance

### 🔄 Phase 3: Proactive Agents (PARTIAL)
- [x] Trigger registry
- [ ] Generalized triggers
- [ ] Approval gates
- [ ] Retry/dead-letter

### ⏳ Phase 4: Connector Reliability (BACKLOG)
- [ ] Checkpoints
- [ ] Error taxonomy
- [ ] Staging smoke tests
- [ ] Metrics

### ⏳ Phase 5: Subagent Hardening (BACKLOG)
- [ ] Cancellation tests
- [ ] Redis failure recovery
- [ ] Pressure tests
- [ ] Tool scope enforcement

### ⏳ Phase 6: Frontend Performance (BACKLOG)
- [ ] Virtualization
- [ ] Split panels
- [ ] SSE buffering

### ⏳ Phase 7: Production Ops (BACKLOG)
- [ ] OpenTelemetry traces
- [ ] Dashboards
- [ ] Chaos tests
- [ ] Runbooks

---

## 📊 SYSTEM METRICS

### Scaling
- **Agents per tenant:** Unlimited
- **Subagents per user:** 4 concurrent
- **Steps per conversation:** 12 max
- **Tools available:** 57
- **Triggers registered:** 1 (Gmail urgent)
- **Mission lanes:** 10 types
- **Subagent types:** 13 specialized

### Performance (Target)
- **Tool latency:** <200ms (read), <500ms (write)
- **LLM latency:** <3s (haiku), <5s (sonnet)
- **Step latency:** <5s (typical)
- **Step timeout:** 120s default

### Reliability (Target)
- **Tool success rate:** 99%+
- **Subagent reliability:** 95%+
- **Connector sync reliability:** 98%+
- **Memory retrieval accuracy:** 90%+

---

## 🚀 QUICK REFERENCE

### To spawn a research subagent:
```python
TASK(
  subagent_type="research",
  prompt="Find latest AI benchmarks",
  description="AI benchmark research"
)
```

### To create a multi-lane mission:
```python
MissionPlanner.build_plan(
  objective="Process customer data",
  execution_mode="auto_review"
  # Returns lane-based DAG
)
```

### To search memories:
```python
MEMORY_SEARCH("customer preferences")
# Returns top-k semantically similar memories
```

### To trigger proactive email check:
```python
# Automatic - runs every 5 min if Gmail connector active
# Matches: is:unread (urgent OR recruiter OR 'action required')
```

### To list all connectors:
```python
LIST_CONNECTORS()
# Returns: [Gmail, Drive, GitHub, Slack, Notion, ...]
```

---

## ⚠️ LIMITATIONS & GAPS

| Component | Status | Gap |
|-----------|--------|-----|
| Tool Contracts | ✅ READY | - |
| Memory Embedding | ✅ READY | pgvector not yet |
| Proactive Triggers | ⚠️ PARTIAL | Only Gmail urgent |
| Connector Reliability | ⚠️ PARTIAL | No checkpoints yet |
| Subagent Cancellation | ❌ MISSING | Needs tests |
| SSE Backpressure | ❌ MISSING | Buffer needed |
| Cost Tracking | ❌ MISSING | No SLA dashboards |
| Chaos Tests | ❌ MISSING | No failure scenarios |

---

## 📝 FILES & LOCATIONS

```
backend/app/services/deepspace/
  ├─ agent_executor.py           (Golden loop)
  ├─ agent_tools.py              (57 tool defs)
  ├─ agent_permissions.py        (5 tier system)
  ├─ agent_activity.py            (Audit logs)
  ├─ master_orchestrator.py       (Fed coordinator)
  ├─ mission_planner.py           (Lane generation)
  ├─ mission_registry.py          (Mission state)
  ├─ subagent_manager.py          (Spawn/track)
  ├─ subagent_registry.py         (Concurrency)
  ├─ proactive_triggers.py        (Triggers)
  ├─ memory_service.py            (Embedding retrieval)
  ├─ orchestration_service.py     (Overview UI)
  └─ execution_policy.py          (Permission gates)

backend/app/services/integrations/
  ├─ mcp_runtime.py               (OAuth2/HTTP)
  ├─ google/                      (Gmail, Calendar, Drive)
  ├─ github/                      (Repos, Issues)
  ├─ slack/                       (Messaging)
  ├─ notion/                      (Pages, Blocks)
  └─ web/                         (Crawling)
```

---

**Last Updated:** June 7, 2026
**System Complexity:** 9/10 Production Roadmap
**Total Codebase Size:** ~15K LOC (DeepSpace core)

