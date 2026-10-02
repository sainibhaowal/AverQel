"use client";

import { CalendarClock, Pause, Play, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/api";

type Schedule = {
  id: string;
  name: string;
  prompt: string;
  interval_minutes: number;
  status: "active" | "paused";
  next_run_at: string;
};

export default function DeepSpaceSchedulesPanel({ conversationId }: { conversationId: string | null }) {
  const [items, setItems] = useState<Schedule[]>([]);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [interval, setInterval] = useState(60);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const response = (await fetchWithAuth("/deepspace/schedules")) as Response;
    if (response.ok) setItems((await response.json()) as Schedule[]);
  }, []);
  useEffect(() => {
    let active = true;
    void (async () => {
      const response = (await fetchWithAuth("/deepspace/schedules")) as Response;
      if (active && response.ok) setItems((await response.json()) as Schedule[]);
    })();
    return () => {
      active = false;
    };
  }, []);

  const create = async () => {
    if (!conversationId || !name.trim() || !prompt.trim()) return;
    setBusy(true);
    try {
      const response = (await fetchWithAuth("/deepspace/schedules", {
        method: "POST",
        body: JSON.stringify({ name, prompt, interval_minutes: interval, conversation_id: conversationId }),
      })) as Response;
      if (response.ok) {
        setName("");
        setPrompt("");
        await load();
      }
    } finally {
      setBusy(false);
    }
  };

  const patch = async (item: Schedule, changes: Partial<Schedule>) => {
    await fetchWithAuth(`/deepspace/schedules/${item.id}`, { method: "PATCH", body: JSON.stringify(changes) });
    await load();
  };

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 overflow-auto p-5" data-testid="deepspace-schedules">
      <div className="flex items-center gap-2 text-sm font-semibold"><CalendarClock size={16} /> Scheduled work</div>
      <p className="text-muted-foreground text-xs">Recurring prompts run through the normal audited DeepSpace worker.</p>
      <div className="grid gap-2 rounded-xl border border-white/10 p-3">
        <input aria-label="Schedule name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Schedule name" className="rounded-lg bg-black/20 px-3 py-2 text-sm" />
        <textarea aria-label="Schedule prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="What should AverQel check?" className="min-h-20 rounded-lg bg-black/20 px-3 py-2 text-sm" />
        <div className="flex items-center gap-2 text-xs"><label htmlFor="schedule-interval">Every</label><input id="schedule-interval" type="number" min={5} max={43200} value={interval} onChange={(event) => setInterval(Number(event.target.value))} className="w-20 rounded-lg bg-black/20 px-2 py-1" /><span>minutes</span><button type="button" disabled={busy || !conversationId} onClick={() => void create()} className="bg-primary ml-auto rounded-lg px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-50">Create</button></div>
      </div>
      <div className="grid gap-2">
        {items.map((item) => <div key={item.id} className="rounded-xl border border-white/10 p-3 text-xs"><div className="flex items-center gap-2 font-semibold"><span className="min-w-0 flex-1 truncate">{item.name}</span><button type="button" aria-label={item.status === "active" ? "Pause schedule" : "Resume schedule"} onClick={() => void patch(item, { status: item.status === "active" ? "paused" : "active" })}>{item.status === "active" ? <Pause size={14} /> : <Play size={14} />}</button><button type="button" aria-label="Delete schedule" onClick={async () => { await fetchWithAuth(`/deepspace/schedules/${item.id}`, { method: "DELETE" }); await load(); }}><Trash2 size={14} /></button></div><p className="text-muted-foreground mt-1">{item.status} · next run {new Date(item.next_run_at).toLocaleString()}</p></div>)}
        {items.length === 0 && <p className="text-muted-foreground text-xs">No schedules yet.</p>}
      </div>
    </section>
  );
}
