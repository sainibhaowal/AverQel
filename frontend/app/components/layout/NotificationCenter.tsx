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
  HeartPulse,
  Cable,
  Bot,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Settings,
  RefreshCw,
  Cpu,
  Globe,
  Wifi,
  Cloud,
  Mail,
  Calendar,
  Database,
  ExternalLink,
} from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import toast from "react-hot-toast";
import { fetchWithAuth } from "@/lib/api";
import { useVisibilityAwareInterval } from "@/app/hooks/useVisibilityAwareInterval";
import Link from "next/link";

type NotificationItem = {
  id: string;
  collection_id: string | null;
  collection_name: string;
  event_type: string;
  message: string;
  created_at: string;
  read_at: string | null;
};

interface VitalsSnapshot {
  internet: string;
  llm: string;
  web_search: string;
  sources: number;
  proactive_daemon?: {
    enabled: boolean;
    phase: string;
    timestamp?: string | null;
    interval_seconds?: number | null;
    healthy: boolean;
  } | null;
}

interface ConnectorItem {
  id: string;
  name: string;
  status: "ACTIVE" | "PAUSED" | "ERROR" | "SYNCING";
  last_sync_at: string | null;
}

interface SubagentRun {
  run_id: string;
  subagent_type: string;
  status: string;
}

const POLL_INTERVAL_MS = 15_000;

function formatWhen(value: string) {
  const date = new Date(value);
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffMin = Math.round(diffMs / 60_000);

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

function getConnectorIcon(name: string) {
  const norm = name.toLowerCase();
  if (norm.includes("slack")) return Zap;
  if (norm.includes("github")) return GithubConnector;
  if (norm.includes("drive")) return Cloud;
  if (norm.includes("gmail")) return Mail;
  if (norm.includes("calendar")) return Calendar;
  if (norm.includes("notion")) return Database;
  return Cable;
}

// Simple local fallback for Github icon to avoid importing massive libraries
interface GithubConnectorProps {
  className?: string;
  size?: number;
}

function GithubConnector(props: GithubConnectorProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={props.className}
      width={props.size || 16}
      height={props.size || 16}
    >
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
      <path d="M9 18c-4.51 2-5-2-7-2" />
    </svg>
  );
}

export default function NotificationCenter() {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [activeTab, setActiveTab] = useState<"inbox" | "vitals">("inbox");

  // Vitals states
  const [vitals, setVitals] = useState<VitalsSnapshot | null>(null);
  const [connectors, setConnectors] = useState<ConnectorItem[]>([]);
  const [subagents, setSubagents] = useState<SubagentRun[]>([]);
  const [vitalsLoading, setVitalsLoading] = useState(false);

  const buttonRef = useRef<HTMLButtonElement | null>(null);

  const unreadCount = useMemo(
    () => notifications.filter((item) => item.read_at === null).length,
    [notifications],
  );

  const loadNotifications = async (options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setLoading(true);
    }
    try {
      const res = (await fetchWithAuth("/collections/notifications")) as Response;
      if (!res.ok) {
        throw new Error(`Failed to load notifications (${res.status})`);
      }
      const data = (await res.json()) as NotificationItem[];
      setNotifications(data);
    } catch (error) {
      console.error(error);
      if (!options?.silent) {
        toast.error("Failed to load notifications.");
      }
    } finally {
      if (!options?.silent) {
        setLoading(false);
      }
    }
  };

  const loadVitalsData = async () => {
    setVitalsLoading(true);
    try {
      const [vitalsRes, connectorsRes, subagentsRes] = (await Promise.all([
        fetchWithAuth("/deepspace/chats/vitals"),
        fetchWithAuth("/integrations/connectors"),
        fetchWithAuth("/deepspace/chats/subagents?limit=8"),
      ])) as [Response, Response, Response];

      if (vitalsRes.ok) {
        setVitals(await vitalsRes.json());
      }
      if (connectorsRes.ok) {
        setConnectors(await connectorsRes.json());
      }
      if (subagentsRes.ok) {
        setSubagents(await subagentsRes.json());
      }
    } catch (error) {
      console.error("Failed to load vitals data:", error);
    } finally {
      setVitalsLoading(false);
    }
  };

  useEffect(() => {
    setMounted(true);
    void loadNotifications();
  }, []);

  useVisibilityAwareInterval(() => {
    void loadNotifications({ silent: true });
  }, POLL_INTERVAL_MS);

  // Poll vitals when drawer is open
  useEffect(() => {
    if (open) {
      void loadVitalsData();
      const interval = setInterval(loadVitalsData, 10000);
      return () => clearInterval(interval);
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  const markRead = async (notificationId: string) => {
    const item = notifications.find((entry) => entry.id === notificationId);
    if (!item || item.read_at) {
      return;
    }
    setBusy(notificationId);
    try {
      const res = (await fetchWithAuth(`/collections/notifications/${notificationId}/read`, {
        method: "POST",
      })) as Response;
      if (!res.ok) {
        throw new Error(`Failed to mark notification read (${res.status})`);
      }
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
      if (!res.ok) {
        throw new Error(`Failed to clear notification (${res.status})`);
      }
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
      if (!res.ok) {
        throw new Error(`Failed to mark all notifications as read (${res.status})`);
      }
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
      if (!res.ok) {
        throw new Error(`Failed to clear notifications (${res.status})`);
      }
      setNotifications([]);
    } catch (error) {
      console.error(error);
      toast.error("Failed to clear notifications.");
    } finally {
      setBusy(null);
    }
  };

  const openNotification = async (item: NotificationItem) => {
    if (!item.read_at) {
      await markRead(item.id);
    }
    setOpen(false);
    if (
      item.event_type === "agent_intervention" ||
      item.collection_name?.includes("Proactive")
    ) {
      router.push("/dashboard/connectors");
      return;
    }
    if (
      item.collection_id &&
      item.event_type !== "collection_deleted" &&
      item.event_type !== "collection_removed"
    ) {
      router.push(`/dashboard/collections/${item.collection_id}?section=access`);
      return;
    }
    router.push("/dashboard/collections");
  };

  const vitalsOptimal =
    vitals?.internet === "connected" &&
    vitals?.llm === "connected" &&
    vitals?.web_search === "available";

  const runningSubagents = subagents.filter((r) => r.status === "running").length;

  const drawerContent = (
    <AnimatePresence>
      {open ? (
        <>
          {/* Backdrop Blur Overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-[9998] bg-black/60 backdrop-blur-sm"
          />

          {/* Slide-out Right Drawer */}
          <motion.div
            initial={{ x: "100%", opacity: 0.9 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "100%", opacity: 0.9 }}
            transition={{ type: "spring", damping: 30, stiffness: 350 }}
            style={{ background: "var(--panel-strong)" }}
            className="fixed inset-y-0 right-0 z-[9999] w-[28rem] max-w-full overflow-hidden flex flex-col rounded-l-[2rem] border-l border-glass-border shadow-[-20px_0_60px_rgba(0,0,0,0.5)] backdrop-blur-3xl"
          >
            {/* Header */}
            <div className="border-glass-border flex items-center justify-between border-b px-6 py-5">
              <div>
                <h2 className="text-foreground text-sm font-black tracking-widest uppercase">System Hub</h2>
                <p className="text-muted-foreground mt-1 text-[10px] font-bold uppercase tracking-wider">
                  {activeTab === "inbox" ? "Notifications & Alerts" : "Live Diagnostics"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-foreground/50 hover:text-foreground hover:bg-white/5 rounded-xl p-2 transition"
              >
                <X size={16} />
              </button>
            </div>

            {/* Tab Selector */}
            <div className="flex border-b border-glass-border bg-white/[0.02]">
              <button
                type="button"
                onClick={() => setActiveTab("inbox")}
                className={`flex-1 py-3 text-center text-xs font-black tracking-widest uppercase transition-all border-b-2 ${
                  activeTab === "inbox"
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                Inbox ({notifications.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("vitals")}
                className={`flex-1 py-3 text-center text-xs font-black tracking-widest uppercase transition-all border-b-2 ${
                  activeTab === "vitals"
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                System Vitals
              </button>
            </div>

            {/* Drawer Content */}
            <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
              {activeTab === "inbox" ? (
                /* INBOX TAB */
                <div>
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
                        className="theme-chip hover:bg-white/5 text-foreground/70 hover:text-foreground inline-flex h-8 px-3 items-center justify-center gap-1.5 rounded-xl text-xs disabled:opacity-40"
                      >
                        <CheckCheck size={14} />
                        Mark all read
                      </button>
                      <button
                        type="button"
                        onClick={() => void clearAll()}
                        disabled={busy !== null || notifications.length === 0}
                        className="theme-chip hover:bg-white/5 text-foreground/70 hover:text-foreground inline-flex h-8 px-3 items-center justify-center gap-1.5 rounded-xl text-xs disabled:opacity-40"
                      >
                        <Trash2 size={14} />
                        Clear all
                      </button>
                    </div>
                  </div>

                  {loading ? (
                    <div className="theme-panel-muted rounded-2xl px-4 py-16 text-center text-sm text-muted-foreground animate-pulse">
                      Loading notifications...
                    </div>
                  ) : notifications.length === 0 ? (
                    <div className="theme-panel-muted rounded-2xl px-4 py-16 text-center text-sm text-muted-foreground border border-white/5 bg-white/[0.01]">
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
                            exit={{ opacity: 0, y: -6 }}
                            className={`group rounded-2xl border p-4 transition ${
                              unread
                                ? "border-primary/30 bg-primary/5 shadow-[0_4px_20px_rgba(var(--primary),0.05)]"
                                : "theme-panel-muted border-glass-border/40 bg-white/[0.01]"
                            }`}
                          >
                            <div className="flex items-start gap-4">
                              <div
                                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                                  unread
                                    ? "bg-primary text-white shadow-md shadow-primary/20"
                                    : "bg-white/5 text-muted-foreground"
                                  }`}
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
                                    <span className="bg-primary mt-1.5 h-2 w-2 shrink-0 rounded-full shadow-[0_0_8px_rgba(var(--primary),0.8)]" />
                                  ) : null}
                                </div>
                                <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">
                                  {item.message}
                                </p>
                                <div className="text-muted-foreground/60 mt-3 flex items-center gap-1.5 text-[9px] font-black tracking-widest uppercase">
                                  <span>{formatWhen(item.created_at)}</span>
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
                                    className="theme-chip hover:bg-white/5 text-foreground/50 hover:text-foreground inline-flex h-7 w-7 items-center justify-center rounded-lg transition"
                                    aria-label="Mark read"
                                  >
                                    <Check size={14} />
                                  </button>
                                ) : null}
                                <button
                                  type="button"
                                  onClick={() => void clearOne(item.id)}
                                  disabled={busy === item.id}
                                  className="theme-chip hover:bg-white/5 text-foreground/50 hover:text-foreground inline-flex h-7 w-7 items-center justify-center rounded-lg transition"
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
              ) : (
                /* SYSTEM VITALS TAB */
                <div className="space-y-6">
                  {/* Live Overview Status */}
                  <div className={`rounded-2xl border p-4 flex items-center justify-between ${
                    vitalsOptimal
                      ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-300"
                      : "border-amber-500/20 bg-amber-500/5 text-amber-300"
                  }`}>
                    <div className="flex items-center gap-3">
                      <HeartPulse className={vitalsOptimal ? "animate-pulse" : ""} size={20} />
                      <div>
                        <p className="text-xs font-black tracking-widest uppercase">System Core Health</p>
                        <p className="text-[10px] opacity-75 font-semibold mt-0.5">
                          {vitalsOptimal ? "All systems are operating normally" : "Some services report degraded vitals"}
                        </p>
                      </div>
                    </div>
                    <span className="text-[10px] font-black tracking-widest uppercase border border-current/25 rounded-md px-2 py-0.5">
                      {vitalsOptimal ? "Optimal" : "Degraded"}
                    </span>
                  </div>

                  {/* Vitals Grid */}
                  <div className="space-y-2.5">
                    <h3 className="text-foreground/30 px-1 text-[9px] font-black tracking-[0.2em] uppercase">Core Vitals</h3>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { name: "Internet Link", value: vitals?.internet, ok: vitals?.internet === "connected" },
                        { name: "LLM Core Connection", value: vitals?.llm, ok: vitals?.llm === "connected" },
                        { name: "Web Search Utility", value: vitals?.web_search, ok: vitals?.web_search === "available" },
                        { name: "Proactive Daemon", value: vitals?.proactive_daemon?.enabled ? "Enabled" : "Disabled", ok: Boolean(vitals?.proactive_daemon?.enabled) },
                      ].map((v) => (
                        <div key={v.name} className="theme-panel-muted border border-white/5 bg-white/[0.01] rounded-xl p-3 flex flex-col justify-between h-16">
                          <span className="text-foreground/40 text-[9px] font-black tracking-wider uppercase truncate">{v.name}</span>
                          <div className="flex items-center justify-between gap-2 mt-1">
                            <span className="text-xs font-bold text-foreground/80 truncate capitalize">{v.value || "unknown"}</span>
                            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${v.ok ? "bg-emerald-500" : "bg-amber-500"}`} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Active Worker Slots */}
                  <div className="theme-panel-muted border border-white/5 bg-white/[0.01] rounded-2xl p-4 space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <Bot size={16} className="text-cyan-400" />
                        <h4 className="text-foreground/70 text-[10px] font-black tracking-[0.16em] uppercase">Active Subagents</h4>
                      </div>
                      <span className="text-xs font-mono font-bold text-foreground/60">{runningSubagents} / 4 slots in use</span>
                    </div>
                    <div className="grid grid-cols-4 gap-1.5">
                      {Array.from({ length: 4 }).map((_, idx) => {
                        const active = idx < runningSubagents;
                        return (
                          <div
                            key={idx}
                            className={`h-1.5 rounded-full transition-all ${
                              active
                                ? "bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.6)]"
                                : "bg-white/5 border border-white/5"
                            }`}
                          />
                        );
                      })}
                    </div>
                  </div>

                  {/* Connectors Health */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between px-1">
                      <h3 className="text-foreground/30 text-[9px] font-black tracking-[0.2em] uppercase">Connectors HUD</h3>
                      <Link
                        href="/dashboard/connectors"
                        onClick={() => setOpen(false)}
                        className="text-[9px] font-black tracking-widest text-primary uppercase hover:underline inline-flex items-center gap-1"
                      >
                        Configure
                        <ExternalLink size={10} />
                      </Link>
                    </div>
                    <div className="space-y-2">
                      {connectors.length === 0 ? (
                        <div className="theme-panel-muted rounded-xl p-4 text-center text-xs text-muted-foreground border border-white/5">
                          No active connectors configured.
                        </div>
                      ) : (
                        connectors.map((c) => {
                          const Icon = getConnectorIcon(c.name);
                          const active = c.status === "ACTIVE" || c.status === "SYNCING";
                          return (
                            <div key={c.id} className="theme-panel-muted border border-white/5 bg-white/[0.01] rounded-xl p-3 flex items-center justify-between gap-3">
                              <div className="flex items-center gap-3 min-w-0">
                                <div className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 ${
                                  active ? "bg-primary/10 text-primary" : "bg-white/5 text-muted-foreground"
                                }`}>
                                  <Icon size={14} />
                                </div>
                                <div className="min-w-0">
                                  <p className="text-xs font-bold text-foreground truncate">{c.name}</p>
                                  <p className="text-[9px] text-muted-foreground/60 truncate mt-0.5">
                                    {c.last_sync_at ? `Synced ${formatWhen(c.last_sync_at)}` : "Never synced"}
                                  </p>
                                </div>
                              </div>
                              <span className={`text-[9px] font-black tracking-widest uppercase border rounded-md px-2 py-0.5 ${
                                c.status === "ACTIVE"
                                  ? "border-emerald-500/20 text-emerald-400 bg-emerald-500/5"
                                  : c.status === "SYNCING"
                                    ? "border-cyan-500/20 text-cyan-400 bg-cyan-500/5"
                                    : c.status === "PAUSED"
                                      ? "border-amber-500/20 text-amber-400 bg-amber-500/5"
                                      : "border-red-500/20 text-red-400 bg-red-500/5"
                              }`}>
                                {c.status.toLowerCase()}
                              </span>
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="border-t border-glass-border px-6 py-4 bg-white/[0.01]">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Activity size={12} className={vitalsOptimal ? "text-emerald-400" : "text-amber-400"} />
                  <span className="text-[10px] font-black tracking-widest uppercase text-muted-foreground">Pulse Status</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    if (activeTab === "inbox") void loadNotifications();
                    else void loadVitalsData();
                  }}
                  disabled={vitalsLoading || loading}
                  className="text-foreground/45 hover:text-foreground inline-flex items-center gap-1.5 text-[9px] font-black tracking-widest uppercase transition disabled:opacity-40"
                >
                  <RefreshCw size={10} className={vitalsLoading || loading ? "animate-spin" : ""} />
                  Sync HUD
                </button>
              </div>
            </div>
          </motion.div>
        </>
      ) : null}
    </AnimatePresence>
  );

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((current) => !current)}
        data-tooltip="Notifications"
        aria-label="Notifications"
        className={`ui-tooltip bg-muted border-glass-border text-muted-foreground hover:text-foreground relative inline-flex h-9 w-9 items-center justify-center rounded-xl border transition-all hover:-translate-y-0.5 hover:shadow-md ${
          open ? "border-primary/35 text-primary" : ""
        }`}
      >
        {unreadCount > 0 ? <BellRing size={16} /> : <Bell size={16} />}
        {unreadCount > 0 ? (
          <span className="bg-primary text-primary-foreground absolute -top-1.5 -right-1.5 inline-flex min-w-[1.2rem] items-center justify-center rounded-full px-1.5 py-0.5 text-[10px] font-bold shadow-[0_0_20px_rgba(var(--primary),0.45)]">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        ) : null}
      </button>

      {mounted ? createPortal(drawerContent, document.body) : null}
    </div>
  );
}
