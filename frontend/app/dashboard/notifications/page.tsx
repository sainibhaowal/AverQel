"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { BellRing, CheckCheck, RefreshCw, Trash2 } from "lucide-react";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";

type Item = {
  id: string;
  source: "application" | "collection";
  event_domain?: string;
  event_type: string;
  title: string;
  message: string;
  href?: string | null;
  collection_id?: string | null;
  collection_name?: string;
  created_at: string;
  read_at: string | null;
};

export default function NotificationsPage() {
  const router = useRouter();
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [offsets, setOffsets] = useState({ application: 0, collection: 0 });
  const [hasOlder, setHasOlder] = useState({ application: false, collection: false });
  const [loadingOlder, setLoadingOlder] = useState(false);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [app, collection] = await Promise.all([
        fetchWithAuth("/notifications?limit=100&offset=0"),
        fetchWithAuth("/collections/notifications?offset=0"),
      ]);
      if (!app.ok || !collection.ok) throw new Error("Notification feed unavailable");
      const applicationItems = (await app.json()) as Array<Omit<Item, "source">>;
      const collectionItems = (await collection.json()) as Array<Omit<Item, "source" | "title">>;
      const merged: Item[] = [
        ...applicationItems.map((item) => ({ ...item, source: "application" as const })),
        ...collectionItems.map((item) => ({
          ...item,
          source: "collection" as const,
          title: item.collection_name ?? "Collection update",
        })),
      ];
      merged.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
      setItems((current) => {
        const newestKeys = new Set(merged.map((item) => `${item.source}:${item.id}`));
        return [
          ...merged,
          ...current.filter((item) => !newestKeys.has(`${item.source}:${item.id}`)),
        ].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
      });
      setOffsets((current) => ({
        application: Math.max(current.application, 100),
        collection: Math.max(current.collection, collectionItems.length),
      }));
      setHasOlder({
        application: app.headers.get("X-Has-More") === "true",
        collection: collectionItems.length === 30,
      });
    } catch (error) {
      console.error(error);
      if (!silent) toast.error("Could not load notifications.");
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  const loadOlder = async () => {
    if (loadingOlder || (!hasOlder.application && !hasOlder.collection)) return;
    setLoadingOlder(true);
    try {
      const [app, collection] = await Promise.all([
        hasOlder.application
          ? fetchWithAuth(`/notifications?limit=100&offset=${offsets.application}`)
          : Promise.resolve(null),
        hasOlder.collection
          ? fetchWithAuth(`/collections/notifications?offset=${offsets.collection}`)
          : Promise.resolve(null),
      ]);
      const older: Item[] = [];
      if (app?.ok) {
        const rows = (await app.json()) as Array<Omit<Item, "source">>;
        older.push(...rows.map((item) => ({ ...item, source: "application" as const })));
        setOffsets((current) => ({ ...current, application: current.application + 100 }));
        setHasOlder((current) => ({
          ...current,
          application: app.headers.get("X-Has-More") === "true",
        }));
      }
      if (collection?.ok) {
        const rows = (await collection.json()) as Array<Omit<Item, "source" | "title">>;
        older.push(
          ...rows.map((item) => ({
            ...item,
            source: "collection" as const,
            title: item.collection_name ?? "Collection update",
          })),
        );
        setOffsets((current) => ({ ...current, collection: current.collection + rows.length }));
        setHasOlder((current) => ({ ...current, collection: rows.length === 30 }));
      }
      setItems((current) => {
        const existing = new Set(current.map((item) => `${item.source}:${item.id}`));
        return [
          ...current,
          ...older.filter((item) => !existing.has(`${item.source}:${item.id}`)),
        ].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
      });
    } catch (error) {
      console.error(error);
      toast.error("Could not load older notifications.");
    } finally {
      setLoadingOlder(false);
    }
  };

  useEffect(() => {
    queueMicrotask(() => void refresh());
    const timer = window.setInterval(() => void refresh(true), 30_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const updateOne = async (item: Item, action: "read" | "dismiss") => {
    const base = item.source === "application" ? "/notifications" : "/collections/notifications";
    setBusy(`${item.source}:${item.id}`);
    try {
      const response = await fetchWithAuth(
        action === "read" ? `${base}/${item.id}/read` : `${base}/${item.id}`,
        { method: action === "read" ? "POST" : "DELETE" },
      );
      if (!response.ok) throw new Error(`Notification update failed (${response.status})`);
      if (action === "dismiss")
        setItems((current) =>
          current.filter((entry) => !(entry.id === item.id && entry.source === item.source)),
        );
      else
        setItems((current) =>
          current.map((entry) =>
            entry.id === item.id && entry.source === item.source
              ? { ...entry, read_at: new Date().toISOString() }
              : entry,
          ),
        );
    } catch (error) {
      console.error(error);
      toast.error("Could not update this notification.");
    } finally {
      setBusy(null);
    }
  };

  const openItem = async (item: Item) => {
    if (!item.read_at) await updateOne(item, "read");
    router.push(
      item.href ||
        (item.collection_id
          ? `/dashboard/collections/${item.collection_id}`
          : "/dashboard/collections"),
    );
  };

  return (
    <div className="dashboard-theme-scope w-full space-y-6">
      <DashboardSectionHeader
        title="Notification Center"
        subtitle="Workspace activity, support, Query, provider and storage alerts"
        icon={BellRing}
      />
      <section className="theme-panel max-w-5xl rounded-2xl p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <p className="text-muted-foreground text-xs">
            {items.filter((item) => !item.read_at).length} unread · showing the latest page from
            each feed
          </p>
          <button
            onClick={() => void refresh()}
            disabled={loading}
            className="border-border text-foreground inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs disabled:opacity-50"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
        {loading ? (
          <div className="text-muted-foreground py-16 text-center text-sm">
            Loading notifications…
          </div>
        ) : items.length === 0 ? (
          <div className="border-border text-muted-foreground rounded-xl border border-dashed py-16 text-center text-sm">
            You’re all caught up.
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <article
                key={`${item.source}:${item.id}`}
                className={`flex flex-wrap items-start gap-3 rounded-xl border p-4 ${item.read_at ? "border-border bg-background/40" : "border-primary/30 bg-primary/5"}`}
              >
                <button onClick={() => void openItem(item)} className="min-w-0 flex-1 text-left">
                  <div className="flex flex-wrap items-center gap-2">
                    <strong className="text-foreground text-sm">{item.title}</strong>
                    {item.event_domain && (
                      <span className="border-border text-muted-foreground rounded-full border px-2 py-0.5 text-[10px] capitalize">
                        {item.event_domain}
                      </span>
                    )}
                    <time className="text-muted-foreground text-[10px]">
                      {new Date(item.created_at).toLocaleString()}
                    </time>
                  </div>
                  <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                    {item.message}
                  </p>
                </button>
                <div className="flex gap-1">
                  {!item.read_at && (
                    <button
                      title="Mark read"
                      disabled={busy !== null}
                      onClick={() => void updateOne(item, "read")}
                      className="text-muted-foreground hover:bg-background hover:text-foreground rounded-lg p-2"
                    >
                      <CheckCheck size={15} />
                    </button>
                  )}
                  <button
                    title="Dismiss"
                    disabled={busy !== null}
                    onClick={() => void updateOne(item, "dismiss")}
                    className="text-muted-foreground hover:bg-background hover:text-destructive rounded-lg p-2"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </article>
            ))}
            {(hasOlder.application || hasOlder.collection) && (
              <button
                onClick={() => void loadOlder()}
                disabled={loadingOlder}
                className="border-border text-foreground w-full rounded-lg border px-4 py-3 text-xs font-semibold disabled:opacity-50"
              >
                {loadingOlder ? "Loading older notifications…" : "Load older notifications"}
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
