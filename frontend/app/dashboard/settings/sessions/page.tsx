"use client";

import { useCallback, useEffect, useState } from "react";
import { LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import toast from "react-hot-toast";

import { fetchWithAuth } from "@/lib/api";

type AuthSession = {
  id: string;
  device_id: string;
  label: string;
  user_agent: string | null;
  created_at: string;
  last_seen_at: string;
  revoked_at: string | null;
  current: boolean;
};

export default function SessionsPage() {
  const [sessions, setSessions] = useState<AuthSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const response = (await fetchWithAuth("/auth/sessions")) as Response;
      if (!response.ok) throw new Error("Sessions could not be loaded.");
      setSessions((await response.json()) as AuthSession[]);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Sessions could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void loadSessions());
  }, [loadSessions]);

  const revoke = async (session: AuthSession) => {
    if (session.current) {
      toast.error("Use Log out for the current session.");
      return;
    }
    setRevokingId(session.id);
    try {
      const response = (await fetchWithAuth(`/auth/sessions/${session.id}`, { method: "DELETE" })) as Response;
      if (!response.ok) throw new Error("Session could not be revoked.");
      setSessions((current) => current.map((item) => item.id === session.id ? { ...item, revoked_at: new Date().toISOString() } : item));
      toast.success("Session revoked.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Session revocation failed.");
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 p-6 lg:p-10">
      <section className="rounded-2xl border border-cyan-200/30 bg-white/70 p-6 shadow-sm dark:border-white/10 dark:bg-white/[0.04]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-300"><ShieldCheck size={15} /> Account security</p>
            <h1 className="text-2xl font-black text-slate-900 dark:text-white">Linked sessions</h1>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Review signed-in browsers and revoke sessions you no longer recognize.</p>
          </div>
          <button type="button" onClick={() => void loadSessions()} disabled={loading} className="inline-flex items-center gap-2 rounded-xl border border-cyan-300/60 px-4 py-2 text-sm font-semibold text-cyan-800 disabled:opacity-50 dark:text-cyan-200"><RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh</button>
        </div>
      </section>

      <section className="space-y-3">
        {loading ? <p className="py-12 text-center text-sm text-slate-500">Loading sessions…</p> : sessions.length === 0 ? <p className="py-12 text-center text-sm text-slate-500">No linked sessions found.</p> : sessions.map((session) => (
          <article key={session.id} className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white/80 p-5 dark:border-white/10 dark:bg-white/[0.04]">
            <div>
              <div className="flex flex-wrap items-center gap-2"><h2 className="font-bold text-slate-900 dark:text-white">{session.label}</h2>{session.current && <span className="rounded-full bg-emerald-100 px-2 py-1 text-xs font-bold text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200">This session</span>}{session.revoked_at && <span className="rounded-full bg-rose-100 px-2 py-1 text-xs font-bold text-rose-800 dark:bg-rose-900/30 dark:text-rose-200">Revoked</span>}</div>
              <p className="mt-1 max-w-2xl break-words text-xs text-slate-500">{session.user_agent || session.device_id}</p>
              <p className="mt-1 text-xs text-slate-500">Last active {new Date(session.last_seen_at).toLocaleString()}</p>
            </div>
            {!session.current && !session.revoked_at && <button type="button" onClick={() => void revoke(session)} disabled={revokingId === session.id} className="inline-flex items-center gap-2 rounded-xl border border-rose-300 px-3 py-2 text-sm font-semibold text-rose-700 disabled:opacity-50 dark:text-rose-200"><LogOut size={15} /> Revoke</button>}
          </article>
        ))}
      </section>
    </main>
  );
}
