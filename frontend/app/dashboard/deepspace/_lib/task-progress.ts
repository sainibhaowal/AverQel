import type { TimelineStep } from "./deepspace-stream";

export type PersistedTask = {
  id: string;
  content: string;
  status: "pending" | "in_progress" | "completed" | "blocked" | "failed";
  active_form?: string;
  priority?: number;
};

export type TaskProgress = {
  tasks: PersistedTask[];
  completed: number;
  verified: boolean;
};

const TASK_STATUSES = new Set<PersistedTask["status"]>([
  "pending",
  "in_progress",
  "completed",
  "blocked",
  "failed",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/** Read the newest persisted task snapshot from one assistant turn's durable tool timeline. */
export function taskProgressFromTimeline(
  timeline: TimelineStep[],
): TaskProgress | null {
  for (let index = timeline.length - 1; index >= 0; index -= 1) {
    const step = timeline[index];
    if (step?.toolName !== "todo_write" || step.status === "failed") {
      continue;
    }

    try {
      const payloadValue: unknown = JSON.parse(step.toolOutput || "");
      if (!isRecord(payloadValue)) continue;
      const taskCheck = isRecord(payloadValue.task_check)
        ? payloadValue.task_check
        : payloadValue;
      const rawTasks = Array.isArray(taskCheck.tasks)
        ? taskCheck.tasks
        : Array.isArray(payloadValue.tasks)
          ? payloadValue.tasks
          : null;
      if (!rawTasks) continue;
      if (rawTasks.length === 0) return null;

      const tasks = rawTasks
        .slice(0, 40)
        .flatMap((item, taskIndex): PersistedTask[] => {
          if (!isRecord(item)) return [];
          const rawStatus = String(item.status ?? "pending").toLowerCase();
          const status = TASK_STATUSES.has(rawStatus as PersistedTask["status"])
            ? (rawStatus as PersistedTask["status"])
            : "pending";
          const content = String(item.content ?? "Untitled task")
            .trim()
            .slice(0, 1_000);
          if (!content) return [];
          const activeForm = String(item.active_form ?? item.activeForm ?? "")
            .trim()
            .slice(0, 1_000);
          const priority =
            typeof item.priority === "number" && Number.isFinite(item.priority)
              ? Math.max(0, Math.floor(item.priority))
              : taskIndex;
          return [
            {
              id: String(item.id ?? `task-${taskIndex}`).slice(0, 80),
              content,
              status,
              ...(activeForm ? { active_form: activeForm } : {}),
              priority,
            },
          ];
        })
        .sort((left, right) => (left.priority ?? 0) - (right.priority ?? 0));
      if (!tasks.length) return null;

      const completedCount =
        typeof taskCheck.completed_count === "number" &&
        Number.isFinite(taskCheck.completed_count)
          ? Math.min(
              tasks.length,
              Math.max(0, Math.floor(taskCheck.completed_count)),
            )
          : tasks.filter((task) => task.status === "completed").length;
      return {
        tasks,
        completed: completedCount,
        verified:
          step.toolInput?.operation === "check" && step.status === "completed",
      };
    } catch {
      // A malformed or truncated tool result cannot be presented as verified task state.
    }
  }
  return null;
}
