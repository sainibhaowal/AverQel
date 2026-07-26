"use client";

import { CheckCircle2, Clock3, ListTodo, AlertTriangle } from "lucide-react";

import DeepSpaceInlineMarkdown from "./DeepSpaceInlineMarkdown";

type TodoItem = {
  content?: string;
  activeForm?: string;
  active_form?: string;
  status?: string;
  priority?: number;
  metadata_json?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

function normalizeTodoStatus(status: unknown): string {
  const value = String(status ?? "").toLowerCase();
  if (value === "completed") return "completed";
  if (value === "in_progress") return "in progress";
  if (value === "pending") return "pending";
  return value || "pending";
}

function statusChipClass(status: string): string {
  if (status === "completed") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
  if (status === "in progress") return "border-cyan-500/30 bg-cyan-500/10 text-cyan-300";
  if (status === "pending") return "border-amber-500/30 bg-amber-500/10 text-amber-300";
  return "border-white/10 bg-white/5 text-foreground/50";
}

export function renderStructuredToolInput(toolName: string, toolInput: Record<string, unknown>) {
  if (toolName !== "todo_write") {
    return null;
  }

  const todos = Array.isArray(toolInput.todos) ? (toolInput.todos as TodoItem[]) : [];
  const title = toolInput.title ? String(toolInput.title) : "Task Ledger";

  return (
    <div className="space-y-2 rounded-xl border border-white/8 bg-black/20 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="text-foreground/45 flex items-center gap-2 text-[10px] tracking-[0.28em] uppercase">
        <ListTodo size={12} className="text-primary/70" />
        <span>{title}</span>
      </div>
      <div className="space-y-2">
        {todos.map((todo, idx) => {
          const content = String(todo.content ?? "").trim() || "Untitled task";
          const activeForm = String(todo.activeForm ?? todo.active_form ?? "").trim();
          const status = normalizeTodoStatus(todo.status);
          return (
            <div
              key={`${content}-${idx}`}
              className="rounded-lg border border-white/6 bg-white/[0.02] px-3 py-2.5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="prose prose-invert text-foreground/80 max-w-none text-[12px] leading-relaxed">
                    <DeepSpaceInlineMarkdown content={content} />
                  </div>
                  {activeForm && activeForm !== content ? (
                    <div className="text-foreground/45 mt-1 text-[11px] leading-relaxed">
                      <span className="text-foreground/25">Active form: </span>
                      <DeepSpaceInlineMarkdown content={activeForm} />
                    </div>
                  ) : null}
                </div>
                <span
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-bold tracking-[0.18em] uppercase ${statusChipClass(status)}`}
                >
                  {status === "completed" ? <CheckCircle2 size={10} /> : <Clock3 size={10} />}
                  {status}
                </span>
              </div>
            </div>
          );
        })}
      </div>
      {todos.length === 0 ? (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200/80">
          <AlertTriangle size={12} className="mr-1 inline-block translate-y-[-1px]" />
          No todo items were provided yet.
        </div>
      ) : null}
    </div>
  );
}

export function renderStructuredToolOutput(toolName: string, toolOutput: string) {
  const trimmed = toolOutput.trim();
  if (!trimmed) {
    return null;
  }

  if (toolName === "todo_write") {
    return (
      <div className="space-y-2 rounded-xl border border-white/8 bg-black/20 p-3">
        <div className="text-foreground/45 flex items-center gap-2 text-[10px] tracking-[0.28em] uppercase">
          <ListTodo size={12} className="text-primary/70" />
          <span>Ledger update</span>
        </div>
        <div className="prose prose-invert text-foreground/70 max-w-none text-[11px] leading-relaxed">
          <DeepSpaceInlineMarkdown content={trimmed} />
        </div>
      </div>
    );
  }

  return (
    <div className="prose prose-invert text-foreground/45 custom-scrollbar max-h-[250px] max-w-none overflow-x-auto overflow-y-auto rounded border border-white/5 bg-black/25 p-2 text-[11px] leading-relaxed">
      <DeepSpaceInlineMarkdown content={toolOutput} />
    </div>
  );
}
