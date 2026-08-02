"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  Brain,
  Check,
  ChevronDown,
  Clock,
  Database,
  Download,
  Globe,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  User,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { apiV1 } from "@/lib/api";

type MemoryScope = "user" | "session" | "global";

type MemoryItem = {
  id: string;
  key: string;
  value: string;
  scope: MemoryScope;
  tags: string[];
  importance_score?: number | null;
  confidence_score?: number | null;
  status?: "active" | "pending" | "archived";
  source?: string | null;
  conversation_id?: string | null;
  expires_at?: string | null;
  access_count?: number | null;
  last_accessed_at?: string | null;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  pgvector_ready?: boolean | null;
  decay_score?: number | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

type MemoryReport = {
  memory_count: number;
  embedded_count: number;
  pgvector_count: number;
  embedding_coverage: number;
  duplicate_count: number;
  stale_count: number;
  average_decay_score: number;
  memory_health_score: number;
  retention_risk_count: number;
};

type MemoryPreferences = {
  automatic_capture_enabled: boolean;
  review_inferred_memories: boolean;
  memory_retrieval_enabled: boolean;
};

const MEMORY_ENDPOINT = "/deepspace/chats/memory";

function displayDate(value?: string | null) {
  if (!value) return "Never";
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function scopeLabel(scope: MemoryScope) {
  if (scope === "session") return "Session";
  if (scope === "global") return "Global";
  return "Personal";
}

export default function MemoryPanel() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [report, setReport] = useState<MemoryReport | null>(null);
  const [preferences, setPreferences] = useState<MemoryPreferences | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<MemoryItem | null>(null);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [scope, setScope] = useState<MemoryScope>("user");
  const [tags, setTags] = useState("");
  const [importance, setImportance] = useState("0.5");
  const [confirmClear, setConfirmClear] = useState(false);

  const load = async (query = "") => {
    setLoading(true);
    try {
      const [memoryData, reportData, preferencesData] = await Promise.all([
        query.trim()
          ? apiV1.get<{ results: MemoryItem[] }>(`${MEMORY_ENDPOINT}/search?query=${encodeURIComponent(query.trim())}`)
          : apiV1.get<MemoryItem[]>(MEMORY_ENDPOINT),
        apiV1.get<MemoryReport>(`${MEMORY_ENDPOINT}/evaluation`),
        apiV1.get<MemoryPreferences>(`${MEMORY_ENDPOINT}/preferences`),
      ]);
      setMemories(Array.isArray(memoryData) ? memoryData : memoryData.results || []);
      setReport(reportData);
      setPreferences(preferencesData);
    } catch (error) {
      console.error("Failed to load DeepSpace memory", error);
      toast.error("Memory is temporarily unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const resetForm = () => {
    setShowForm(false);
    setEditing(null);
    setKey("");
    setValue("");
    setScope("user");
    setTags("");
    setImportance("0.5");
  };

  const openEdit = (memory: MemoryItem) => {
    setEditing(memory);
    setShowForm(true);
    setKey(memory.key);
    setValue(memory.value);
    setScope(memory.scope === "global" ? "user" : memory.scope);
    setTags(memory.tags.join(", "));
    setImportance(String(memory.importance_score ?? 0.5));
  };

  const saveMemory = async () => {
    if (!key.trim() || !value.trim()) {
      toast.error("Memory key and value are required.");
      return;
    }
    setBusy(true);
    try {
      const body = {
        key: key.trim(),
        value: value.trim(),
        scope,
        tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean).slice(0, 20),
        importance_score: Math.min(1, Math.max(0, Number(importance) || 0.5)),
      };
      if (editing) {
        const updateBody = {
          value: body.value,
          scope: body.scope,
          tags: body.tags,
          importance_score: body.importance_score,
        };
        await apiV1.patch(`${MEMORY_ENDPOINT}/${encodeURIComponent(editing.id)}`, updateBody);
        toast.success("Memory updated");
      } else {
        await apiV1.post(MEMORY_ENDPOINT, body);
        toast.success("Memory saved");
      }
      resetForm();
      await load(searchQuery);
    } catch (error) {
      console.error("Failed to save DeepSpace memory", error);
      toast.error(error instanceof Error ? error.message : "Memory could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const forgetMemory = async (memory: MemoryItem) => {
    setBusy(true);
    try {
      await apiV1.delete(`${MEMORY_ENDPOINT}/${encodeURIComponent(memory.key)}`);
      setMemories((current) => current.filter((item) => item.key !== memory.key));
      toast.success("Memory forgotten");
      await load(searchQuery);
    } catch (error) {
      console.error("Failed to forget memory", error);
      toast.error("Memory could not be removed.");
    } finally {
      setBusy(false);
    }
  };

  const runCleanup = async (kind: "duplicates" | "stale") => {
    setBusy(true);
    try {
      await apiV1.post(kind === "duplicates" ? `${MEMORY_ENDPOINT}/cleanup` : `${MEMORY_ENDPOINT}/cleanup-stale`);
      toast.success(kind === "duplicates" ? "Duplicate memories cleaned" : "Expired session memories cleaned");
      await load(searchQuery);
    } catch (error) {
      console.error("Failed to clean memory", error);
      toast.error("Memory cleanup failed.");
    } finally {
      setBusy(false);
    }
  };

  const clearPersonal = async () => {
    setBusy(true);
    try {
      await apiV1.delete(`${MEMORY_ENDPOINT}/clear`);
      toast.success("Personal memory cleared");
      await load();
      setConfirmClear(false);
    } catch (error) {
      console.error("Failed to clear memory", error);
      toast.error("Memory could not be cleared.");
    } finally {
      setBusy(false);
    }
  };

  const updatePreferences = async (patch: Partial<MemoryPreferences>) => {
    setBusy(true);
    try {
      const updated = await apiV1.patch<MemoryPreferences>(`${MEMORY_ENDPOINT}/preferences`, patch);
      setPreferences(updated);
      toast.success("Memory preference updated");
    } catch (error) {
      console.error("Failed to update memory preferences", error);
      toast.error("Memory preference could not be updated.");
    } finally {
      setBusy(false);
    }
  };

  const reviewCandidate = async (memory: MemoryItem, action: "approve" | "reject") => {
    setBusy(true);
    try {
      if (action === "approve") {
        await apiV1.post(`${MEMORY_ENDPOINT}/${encodeURIComponent(memory.id)}/approve`);
      } else {
        await apiV1.delete(`${MEMORY_ENDPOINT}/${encodeURIComponent(memory.id)}/candidate`);
      }
      toast.success(action === "approve" ? "Memory approved" : "Memory candidate discarded");
      await load(searchQuery);
    } catch (error) {
      console.error("Failed to review memory candidate", error);
      toast.error("Memory candidate could not be updated.");
    } finally {
      setBusy(false);
    }
  };

  const exportMemory = () => {
    const blob = new Blob([JSON.stringify(memories, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "deepspace-memory.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const visibleCount = useMemo(() => memories.length, [memories]);
  const candidates = useMemo(() => memories.filter((memory) => memory.status === "pending"), [memories]);
  const activeMemories = useMemo(() => memories.filter((memory) => memory.status !== "pending"), [memories]);

  return (
    <div className="bg-background/50 flex h-full min-h-0 flex-col overflow-hidden backdrop-blur-3xl">
      <header className="shrink-0 border-b border-white/5 bg-white/[0.03] p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="bg-primary/15 border-primary/25 rounded-xl border p-2.5"><Brain size={20} className="text-primary" /></div>
            <div>
              <h2 className="text-foreground/90 text-lg font-black tracking-tight">DeepSpace Memory</h2>
              <p className="text-foreground/40 text-[10px] font-bold tracking-[0.2em] uppercase">Scoped, searchable persistent context</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void load(searchQuery)} disabled={busy} className="theme-chip inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs"><RefreshCw size={13} />Refresh</button>
            <button type="button" onClick={exportMemory} disabled={!memories.length} className="theme-chip inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs"><Download size={13} />Export</button>
            <button type="button" onClick={() => { resetForm(); setShowForm(true); }} className="bg-primary text-primary-foreground inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold"><Plus size={14} />Remember</button>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric icon={<Database size={14} />} label="Memories" value={String(report?.memory_count ?? visibleCount)} />
          <Metric icon={<Activity size={14} />} label="Health" value={report ? `${Math.round(report.memory_health_score)}%` : "—"} />
          <Metric icon={<ShieldCheck size={14} />} label="Embedded" value={report ? `${Math.round(report.embedding_coverage * 100)}%` : "—"} />
          <Metric icon={<Clock size={14} />} label="Retention risk" value={report ? String(report.retention_risk_count) : "—"} />
        </div>

        <div className="relative mt-4">
          <Search size={14} className="text-foreground/30 absolute top-1/2 left-4 -translate-y-1/2" />
          <input type="search" placeholder="Search memories..." value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void load(searchQuery); }} className="text-foreground/80 focus:border-primary/50 w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pr-4 pl-10 text-xs focus:outline-none" />
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <PreferenceToggle label="Automatic capture" description="Create reviewable candidates from clear lasting preferences." checked={Boolean(preferences?.automatic_capture_enabled)} disabled={busy} onChange={(checked) => void updatePreferences({ automatic_capture_enabled: checked })} />
          <PreferenceToggle label="Review inferred" description="Require approval before DeepSpace uses an inferred memory." checked={Boolean(preferences?.review_inferred_memories ?? true)} disabled={busy || !preferences?.automatic_capture_enabled} onChange={(checked) => void updatePreferences({ review_inferred_memories: checked })} />
          <PreferenceToggle label="Use memory in chat" description="Allow relevant active memories to be recalled in answers." checked={Boolean(preferences?.memory_retrieval_enabled ?? true)} disabled={busy} onChange={(checked) => void updatePreferences({ memory_retrieval_enabled: checked })} />
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
        {showForm ? <MemoryForm editing={Boolean(editing)} keyValue={key} value={value} scope={scope} tags={tags} importance={importance} busy={busy} onKeyChange={setKey} onValueChange={setValue} onScopeChange={setScope} onTagsChange={setTags} onImportanceChange={setImportance} onSave={() => void saveMemory()} onCancel={resetForm} /> : null}

        {confirmClear ? <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-400/25 bg-red-400/[0.06] p-3"><p className="text-xs text-red-100/80">Clear all personal and temporary memories? Shared memories remain protected.</p><div className="flex gap-2"><button type="button" onClick={() => setConfirmClear(false)} className="theme-chip rounded-lg px-3 py-1.5 text-xs">Cancel</button><button type="button" onClick={() => void clearPersonal()} disabled={busy} className="rounded-lg bg-red-500/20 px-3 py-1.5 text-xs font-semibold text-red-100">Clear memories</button></div></div> : null}
        {loading ? <div className="flex min-h-48 items-center justify-center"><RefreshCw className="text-primary animate-spin" size={22} /></div> : memories.length === 0 ? (
          <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] text-center"><Database size={34} className="text-foreground/25" /><p className="text-foreground/60 mt-4 text-sm font-semibold">No memories yet</p><p className="text-foreground/35 mt-2 max-w-sm text-xs">Ask DeepSpace to remember a lasting preference, or save one manually.</p></div>
        ) : (
          <AnimatePresence mode="popLayout"><div className="space-y-3">{candidates.length ? <section className="rounded-xl border border-amber-400/20 bg-amber-400/[0.04] p-3"><div className="mb-2 flex items-center justify-between"><p className="text-xs font-bold text-amber-100">Review memory candidates</p><span className="text-[10px] text-amber-100/60">{candidates.length} pending</span></div><div className="space-y-2">{candidates.map((memory) => <CandidateCard key={memory.id} memory={memory} busy={busy} onReview={reviewCandidate} />)}</div></section> : null}{activeMemories.map((memory) => <motion.article key={memory.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="group rounded-xl border border-white/10 bg-white/[0.04] p-4 transition hover:border-primary/30 hover:bg-white/[0.06]">
            <div className="flex items-start justify-between gap-4"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h3 className="text-foreground/90 text-sm font-bold">{memory.key}</h3><span className="text-primary/80 bg-primary/10 border-primary/20 rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase"><ScopeIcon scope={memory.scope} /> {scopeLabel(memory.scope)}</span></div><p className="text-foreground/65 mt-2 whitespace-pre-wrap text-sm leading-relaxed">{memory.value}</p><div className="text-foreground/35 mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px]"><span>{displayDate(memory.updated_at || memory.created_at)}</span><span>Used {memory.access_count ?? 0} times</span><span>Importance {Math.round((memory.importance_score ?? 0) * 100)}%</span><span>Confidence {Math.round((memory.confidence_score ?? 1) * 100)}%</span><span>{memory.pgvector_ready ? "Vector ready" : "Embedding pending"}</span>{memory.expires_at ? <span>Expires {displayDate(memory.expires_at)}</span> : null}</div>{memory.source ? <p className="text-foreground/30 mt-2 text-[10px]">Source: {memory.source.replace(/_/g, " ")}</p> : null}{memory.tags.length ? <div className="mt-2 flex flex-wrap gap-1">{memory.tags.map((tag) => <span key={tag} className="text-foreground/40 rounded border border-white/10 px-1.5 py-0.5 text-[9px]">#{tag}</span>)}</div> : null}</div>{memory.scope !== "global" ? <div className="flex shrink-0 gap-1 opacity-60 transition group-hover:opacity-100"><button type="button" onClick={() => openEdit(memory)} className="theme-chip rounded-lg px-2 py-1.5 text-[10px]">Edit</button><button type="button" onClick={() => void forgetMemory(memory)} disabled={busy} aria-label="Forget memory" className="rounded-lg p-2 text-red-400/70 hover:bg-red-400/10 hover:text-red-400"><Trash2 size={14} /></button></div> : null}</div>
          </motion.article>)}</div></AnimatePresence>
        )}
      </div>

      <footer className="shrink-0 border-t border-white/5 bg-white/[0.03] p-4"><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-foreground/40 max-w-2xl text-[10px] leading-relaxed"><span className="text-primary/80 font-bold">Privacy:</span> chat history remains separate. Inferred candidates never become active until approved when review is enabled. Sensitive personal data and connector credentials are never auto-saved.</p><div className="flex flex-wrap gap-2"><button type="button" onClick={() => void runCleanup("duplicates")} disabled={busy} className="theme-chip rounded-lg px-2.5 py-1.5 text-[10px]">Clean duplicates</button><button type="button" onClick={() => void runCleanup("stale")} disabled={busy} className="theme-chip rounded-lg px-2.5 py-1.5 text-[10px]">Clean expired</button><button type="button" onClick={() => setConfirmClear(true)} disabled={busy} className="rounded-lg border border-red-400/20 px-2.5 py-1.5 text-[10px] text-red-300/80 hover:bg-red-400/10">Clear personal</button></div></div></footer>
    </div>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return <div className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5"><div className="text-foreground/35 flex items-center gap-1.5 text-[9px] font-bold uppercase"><span className="text-primary/70">{icon}</span>{label}</div><div className="text-foreground/90 mt-1 text-lg font-black">{value}</div></div>;
}

function ScopeIcon({ scope }: { scope: MemoryScope }) {
  return scope === "global" ? <Globe size={10} className="inline" /> : <User size={10} className="inline" />;
}

function PreferenceToggle({ label, description, checked, disabled, onChange }: { label: string; description: string; checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void }) {
  return <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3"><input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} className="mt-0.5 accent-cyan-400" /><span><span className="text-foreground/80 block text-[11px] font-semibold">{label}</span><span className="text-foreground/35 mt-1 block text-[10px] leading-relaxed">{description}</span></span></label>;
}

function CandidateCard({ memory, busy, onReview }: { memory: MemoryItem; busy: boolean; onReview: (memory: MemoryItem, action: "approve" | "reject") => Promise<void> }) {
  return <div className="rounded-lg border border-amber-400/15 bg-black/10 p-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-foreground/85 text-xs font-semibold">{memory.key}</p><p className="text-foreground/55 mt-1 text-xs leading-relaxed">{memory.value}</p><p className="mt-2 text-[10px] text-amber-100/55">Inferred from this conversation · Confidence {Math.round((memory.confidence_score ?? 0) * 100)}%</p></div><div className="flex shrink-0 gap-2"><button type="button" disabled={busy} onClick={() => void onReview(memory, "reject")} className="theme-chip rounded-lg px-2.5 py-1.5 text-[10px]">Discard</button><button type="button" disabled={busy} onClick={() => void onReview(memory, "approve")} className="rounded-lg bg-emerald-400/15 px-2.5 py-1.5 text-[10px] font-semibold text-emerald-100">Approve</button></div></div></div>;
}

function MemoryForm({ editing, keyValue, value, scope, tags, importance, busy, onKeyChange, onValueChange, onScopeChange, onTagsChange, onImportanceChange, onSave, onCancel }: { editing: boolean; keyValue: string; value: string; scope: MemoryScope; tags: string; importance: string; busy: boolean; onKeyChange: (value: string) => void; onValueChange: (value: string) => void; onScopeChange: (value: MemoryScope) => void; onTagsChange: (value: string) => void; onImportanceChange: (value: string) => void; onSave: () => void; onCancel: () => void }) {
  return <div className="mb-5 rounded-xl border border-primary/20 bg-primary/[0.04] p-4"><div className="mb-3 flex items-center justify-between"><p className="text-foreground/80 text-xs font-bold">{editing ? "Edit memory" : "Save memory"}</p><button type="button" onClick={onCancel} className="text-foreground/50 hover:text-foreground"><X size={15} /></button></div><div className="grid gap-3 md:grid-cols-2"><input value={keyValue} onChange={(event) => onKeyChange(event.target.value)} disabled={editing} placeholder="Key, e.g. writing_style" className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs disabled:opacity-50" /><MemoryScopeSelect value={scope} onChange={onScopeChange} /><textarea value={value} onChange={(event) => onValueChange(event.target.value)} placeholder="What should DeepSpace remember?" rows={3} className="md:col-span-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs" /><input value={tags} onChange={(event) => onTagsChange(event.target.value)} placeholder="Tags, comma separated" className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs" /><label className="text-foreground/50 flex items-center gap-2 text-xs">Importance <input type="text" inputMode="decimal" pattern="^(?:0(?:\\.\\d*)?|1(?:\\.0*)?)$" aria-label="Importance from 0 to 1" value={importance} onChange={(event) => onImportanceChange(event.target.value)} className="w-20 rounded-lg border border-white/10 bg-black/20 px-2 py-2 text-xs" /></label></div><div className="mt-3 flex justify-end gap-2"><button type="button" onClick={onCancel} className="theme-chip rounded-lg px-3 py-2 text-xs">Cancel</button><button type="button" onClick={onSave} disabled={busy} className="bg-primary text-primary-foreground inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold">{busy ? <RefreshCw size={13} className="animate-spin" /> : <Check size={13} />}{editing ? "Update" : "Save"}</button></div></div>;
}

function MemoryScopeSelect({ value, onChange }: { value: MemoryScope; onChange: (value: MemoryScope) => void }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const options: Array<{ value: Extract<MemoryScope, "user" | "session">; label: string }> = [
    { value: "user", label: "Personal" },
    { value: "session", label: "Session" },
  ];
  const selected = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return <div ref={rootRef} className="relative"><button ref={buttonRef} type="button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((current) => !current)} className={`flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-2 text-left text-xs transition-all ${open ? "border-cyan-300/45 bg-cyan-300/[0.08] text-cyan-50 shadow-[0_0_18px_rgba(34,211,238,0.12)]" : "border-white/10 bg-black/20 text-foreground/85 hover:border-white/20 hover:bg-white/[0.05]"}`}><span>{selected.label}</span><ChevronDown size={15} className={`text-foreground/45 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" /></button>{open ? <div role="listbox" aria-label="Memory scope" className="absolute left-0 top-[calc(100%+0.45rem)] z-50 w-full overflow-hidden rounded-xl border border-white/15 bg-[#101713]/[0.98] p-1.5 shadow-[0_16px_36px_rgba(0,0,0,0.55)] backdrop-blur-xl">{options.map((option) => { const active = option.value === value; return <button key={option.value} type="button" role="option" aria-selected={active} onClick={() => { onChange(option.value); setOpen(false); buttonRef.current?.focus(); }} className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs transition-colors ${active ? "bg-cyan-300/15 text-cyan-100" : "text-foreground/70 hover:bg-white/[0.08] hover:text-foreground"}`}><span>{option.label}</span>{active ? <Check size={13} className="text-cyan-300" aria-hidden="true" /> : null}</button>; })}</div> : null}</div>;
}
