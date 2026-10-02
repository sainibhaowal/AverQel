"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  Clock3,
  Eye,
  History,
  Pencil,
  Play,
  RefreshCw,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchWithAuth } from "@/lib/api";
import { averqelConfirm } from "@/app/components/ui/AverQelDialogHost";
import toast from "react-hot-toast";

type Choice = { id: string; name: string };
type Condition = { field: string; operator: string; value: string };
type Evaluation = {
  id: string;
  status: string;
  scanned_count: number;
  matched_count: number;
  duration_ms: number;
  error_message?: string | null;
  created_at?: string;
  completed_at?: string | null;
};
type Collection = {
  id: string;
  name: string;
  match_mode: "all" | "any";
  conditions: Condition[];
  enabled: boolean;
  match_count?: number | null;
  match_count_stale?: boolean;
  created_at?: string;
  updated_at?: string;
  last_evaluation?: Evaluation | null;
};
type Result = {
  document_id: string;
  filename: string;
  status: string;
  content_type: string;
  quarantined: boolean;
  extraction_coverage_score?: number | null;
};
type EvaluationPage = {
  page: number;
  page_size: number;
  total: number;
  scanned_count: number;
  duration_ms: number;
  evaluated_at?: string;
  evaluation?: Evaluation | null;
  items: Result[];
};

const fieldOptions = [
  ["status", "Status"],
  ["quarantined", "Quarantined"],
  ["ocr_confidence", "OCR confidence"],
  ["content_type", "Content type"],
  ["filename", "Filename"],
  ["tag", "Tag"],
  ["folder", "Folder"],
] as const;
const stringOperators = [
  ["equals", "Equals"],
  ["not_equals", "Does not equal"],
  ["contains", "Contains"],
  ["starts_with", "Starts with"],
] as const;
const numericOperators = [
  ["equals", "Equals"],
  ["not_equals", "Does not equal"],
  ["greater_than", "Greater than"],
  ["less_than", "Less than"],
] as const;
const booleanOperators = [
  ["equals", "Equals"],
  ["not_equals", "Does not equal"],
] as const;
const relationOperators = [
  ["equals", "Has"],
  ["not_equals", "Does not have"],
] as const;

function optionsForField(field: string): ReadonlyArray<readonly [string, string]> {
  if (field === "ocr_confidence") return numericOperators;
  if (field === "quarantined") return booleanOperators;
  if (field === "tag" || field === "folder") return relationOperators;
  return stringOperators;
}

function OptionSelect({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: string;
  options: ReadonlyArray<readonly [string, string]>;
  onChange: (value: string) => void;
  ariaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const label = options.find(([key]) => key === value)?.[1] ?? value;
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <div ref={rootRef} className="relative min-w-0 flex-1">
      <button
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="theme-input flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-xs"
      >
        {label}
        <ChevronDown size={14} className={open ? "rotate-180" : ""} />
      </button>
      {open ? (
        <div
          className="bg-background border-primary/25 absolute inset-x-0 top-full z-50 mt-1 rounded-xl border p-1 shadow-xl"
          role="listbox"
        >
          {options.map(([key, optionLabel]) => (
            <button
              key={key}
              type="button"
              role="option"
              aria-selected={key === value}
              onClick={() => {
                onChange(key);
                setOpen(false);
              }}
              className={`w-full rounded-lg px-3 py-2 text-left text-xs ${key === value ? "bg-primary/10 text-primary" : "text-foreground hover:bg-primary/5"}`}
            >
              {optionLabel}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function conditionLabel(condition: Condition, tags: Choice[], folders: Choice[]): string {
  const field = fieldOptions.find(([key]) => key === condition.field)?.[1] ?? condition.field;
  const operator =
    optionsForField(condition.field).find(([key]) => key === condition.operator)?.[1] ??
    condition.operator;
  const choices = condition.field === "tag" ? tags : condition.field === "folder" ? folders : [];
  const value = choices.find((choice) => choice.id === condition.value)?.name ?? condition.value;
  return `${field} ${operator.toLowerCase()} ${value}`;
}

const emptyCondition = (): Condition => ({ field: "status", operator: "equals", value: "" });

export default function SmartCollectionsPanel() {
  const router = useRouter();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [tags, setTags] = useState<Choice[]>([]);
  const [folders, setFolders] = useState<Choice[]>([]);
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"all" | "any">("all");
  const [conditions, setConditions] = useState<Condition[]>([emptyCondition()]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [history, setHistory] = useState<Record<string, Evaluation[]>>({});
  const [preview, setPreview] = useState<{ id: string; data: EvaluationPage } | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const responses = (await Promise.all([
        fetchWithAuth("/documents/organization/smart-collections"),
        fetchWithAuth("/documents/organization/tags"),
        fetchWithAuth("/documents/organization/folders"),
      ])) as Response[];
      if (!responses[0].ok) throw new Error("Smart Collections could not be loaded.");
      setCollections(((await responses[0].json()) as { items?: Collection[] }).items ?? []);
      if (responses[1].ok)
        setTags(((await responses[1].json()) as { items?: Choice[] }).items ?? []);
      if (responses[2].ok)
        setFolders(((await responses[2].json()) as { items?: Choice[] }).items ?? []);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Smart Collections could not be loaded.",
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
    setName("");
    setMode("all");
    setConditions([emptyCondition()]);
  };

  const updateCondition = (index: number, next: Partial<Condition>) => {
    setConditions((current) =>
      current.map((condition, itemIndex) => {
        if (itemIndex !== index) return condition;
        const updated = { ...condition, ...next };
        if (next.field && next.field !== condition.field) {
          updated.operator = optionsForField(next.field)[0][0];
          updated.value = next.field === "quarantined" ? "true" : "";
        }
        return updated;
      }),
    );
  };

  const save = async () => {
    if (!name.trim() || conditions.some((condition) => !condition.value.trim())) {
      toast.error("Provide a name and a value for every condition.");
      return;
    }
    setBusy(true);
    try {
      const endpoint = editingId
        ? `/documents/organization/smart-collections/${editingId}`
        : "/documents/organization/smart-collections";
      const response = (await fetchWithAuth(endpoint, {
        method: editingId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), match_mode: mode, conditions }),
      })) as Response;
      if (!response.ok)
        throw new Error((await response.text()) || "Smart Collection could not be saved.");
      const saved = (await response.json()) as Collection;
      setCollections((current) =>
        editingId
          ? current.map((item) => (item.id === saved.id ? saved : item))
          : [...current, saved].sort((a, b) => a.name.localeCompare(b.name)),
      );
      reset();
      toast.success(editingId ? "Smart Collection updated." : "Smart Collection created.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Smart Collection could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const edit = (collection: Collection) => {
    setEditingId(collection.id);
    setName(collection.name);
    setMode(collection.match_mode);
    setConditions(
      collection.conditions.map((condition) => ({ ...condition, value: String(condition.value) })),
    );
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const toggle = async (collection: Collection) => {
    const response = (await fetchWithAuth(
      `/documents/organization/smart-collections/${collection.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !collection.enabled }),
      },
    )) as Response;
    if (!response.ok) {
      toast.error("Smart Collection could not be updated.");
      return;
    }
    const updated = (await response.json()) as Collection;
    setCollections((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    toast.success(updated.enabled ? "Smart Collection enabled." : "Smart Collection disabled.");
  };

  const remove = async (collection: Collection) => {
    if (!(await averqelConfirm(`Delete Smart Collection “${collection.name}”?`))) return;
    const response = (await fetchWithAuth(
      `/documents/organization/smart-collections/${collection.id}`,
      { method: "DELETE" },
    )) as Response;
    if (!response.ok) {
      toast.error("Smart Collection could not be deleted.");
      return;
    }
    setCollections((current) => current.filter((item) => item.id !== collection.id));
    if (preview?.id === collection.id) setPreview(null);
    toast.success("Smart Collection deleted.");
  };

  const evaluate = async (collection: Collection, page = 1) => {
    const response = (await fetchWithAuth(
      `/documents/organization/smart-collections/${collection.id}/evaluate?page=${page}&page_size=25`,
      { method: "POST" },
    )) as Response;
    if (!response.ok) {
      toast.error((await response.text()) || "Smart Collection evaluation failed.");
      return;
    }
    const data = (await response.json()) as EvaluationPage;
    setPreview({ id: collection.id, data });
    setCollections((current) =>
      current.map((item) =>
        item.id === collection.id
          ? {
              ...item,
              match_count: data.total,
              match_count_stale: false,
              last_evaluation: data.evaluation,
            }
          : item,
      ),
    );
    toast.success(`${data.total} matching document${data.total === 1 ? "" : "s"} found.`);
  };

  const loadHistory = async (collection: Collection) => {
    const response = (await fetchWithAuth(
      `/documents/organization/smart-collections/${collection.id}/evaluations?limit=20`,
    )) as Response;
    if (!response.ok) {
      toast.error("Evaluation history could not be loaded.");
      return;
    }
    const data = (await response.json()) as { items?: Evaluation[] };
    setHistory((current) => ({ ...current, [collection.id]: data.items ?? [] }));
  };

  const availableChoices = (field: string) =>
    field === "tag" ? tags : field === "folder" ? folders : [];
  const conditionCountLabel = useMemo(
    () => `${conditions.length} condition${conditions.length === 1 ? "" : "s"}`,
    [conditions.length],
  );

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
          <h1 className="text-foreground mt-2 text-2xl font-black">Smart Collections</h1>
          <p className="text-muted-foreground mt-2 text-sm">
            Dynamic document groups recalculated from live, tenant-safe rules.
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
      <section className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div className="theme-panel p-6">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
              {editingId ? "Edit Smart Collection" : "Create and configure"}
            </h2>
            {editingId ? (
              <button
                type="button"
                onClick={reset}
                aria-label="Cancel editing"
                className="theme-pill p-2"
              >
                <X size={14} />
              </button>
            ) : null}
          </div>
          <div className="mt-4 space-y-3">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Smart Collection name"
              className="theme-input w-full rounded-xl px-3 py-3 text-sm"
            />
            <OptionSelect
              value={mode}
              options={[
                ["all", "Match all conditions"],
                ["any", "Match any condition"],
              ]}
              onChange={(value) => setMode(value as "all" | "any")}
              ariaLabel="Condition match mode"
            />
            {conditions.map((condition, index) => (
              <div
                key={`${index}-${condition.field}`}
                className="border-primary/15 bg-primary/5 rounded-xl border p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-primary text-[10px] font-black uppercase">
                    Condition {index + 1}
                  </p>
                  {conditions.length > 1 ? (
                    <button
                      type="button"
                      aria-label={`Remove condition ${index + 1}`}
                      onClick={() =>
                        setConditions((current) =>
                          current.filter((_, itemIndex) => itemIndex !== index),
                        )
                      }
                      className="text-muted-foreground hover:text-danger"
                    >
                      <X size={14} />
                    </button>
                  ) : null}
                </div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <OptionSelect
                    value={condition.field}
                    options={fieldOptions}
                    onChange={(value) => updateCondition(index, { field: value })}
                    ariaLabel={`Condition ${index + 1} field`}
                  />
                  <OptionSelect
                    value={condition.operator}
                    options={optionsForField(condition.field)}
                    onChange={(value) => updateCondition(index, { operator: value })}
                    ariaLabel={`Condition ${index + 1} operator`}
                  />
                </div>
                {condition.field === "tag" || condition.field === "folder" ? (
                  <OptionSelect
                    value={condition.value}
                    options={[
                      ["", condition.field === "tag" ? "Choose a tag" : "Choose a folder"],
                      ...availableChoices(condition.field).map(
                        (choice) => [choice.id, choice.name] as const,
                      ),
                    ]}
                    onChange={(value) => updateCondition(index, { value })}
                    ariaLabel={`Condition ${index + 1} value`}
                  />
                ) : condition.field === "quarantined" ? (
                  <OptionSelect
                    value={condition.value || "true"}
                    options={[
                      ["true", "Yes"],
                      ["false", "No"],
                    ]}
                    onChange={(value) => updateCondition(index, { value })}
                    ariaLabel={`Condition ${index + 1} value`}
                  />
                ) : (
                  <input
                    value={condition.value}
                    onChange={(event) => updateCondition(index, { value: event.target.value })}
                    placeholder={
                      condition.field === "ocr_confidence" ? "0 to 1" : "Condition value"
                    }
                    className="theme-input mt-2 w-full rounded-xl px-3 py-3 text-sm"
                  />
                )}
              </div>
            ))}
            <button
              type="button"
              onClick={() => setConditions((current) => [...current, emptyCondition()])}
              className="theme-pill w-full px-3 py-2 text-xs font-bold"
            >
              + Add condition
            </button>
            <p className="text-muted-foreground text-[10px]">
              {conditionCountLabel}. Tag and folder choices are restricted to this organization.
            </p>
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy}
              className="bg-primary text-primary-foreground flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-xs font-black uppercase disabled:opacity-50"
            >
              <Save size={15} /> {editingId ? "Save collection" : "Create collection"}
            </button>
          </div>
        </div>
        <div className="theme-panel p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
              Configured Smart Collections
            </h2>
            <span className="text-muted-foreground text-xs">{collections.length} total</span>
          </div>
          <div className="mt-4 space-y-3">
            {collections.length ? (
              collections.map((collection) => (
                <article
                  key={collection.id}
                  className="border-glass-border bg-background/30 rounded-xl border p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-foreground truncate text-sm font-bold">
                        {collection.name}
                      </h3>
                      <p className="text-muted-foreground mt-1 text-[10px]">
                        Match {collection.match_mode} conditions ·{" "}
                        {collection.enabled ? "Enabled" : "Disabled"}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {collection.conditions.map((condition, index) => (
                          <span
                            key={`${collection.id}-${index}`}
                            className="bg-primary/5 text-primary rounded-md px-2 py-1 text-[10px]"
                          >
                            {conditionLabel(condition, tags, folders)}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        onClick={() => edit(collection)}
                        aria-label={`Edit ${collection.name}`}
                        className="theme-pill p-2"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => void toggle(collection)}
                        aria-label={
                          collection.enabled
                            ? `Disable ${collection.name}`
                            : `Enable ${collection.name}`
                        }
                        className="theme-pill p-2"
                      >
                        {collection.enabled ? <Check size={14} /> : <Play size={14} />}
                      </button>
                      <button
                        type="button"
                        onClick={() => void remove(collection)}
                        aria-label={`Delete ${collection.name}`}
                        className="text-danger hover:bg-danger/10 rounded-lg p-2"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <p className="text-primary mt-3 text-xs">
                    {collection.match_count == null
                      ? "Not evaluated yet"
                      : `${collection.match_count} matching document${collection.match_count === 1 ? "" : "s"}`}
                    {collection.last_evaluation?.duration_ms != null
                      ? ` · ${collection.last_evaluation.duration_ms} ms`
                      : ""}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void evaluate(collection)}
                      className="bg-primary text-primary-foreground flex items-center gap-1 rounded-lg px-3 py-2 text-[10px] font-black uppercase"
                    >
                      <Eye size={12} /> Preview
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        router.push(
                          `/dashboard/documents?smart_collection=${encodeURIComponent(collection.id)}`,
                        )
                      }
                      className="theme-pill px-3 py-2 text-[10px] font-bold uppercase"
                    >
                      Open in Documents Hub
                    </button>
                    <button
                      type="button"
                      onClick={() => void loadHistory(collection)}
                      className="theme-pill flex items-center gap-1 px-3 py-2 text-[10px] font-bold uppercase"
                    >
                      <History size={12} /> History
                    </button>
                  </div>
                  <p className="text-muted-foreground mt-2 flex items-center gap-1 text-[10px]">
                    <Clock3 size={12} /> Last evaluation:{" "}
                    {collection.last_evaluation?.completed_at ?? "never"}
                  </p>
                  {history[collection.id] ? (
                    <div className="border-primary/10 mt-3 space-y-2 border-t pt-3">
                      {history[collection.id].length ? (
                        history[collection.id].map((evaluation) => (
                          <div
                            key={evaluation.id}
                            className="bg-background/30 rounded-lg p-2 text-[10px]"
                          >
                            <p className="font-bold">
                              {evaluation.status} · {evaluation.matched_count} matched ·{" "}
                              {evaluation.duration_ms} ms
                            </p>
                            {evaluation.error_message ? (
                              <p className="text-danger mt-1">{evaluation.error_message}</p>
                            ) : null}
                          </div>
                        ))
                      ) : (
                        <p className="text-muted-foreground text-[10px]">
                          No evaluations recorded.
                        </p>
                      )}
                    </div>
                  ) : null}
                  {preview?.id === collection.id ? (
                    <div className="border-primary/10 mt-3 border-t pt-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-primary text-[10px] font-black uppercase">
                          Preview results · {preview.data.total} total
                        </p>
                        <button
                          type="button"
                          onClick={() => setPreview(null)}
                          className="text-muted-foreground hover:text-primary"
                        >
                          <X size={14} />
                        </button>
                      </div>
                      {preview.data.items.length ? (
                        <div className="mt-2 space-y-1">
                          {preview.data.items.map((item) => (
                            <Link
                              key={item.document_id}
                              href={`/dashboard/documents/${item.document_id}`}
                              className="border-glass-border hover:border-primary/40 flex items-center justify-between rounded-lg border px-2 py-2 text-[10px]"
                            >
                              <span className="truncate font-bold">{item.filename}</span>
                              <span className="text-muted-foreground ml-2">{item.status}</span>
                            </Link>
                          ))}
                        </div>
                      ) : (
                        <p className="text-muted-foreground mt-2 text-[10px]">
                          No matching documents.
                        </p>
                      )}
                      {preview.data.total > preview.data.page_size ? (
                        <div className="mt-2 flex justify-between">
                          <button
                            type="button"
                            disabled={preview.data.page <= 1}
                            onClick={() => void evaluate(collection, preview.data.page - 1)}
                            className="theme-pill px-2 py-1 text-[10px] disabled:opacity-40"
                          >
                            Previous
                          </button>
                          <span className="text-muted-foreground py-1 text-[10px]">
                            Page {preview.data.page} of{" "}
                            {Math.ceil(preview.data.total / preview.data.page_size)}
                          </span>
                          <button
                            type="button"
                            disabled={
                              preview.data.page >=
                              Math.ceil(preview.data.total / preview.data.page_size)
                            }
                            onClick={() => void evaluate(collection, preview.data.page + 1)}
                            className="theme-pill px-2 py-1 text-[10px] disabled:opacity-40"
                          >
                            Next
                          </button>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              ))
            ) : (
              <div className="py-16 text-center">
                <p className="text-muted-foreground text-sm">Nothing configured yet.</p>
                <p className="text-muted-foreground mt-2 text-xs">
                  Create a Smart Collection to group documents dynamically.
                </p>
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
