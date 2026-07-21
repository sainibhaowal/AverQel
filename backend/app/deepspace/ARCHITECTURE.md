# DeepSpace architecture

DeepSpace is a policy-governed, hierarchical multi-agent orchestration system.
The top-level package contains only domain subpackages; modules belong to the
layer that owns their responsibility.

| Package | Responsibility |
| --- | --- |
| `orchestration` | Public DeepSpace service and federated mission coordination. |
| `execution` | Agent loop, tool catalog, tool contracts, and permissions. |
| `planning` | Mission planning, typed plan schemas, and validation. |
| `missions` | Redis-backed mission registry, event history, lane state, and cancellation. |
| `runtime` | Runtime contexts, events, policies, state transitions, and SSE mapping. |
| `subagents` | Subagent profiles, run registry, execution contexts, and result handling. |
| `policy` | Autonomy and execution authorization rules. |
| `workspace` | Sandboxed workspace access, shell sessions, and workspace modes. |
| `integrations` | Client proxy, exports, and voice integration. |
| `proactive` | Trigger definitions and trigger execution. |
| `memory` | Long-term memory and todo services. |
| `autonomy` | Goal contracts, evidence collection, bounded repair/re-plan decisions, and completion gates. |

## Execution model

Requests enter the agent loop with a goal contract. Each tool result becomes an
observation; the autonomy controller records evidence and chooses `continue`,
`repair`, `replan`, `ask_human`, `stop`, or `finish`. Coding requests require an
artifact change, passing verification, and a reviewed diff before completion.
Mission lanes use validated state transitions and append operator-visible
events. The coding harness adds command/network/timeout/tool-call boundaries and
automatically records a coding mission for a conversation,
then creates a detached Git worktree/branch when the workspace is a Git repo.
The optional container backend mounts that worktree read/write into a
network-disabled disposable container and routes shell verification through
`docker exec`; it is enabled by a coding contract with
`isolation_mode="container"` and an approved image. The application default is
container isolation; deployments without Docker fail closed for coding tasks.

This is not a LangGraph-style checkpointed graph runtime or a Ralph infinite loop:
it is a bounded, policy-governed manager/worker loop with Redis mission state,
typed lane transitions, and evidence-based termination.

Imports must target the owning subpackage, for example:

```python
from app.deepspace.execution.agent_executor import AgentExecutor
from app.deepspace.orchestration.master_orchestrator import MasterOrchestrator
```

Do not add compatibility modules at the package root. They conceal ownership
and reintroduce the flat layout this structure removes.
