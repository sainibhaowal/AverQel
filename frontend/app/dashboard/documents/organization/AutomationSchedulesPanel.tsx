"use client";

import Link from "next/link";
import {
  ArrowLeft,
  Check,
  Clock3,
  ChevronDown,
  History,
  Pencil,
  Play,
  RefreshCw,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchWithAuth } from "@/lib/api";
import { averqelConfirm } from "@/app/components/ui/AverQelDialogHost";
import toast from "react-hot-toast";

type Rule = { id: string; name: string; enabled: boolean; priority: number };
type Run = {
  id: string;
  source: string;
  status: string;
  scanned_count: number;
  matched_count: number;
  applied_count: number;
  failed_count: number;
  error_message?: string | null;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
};
type Schedule = {
  id: string;
  name: string;
  interval_seconds: number;
  cadence: "interval" | "hourly" | "daily" | "weekly";
  timezone: string;
  run_time?: string | null;
  weekday?: number | null;
  enabled: boolean;
  rule_ids: string[];
  rule_names: string[];
  runs_all_enabled_rules: boolean;
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_run?: Run | null;
};

const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const cadenceOptions = [
  { value: "interval", label: "Custom interval" },
  { value: "hourly", label: "Every hour" },
  { value: "daily", label: "Every day" },
  { value: "weekly", label: "Every week" },
];

const emptyForm = {
  name: "",
  cadence: "daily" as Schedule["cadence"],
  interval_seconds: "3600",
  timezone: "UTC",
  run_time: "09:00",
  weekday: "0",
  enabled: true,
};

function OptionSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value)?.label ?? value;
  return (
    <div className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="theme-input flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-sm"
      >
        {selected}
        <ChevronDown size={15} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open ? (
        <div
          className="bg-background border-primary/25 absolute inset-x-0 top-full z-50 mt-1 overflow-hidden rounded-xl border p-1 shadow-xl"
          role="listbox"
        >
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={option.value === value}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              className={`w-full rounded-lg px-3 py-2 text-left text-sm ${option.value === value ? "bg-primary/10 text-primary" : "text-foreground hover:bg-primary/5"}`}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function formatInterval(seconds: number): string {
  if (seconds % 86_400 === 0)
    return `Every ${seconds / 86_400} day${seconds === 86_400 ? "" : "s"}`;
  if (seconds % 3_600 === 0) return `Every ${seconds / 3_600} hour${seconds === 3_600 ? "" : "s"}`;
  if (seconds % 60 === 0) return `Every ${seconds / 60} minute${seconds === 60 ? "" : "s"}`;
  return `Every ${seconds} seconds`;
}

function scheduleDescription(schedule: Schedule): string {
  if (schedule.cadence === "interval")
    return `${formatInterval(schedule.interval_seconds)} · ${schedule.timezone}`;
  if (schedule.cadence === "hourly") return `Every hour · ${schedule.timezone}`;
  if (schedule.cadence === "weekly") {
    return `Every ${weekdays[schedule.weekday ?? 0]} at ${schedule.run_time ?? "00:00"} · ${schedule.timezone}`;
  }
  return `Every day at ${schedule.run_time ?? "00:00"} · ${schedule.timezone}`;
}

function runSummary(run: Run | null | undefined): string {
  if (!run) return "No runs yet";
  return `${run.status.replaceAll("_", " ")} · ${run.matched_count} matched · ${run.applied_count} applied · ${run.failed_count} failed`;
}

export default function AutomationSchedulesPanel() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [selectedRuleIds, setSelectedRuleIds] = useState<string[]>([]);
  const [allEnabledRules, setAllEnabledRules] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [history, setHistory] = useState<Record<string, Run[]>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [scheduleResponse, ruleResponse] = (await Promise.all([
        fetchWithAuth("/documents/organization/automation-schedules"),
        fetchWithAuth("/documents/organization/classification-rules"),
      ])) as [Response, Response];
      if (!scheduleResponse.ok) throw new Error("Automation schedules could not be loaded.");
      setSchedules(((await scheduleResponse.json()) as { items?: Schedule[] }).items ?? []);
      if (ruleResponse.ok)
        setRules(((await ruleResponse.json()) as { items?: Rule[] }).items ?? []);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Automation schedules could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const reset = () => {
    setEditingId(null);
    setForm(emptyForm);
    setSelectedRuleIds([]);
    setAllEnabledRules(true);
  };

  const setField = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const save = async () => {
    if (!form.name.trim()) {
      toast.error("Schedule name is required.");
      return;
    }
    if (!allEnabledRules && selectedRuleIds.length === 0) {
      toast.error("Select at least one classification rule or choose all enabled rules.");
      return;
    }
    if ((form.cadence === "daily" || form.cadence === "weekly") && !form.run_time) {
      toast.error("Choose a run time.");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        name: form.name.trim(),
        cadence: form.cadence,
        interval_seconds: Math.max(60, Number(form.interval_seconds) || 3600),
        timezone: form.timezone.trim() || "UTC",
        run_time: form.cadence === "interval" || form.cadence === "hourly" ? null : form.run_time,
        weekday: form.cadence === "weekly" ? Number(form.weekday) : null,
        enabled: form.enabled,
        rule_ids: allEnabledRules ? null : selectedRuleIds,
      };
      const endpoint = editingId
        ? `/documents/organization/automation-schedules/${editingId}`
        : "/documents/organization/automation-schedules";
      const response = (await fetchWithAuth(endpoint, {
        method: editingId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })) as Response;
      if (!response.ok) throw new Error((await response.text()) || "Schedule could not be saved.");
      const saved = (await response.json()) as Schedule;
      setSchedules((current) =>
        editingId
          ? current.map((item) => (item.id === saved.id ? saved : item))
          : [...current, saved].sort((a, b) => a.name.localeCompare(b.name)),
      );
      reset();
      toast.success(editingId ? "Schedule updated." : "Schedule created.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Schedule could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const edit = (schedule: Schedule) => {
    setEditingId(schedule.id);
    setForm({
      name: schedule.name,
      cadence: schedule.cadence,
      interval_seconds: String(schedule.interval_seconds),
      timezone: schedule.timezone,
      run_time: schedule.run_time ?? "09:00",
      weekday: String(schedule.weekday ?? 0),
      enabled: schedule.enabled,
    });
    setSelectedRuleIds(schedule.rule_ids);
    setAllEnabledRules(schedule.runs_all_enabled_rules);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const toggle = async (schedule: Schedule) => {
    const response = (await fetchWithAuth(
      `/documents/organization/automation-schedules/${schedule.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !schedule.enabled }),
      },
    )) as Response;
    if (!response.ok) {
      toast.error("Schedule could not be updated.");
      return;
    }
    const updated = (await response.json()) as Schedule;
    setSchedules((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    toast.success(updated.enabled ? "Schedule enabled." : "Schedule disabled.");
  };

  const remove = async (schedule: Schedule) => {
    if (!(await averqelConfirm(`Delete schedule “${schedule.name}”?`))) return;
    const response = (await fetchWithAuth(
      `/documents/organization/automation-schedules/${schedule.id}`,
      { method: "DELETE" },
    )) as Response;
    if (!response.ok) {
      toast.error("Schedule could not be deleted.");
      return;
    }
    setSchedules((current) => current.filter((item) => item.id !== schedule.id));
    toast.success("Schedule deleted.");
  };

  const loadHistory = async (schedule: Schedule) => {
    const response = (await fetchWithAuth(
      `/documents/organization/automation-schedules/${schedule.id}/runs?limit=20`,
    )) as Response;
    if (!response.ok) {
      toast.error("Schedule history could not be loaded.");
      return;
    }
    const data = (await response.json()) as { items?: Run[] };
    setHistory((current) => ({ ...current, [schedule.id]: data.items ?? [] }));
  };

  const runNow = async (schedule: Schedule) => {
    setRunningId(schedule.id);
    try {
      const response = (await fetchWithAuth(
        `/documents/organization/automation-schedules/${schedule.id}/run`,
        { method: "POST" },
      )) as Response;
      if (!response.ok)
        throw new Error((await response.text()) || "Schedule run could not be started.");
      const queued = (await response.json()) as Run;
      for (let attempt = 0; attempt < 120; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const statusResponse = (await fetchWithAuth(
          `/documents/organization/automation-schedules/runs/${queued.id}`,
        )) as Response;
        if (!statusResponse.ok) continue;
        const status = (await statusResponse.json()) as Run;
        if (!["queued", "running"].includes(status.status)) {
          setSchedules((current) =>
            current.map((item) =>
              item.id === schedule.id
                ? { ...item, last_run: status, last_run_at: status.completed_at }
                : item,
            ),
          );
          toast[status.status === "failed" ? "error" : "success"](
            `Schedule ${status.status.replaceAll("_", " ")}: ${status.matched_count} matched, ${status.applied_count} applied, ${status.failed_count} failed.`,
          );
          return;
        }
      }
      toast("Schedule is still processing. Refresh to see the result.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Schedule run could not be started.");
    } finally {
      setRunningId(null);
    }
  };

  const enabledRules = useMemo(() => rules.filter((rule) => rule.enabled), [rules]);
  const ruleSummary = allEnabledRules
    ? "All enabled classification rules"
    : `${selectedRuleIds.length} selected rule${selectedRuleIds.length === 1 ? "" : "s"}`;

  return (
    <main className="documents-theme-scope mx-auto w-full max-w-[1500px] space-y-6 p-4 md:p-8">
      <Link
        href="/dashboard/documents"
        className="text-muted-foreground hover:text-primary inline-flex items-center gap-2 text-xs font-bold"
      >
        <ArrowLeft size={15} /> Documents Hub
      </Link>
      <header className="theme-panel flex flex-wrap items-center justify-between gap-4 p-6">
        <div>
          <p className="text-primary text-[10px] font-black tracking-[0.2em] uppercase">
            Documents Hub / Organization
          </p>
          <h1 className="text-foreground mt-2 text-2xl font-black">Automation Schedules</h1>
          <p className="text-muted-foreground mt-2 text-sm">
            Run selected classification rules on a reliable recurring schedule.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="theme-pill flex items-center gap-2 px-4 py-2 text-xs font-bold"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </header>
      <section className="grid gap-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div className="theme-panel p-6">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
              {editingId ? "Edit schedule" : "Create and configure"}
            </h2>
            {editingId ? (
              <button
                type="button"
                onClick={reset}
                className="theme-pill p-2"
                aria-label="Cancel editing"
              >
                <X size={14} />
              </button>
            ) : null}
          </div>
          <div className="mt-4 space-y-3">
            <input
              value={form.name}
              onChange={(event) => setField("name", event.target.value)}
              placeholder="Schedule name"
              className="theme-input w-full rounded-xl px-3 py-3 text-sm"
            />
            <OptionSelect
              value={form.cadence}
              options={cadenceOptions}
              onChange={(value) => setField("cadence", value as Schedule["cadence"])}
            />
            {form.cadence === "interval" ? (
              <input
                value={form.interval_seconds}
                onChange={(event) => setField("interval_seconds", event.target.value)}
                type="number"
                min="60"
                placeholder="Interval seconds"
                className="theme-input w-full rounded-xl px-3 py-3 text-sm"
              />
            ) : null}
            {form.cadence === "daily" || form.cadence === "weekly" ? (
              <input
                value={form.run_time}
                onChange={(event) => setField("run_time", event.target.value)}
                type="time"
                className="theme-input w-full rounded-xl px-3 py-3 text-sm"
              />
            ) : null}
            {form.cadence === "weekly" ? (
              <OptionSelect
                value={form.weekday}
                options={weekdays.map((label, value) => ({ value: String(value), label }))}
                onChange={(value) => setField("weekday", value)}
              />
            ) : null}
            <input
              value={form.timezone}
              onChange={(event) => setField("timezone", event.target.value)}
              placeholder="Timezone, e.g. Europe/Berlin"
              className="theme-input w-full rounded-xl px-3 py-3 text-sm"
            />
            <div className="border-primary/15 bg-primary/5 rounded-xl border p-3">
              <p className="text-primary text-[10px] font-black uppercase">Rules to run</p>
              <label className="text-foreground mt-2 flex items-center gap-2 text-xs font-bold">
                <input
                  type="checkbox"
                  checked={allEnabledRules}
                  onChange={(event) => setAllEnabledRules(event.target.checked)}
                />{" "}
                All enabled rules
              </label>
              {!allEnabledRules ? (
                <div className="mt-2 max-h-36 space-y-1 overflow-auto">
                  {rules.map((rule) => (
                    <label
                      key={rule.id}
                      className="text-muted-foreground flex items-center gap-2 text-xs"
                    >
                      <input
                        type="checkbox"
                        checked={selectedRuleIds.includes(rule.id)}
                        onChange={() =>
                          setSelectedRuleIds((current) =>
                            current.includes(rule.id)
                              ? current.filter((id) => id !== rule.id)
                              : [...current, rule.id],
                          )
                        }
                      />{" "}
                      {rule.name}
                      {rule.enabled ? "" : " (disabled)"}
                    </label>
                  ))}
                </div>
              ) : null}
              <p className="text-muted-foreground mt-2 text-[10px]">
                {ruleSummary}. Disabled rules are always skipped.
              </p>
            </div>
            <label className="border-glass-border bg-background/30 flex items-center gap-2 rounded-xl border px-3 py-3 text-xs font-bold">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => setField("enabled", event.target.checked)}
              />{" "}
              Enabled
            </label>
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy}
              className="bg-primary text-primary-foreground flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-xs font-black uppercase disabled:opacity-50"
            >
              <Save size={15} /> {editingId ? "Save schedule" : "Create schedule"}
            </button>
          </div>
        </div>
        <div className="theme-panel p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
              Configured schedules
            </h2>
            <span className="text-muted-foreground text-xs">{schedules.length} total</span>
          </div>
          <div className="mt-4 space-y-3">
            {schedules.length ? (
              schedules.map((schedule) => (
                <article
                  key={schedule.id}
                  className="border-glass-border bg-background/30 rounded-xl border p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-foreground truncate text-sm font-bold">
                        {schedule.name}
                      </h3>
                      <p className="text-muted-foreground mt-1 text-[10px]">
                        {scheduleDescription(schedule)} ·{" "}
                        {schedule.enabled ? "Enabled" : "Disabled"}
                      </p>
                      <p className="text-muted-foreground mt-1 text-[10px]">
                        {schedule.runs_all_enabled_rules
                          ? "All enabled rules"
                          : schedule.rule_names.join(", ") || "No rules selected"}
                      </p>
                      <p className="text-primary mt-1 text-[10px]">
                        Next: {schedule.next_run_at ?? "pending"} · Last:{" "}
                        {schedule.last_run_at ?? "never"}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        onClick={() => edit(schedule)}
                        className="theme-pill p-2"
                        aria-label={`Edit ${schedule.name}`}
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => void toggle(schedule)}
                        className={`theme-pill p-2 ${schedule.enabled ? "text-primary" : "text-foreground/40"}`}
                        aria-label={
                          schedule.enabled ? `Disable ${schedule.name}` : `Enable ${schedule.name}`
                        }
                      >
                        <Check size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => void remove(schedule)}
                        className="text-danger hover:bg-danger/10 rounded-lg p-2"
                        aria-label={`Delete ${schedule.name}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void runNow(schedule)}
                      disabled={runningId === schedule.id}
                      className="bg-primary text-primary-foreground flex items-center gap-1 rounded-lg px-3 py-2 text-[10px] font-black uppercase disabled:opacity-50"
                    >
                      <Play size={12} /> {runningId === schedule.id ? "Running…" : "Run now"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void loadHistory(schedule)}
                      className="theme-pill flex items-center gap-1 px-3 py-2 text-[10px] font-bold uppercase"
                    >
                      <History size={12} /> History
                    </button>
                  </div>
                  <p className="text-muted-foreground mt-2 flex items-center gap-1 text-[10px]">
                    <Clock3 size={12} /> {runSummary(schedule.last_run)}
                  </p>
                  {history[schedule.id] ? (
                    <div className="border-primary/10 mt-3 space-y-2 border-t pt-3">
                      {history[schedule.id].length ? (
                        history[schedule.id].map((run) => (
                          <div key={run.id} className="bg-background/30 rounded-lg p-2 text-[10px]">
                            <p className="font-bold">
                              {run.source} · {run.status}
                            </p>
                            <p className="text-muted-foreground">
                              {run.scanned_count} scanned · {run.matched_count} matched ·{" "}
                              {run.applied_count} applied · {run.failed_count} failed
                            </p>
                            {run.error_message ? (
                              <p className="text-danger mt-1">{run.error_message}</p>
                            ) : null}
                          </div>
                        ))
                      ) : (
                        <p className="text-muted-foreground text-[10px]">No runs recorded.</p>
                      )}
                    </div>
                  ) : null}
                </article>
              ))
            ) : (
              <div className="py-16 text-center">
                <p className="text-muted-foreground text-sm">Nothing configured yet.</p>
                <p className="text-muted-foreground mt-2 text-xs">
                  Create a schedule to run selected rules automatically.
                </p>
              </div>
            )}
          </div>
        </div>
      </section>
      <p className="text-muted-foreground text-xs">
        {enabledRules.length} enabled classification rule{enabledRules.length === 1 ? "" : "s"}{" "}
        available. Schedules process documents in batches and preserve per-document history.
      </p>
    </main>
  );
}
