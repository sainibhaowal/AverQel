"use client";

import { motion, useReducedMotion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Circle,
  ListChecks,
  PauseCircle,
} from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import type { TaskProgress, PersistedTask } from "../_lib/task-progress";

function taskStatusLabel(status: PersistedTask["status"]): string {
  if (status === "in_progress") return "In progress";
  if (status === "completed") return "Complete";
  if (status === "blocked") return "Blocked";
  if (status === "failed") return "Failed";
  return "Pending";
}

function TaskStatusIcon({
  status,
  reduceMotion,
  live = true,
}: {
  status: PersistedTask["status"];
  reduceMotion: boolean;
  live?: boolean;
}) {
  if (status === "completed") {
    return (
      <motion.span
        key="completed"
        initial={reduceMotion ? false : { scale: 0.45, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={
          reduceMotion
            ? { duration: 0.01 }
            : { type: "spring", stiffness: 520, damping: 24 }
        }
        className="inline-flex text-emerald-400"
        aria-label="Complete"
      >
        <CheckCircle2 size={15} />
      </motion.span>
    );
  }

  if (status === "in_progress") {
    if (!live) {
      return <PauseCircle size={15} className="text-amber-300" aria-label="Paused" />;
    }
    return (
      <span
        className="inline-flex h-4 w-4 items-center justify-center gap-[2px]"
        aria-label="In progress"
      >
        {[0, 1, 2].map((index) => (
          <motion.span
            key={index}
            className="h-1 w-1 rounded-full bg-cyan-300"
            animate={
              reduceMotion
                ? undefined
                : { y: [0, -3, 0], opacity: [0.5, 1, 0.5] }
            }
            transition={
              reduceMotion
                ? undefined
                : {
                    duration: 0.72,
                    repeat: Infinity,
                    ease: "easeInOut",
                    delay: index * 0.12,
                  }
            }
          />
        ))}
      </span>
    );
  }

  if (status === "blocked" || status === "failed") {
    return (
      <AlertCircle
        size={15}
        className="text-amber-300"
        aria-label={taskStatusLabel(status)}
      />
    );
  }

  return (
    <Circle size={14} className="text-foreground/30" aria-label="Pending" />
  );
}

export default function DeepSpaceTaskPlanDrawer({
  progress,
  isStreaming,
}: {
  progress: TaskProgress;
  isStreaming: boolean;
}) {
  const reduceMotion = useReducedMotion() ?? false;
  const [expanded, setExpanded] = useState(false);
  const listId = `deepspace-task-plan-${useId().replace(/:/g, "")}`;
  const previousPlanKey = useRef<string | null>(null);
  const planKey = useMemo(
    () =>
      progress.tasks
        .map((task) => `${task.id}:${task.content}`)
        .join("|")
        .slice(0, 8_000),
    [progress.tasks],
  );

  useEffect(() => {
    if (isStreaming && previousPlanKey.current !== planKey) setExpanded(true);
    previousPlanKey.current = planKey;
  }, [isStreaming, planKey]);

  const total = progress.tasks.length;
  const completed = Math.min(Math.max(progress.completed, 0), total);
  const activeTask = progress.tasks.find(
    (task) => task.status === "in_progress",
  );
  const needsAttention = progress.tasks.some(
    (task) => task.status === "blocked" || task.status === "failed",
  );
  const allComplete = total > 0 && completed === total;
  const headerStatus = needsAttention
    ? "Needs attention"
    : allComplete
      ? progress.verified
        ? isStreaming
          ? "Verified · preparing answer"
          : "Complete"
        : isStreaming
          ? "Verifying completion"
          : "Awaiting verification"
      : activeTask
        ? isStreaming
          ? activeTask.active_form || activeTask.content
          : "Paused · retry to continue"
        : isStreaming
          ? "Working through plan"
          : "Plan incomplete";
  const progressPercent = total ? Math.round((completed / total) * 100) : 0;

  return (
    <motion.section
      aria-label="Task plan"
      data-testid="deepspace-task-plan-drawer"
      initial={
        reduceMotion ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.99 }
      }
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 5, scale: 0.99 }}
      transition={
        reduceMotion
          ? { duration: 0.01 }
          : { duration: 0.22, ease: [0.22, 1, 0.36, 1] }
      }
      className="mx-auto mb-2 w-full max-w-[min(100%,74rem)] overflow-hidden rounded-xl border border-cyan-300/15 bg-slate-50/95 shadow-[0_10px_32px_-24px_rgba(34,211,238,0.55)] backdrop-blur-xl dark:bg-[#0b1411]/95"
    >
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={listId}
        onClick={() => setExpanded((value) => !value)}
        className="flex min-h-10 w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-cyan-300/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyan-300/60 sm:px-3.5"
      >
        <ListChecks
          size={15}
          className="shrink-0 text-cyan-700 dark:text-cyan-200"
          aria-hidden="true"
        />
        <span className="shrink-0 text-[10px] font-bold tracking-[0.12em] text-slate-700 uppercase dark:text-foreground/75">
          Task plan
        </span>
        <span className="shrink-0 rounded-lg border border-cyan-600/15 bg-cyan-500/[0.07] px-2 py-0.5 text-[10px] font-semibold tabular-nums text-cyan-800 dark:border-cyan-300/15 dark:text-cyan-100">
          {completed}/{total}
        </span>
        {!expanded && activeTask ? (
          <span
            data-testid="deepspace-active-task-summary"
            className="inline-flex min-w-0 shrink items-center gap-1.5 text-cyan-800 dark:text-cyan-100"
          >
            <TaskStatusIcon
              status={activeTask.status}
              reduceMotion={reduceMotion}
              live={isStreaming}
            />
            <span className="shrink-0 text-[9px] font-semibold tracking-wide uppercase">
              {isStreaming ? "Active" : "Paused"}
            </span>
          </span>
        ) : null}
        <span
          className={`min-w-0 flex-1 truncate text-[11px] ${needsAttention ? "text-amber-700 dark:text-amber-200" : allComplete && progress.verified && !isStreaming ? "text-emerald-700 dark:text-emerald-300" : "text-slate-500 dark:text-foreground/55"}`}
          aria-live="polite"
        >
          {headerStatus}
        </span>
        {expanded ? (
          <ChevronDown
            size={15}
            className="shrink-0 text-slate-400 dark:text-foreground/45"
            aria-hidden="true"
          />
        ) : (
          <ChevronUp
            size={15}
            className="shrink-0 text-slate-400 dark:text-foreground/45"
            aria-hidden="true"
          />
        )}
      </button>

      <div id={listId} aria-hidden={!expanded} className="overflow-hidden">
        <motion.div
          initial={false}
          animate={{
            height: expanded ? "auto" : 0,
            opacity: expanded ? 1 : 0,
          }}
          transition={
            reduceMotion
              ? { duration: 0.01 }
              : {
                  height: { duration: 0.28, ease: [0.22, 1, 0.36, 1] },
                  opacity: { duration: 0.18 },
                }
          }
          className="overflow-hidden"
        >
          <div className="border-t border-cyan-300/10 px-3 pt-2.5 pb-3 sm:px-3.5">
            <div
              className="mb-2 h-1 overflow-hidden rounded-sm bg-slate-200 dark:bg-white/[0.07]"
              role="progressbar"
              aria-label="Task plan completion"
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuenow={completed}
            >
              <motion.div
                className="h-full rounded-sm bg-gradient-to-r from-cyan-500 to-emerald-400 dark:from-cyan-300 dark:to-emerald-300"
                initial={false}
                animate={{ width: `${progressPercent}%` }}
                transition={
                  reduceMotion
                    ? { duration: 0.01 }
                    : { duration: 0.42, ease: "easeOut" }
                }
              />
            </div>
            <ol
              className="max-h-56 space-y-1 overflow-y-auto pr-1"
              aria-label="Planned tasks"
            >
              {progress.tasks.map((task, index) => (
                <motion.li
                  key={task.id || `${task.content}-${index}`}
                  layout={!reduceMotion}
                  transition={
                    reduceMotion
                      ? { duration: 0.01 }
                      : {
                          layout: {
                            duration: 0.28,
                            ease: [0.22, 1, 0.36, 1],
                          },
                        }
                  }
                  className={`flex items-start gap-2.5 rounded-lg px-2 py-2 text-[11px] transition-colors duration-300 ${task.status === "in_progress" && isStreaming ? "bg-cyan-500/[0.07] dark:bg-cyan-300/[0.06]" : ""}`}
                >
                  <span className="mt-px grid h-4 w-4 shrink-0 place-items-center">
                    <TaskStatusIcon
                      status={task.status}
                      reduceMotion={reduceMotion}
                      live={isStreaming}
                    />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span
                      className={`block leading-relaxed ${task.status === "completed" ? "text-slate-400 line-through decoration-emerald-500/40 dark:text-foreground/40" : "text-slate-700 dark:text-foreground/80"}`}
                    >
                      {task.content}
                    </span>
                    {task.status === "in_progress" && isStreaming && task.active_form ? (
                      <span className="mt-0.5 block truncate text-[10px] text-cyan-700 dark:text-cyan-100/65">
                        {task.active_form}
                      </span>
                    ) : null}
                  </span>
                  <span
                    className={`shrink-0 pt-0.5 text-[9px] font-semibold tracking-wide uppercase ${task.status === "completed" ? "text-emerald-700 dark:text-emerald-300" : task.status === "in_progress" && isStreaming ? "text-cyan-700 dark:text-cyan-200" : task.status === "in_progress" || task.status === "blocked" || task.status === "failed" ? "text-amber-700 dark:text-amber-200" : "text-slate-400 dark:text-foreground/35"}`}
                  >
                    {task.status === "in_progress" && !isStreaming
                      ? "Paused"
                      : taskStatusLabel(task.status)}
                  </span>
                </motion.li>
              ))}
            </ol>
            {allComplete && isStreaming ? (
              <div
                className="mt-2 flex items-center gap-2 border-t border-cyan-300/10 pt-2 text-[10px] text-cyan-800 dark:text-cyan-100/65"
                role="status"
              >
                <span
                  className="inline-flex h-4 w-4 items-center justify-center gap-[2px]"
                  aria-hidden="true"
                >
                  {[0, 1, 2].map((index) => (
                    <motion.span
                      key={index}
                      className="h-1 w-1 rounded-full bg-cyan-500 dark:bg-cyan-300"
                      animate={
                        reduceMotion
                          ? undefined
                          : { y: [0, -3, 0], opacity: [0.5, 1, 0.5] }
                      }
                      transition={
                        reduceMotion
                          ? undefined
                          : {
                              duration: 0.72,
                              repeat: Infinity,
                              ease: "easeInOut",
                              delay: index * 0.12,
                            }
                      }
                    />
                  ))}
                </span>
                {progress.verified
                  ? "Task list verified · preparing the final answer"
                  : "Verifying every task before the answer"}
              </div>
            ) : null}
          </div>
        </motion.div>
      </div>
    </motion.section>
  );
}
