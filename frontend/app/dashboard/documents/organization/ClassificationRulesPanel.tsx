"use client";

import Link from "next/link";
import {
  Check,
  ChevronDown,
  Eye,
  Folder,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Save,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchWithAuth } from "@/lib/api";
import { averqelConfirm } from "@/app/components/ui/AverQelDialogHost";
import toast from "react-hot-toast";

type Choice = { id: string; name: string };

function RoundedActionSelect({
  value,
  placeholder,
  options,
  onChange,
}: {
  value: string;
  placeholder: string;
  options: Choice[];
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = options.find((option) => option.id === value)?.name ?? placeholder;

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const choose = (nextValue: string) => {
    onChange(nextValue);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="theme-input flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-sm"
      >
        <span className={value ? "text-foreground" : "text-muted-foreground"}>{selected}</span>
        <ChevronDown size={15} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open ? (
        <div
          role="listbox"
          className="bg-background border-primary/25 absolute inset-x-0 top-full z-50 mt-1 overflow-hidden rounded-xl border p-1 shadow-xl"
        >
          <button
            type="button"
            role="option"
            aria-selected={!value}
            onClick={() => choose("")}
            className={`w-full rounded-lg px-3 py-2 text-left text-sm ${!value ? "bg-primary/10 text-primary" : "text-foreground hover:bg-primary/5"}`}
          >
            {placeholder}
          </button>
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              role="option"
              aria-selected={option.id === value}
              onClick={() => choose(option.id)}
              className={`w-full rounded-lg px-3 py-2 text-left text-sm ${option.id === value ? "bg-primary/10 text-primary" : "text-foreground hover:bg-primary/5"}`}
            >
              {option.name}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

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
type Rule = {
  id: string;
  name: string;
  filename_pattern: string;
  content_type?: string | null;
  tag_id?: string | null;
  tag_name?: string | null;
  folder_id?: string | null;
  folder_name?: string | null;
  priority: number;
  enabled: boolean;
  last_run?: Run | null;
};
type Preview = {
  matched_count: number;
  items: Array<{ document_id: string; filename: string; content_type: string; status: string }>;
};

const emptyForm = {
  name: "",
  filename_pattern: "*",
  content_type: "",
  tag_id: "",
  folder_id: "",
  priority: "100",
  enabled: true,
};

function runLabel(run: Run | null | undefined): string {
  if (!run) return "Never run";
  return `${run.status.replaceAll("_", " ")} · ${run.matched_count} matched · ${run.applied_count} applied${run.failed_count ? ` · ${run.failed_count} failed` : ""}`;
}

export default function ClassificationRulesPanel() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [tags, setTags] = useState<Choice[]>([]);
  const [folders, setFolders] = useState<Choice[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<{ rule: Rule; data: Preview } | null>(null);
  const [history, setHistory] = useState<Record<string, Run[]>>({});
  const [runningId, setRunningId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rulesResponse, tagsResponse, foldersResponse] = (await Promise.all([
        fetchWithAuth("/documents/organization/classification-rules"),
        fetchWithAuth("/documents/organization/tags"),
        fetchWithAuth("/documents/organization/folders"),
      ])) as [Response, Response, Response];
      if (!rulesResponse.ok) throw new Error("Classification rules could not be loaded.");
      setRules(((await rulesResponse.json()) as { items?: Rule[] }).items ?? []);
      if (tagsResponse.ok)
        setTags(((await tagsResponse.json()) as { items?: Choice[] }).items ?? []);
      if (foldersResponse.ok)
        setFolders(((await foldersResponse.json()) as { items?: Choice[] }).items ?? []);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Classification rules could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const actionSummary = useMemo(
    () =>
      [
        form.tag_id
          ? `Tag: ${tags.find((item) => item.id === form.tag_id)?.name ?? "selected"}`
          : null,
        form.folder_id
          ? `Folder: ${folders.find((item) => item.id === form.folder_id)?.name ?? "selected"}`
          : null,
      ].filter(Boolean) as string[],
    [folders, form.folder_id, form.tag_id, tags],
  );

  const setField = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const reset = () => {
    setEditingId(null);
    setForm(emptyForm);
    setPreview(null);
  };

  const save = async () => {
    if (!form.name.trim() || !form.filename_pattern.trim()) {
      toast.error("Rule name and filename pattern are required.");
      return;
    }
    if (!form.tag_id && !form.folder_id) {
      toast.error("Choose a tag or folder action so this rule has a visible effect.");
      return;
    }
    setBusy(true);
    try {
      const endpoint = editingId
        ? `/documents/organization/classification-rules/${editingId}`
        : "/documents/organization/classification-rules";
      const response = (await fetchWithAuth(endpoint, {
        method: editingId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name.trim(),
          filename_pattern: form.filename_pattern.trim(),
          content_type: form.content_type.trim() || null,
          tag_id: form.tag_id || null,
          folder_id: form.folder_id || null,
          priority: Math.max(0, Math.min(10000, Number(form.priority) || 0)),
          enabled: form.enabled,
        }),
      })) as Response;
      if (!response.ok) throw new Error((await response.text()) || "Rule could not be saved.");
      const saved = (await response.json()) as Rule;
      setRules((current) =>
        editingId
          ? current.map((item) => (item.id === saved.id ? saved : item))
          : [...current, saved].sort(
              (a, b) => a.priority - b.priority || a.name.localeCompare(b.name),
            ),
      );
      reset();
      toast.success(editingId ? "Classification rule updated." : "Classification rule created.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Rule could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const edit = (rule: Rule) => {
    setEditingId(rule.id);
    setForm({
      name: rule.name,
      filename_pattern: rule.filename_pattern,
      content_type: rule.content_type ?? "",
      tag_id: rule.tag_id ?? "",
      folder_id: rule.folder_id ?? "",
      priority: String(rule.priority),
      enabled: rule.enabled,
    });
    setPreview(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const remove = async (rule: Rule) => {
    if (!(await averqelConfirm(`Delete classification rule “${rule.name}”?`))) return;
    const response = (await fetchWithAuth(
      `/documents/organization/classification-rules/${rule.id}`,
      { method: "DELETE" },
    )) as Response;
    if (!response.ok) {
      toast.error("Rule could not be deleted.");
      return;
    }
    setRules((current) => current.filter((item) => item.id !== rule.id));
    toast.success("Classification rule deleted.");
  };

  const toggle = async (rule: Rule) => {
    const response = (await fetchWithAuth(
      `/documents/organization/classification-rules/${rule.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !rule.enabled }),
      },
    )) as Response;
    if (!response.ok) {
      toast.error("Rule state could not be changed.");
      return;
    }
    const updated = (await response.json()) as Rule;
    setRules((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    toast.success(updated.enabled ? "Rule enabled." : "Rule disabled.");
  };

  const testRule = async (rule: Rule) => {
    const response = (await fetchWithAuth(
      `/documents/organization/classification-rules/${rule.id}/preview`,
      { method: "POST" },
    )) as Response;
    if (!response.ok) {
      toast.error("Rule preview could not be generated.");
      return;
    }
    const data = (await response.json()) as {
      rule: Rule;
      matched_count: number;
      items: Preview["items"];
    };
    setPreview({ rule: data.rule, data: { matched_count: data.matched_count, items: data.items } });
  };

  const loadHistory = async (rule: Rule) => {
    if (history[rule.id]) {
      setHistory((current) => {
        const next = { ...current };
        delete next[rule.id];
        return next;
      });
      return;
    }
    const response = (await fetchWithAuth(
      `/documents/organization/classification-rules/${rule.id}/runs?limit=20`,
    )) as Response;
    if (!response.ok) {
      toast.error("Run history could not be loaded.");
      return;
    }
    const data = (await response.json()) as { items?: Run[] };
    setHistory((current) => ({ ...current, [rule.id]: data.items ?? [] }));
  };

  const runRule = async (rule: Rule) => {
    if (!rule.enabled) {
      toast.error("Enable the rule before running it.");
      return;
    }
    setRunningId(rule.id);
    try {
      const response = (await fetchWithAuth(
        `/documents/organization/classification-rules/${rule.id}/run`,
        { method: "POST" },
      )) as Response;
      if (!response.ok)
        throw new Error((await response.text()) || "Rule run could not be started.");
      const queued = (await response.json()) as Run;
      for (let attempt = 0; attempt < 120; attempt += 1) {
        const statusResponse = (await fetchWithAuth(
          `/documents/organization/classification-rules/runs/${queued.id}`,
        )) as Response;
        if (!statusResponse.ok) break;
        const status = (await statusResponse.json()) as Run;
        setRules((current) =>
          current.map((item) => (item.id === rule.id ? { ...item, last_run: status } : item)),
        );
        if (["completed", "completed_with_errors", "failed"].includes(status.status)) {
          toast[status.status === "failed" ? "error" : "success"](
            `Rule run ${status.status.replaceAll("_", " ")}: ${status.matched_count} matched, ${status.applied_count} applied${status.failed_count ? `, ${status.failed_count} failed` : ""}.`,
          );
          await load();
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      toast("Rule run is still processing. Refresh to see its final status.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Rule run could not be started.");
    } finally {
      setRunningId(null);
    }
  };

  return (
    <main className="documents-theme-scope mx-auto w-full max-w-[1500px] space-y-6 p-4 md:p-8">
      <Link
        href="/dashboard/documents"
        className="text-muted-foreground hover:text-primary inline-flex items-center gap-2 text-xs font-bold"
      >
        ← Documents Hub
      </Link>
      <header className="theme-panel flex flex-wrap items-center justify-between gap-4 p-6">
        <div>
          <p className="text-primary text-[10px] font-black tracking-[0.2em] uppercase">
            Documents Hub / Organization
          </p>
          <h1 className="text-foreground mt-2 text-2xl font-black">Classification Rules</h1>
          <p className="text-muted-foreground mt-2 text-sm">
            Automatically organize matching documents on upload or apply a rule to existing
            documents.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="theme-pill flex items-center gap-2 px-4 py-2 text-xs font-bold"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </header>

      <section className="grid gap-6 xl:grid-cols-[minmax(330px,0.8fr)_minmax(0,1.2fr)]">
        <div className="theme-panel p-6">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
              {editingId ? "Edit rule" : "Create and configure"}
            </h2>
            {editingId ? (
              <button
                type="button"
                onClick={reset}
                className="text-muted-foreground hover:text-primary flex items-center gap-1 text-xs font-bold"
              >
                <X size={14} /> Cancel
              </button>
            ) : null}
          </div>
          <div className="mt-4 space-y-3">
            <input
              value={form.name}
              onChange={(event) => setField("name", event.target.value)}
              maxLength={128}
              placeholder="Classification rule name"
              aria-label="Classification rule name"
              className="theme-input w-full rounded-xl px-3 py-3 text-sm"
            />
            <input
              value={form.filename_pattern}
              onChange={(event) => setField("filename_pattern", event.target.value)}
              maxLength={256}
              placeholder="Filename pattern, e.g. invoice-*"
              aria-label="Filename pattern"
              className="theme-input w-full rounded-xl px-3 py-3 text-sm"
            />
            <input
              value={form.content_type}
              onChange={(event) => setField("content_type", event.target.value)}
              maxLength={128}
              placeholder="Content type (optional), e.g. application/pdf"
              aria-label="Rule content type"
              className="theme-input w-full rounded-xl px-3 py-3 text-sm"
            />
            <label>
              <span className="text-muted-foreground mb-1 flex items-center gap-1 text-[10px] font-black uppercase">
                <Tag size={12} /> Apply tag
              </span>
              <RoundedActionSelect
                value={form.tag_id}
                placeholder="No tag action"
                options={tags}
                onChange={(value) => setField("tag_id", value)}
              />
            </label>
            <label>
              <span className="text-muted-foreground mb-1 flex items-center gap-1 text-[10px] font-black uppercase">
                <Folder size={12} /> Move to folder
              </span>
              <RoundedActionSelect
                value={form.folder_id}
                placeholder="No folder action"
                options={folders}
                onChange={(value) => setField("folder_id", value)}
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label>
                <span className="text-muted-foreground mb-1 block text-[10px] font-black uppercase">
                  Priority
                </span>
                <input
                  type="number"
                  min={0}
                  max={10000}
                  value={form.priority}
                  onChange={(event) => setField("priority", event.target.value)}
                  className="theme-input w-full rounded-xl px-3 py-3 text-sm"
                />
              </label>
              <label className="border-glass-border flex items-center gap-2 rounded-xl border px-3 py-3 text-sm">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) => setField("enabled", event.target.checked)}
                />{" "}
                <span className="text-xs font-bold">Enabled</span>
              </label>
            </div>
            <div className="bg-primary/5 border-primary/15 rounded-xl border p-3">
              <p className="text-muted-foreground text-[10px] font-black uppercase">
                What this rule will do
              </p>
              <p className="text-foreground mt-1 text-xs">
                Match <strong>{form.filename_pattern || "the filename pattern"}</strong>
                {form.content_type ? ` with ${form.content_type}` : ""} and apply:{" "}
                {actionSummary.length ? actionSummary.join(" · ") : "choose a tag or folder action"}
                .
              </p>
            </div>
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy}
              className="bg-primary text-primary-foreground flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-xs font-black uppercase disabled:opacity-50"
            >
              {editingId ? <Save size={15} /> : <Plus size={15} />}
              {editingId ? "Save changes" : "Create rule"}
            </button>
          </div>
        </div>

        <div className="theme-panel p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
                Configured classification rules
              </h2>
              <p className="text-muted-foreground mt-1 text-xs">
                {rules.length} rule{rules.length === 1 ? "" : "s"} · evaluated by priority
              </p>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {rules.length ? (
              rules.map((rule) => (
                <article
                  key={rule.id}
                  className="border-glass-border bg-background/30 rounded-xl border p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-foreground truncate text-sm font-bold">{rule.name}</h3>
                        <span
                          className={`rounded-full px-2 py-1 text-[9px] font-black uppercase ${rule.enabled ? "bg-primary/10 text-primary" : "bg-foreground/5 text-foreground/50"}`}
                        >
                          {rule.enabled ? "Enabled" : "Disabled"}
                        </span>
                        <span className="text-muted-foreground text-[10px]">
                          Priority {rule.priority}
                        </span>
                      </div>
                      <p className="text-muted-foreground mt-2 text-xs">
                        When filename matches{" "}
                        <code className="text-primary">{rule.filename_pattern}</code>
                        {rule.content_type ? ` and type is ${rule.content_type}` : ""}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {rule.tag_name ? (
                          <span className="bg-primary/10 text-primary rounded-full px-2 py-1 text-[10px]">
                            Tag: {rule.tag_name}
                          </span>
                        ) : null}
                        {rule.folder_name ? (
                          <span className="bg-primary/10 text-primary rounded-full px-2 py-1 text-[10px]">
                            Folder: {rule.folder_name}
                          </span>
                        ) : null}
                        {!rule.tag_name && !rule.folder_name ? (
                          <span className="bg-warning/10 text-warning rounded-full px-2 py-1 text-[10px]">
                            No action configured
                          </span>
                        ) : null}
                      </div>
                      <p className="text-muted-foreground mt-3 text-[10px]">
                        Last run: {runLabel(rule.last_run)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        onClick={() => edit(rule)}
                        aria-label={`Edit ${rule.name}`}
                        className="theme-pill p-2"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => void toggle(rule)}
                        aria-label={rule.enabled ? `Disable ${rule.name}` : `Enable ${rule.name}`}
                        className="theme-pill p-2"
                      >
                        <Check
                          size={14}
                          className={rule.enabled ? "text-primary" : "text-foreground/35"}
                        />
                      </button>
                      <button
                        type="button"
                        onClick={() => void remove(rule)}
                        aria-label={`Delete ${rule.name}`}
                        className="text-danger hover:bg-danger/10 rounded-lg p-2"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void testRule(rule)}
                      className="theme-pill flex items-center gap-2 px-3 py-2 text-[10px] font-black uppercase"
                    >
                      <Eye size={13} /> Test rule
                    </button>
                    <button
                      type="button"
                      onClick={() => void runRule(rule)}
                      disabled={runningId === rule.id || !rule.enabled}
                      className="bg-primary text-primary-foreground flex items-center gap-2 rounded-lg px-3 py-2 text-[10px] font-black uppercase disabled:opacity-50"
                    >
                      <Play size={13} />
                      {runningId === rule.id ? "Applying…" : "Run now"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void loadHistory(rule)}
                      className="theme-pill flex items-center gap-2 px-3 py-2 text-[10px] font-black uppercase"
                    >
                      <ChevronDown size={13} /> History
                    </button>
                  </div>
                  {history[rule.id] ? (
                    <div className="border-glass-border mt-3 space-y-2 border-t pt-3">
                      {history[rule.id].length ? (
                        history[rule.id].map((run) => (
                          <div key={run.id} className="bg-background/30 rounded-lg p-2 text-[10px]">
                            <div className="flex flex-wrap justify-between gap-2">
                              <span className="font-bold">
                                {run.source} · {run.status}
                              </span>
                              <span>
                                {run.matched_count} matched · {run.applied_count} applied ·{" "}
                                {run.failed_count} failed
                              </span>
                            </div>
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
              <p className="text-muted-foreground py-10 text-center text-sm">
                {loading ? "Loading rules…" : "Nothing configured yet."}
              </p>
            )}
          </div>
        </div>
      </section>

      {preview ? (
        <section className="theme-panel p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
                Rule preview: {preview.rule.name}
              </h2>
              <p className="text-primary mt-1 text-xs font-bold">
                {preview.data.matched_count} existing document
                {preview.data.matched_count === 1 ? "" : "s"} match · no changes were made
              </p>
            </div>
            <button
              type="button"
              onClick={() => setPreview(null)}
              className="theme-pill p-2"
              aria-label="Close rule preview"
            >
              <X size={14} />
            </button>
          </div>
          {preview.data.items.length ? (
            <div className="mt-4 grid gap-2 md:grid-cols-2">
              {preview.data.items.map((item) => (
                <Link
                  key={item.document_id}
                  href={`/dashboard/documents/${item.document_id}`}
                  className="border-glass-border hover:border-primary/50 flex items-center justify-between gap-3 rounded-xl border p-3"
                >
                  <span className="truncate text-xs font-bold">{item.filename}</span>
                  <span className="text-muted-foreground shrink-0 text-[10px]">{item.status}</span>
                </Link>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground border-glass-border mt-5 rounded-xl border border-dashed py-8 text-center text-sm">
              No existing documents match this rule.
            </p>
          )}
          <p className="text-muted-foreground mt-3 text-[10px]">
            Run now applies the configured tag and folder actions to all matching documents and
            records the result.
          </p>
        </section>
      ) : null}
    </main>
  );
}
