"use client";

import { useCallback, useEffect, useState } from "react";
import { LogOut, MonitorSmartphone, RefreshCw } from "lucide-react";
import toast from "react-hot-toast";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";

const PAGE_SIZE = 25;

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

async function responseError(response: Response, fallback: string): Promise<string> {
  try {
    const data = (await response.json()) as {
      error?: { message?: string };
      detail?: string;
    };
    return data.error?.message || data.detail || fallback;
  } catch {
    return fallback;
  }
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<AuthSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const response = (await fetchWithAuth(
        `/auth/sessions?limit=${PAGE_SIZE + 1}&offset=0`,
      )) as Response;
      if (!response.ok)
        throw new Error(await responseError(response, "Sessions could not be loaded."));
      const result = (await response.json()) as AuthSession[];
      setSessions(result.slice(0, PAGE_SIZE));
      setHasMore(result.length > PAGE_SIZE);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Sessions could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void loadSessions());
  }, [loadSessions]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const offset = sessions.length;
      const response = (await fetchWithAuth(
        `/auth/sessions?limit=${PAGE_SIZE + 1}&offset=${offset}`,
      )) as Response;
      if (!response.ok)
        throw new Error(await responseError(response, "More sessions could not be loaded."));
      const result = (await response.json()) as AuthSession[];
      setSessions((current) => {
        const knownIds = new Set(current.map((session) => session.id));
        return [
          ...current,
          ...result.slice(0, PAGE_SIZE).filter((session) => !knownIds.has(session.id)),
        ];
      });
      setHasMore(result.length > PAGE_SIZE);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "More sessions could not be loaded.");
    } finally {
      setLoadingMore(false);
    }
  };

  const revoke = async (session: AuthSession) => {
    if (session.current) {
      toast.error("Use Log out for the current session.");
      return;
    }
    setRevokingId(session.id);
    try {
      const response = (await fetchWithAuth(`/auth/sessions/${session.id}`, {
        method: "DELETE",
      })) as Response;
      if (!response.ok) {
        throw new Error(await responseError(response, "Session could not be revoked."));
      }
      setSessions((current) =>
        current.map((item) =>
          item.id === session.id ? { ...item, revoked_at: new Date().toISOString() } : item,
        ),
      );
      toast.success("Session revoked.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Session revocation failed.");
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <main className="dashboard-theme-scope w-full min-w-0 space-y-6">
      <DashboardSectionHeader
        title="Linked sessions"
        subtitle="Review sign-ins and revoke sessions you do not recognize"
        icon={MonitorSmartphone}
        accentClassName="bg-success text-success"
        accentGlowClassName="shadow-[0_0_18px_rgba(var(--success),0.28)]"
        backHref="/dashboard/settings"
        backLabel="Back"
        actions={
          <button
            type="button"
            onClick={() => void loadSessions()}
            disabled={loading}
            className="border-border/70 bg-card/50 text-muted-foreground hover:text-foreground inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-bold transition-colors disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        }
      />
      <p className="text-muted-foreground text-xs">
        Device labels use browser information and a random browser ID; they do not identify physical
        hardware.
      </p>

      <section className="space-y-3" aria-label="Signed-in sessions" aria-busy={loading}>
        {loading ? (
          <p className="py-12 text-center text-sm text-slate-500" role="status">
            Loading sessions…
          </p>
        ) : sessions.length === 0 ? (
          <p className="py-12 text-center text-sm text-slate-500">No linked sessions found.</p>
        ) : (
          sessions.map((session) => (
            <article
              key={session.id}
              className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white/80 p-5 dark:border-white/10 dark:bg-white/[0.04]"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-bold text-slate-900 dark:text-white">{session.label}</h2>
                  {session.current && (
                    <span className="rounded-full bg-emerald-100 px-2 py-1 text-xs font-bold text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200">
                      This session
                    </span>
                  )}
                  {session.revoked_at && (
                    <span className="rounded-full bg-rose-100 px-2 py-1 text-xs font-bold text-rose-800 dark:bg-rose-900/30 dark:text-rose-200">
                      Revoked
                    </span>
                  )}
                </div>
                <p className="mt-1 max-w-2xl text-xs break-words text-slate-500">
                  {session.user_agent ||
                    (session.device_id.startsWith("legacy-")
                      ? "Browser details were unavailable for this earlier sign-in."
                      : "Browser details were not reported.")}
                </p>
                <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
                  <span>Signed in {new Date(session.created_at).toLocaleString()}</span>
                  <span>Last token refresh {new Date(session.last_seen_at).toLocaleString()}</span>
                </div>
              </div>
              {!session.current && !session.revoked_at && (
                <button
                  type="button"
                  onClick={() => void revoke(session)}
                  disabled={revokingId === session.id}
                  className="inline-flex items-center gap-2 rounded-xl border border-rose-300 px-3 py-2 text-sm font-semibold text-rose-700 disabled:opacity-50 dark:text-rose-200"
                >
                  <LogOut size={15} /> {revokingId === session.id ? "Revoking…" : "Revoke"}
                </button>
              )}
            </article>
          ))
        )}
        {!loading && hasMore && (
          <button
            type="button"
            onClick={() => void loadMore()}
            disabled={loadingMore}
            className="w-full rounded-xl border border-cyan-300/60 px-4 py-3 text-sm font-semibold text-cyan-800 disabled:opacity-50 dark:text-cyan-200"
          >
            {loadingMore ? "Loading…" : "Load more sessions"}
          </button>
        )}
      </section>
    </main>
  );
}
