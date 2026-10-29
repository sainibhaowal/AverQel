"use client";

import { CalendarClock, Pause, Play, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchWithAuth } from "@/lib/api";
import AverQelLoading from "@/app/components/ui/AverQelLoading";

type Schedule = {
  id: string;
  name: string;
  prompt: string;
  interval_minutes: number;
  status: "active" | "paused";
  next_run_at: string;
};

export default function DeepSpaceSchedulesPanel({
  conversationId,
  isPanelActive = true,
}: {
  conversationId: string | null;
  isPanelActive?: boolean;
}) {
  const [items, setItems] = useState<Schedule[]>([]);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [interval, setInterval] = useState(60);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const hasLoadedRef = useRef(false);
  const wasActiveRef = useRef(isPanelActive);

  const load = useCallback(async () => {
    try {
      const response = (await fetchWithAuth("/deepspace/schedules")) as Response;
      if (!response.ok) {
        setLoadError(true);
        return;
      }
      setItems((await response.json()) as Schedule[]);
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      hasLoadedRef.current = true;
    }
  }, []);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      void load().finally(() => {
        if (active) setLoading(false);
      });
    });
    return () => {
      active = false;
    };
  }, [load]);
  useEffect(() => {
    const wasActive = wasActiveRef.current;
    wasActiveRef.current = isPanelActive;
    if (isPanelActive && !wasActive && hasLoadedRef.current) {
      queueMicrotask(() => {
        if (wasActiveRef.current) void load();
      });
    }
  }, [isPanelActive, load]);

  const create = async () => {
    if (!conversationId || !name.trim() || !prompt.trim()) return;
    setBusy(true);
    try {
      const response = (await fetchWithAuth("/deepspace/schedules", {
        method: "POST",
        body: JSON.stringify({
          name,
          prompt,
          interval_minutes: interval,
          conversation_id: conversationId,
        }),
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
    await fetchWithAuth(`/deepspace/schedules/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    });
    await load();
  };

  return (
    <section
      className="flex h-full min-h-0 flex-col gap-4 overflow-auto p-5"
      data-testid="deepspace-schedules"
    >
      <div className="text-foreground flex items-center gap-2 text-sm font-semibold">
        <CalendarClock size={16} /> Scheduled work
      </div>
      <p className="text-muted-foreground text-xs">
        Recurring prompts run through the normal audited DeepSpace worker.
      </p>
      <div className="border-border bg-surface-0/45 grid gap-2 rounded-xl border p-3">
        <input
          aria-label="Schedule name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Schedule name"
          className="border-border bg-background text-foreground placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-primary/35 rounded-lg border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
        />
        <textarea
          aria-label="Schedule prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="What should AverQel check?"
          className="border-border bg-background text-foreground placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-primary/35 min-h-20 rounded-lg border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
        />
        <div className="flex items-center gap-2 text-xs">
          <label htmlFor="schedule-interval">Every</label>
          <input
            id="schedule-interval"
            type="number"
            min={5}
            max={43200}
            value={interval}
            onChange={(event) => setInterval(Number(event.target.value))}
            className="border-border bg-background text-foreground focus-visible:border-primary focus-visible:ring-primary/35 w-20 rounded-lg border px-2 py-1 focus-visible:ring-2 focus-visible:outline-none"
          />
          <span>minutes</span>
          <button
            type="button"
            disabled={busy || !conversationId}
            onClick={() => void create()}
            className="bg-primary text-primary-foreground focus-visible:ring-primary/50 border-primary/40 hover:bg-primary/90 ml-auto rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            Create
          </button>
        </div>
      </div>
      {loading ? (
        <AverQelLoading label="Loading scheduled work…" size="section" className="min-h-32" />
      ) : loadError ? (
        <p role="alert" className="text-muted-foreground text-xs">
          Scheduled work could not be loaded.
        </p>
      ) : (
        <div className="grid gap-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="border-border bg-surface-0/35 text-foreground rounded-xl border p-3 text-xs"
            >
              <div className="flex items-center gap-2 font-semibold">
                <span className="min-w-0 flex-1 truncate">{item.name}</span>
                <button
                  type="button"
                  aria-label={item.status === "active" ? "Pause schedule" : "Resume schedule"}
                  onClick={() =>
                    void patch(item, { status: item.status === "active" ? "paused" : "active" })
                  }
                  className="text-muted-foreground hover:bg-primary/10 hover:text-primary focus-visible:ring-primary/50 rounded-md p-1 transition-colors focus-visible:ring-2 focus-visible:outline-none"
                >
                  {item.status === "active" ? <Pause size={14} /> : <Play size={14} />}
                </button>
                <button
                  type="button"
                  aria-label="Delete schedule"
                  onClick={async () => {
                    await fetchWithAuth(`/deepspace/schedules/${item.id}`, { method: "DELETE" });
                    await load();
                  }}
                  className="text-muted-foreground hover:bg-danger/10 hover:text-danger focus-visible:ring-danger/50 rounded-md p-1 transition-colors focus-visible:ring-2 focus-visible:outline-none"
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <p className="text-muted-foreground mt-1">
                <span
                  className={
                    item.status === "active" ? "text-primary font-semibold" : "font-semibold"
                  }
                >
                  {item.status}
                </span>
                {` · next run ${new Date(item.next_run_at).toLocaleString()}`}
              </p>
            </div>
          ))}
          {items.length === 0 && <p className="text-muted-foreground text-xs">No schedules yet.</p>}
        </div>
      )}
    </section>
  );
}
