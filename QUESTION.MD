## What DeepSpace is

DeepSpace is a two-level agentic system:

1. A direct bounded agent loop for normal requests.
2. A mission orchestration system for complex, multi-step work.

It is not one single loop and it is not an always-autonomous infinite worker. The actual architecture is:

```text
User request
   │
   ▼
API authentication / tenant permissions
   │
   ▼
DeepSpaceService
   │
   ├── Simple/conversational request
   │       └── AgentExecutor loop
   │
   └── Complex/orchestration request
           └── MissionPlanner
                   └── MasterOrchestrator
                           ├── main_chat lane
                           ├── research lane
                           ├── analysis lane
                           ├── writer/executor lanes
                           ├── connector lanes
                           └── support/memory/proactive lanes
```

The main entry point is [deepspace_service.py](/home/sephi-asi/AverQel/backend/app/services/deepspace/orchestration/deepspace_service.py).

---

## 1. User sends a prompt

The request enters through:

[deepspace_chats.py](/home/sephi-asi/AverQel/backend/app/api/v1/deepspace_chats.py)

Before the agent runs, DeepSpace performs:

- JWT/API-key authentication
- tenant validation
- permission checks
- conversation lookup or creation
- user-message persistence
- execution-mode lookup
- optional workspace/session setup
- SSE or WebSocket streaming setup

The user message is then passed to `DeepSpaceService.stream_chat()`.

---

## 2. DeepSpace decides which execution path to use

DeepSpace does not send every prompt through the full planner.

It first classifies the request.

### Direct-agent path

Used for:

- greetings
- normal questions
- short explanations
- ordinary chat
- simple requests that do not imply a workflow

Examples:

```text
"Hello"
"What is Python?"
"Explain recursion"
"Rewrite this paragraph"
```

These go directly to `AgentExecutor`.

### Orchestrated mission path

The current routing is mostly heuristic. DeepSpace looks for signals such as:

- workflow
- orchestrate
- multi-step
- delegate
- parallel
- subagent
- connector
- sync
- proactive
- approval
- repository/repo
- workspace
- terminal
- command
- run
- loop
- implementation or coding-related terms
- large history/context
- long complex requests

Examples:

```text
"Fix the failing tests in this repository"
"Research this topic, compare alternatives, and write a report"
"Inspect the codebase, implement the feature, run tests, and review the diff"
"Coordinate multiple agents to migrate this module"
```

These go through `MissionPlanner` and then `MasterOrchestrator`.

This means DeepSpace currently has a hybrid routing model, not a fully learned routing policy.

---

# Direct execution path

## 3. `AgentExecutor` creates the runtime

The main loop is implemented in:

[agent_executor.py](/home/sephi-asi/AverQel/backend/app/services/deepspace/execution/agent_executor.py)

It builds a runtime containing:

- user message
- conversation history
- current workspace
- memory facts
- selected model/provider
- reasoning profile
- enabled tools
- tenant and permission context
- coding mission contract if applicable
- runtime policies
- cancellation and budget controls

For short conversational messages, DeepSpace can skip expensive memory loading. For more substantial requests, it loads relevant memory and workspace context.

It also discovers connector/MCP tools dynamically and filters tools that are not currently allowed.

---

## 4. The model receives a system prompt

The system prompt tells the model that it may:

- answer directly
- use tools
- inspect files
- search the web
- write memory
- perform workspace operations
- continue working when evidence is incomplete
- avoid claiming completion without proof

The model does not expose chain-of-thought. It emits:

- thinking events
- answer deltas
- tool-call deltas
- final answer events

These are converted into SSE events for the frontend.

---

## 5. The executor runs a bounded loop

The executor loop is capped at:

```text
MAX_STEPS = 12
```

A single turn generally follows:

```text
Model decision
   │
   ├── Direct answer
   │       └── completion evaluation
   │
   └── Tool call
           ├── permission check
           ├── contract validation
           ├── tool execution
           ├── result observation
           ├── autonomy decision
           └── next model turn
```

If the model gives a direct answer without using tools, DeepSpace asks the autonomy controller whether that answer is sufficient.

For a normal informational question, it can finish immediately.

For a coding task, direct text is not enough. The autonomy gate forces the model to gather evidence through tools.

---

# Tool execution and permissions

## 6. Every tool call is classified

Tools are defined and controlled through:

- [agent_permissions.py](/home/sephi-asi/AverQel/backend/app/services/deepspace/execution/agent_permissions.py)
- [tool_contracts.py](/home/sephi-asi/AverQel/backend/app/services/deepspace/execution/tool_contracts.py)
- [agent_tools.py](/home/sephi-asi/AverQel/backend/app/services/deepspace/execution/agent_tools.py)

### Tier 1: read-only tools

Usually allowed automatically:

- read files
- list directories
- glob/search
- grep
- web search
- read memory
- read todos
- inspect connector status
- ask a question
- planning-mode operations

### Tier 2: modifying or external tools

Usually require confirmation:

- write files
- edit files
- notebook changes
- memory writes
- todo writes
- synchronization
- crawling or data modification
- some connector actions

### Tier 3: dangerous tools

Require explicit approval:

- shell/bash
- process termination
- destructive operations
- shutdown or privileged actions

### External integrations

Email, GitHub, Drive, Slack, calendars, Notion, and similar systems are treated as side-effectful integrations. They are not automatically trusted.

Each tool contract defines:

- risk class
- capabilities
- retry behavior
- timeout
- idempotency
- compensation behavior
- approval requirements
- tenant restrictions
- workspace restrictions
- whether the tool is untrusted

---

## 7. Tools can execute in parallel or sequentially

DeepSpace separates tools into classes:

### Read-only tools

Can run concurrently.

Example:

```text
Read five files
Search for a symbol
Inspect Git status
Read configuration
```

### Side-effect tools

Run sequentially.

Example:

```text
Edit file
Run migration
Send email
Create GitHub issue
Push deployment
```

Workspace-mutating lanes are also serialized by the orchestrator to avoid conflicting writes.

Tool results are:

- audited
- timeout-limited
- cancellation-aware
- retried only when allowed by the contract
- returned to the model as new context

---

# Autonomy and completion

## 8. DeepSpace does not trust the model’s claim of completion

The autonomy system is implemented under:

```text
backend/app/services/deepspace/autonomy/
```

The central structures are:

- `GoalContract`
- `CompletionEvidence`
- `AutonomyController`
- `DecisionKind`

The controller can decide:

```text
continue
finish
repair
replan
ask_human
stop
```

It records:

- successful tool calls
- failed tool calls
- verification results
- review results
- changed artifacts
- isolation readiness
- repeated actions
- unsafe actions
- evidence count
- declared verification commands

For coding work, DeepSpace requires evidence such as:

- an artifact changed
- tests or declared checks passed
- no unresolved failures
- diff review completed
- workspace isolation was available
- required verification commands ran

Therefore, this response is not accepted as proof:

```text
"I fixed the bug."
```

The system expects something closer to:

```text
Changed file: x.py
Ran: pytest tests/test_x.py
Result: passed
Reviewed diff: clean
```

If verification fails, the controller can request repair. Repair is bounded; it is not infinite.

Repeated identical actions trigger replanning. Unsafe actions trigger human approval or stop.

---

# Coding request flow

Suppose the user says:

```text
"Fix the failing tests in my repository."
```

The actual sequence is approximately:

```text
1. Request enters DeepSpaceService
2. Router detects repository/coding intent
3. MissionPlanner creates a mission plan
4. MasterOrchestrator registers a mission
5. Coding GoalContract is created
6. Isolated Git worktree is prepared
7. Optional Docker container is started
8. Agent reads repository files
9. Agent identifies failing code
10. Agent edits files
11. Agent runs tests/lint/type checks
12. Agent inspects the diff
13. Failures trigger repair/replan
14. Completion gate checks evidence
15. Mission is marked completed, blocked, failed, or awaiting approval
16. Final answer and metadata are persisted
```

The coding harness is controlled by:

[coding_harness.py](/home/sephi-asi/AverQel/backend/app/services/deepspace/workspace/coding_harness.py)

It provides:

- isolated Git worktrees
- unique mission branches
- allowed-path validation
- command allowlists
- network restrictions
- output limits
- time/tool/token/cost budgets
- blocked destructive commands
- optional Docker isolation
- cleanup and rollback

The default container mode is fail-closed if Docker or a valid repository is unavailable.

Blocked commands include patterns such as:

```text
rm -rf
drop database
truncate
mkfs
dd
kill
shutdown
sudo
curl | bash
git reset
git clean
git push
```

---

# Orchestrated mission path

## 9. The planner creates a typed mission

The planner is:

[mission_planner.py](/home/sephi-asi/AverQel/backend/app/services/deepspace/planning/mission_planner.py)

It first asks a model to produce structured JSON containing:

- objective
- lanes
- dependencies
- lane types
- approval policy
- acceptance criteria
- references
- execution signals

Allowed lane types include:

```text
main_chat
research
analysis
writer
executor
memory
proactive
connector
support
approval
```

The planner output is validated. If the model returns invalid JSON or an unsafe plan, DeepSpace falls back to a deterministic policy plan.

The fallback is intentionally conservative and often produces one `main_chat` lane rather than inventing a complex graph.

---

## 10. `MasterOrchestrator` executes the mission graph

The orchestrator is:

[master_orchestrator.py](/home/sephi-asi/AverQel/backend/app/services/deepspace/orchestration/master_orchestrator.py)

It:

1. creates or resumes a mission
2. registers the mission in Redis
3. persists the plan
4. creates lane records
5. builds dependency edges
6. launches dependency-ready lanes
7. limits parallelism
8. pauses for approvals
9. tracks lane results
10. handles cancellation
11. synthesizes final output
12. sets final mission status

Example mission:

```text
User request:
"Research competitors, inspect our pricing code, and write recommendations."
```

Possible graph:

```text
research ─────┐
              ├── analysis ─── writer ─── main_chat
code_inspect ─┘
```

Read-only lanes can run in parallel.

Workspace-writing lanes are serialized to prevent collisions.

---

## 11. Subagents have specialized profiles

Subagent profiles include roles such as:

- research/explorer
- analysis
- writer
- executor
- planner
- file
- support
- implementer
- tester
- reviewer
- repair
- release

Each profile controls:

- available tools
- expected output
- task scope
- role behavior
- permissions

A tester should not behave like a release agent. A research agent should not modify repository files.

The subagent manager creates context, runs the role, normalizes its result, and returns a structured lane result to the orchestrator.

---

# Mission persistence and resumability

## 12. Redis stores mission state

The mission registry is:

[mission_registry.py](/home/sephi-asi/AverQel/backend/app/services/deepspace/missions/mission_registry.py)

It stores:

- mission status
- lane status
- plan graph
- approval queue
- cancellation state
- heartbeats
- event history
- lane results
- repair nodes
- idempotency keys

Events include:

```text
mission_start
mission_planning
mission_plan
mission_graph
lane_start
lane_result
tool_observation
autonomy_decision
approval_requested
mission_cancelled
mission_summary
mission_done
```

Events are deduplicated using idempotency keys and retained with a bounded history.

If execution pauses for approval or the worker restarts, the mission can be resumed using the mission ID.

---

# Approval flow

## 13. When approval is required

For example:

```text
"Send this email to the customer."
```

The flow is:

```text
Model selects email tool
   │
   ▼
Tool contract identifies external side effect
   │
   ▼
DeepSpace emits approval request
   │
   ▼
Mission becomes awaiting_approval
   │
   ▼
Frontend asks user
   │
   ├── Approve → resume mission
   └── Deny   → cancel/decline operation
```

The resume route handles:

- orchestrated mission approvals
- direct-agent pending tool approvals

This is human-in-the-loop, not fully unrestricted autonomy.

---

# Memory, workspace, and integrations

## Memory

The memory service can:

- load relevant facts before execution
- write durable discoveries when permitted
- maintain todo/task state
- attach memory context to future turns

## Workspace

The workspace subsystem controls:

- workspace root
- sandbox mode
- shell execution
- file access
- coding isolation
- container lifecycle
- workspace policy

## Integrations

The integration layer includes:

- client proxy
- export service
- voice agent
- connector/MCP discovery
- external service adapters

All integrations still pass through tool contracts and permission checks.

## Proactive behavior

Proactive triggers can start work based on events or conditions, but they are bounded and policy-controlled. They are not equivalent to an unrestricted background consciousness.

---

# What happens in common examples

## Example 1: “Hello”

```text
API authentication
→ conversation lookup
→ conversational routing
→ AgentExecutor
→ model produces text
→ completion accepted
→ assistant message saved
→ answer streamed
```

No mission graph is usually created.

## Example 2: “What is the latest OpenAI pricing?”

```text
API/authentication
→ direct agent route
→ web-intent detection
→ web context/tool availability
→ model decides whether to search
→ result observation
→ answer with current information
→ message persisted
```

The request may remain a direct agent turn rather than a multi-lane mission.

## Example 3: “Fix this bug, run tests, and review the diff”

```text
Orchestration routing
→ mission planner
→ executor/implementer/tester/reviewer lanes
→ coding contract
→ isolated worktree/container
→ inspect files
→ edit
→ test
→ review diff
→ repair if needed
→ completion gate
→ final answer
```

This is the strongest use case for the current architecture.

## Example 4: “Delete all production records”

```text
Tool request
→ destructive command detection
→ contract rejection or approval requirement
→ likely stop/ask_human
```

The model cannot simply override the safety layer.

## Example 5: “Do whatever is needed”

This is ambiguous. DeepSpace may:

- ask a clarification question
- create a limited plan
- refuse to claim completion without a defined goal
- request approval before consequential actions

It cannot reliably infer unlimited authority from an ambiguous prompt.

---

# Mission statuses

The system tracks states such as:

```text
planning
ready
running
awaiting_approval
synthesizing
repairing
blocked
failed
completed
cancelled
declined
```

Lane states are tracked independently, so one lane can fail while another succeeds.

The final mission status is not blindly marked completed. It considers:

- blocked lanes
- failed lanes
- pending approvals
- cancellation
- autonomy completion evidence

---

# What kind of autonomy DeepSpace actually has

DeepSpace has constrained, evidence-based autonomy:

```text
Model proposes actions
→ policy authorizes actions
→ tools execute actions
→ controller observes results
→ controller decides whether continuation is justified
→ completion requires evidence
```

This is stronger than a simple chatbot and stronger than a naive “keep trying” loop.

However, it is not infinite autonomous operation. It is bounded by:

- maximum executor steps
- tool-call budgets
- time limits
- token/cost budgets
- repair budgets
- permissions
- approval gates
- workspace restrictions
- command allowlists
- cancellation
- model/provider availability

The model controls strategy. The deterministic runtime controls safety, state, evidence, and termination.

---

# Most important practical limitation

The biggest limitation is that orchestration selection is still partly heuristic.

A complex prompt can be routed to the direct agent path if it does not contain the expected orchestration signals. Conversely, a prompt containing terms like “repo”, “run”, or “workflow” can enter mission mode even when a direct response would have been enough.

Also, the model planner has a safe fallback that may reduce a complex request to a single main lane. Therefore, having many orchestration files does not guarantee that every request uses true multi-agent execution.

In practical terms:

```text
DeepSpace has the infrastructure for autonomous coding,
but autonomy is activated only when routing, planning,
permissions, isolation, tools, verification, and completion evidence
all line up correctly.
```

The architecture is therefore best described as:

> A bounded, policy-controlled, evidence-gated, resumable multi-agent orchestration platform with a direct tool-using agent loop and optional isolated coding execution.

It is not:

- an unlimited Ralph loop
- an always-running autonomous worker
- a purely graph-native runtime like LangGraph
- a system that can safely perform every external action without approval
- a guarantee that every model answer is correct or verified

You cannot make it “perfect” by simply increasing `MAX_STEPS`. The reliable solution is to replace the current heuristic routing and bounded single-run behavior with a durable supervisor architecture.









## What should change

### 1. Use a real task-intent classifier

Currently, routing depends partly on keywords such as `repo`, `run`, or `workflow`.

Replace that with a structured classifier that determines:

```text
task_type: chat | research | coding | automation | external_action
complexity: small | medium | large
risk: low | medium | high
needs_tools: true | false
needs_subagents: true | false
needs_approval: true | false
```

Then route based on the classification, not only words.

For example:

```text
"Please investigate why checkout is slow, fix it, test it, and explain the change."
```

should be classified as:

```text
task_type: coding
complexity: large
needs_subagents: true
needs_verification: true
```

---

### 2. Always create a task contract first

Before execution, create a durable contract containing:

- objective
- expected deliverables
- allowed files/systems
- verification commands
- time/token/cost budget
- approval requirements
- definition of done

If the request is vague, the system should ask for clarification before doing dangerous work.

---

### 3. Add a persistent supervisor loop

Instead of one executor stopping permanently at step 12:

```text
Supervisor
   ├── starts executor
   ├── saves checkpoint
   ├── evaluates progress
   ├── starts another executor if unfinished
   ├── replans when necessary
   └── stops only when done, blocked, unsafe, or budget exhausted
```

`MAX_STEPS = 12` can remain as a per-run limit, but the supervisor can start another run using the saved state.

The total mission still needs a larger limit, for example:

```text
maximum mission time
maximum total tool calls
maximum total cost
maximum repair attempts
maximum repeated actions
```

This gives you long-running execution without an infinite loop.

---

### 4. Make checkpoints first-class

After every important action, save:

- current plan
- completed tasks
- pending tasks
- tool results
- changed files
- test results
- failures
- next recommended action
- current budget
- mission status

If the process crashes or reaches step 12, the next run resumes from the checkpoint instead of starting over.

---

### 5. Make planning hierarchical

Use three planning levels:

```text
Mission plan
   └── Phase plan
          └── Executor steps
```

Example:

```text
Mission: Fix authentication bug

Phase 1: Understand system
Phase 2: Implement fix
Phase 3: Test
Phase 4: Review
Phase 5: Prepare final result
```

Each phase can use several executor runs and several subagents.

This is much more reliable than asking one agent to solve everything in one loop.

---

### 6. Use adaptive orchestration

The system should decide dynamically:

- one agent is enough
- several read-only agents should work in parallel
- writing agents must work sequentially
- a specialist is needed
- a failed approach requires replanning
- a human must approve the next action

The model may recommend a plan, but deterministic policy code must validate it.

---

### 7. Add a proper verification pipeline

Never finish only because the model says “done”.

For coding tasks, require:

```text
artifact changed
tests passed
lint/type checks passed where applicable
diff reviewed
no unresolved errors
acceptance criteria satisfied
```

For research tasks, require:

```text
sources collected
claims supported
conflicting information checked
requested format produced
```

For external actions, require:

```text
target confirmed
permission granted
action succeeded
result recorded
```

---

### 8. Improve fallback behavior

A planner fallback should not always reduce the task to one `main_chat` lane.

Fallback planning should inspect the contract and create a minimal safe graph such as:

```text
inspect → implement → test → review
```

For research:

```text
collect → compare → synthesize → review
```

For automation:

```text
validate → execute → verify → report
```

---

## Recommended long-term architecture

```text
Request
  │
  ▼
Intent + risk classifier
  │
  ▼
Goal contract
  │
  ▼
Hierarchical planner
  │
  ▼
Durable mission supervisor
  │
  ├── Executor run 1
  ├── Checkpoint
  ├── Executor run 2
  ├── Replan or repair
  ├── Checkpoint
  └── Verification
  │
  ▼
Completion gate
  │
  ├── completed
  ├── awaiting approval
  ├── blocked
  └── failed
```

## What should remain bounded

Do not remove all limits. Keep:

- per-run step limit
- total mission budget
- tool-call limit
- time limit
- cost limit
- repair limit
- approval gates
- command safety rules
- isolation requirements

The goal is not unlimited autonomy. The goal is:

> Long-running, resumable autonomy with checkpoints, replanning, verification, and safe termination.

That would make DeepSpace substantially more reliable for complex coding and automation tasks while preventing infinite loops, repeated failures, and unsafe actions.
