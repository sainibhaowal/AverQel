"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Calendar,
  ExternalLink,
  Filter,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchWithAuth } from "@/lib/api";
import { averqelConfirm } from "@/app/components/ui/AverQelDialogHost";
import toast from "react-hot-toast";

type SavedFilters = {
  q?: string;
  status?: string;
  content_type?: string;
  ocr_used?: boolean;
  quarantined?: boolean;
  tag_id?: string;
  created_from?: string;
  created_to?: string;
};

type SavedView = { id: string; name: string; description: string; filters: SavedFilters };
type Tag = { id: string; name: string };
type Result = {
  document_id: string;
  filename: string;
  status: string;
  content_type: string;
  created_at: string;
  processing_progress?: number;
  quarantined?: boolean;
};
type Evaluation = { view_id: string; total: number; items: Result[] };

const statusOptions = [
  "queued",
  "downloading",
  "parsing",
  "chunking",
  "embedding",
  "indexed",
  "completed",
  "failed",
  "dead_lettered",
];

function filterEntries(filters: SavedFilters, tags: Tag[]): Array<{ key: string; label: string }> {
  const tag = filters.tag_id ? tags.find((item) => item.id === filters.tag_id)?.name : undefined;
  return [
    filters.q ? { key: "q", label: `Name contains “${filters.q}”` } : null,
    filters.status ? { key: "status", label: `Status: ${filters.status}` } : null,
    filters.content_type ? { key: "content_type", label: `Type: ${filters.content_type}` } : null,
    filters.ocr_used !== undefined
      ? { key: "ocr_used", label: `OCR: ${filters.ocr_used ? "used" : "not used"}` }
      : null,
    filters.quarantined !== undefined
      ? { key: "quarantined", label: filters.quarantined ? "Quarantined" : "Not quarantined" }
      : null,
    filters.tag_id ? { key: "tag_id", label: `Tag: ${tag ?? "selected tag"}` } : null,
    filters.created_from ? { key: "created_from", label: `From: ${filters.created_from}` } : null,
    filters.created_to ? { key: "created_to", label: `To: ${filters.created_to}` } : null,
  ].filter((item): item is { key: string; label: string } => Boolean(item));
}

function emptyFilters(): SavedFilters {
  return { q: "", status: "", content_type: "", tag_id: "", created_from: "", created_to: "" };
}

export default function SavedViewsPanel() {
  const router = useRouter();
  const [views, setViews] = useState<SavedView[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [filters, setFilters] = useState<SavedFilters>(emptyFilters);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [busy, setBusy] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [viewsResponse, tagsResponse] = (await Promise.all([
        fetchWithAuth("/documents/organization/saved-views"),
        fetchWithAuth("/documents/organization/tags"),
      ])) as [Response, Response];
      if (!viewsResponse.ok) throw new Error("Saved views could not be loaded.");
      const viewPayload = (await viewsResponse.json()) as { items?: SavedView[] };
      setViews(viewPayload.items ?? []);
      if (tagsResponse.ok) setTags(((await tagsResponse.json()) as { items?: Tag[] }).items ?? []);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Saved views could not be loaded.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const activeChips = useMemo(() => filterEntries(filters, tags), [filters, tags]);

  const resetForm = () => {
    setEditingId(null);
    setName("");
    setDescription("");
    setFilters(emptyFilters());
  };

  const updateFilter = <K extends keyof SavedFilters>(key: K, value: SavedFilters[K]) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const normalizedFilters = (): SavedFilters => {
    const next: SavedFilters = {};
    (Object.keys(filters) as Array<keyof SavedFilters>).forEach((key) => {
      const value = filters[key];
      if (typeof value === "string" ? value.trim() : value !== undefined) {
        (next[key] as SavedFilters[typeof key]) = typeof value === "string" ? value.trim() : value;
      }
    });
    return next;
  };

  const save = async () => {
    if (!name.trim()) {
      toast.error("A saved view name is required.");
      return;
    }
    const nextFilters = normalizedFilters();
    if (
      nextFilters.created_from &&
      nextFilters.created_to &&
      nextFilters.created_from > nextFilters.created_to
    ) {
      toast.error("The start date must be before the end date.");
      return;
    }
    setBusy(true);
    try {
      const endpoint = editingId
        ? `/documents/organization/saved-views/${editingId}`
        : "/documents/organization/saved-views";
      const response = (await fetchWithAuth(endpoint, {
        method: editingId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim(),
          filters: nextFilters,
        }),
      })) as Response;
      if (!response.ok)
        throw new Error((await response.text()) || "Saved view could not be saved.");
      const saved = (await response.json()) as SavedView;
      setViews((current) =>
        editingId
          ? current.map((item) => (item.id === saved.id ? saved : item))
          : [...current, saved].sort((a, b) => a.name.localeCompare(b.name)),
      );
      resetForm();
      toast.success(editingId ? "Saved view updated." : "Saved view created.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Saved view could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const edit = (view: SavedView) => {
    setEditingId(view.id);
    setName(view.name);
    setDescription(view.description ?? "");
    setFilters({ ...emptyFilters(), ...view.filters });
    setEvaluation(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const run = async (view: SavedView) => {
    setRunningId(view.id);
    setError(null);
    try {
      const response = (await fetchWithAuth(
        `/documents/organization/saved-views/${view.id}/documents`,
      )) as Response;
      if (!response.ok) throw new Error("This saved view could not be evaluated.");
      setEvaluation((await response.json()) as Evaluation);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "This saved view could not be evaluated.",
      );
    } finally {
      setRunningId(null);
    }
  };

  const remove = async (view: SavedView) => {
    if (!(await averqelConfirm(`Delete saved view “${view.name}”?`))) return;
    const response = (await fetchWithAuth(`/documents/organization/saved-views/${view.id}`, {
      method: "DELETE",
    })) as Response;
    if (!response.ok) {
      toast.error("Saved view could not be deleted.");
      return;
    }
    setViews((current) => current.filter((item) => item.id !== view.id));
    if (evaluation?.view_id === view.id) setEvaluation(null);
    if (editingId === view.id) resetForm();
    toast.success("Saved view deleted.");
  };

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
          <h1 className="text-foreground mt-2 text-2xl font-black">Saved Views</h1>
          <p className="text-muted-foreground mt-2 text-sm">
            Save repeatable filters and reopen them as live, access-controlled document views.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={busy}
          className="theme-pill flex items-center gap-2 px-4 py-2 text-xs font-bold"
        >
          <RefreshCw size={14} className={busy ? "animate-spin" : ""} /> Refresh
        </button>
      </header>

      <section className="grid gap-6 xl:grid-cols-[minmax(320px,0.8fr)_minmax(0,1.2fr)]">
        <div className="theme-panel p-6">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
              {editingId ? "Edit saved view" : "Create saved view"}
            </h2>
            {editingId ? (
              <button
                type="button"
                onClick={resetForm}
                className="text-muted-foreground hover:text-primary flex items-center gap-1 text-xs font-bold"
              >
                <X size={14} /> Cancel
              </button>
            ) : null}
          </div>
          <div className="mt-4 space-y-3">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={128}
              placeholder="Saved view name"
              aria-label="Saved view name"
              className="theme-input w-full rounded-xl px-3 py-3 text-sm"
            />
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={2000}
              placeholder="Description (optional)"
              aria-label="Saved view description"
              rows={3}
              className="theme-input w-full resize-y rounded-xl px-3 py-3 text-sm"
            />
            <div className="border-glass-border border-t pt-4">
              <p className="text-muted-foreground mb-3 flex items-center gap-2 text-[10px] font-black tracking-widest uppercase">
                <Filter size={13} /> Document filters
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="sm:col-span-2">
                  <span className="text-muted-foreground mb-1 block text-[10px] font-bold uppercase">
                    Filename search
                  </span>
                  <div className="relative">
                    <Search
                      size={14}
                      className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 -translate-y-1/2"
                    />
                    <input
                      value={filters.q ?? ""}
                      onChange={(event) => updateFilter("q", event.target.value)}
                      placeholder="invoice, report, contract..."
                      className="theme-input w-full rounded-xl py-2.5 pr-3 pl-9 text-xs"
                    />
                  </div>
                </label>
                <label>
                  <span className="text-muted-foreground mb-1 block text-[10px] font-bold uppercase">
                    Status
                  </span>
                  <select
                    value={filters.status ?? ""}
                    onChange={(event) => updateFilter("status", event.target.value)}
                    className="theme-input w-full rounded-xl px-3 py-2.5 text-xs"
                  >
                    <option value="">Any status</option>
                    {statusOptions.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span className="text-muted-foreground mb-1 block text-[10px] font-bold uppercase">
                    Content type
                  </span>
                  <input
                    value={filters.content_type ?? ""}
                    onChange={(event) => updateFilter("content_type", event.target.value)}
                    placeholder="application/pdf"
                    className="theme-input w-full rounded-xl px-3 py-2.5 text-xs"
                  />
                </label>
                <label>
                  <span className="text-muted-foreground mb-1 block text-[10px] font-bold uppercase">
                    OCR
                  </span>
                  <select
                    value={filters.ocr_used === undefined ? "" : String(filters.ocr_used)}
                    onChange={(event) =>
                      updateFilter(
                        "ocr_used",
                        event.target.value === "" ? undefined : event.target.value === "true",
                      )
                    }
                    className="theme-input w-full rounded-xl px-3 py-2.5 text-xs"
                  >
                    <option value="">Any OCR state</option>
                    <option value="true">OCR used</option>
                    <option value="false">OCR not used</option>
                  </select>
                </label>
                <label>
                  <span className="text-muted-foreground mb-1 block text-[10px] font-bold uppercase">
                    Quarantine
                  </span>
                  <select
                    value={filters.quarantined === undefined ? "" : String(filters.quarantined)}
                    onChange={(event) =>
                      updateFilter(
                        "quarantined",
                        event.target.value === "" ? undefined : event.target.value === "true",
                      )
                    }
                    className="theme-input w-full rounded-xl px-3 py-2.5 text-xs"
                  >
                    <option value="">Any quarantine state</option>
                    <option value="true">Quarantined only</option>
                    <option value="false">Not quarantined</option>
                  </select>
                </label>
                <label>
                  <span className="text-muted-foreground mb-1 block text-[10px] font-bold uppercase">
                    Tag
                  </span>
                  <select
                    value={filters.tag_id ?? ""}
                    onChange={(event) => updateFilter("tag_id", event.target.value)}
                    className="theme-input w-full rounded-xl px-3 py-2.5 text-xs"
                  >
                    <option value="">Any tag</option>
                    {tags.map((tag) => (
                      <option key={tag.id} value={tag.id}>
                        {tag.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span className="text-muted-foreground mb-1 flex items-center gap-1 text-[10px] font-bold uppercase">
                    <Calendar size={12} /> Created from
                  </span>
                  <input
                    type="date"
                    value={filters.created_from ?? ""}
                    onChange={(event) => updateFilter("created_from", event.target.value)}
                    className="theme-input w-full rounded-xl px-3 py-2.5 text-xs"
                  />
                </label>
                <label>
                  <span className="text-muted-foreground mb-1 flex items-center gap-1 text-[10px] font-bold uppercase">
                    <Calendar size={12} /> Created to
                  </span>
                  <input
                    type="date"
                    value={filters.created_to ?? ""}
                    onChange={(event) => updateFilter("created_to", event.target.value)}
                    className="theme-input w-full rounded-xl px-3 py-2.5 text-xs"
                  />
                </label>
              </div>
            </div>
            <div>
              <p className="text-muted-foreground mb-2 text-[10px] font-black tracking-widest uppercase">
                Filter summary
              </p>
              <div className="flex min-h-8 flex-wrap gap-1.5">
                {activeChips.length ? (
                  activeChips.map((chip) => (
                    <span
                      key={chip.key}
                      className="bg-primary/10 text-primary rounded-full px-2.5 py-1 text-[10px] font-bold"
                    >
                      {chip.label}
                    </span>
                  ))
                ) : (
                  <span className="text-muted-foreground text-xs">All accessible documents</span>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy}
              className="bg-primary text-primary-foreground flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-xs font-black uppercase disabled:opacity-50"
            >
              {editingId ? <Save size={15} /> : <Plus size={15} />}
              {editingId ? "Save changes" : "Create saved view"}
            </button>
          </div>
        </div>

        <div className="theme-panel p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
                Configured saved views
              </h2>
              <p className="text-muted-foreground mt-1 text-xs">
                {views.length} saved view{views.length === 1 ? "" : "s"}
              </p>
            </div>
          </div>
          {error ? (
            <p
              role="alert"
              className="text-danger mt-4 rounded-xl border border-red-300/30 bg-red-500/5 p-3 text-xs"
            >
              {error}
            </p>
          ) : null}
          <div className="mt-4 space-y-3">
            {views.length ? (
              views.map((view) => {
                const chips = filterEntries(view.filters ?? {}, tags);
                return (
                  <article
                    key={view.id}
                    className="border-glass-border bg-background/30 rounded-xl border p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="text-foreground truncate text-sm font-bold">{view.name}</h3>
                        {view.description ? (
                          <p className="text-muted-foreground mt-1 text-xs">{view.description}</p>
                        ) : (
                          <p className="text-muted-foreground mt-1 text-xs italic">
                            No description
                          </p>
                        )}
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {chips.length ? (
                            chips.map((chip) => (
                              <span
                                key={chip.key}
                                className="bg-primary/10 text-primary rounded-full px-2 py-1 text-[10px] font-bold"
                              >
                                {chip.label}
                              </span>
                            ))
                          ) : (
                            <span className="text-muted-foreground text-[10px]">
                              All accessible documents
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onClick={() => edit(view)}
                          aria-label={`Edit ${view.name}`}
                          className="theme-pill p-2"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => void remove(view)}
                          aria-label={`Delete ${view.name}`}
                          className="text-danger hover:bg-danger/10 rounded-lg p-2"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void run(view)}
                        disabled={runningId === view.id}
                        className="bg-primary text-primary-foreground flex items-center gap-2 rounded-lg px-3 py-2 text-[10px] font-black uppercase disabled:opacity-50"
                      >
                        <Play size={13} />
                        {runningId === view.id ? "Running..." : "Run view"}
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          router.push(
                            `/dashboard/documents?saved_view=${encodeURIComponent(view.id)}`,
                          )
                        }
                        className="theme-pill flex items-center gap-2 px-3 py-2 text-[10px] font-black uppercase"
                      >
                        <ExternalLink size={13} /> Open in Documents Hub
                      </button>
                    </div>
                  </article>
                );
              })
            ) : (
              <div className="text-muted-foreground border-glass-border rounded-xl border border-dashed py-14 text-center text-sm">
                {busy ? "Loading saved views…" : "Nothing configured yet."}
              </div>
            )}
          </div>
        </div>
      </section>

      {evaluation ? (
        <section className="theme-panel p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
                Matching document results
              </h2>
              <p className="text-primary mt-1 text-xs font-bold">
                {evaluation.total} accessible document{evaluation.total === 1 ? "" : "s"} matched
                {evaluation.items.length < evaluation.total
                  ? ` · showing the first ${evaluation.items.length}`
                  : ""}
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                const view = views.find((item) => item.id === evaluation.view_id);
                if (view) void run(view);
              }}
              className="theme-pill flex items-center gap-2 px-3 py-2 text-xs font-bold"
            >
              <RefreshCw size={13} /> Refresh results
            </button>
          </div>
          {evaluation.items.length ? (
            <div className="mt-4 grid gap-2 md:grid-cols-2">
              {evaluation.items.map((item) => (
                <Link
                  key={item.document_id}
                  href={`/dashboard/documents/${item.document_id}`}
                  className="border-glass-border hover:border-primary/50 flex min-w-0 items-center justify-between gap-3 rounded-xl border p-3 transition-colors"
                >
                  <span className="min-w-0 truncate text-xs font-bold">{item.filename}</span>
                  <span className="text-muted-foreground shrink-0 text-[10px]">{item.status}</span>
                </Link>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground border-glass-border mt-6 rounded-xl border border-dashed py-10 text-center text-sm">
              No documents match this view.
            </p>
          )}
          <p className="text-muted-foreground mt-4 text-[10px]">
            Results are limited to documents you can access in the current organization and update
            when you run the view.
          </p>
        </section>
      ) : null}
    </main>
  );
}
