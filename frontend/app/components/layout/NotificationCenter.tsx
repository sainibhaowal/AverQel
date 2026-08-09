"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Bell,
  BellRing,
  Check,
  CheckCheck,
  ChevronRight,
  Link2Off,
  Trash2,
  UserMinus,
  Users,
  X,
  Zap,
} from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import toast from "react-hot-toast";
import { fetchWithAuth } from "@/lib/api";
import { useVisibilityAwareInterval } from "@/app/hooks/useVisibilityAwareInterval";

type NotificationItem = {
  id: string;
  collection_id: string | null;
  collection_name: string;
  event_type: string;
  message: string;
  created_at: string;
  read_at: string | null;
};

const POLL_INTERVAL_MS = 15_000;

function formatWhen(value: string, now: number | null) {
  const date = new Date(value);
  if (now === null) return date.toISOString();
  const diffMin = Math.round((Date.now() - date.getTime()) / 60_000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffMin < 24 * 60) return `${Math.round(diffMin / 60)}h ago`;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function getNotificationIcon(eventType: string) {
  if (eventType === "member_left") return UserMinus;
  if (eventType === "collection_deleted" || eventType === "collection_removed") return Link2Off;
  if (eventType === "agent_intervention") return Zap;
  return Users;
}

export default function NotificationCenter() {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [now, setNow] = useState<number | null>(null);

  const unreadCount = useMemo(
    () => notifications.filter((item) => item.read_at === null).length,
    [notifications],
  );

  const loadNotifications = async (options?: { silent?: boolean }) => {
    if (!options?.silent) setLoading(true);
    try {
      const res = (await fetchWithAuth("/collections/notifications")) as Response;
      if (!res.ok) throw new Error(`Failed to load notifications (${res.status})`);
      setNotifications((await res.json()) as NotificationItem[]);
    } catch (error) {
      console.error(error);
      if (!options?.silent) toast.error("Failed to load notifications.");
    } finally {
      if (!options?.silent) setLoading(false);
    }
  };

  useEffect(() => {
    setMounted(true);
    setNow(Date.now());
    void loadNotifications();
  }, []);

  useVisibilityAwareInterval(() => void loadNotifications({ silent: true }), POLL_INTERVAL_MS);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const markRead = async (notificationId: string) => {
    const item = notifications.find((entry) => entry.id === notificationId);
    if (!item || item.read_at) return;
    setBusy(notificationId);
    try {
      const res = (await fetchWithAuth(`/collections/notifications/${notificationId}/read`, {
        method: "POST",
      })) as Response;
      if (!res.ok) throw new Error(`Failed to mark notification read (${res.status})`);
      const updated = (await res.json()) as NotificationItem;
      setNotifications((current) =>
        current.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
    } catch (error) {
      console.error(error);
      toast.error("Failed to mark notification as read.");
    } finally {
      setBusy(null);
    }
  };

  const clearOne = async (notificationId: string) => {
    setBusy(notificationId);
    try {
      const res = (await fetchWithAuth(`/collections/notifications/${notificationId}`, {
        method: "DELETE",
      })) as Response;
      if (!res.ok) throw new Error(`Failed to clear notification (${res.status})`);
      setNotifications((current) => current.filter((entry) => entry.id !== notificationId));
    } catch (error) {
      console.error(error);
      toast.error("Failed to clear notification.");
    } finally {
      setBusy(null);
    }
  };

  const markAllRead = async () => {
    setBusy("all-read");
    try {
      const res = (await fetchWithAuth("/collections/notifications/read-all", {
        method: "POST",
      })) as Response;
      if (!res.ok) throw new Error(`Failed to mark all notifications as read (${res.status})`);
      setNotifications((current) =>
        current.map((entry) => ({ ...entry, read_at: entry.read_at ?? new Date().toISOString() })),
      );
    } catch (error) {
      console.error(error);
      toast.error("Failed to mark all notifications as read.");
    } finally {
      setBusy(null);
    }
  };

  const clearAll = async () => {
    setBusy("all-clear");
    try {
      const res = (await fetchWithAuth("/collections/notifications", {
        method: "DELETE",
      })) as Response;
      if (!res.ok) throw new Error(`Failed to clear notifications (${res.status})`);
      setNotifications([]);
    } catch (error) {
      console.error(error);
      toast.error("Failed to clear notifications.");
    } finally {
      setBusy(null);
    }
  };

  const openNotification = async (item: NotificationItem) => {
    if (!item.read_at) await markRead(item.id);
    setOpen(false);
    if (
      item.collection_id &&
      item.event_type !== "collection_deleted" &&
      item.event_type !== "collection_removed"
    ) {
      router.push(`/dashboard/collections/${item.collection_id}?section=access`);
    } else {
      router.push("/dashboard/collections");
    }
  };

  const drawerContent = (
    <AnimatePresence>
      {open ? (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-[9998] bg-black/60 backdrop-blur-sm"
          />
          <motion.div
            initial={{ x: "100%", opacity: 0.9 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "100%", opacity: 0.9 }}
            transition={{ type: "spring", damping: 30, stiffness: 350 }}
            style={{ background: "var(--panel-strong)" }}
            className="border-glass-border fixed inset-y-0 right-0 z-[9999] flex w-[28rem] max-w-full flex-col overflow-hidden rounded-l-[2rem] border-l shadow-[-20px_0_60px_rgba(0,0,0,0.5)] backdrop-blur-3xl"
          >
            <div className="border-glass-border flex items-center justify-between border-b px-6 py-5">
              <div>
                <h2 className="text-foreground text-sm font-black tracking-widest uppercase">
                  Notifications
                </h2>
                <p className="text-muted-foreground mt-1 text-[10px] font-bold tracking-wider uppercase">
                  Workspace updates
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-foreground/50 hover:text-foreground rounded-xl p-2 transition hover:bg-white/5"
              >
                <X size={16} />
              </button>
            </div>
            <div className="custom-scrollbar flex-1 overflow-y-auto p-6">
              <div className="mb-4 flex items-center justify-between">
                <p className="text-muted-foreground text-xs font-bold">
                  {unreadCount > 0
                    ? `${unreadCount} unread alert${unreadCount > 1 ? "s" : ""}`
                    : "No unread updates"}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void markAllRead()}
                    disabled={busy !== null || unreadCount === 0}
                    className="theme-chip text-foreground/70 inline-flex h-8 items-center gap-1.5 rounded-xl px-3 text-xs hover:bg-white/5 disabled:opacity-40"
                  >
                    <CheckCheck size={14} />
                    Mark all read
                  </button>
                  <button
                    type="button"
                    onClick={() => void clearAll()}
                    disabled={busy !== null || notifications.length === 0}
                    className="theme-chip text-foreground/70 inline-flex h-8 items-center gap-1.5 rounded-xl px-3 text-xs hover:bg-white/5 disabled:opacity-40"
                  >
                    <Trash2 size={14} />
                    Clear all
                  </button>
                </div>
              </div>
              {loading ? (
                <div className="theme-panel-muted text-muted-foreground animate-pulse rounded-2xl px-4 py-16 text-center text-sm">
                  Loading notifications...
                </div>
              ) : notifications.length === 0 ? (
                <div className="theme-panel-muted text-muted-foreground rounded-2xl border border-white/5 bg-white/[0.01] px-4 py-16 text-center text-sm">
                  No notifications yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {notifications.map((item) => {
                    const Icon = getNotificationIcon(item.event_type);
                    const unread = item.read_at === null;
                    return (
                      <motion.div
                        key={item.id}
                        layout
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        className={`group rounded-2xl border p-4 transition ${unread ? "border-primary/30 bg-primary/5" : "theme-panel-muted border-glass-border/40 bg-white/[0.01]"}`}
                      >
                        <div className="flex items-start gap-4">
                          <div
                            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${unread ? "bg-primary text-white" : "text-muted-foreground bg-white/5"}`}
                          >
                            <Icon size={16} />
                          </div>
                          <button
                            type="button"
                            onClick={() => void openNotification(item)}
                            className="min-w-0 flex-1 text-left"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <p className="text-foreground text-sm font-semibold">
                                {item.collection_name}
                              </p>
                              {unread ? (
                                <span className="bg-primary mt-1.5 h-2 w-2 shrink-0 rounded-full" />
                              ) : null}
                            </div>
                            <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">
                              {item.message}
                            </p>
                            <div className="text-muted-foreground/60 mt-3 flex items-center gap-1.5 text-[9px] font-black tracking-widest uppercase">
                              <span>{formatWhen(item.created_at, now)}</span>
                              <ChevronRight size={10} />
                              <span>{unread ? "Resolve" : "View"}</span>
                            </div>
                          </button>
                          <div className="flex shrink-0 items-center gap-1.5">
                            {unread ? (
                              <button
                                type="button"
                                onClick={() => void markRead(item.id)}
                                disabled={busy === item.id}
                                className="theme-chip text-foreground/50 inline-flex h-7 w-7 items-center justify-center rounded-lg"
                                aria-label="Mark read"
                              >
                                <Check size={14} />
                              </button>
                            ) : null}
                            <button
                              type="button"
                              onClick={() => void clearOne(item.id)}
                              disabled={busy === item.id}
                              className="theme-chip text-foreground/50 inline-flex h-7 w-7 items-center justify-center rounded-lg"
                              aria-label="Clear"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="border-glass-border border-t px-6 py-4">
              <button
                type="button"
                onClick={() => void loadNotifications()}
                disabled={loading}
                className="text-foreground/45 hover:text-foreground inline-flex items-center gap-1.5 text-[9px] font-black tracking-widest uppercase disabled:opacity-40"
              >
                Refresh
              </button>
            </div>
          </motion.div>
        </>
      ) : null}
    </AnimatePresence>
  );

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        data-tooltip="Notifications"
        aria-label="Notifications"
        className={`ui-tooltip bg-muted border-glass-border text-muted-foreground hover:text-foreground relative inline-flex h-9 w-9 items-center justify-center rounded-xl border transition-all hover:-translate-y-0.5 hover:shadow-md ${open ? "border-primary/35 text-primary" : ""}`}
      >
        {unreadCount > 0 ? <BellRing size={16} /> : <Bell size={16} />}
        {unreadCount > 0 ? (
          <span className="bg-primary text-primary-foreground absolute -top-1.5 -right-1.5 inline-flex min-w-[1.2rem] items-center justify-center rounded-full px-1.5 py-0.5 text-[10px] font-bold">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        ) : null}
      </button>
      {mounted ? createPortal(drawerContent, document.body) : null}
    </div>
  );
}
