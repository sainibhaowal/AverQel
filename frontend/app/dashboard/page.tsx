"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  Cable,
  Clock3,
  Database,
  FileClock,
  FileSearch,
  FileText,
  FolderKanban,
  History,
  Layers3,
  RefreshCcw,
  Search,
  ShieldAlert,
  Upload,
  Zap,
  Activity,
  ShieldCheck,
  Settings2,
  Sparkles,
} from "lucide-react";

import Link from "next/link";
import type { ComponentType } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import UploadModal from "@/app/components/dashboard/documents/UploadModal";
import ParticleAccelerator from "@/app/components/dashboard/ParticleAccelerator";
import { hasAdminRole, hasProviderAccess } from "@/lib/roles";
import { fetchWithAuth } from "../../lib/api";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useVisibilityAwareInterval } from "@/app/hooks/useVisibilityAwareInterval";

interface DashboardStats {
  total_documents: number;
  total_queries: number;
  storage_used_bytes: number;
  active_jobs: number;
}

interface DashboardDocumentBreakdown {
  indexed: number;
  processing: number;
  failed: number;
  queued: number;
  quarantined: number;
}

interface DashboardRecentDocument {
  document_id: string;
  filename: string;
  status: string;
  processing_progress: number;
  size_bytes: number;
  created_at: string;
  extraction_method: string | null;
  collection_names: string[];
}

interface DashboardProviderRuntime {
  feature_scope: string;
  provider_display_name: string;
  provider_type: string;
  model_name: string;
  health_status: string | null;
  latency_ms: number | null;
}

interface DashboardCollectionSummary {
  collection_id: string;
  name: string;
  document_count: number;
  updated_at: string;
}

interface DashboardActivityItem {
  id: string;
  action: string;
  status: string;
  resource_type: string;
  resource_id: string | null;
  created_at: string;
}

interface DashboardOverview {
  stats: DashboardStats;
  document_breakdown: DashboardDocumentBreakdown;
  recent_documents: DashboardRecentDocument[];
  provider_runtimes: DashboardProviderRuntime[];
  collections: DashboardCollectionSummary[];
  recent_activity: DashboardActivityItem[];
}

type AttentionTone = "healthy" | "working" | "risk" | "neutral";

interface AttentionItem {
  label: string;
  value: number;
  helper: string;
  icon: ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  tone: AttentionTone;
  href: string;
}

const CARD_ENTER = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
};

const EMPTY_OVERVIEW: DashboardOverview = {
  stats: {
    total_documents: 0,
    total_queries: 0,
    storage_used_bytes: 0,
    active_jobs: 0,
  },
  document_breakdown: {
    indexed: 0,
    processing: 0,
    failed: 0,
    queued: 0,
    quarantined: 0,
  },
  recent_documents: [],
  provider_runtimes: [],
  collections: [],
  recent_activity: [],
};

export default function DashboardPage() {
  const { user } = useAuth();
  const { theme } = useTheme();
  const hasAdminAccess = hasAdminRole(user?.roles);
  const hasProviderSettingsAccess = hasProviderAccess(user?.roles);
  const [overview, setOverview] = useState<DashboardOverview>(EMPTY_OVERVIEW);
  const [loading, setLoading] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const [isUploadOpen, setIsUploadOpen] = useState(false);

  const fetchDashboardData = useCallback(async () => {
    try {
      const overviewRes = (await fetchWithAuth("/dashboard/overview")) as Response;

      if (overviewRes.ok) {
        setOverview(await overviewRes.json());
      }
    } catch (error) {
      console.error("Failed to fetch dashboard overview", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  useVisibilityAwareInterval(fetchDashboardData, 30000);

  const stats = overview.stats;
  const breakdown = overview.document_breakdown;

  const topStats = useMemo(
    () => [
      {
        label: "Indexed docs",
        value: stats.total_documents,
        detail: "Grounded files ready",
        icon: FileText,
      },
      {
        label: "Queries run",
        value: stats.total_queries,
        detail: "Grounded conversations",
        icon: Search,
      },
      {
        label: "Storage",
        value: formatBytes(stats.storage_used_bytes),
        detail: "Indexed footprint",
        icon: Database,
      },
      {
        label: "Live jobs",
        value: stats.active_jobs,
        detail: "Pipeline work now",
        icon: Zap,
      },
    ],
    [stats],
  );

  const attentionItems = useMemo<AttentionItem[]>(
    () => [
      {
        label: "Failed documents",
        value: breakdown.failed,
        helper: breakdown.failed > 0 ? "Needs retry or diagnosis" : "No failed ingestions",
        icon: ShieldAlert,
        tone: breakdown.failed > 0 ? "risk" : "healthy",
        href: "/dashboard/documents",
      },
      {
        label: "Processing now",
        value: breakdown.processing + stats.active_jobs,
        helper:
          breakdown.processing + stats.active_jobs > 0
            ? "Indexing is still in flight"
            : "No active processing backlog",
        icon: RefreshCcw,
        tone: breakdown.processing + stats.active_jobs > 0 ? "working" : "neutral",
        href: "/dashboard/documents",
      },
      {
        label: "Queued",
        value: breakdown.queued,
        helper: breakdown.queued > 0 ? "Waiting for pipeline capacity" : "No queued uploads",
        icon: FileClock,
        tone: breakdown.queued > 0 ? "working" : "neutral",
        href: "/dashboard/documents",
      },
      {
        label: "Quarantined",
        value: breakdown.quarantined,
        helper: breakdown.quarantined > 0 ? "Review extraction quality" : "No quarantined files",
        icon: AlertTriangle,
        tone: breakdown.quarantined > 0 ? "risk" : "healthy",
        href: "/dashboard/documents",
      },
    ],
    [breakdown, stats.active_jobs],
  );

  const activityGroups = useMemo(() => {
    const groups: { id: string; items: DashboardActivityItem[] }[] = [];
    let current: DashboardActivityItem[] = [];

    overview.recent_activity.forEach((item, idx) => {
      if (idx === 0) {
        current = [item];
      } else {
        const prev = overview.recent_activity[idx - 1];
        if (item.action === prev.action && item.resource_type === prev.resource_type) {
          current.push(item);
        } else {
          groups.push({ id: current[0].id, items: current });
          current = [item];
        }
      }
    });

    if (current.length > 0) {
      groups.push({ id: current[0].id, items: current });
    }
    return groups;
  }, [overview.recent_activity]);

  const toggleGroup = (groupId: string) => {
    setExpandedGroups((prev) => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  const quickActions = [
    {
      title: "Upload documents",
      body: "Bring PDFs and text files into the workspace and index them for grounded answers.",
      icon: Upload,
      action: () => setIsUploadOpen(true),
      primary: true,
    },
    {
      title: "Ask a grounded query",
      body: "Search, summarize, compare, and inspect evidence from the current document set.",
      icon: Search,
      href: "/dashboard/query",
    },
  ];

  if (hasProviderSettingsAccess) {
    quickActions.push({
      title: "Review providers",
      body: "Confirm chat and embedding routes are healthy before query traffic hits them.",
      icon: Cable,
      href: "/dashboard/settings/providers",
    });
  }

  return (
    <div className="space-y-8 pb-10">
      <motion.section
        {...CARD_ENTER}
        transition={{ duration: 0.5 }}
        className={`relative min-h-0 overflow-hidden rounded-[1.5rem] border p-6 shadow-xl transition-all duration-300 sm:rounded-[2rem] sm:p-8 lg:p-10 ${
          theme === "dark"
            ? "border-white/5 bg-[#05070a] shadow-none"
            : "border-teal-500/10 bg-gradient-to-br from-[#ffffff] via-[#f2faf7] to-[#f5f8fa] shadow-lg shadow-teal-950/[0.02]"
        }`}
      >
        {/* Dynamic Background Elements */}
        <div className="bg-primary/10 absolute top-[-10%] right-[-10%] h-[250px] w-[250px] animate-pulse rounded-full opacity-40 blur-[80px] sm:h-[400px] sm:w-[400px] sm:blur-[100px] dark:opacity-80" />
        <div className="bg-accent/5 absolute bottom-[-20%] left-[-10%] h-[200px] w-[200px] rounded-full opacity-20 blur-[60px] sm:h-[300px] sm:w-[300px] sm:blur-[80px] dark:opacity-80" />
        <ParticleAccelerator />

        <div className="relative z-10 flex h-full flex-col justify-center gap-6 xl:flex-row xl:items-center xl:justify-between">
          <div className="max-w-2xl space-y-4">
            <div className="flex items-center gap-2.5">
              <div className="bg-primary/10 border-primary/20 text-primary shadow-primary/5 flex h-9 w-9 items-center justify-center rounded-lg border shadow-lg">
                <ShieldAlert size={18} className="stroke-[2.5]" />
              </div>
              <span className="text-primary/80 text-[10px] font-black tracking-[0.25em] uppercase">
                System Command Surface
              </span>
            </div>

            <div className="space-y-2.5">
              <h1
                className={`text-2xl leading-[1.15] font-black tracking-tight sm:text-4xl md:text-5xl ${
                  theme === "dark" ? "text-white" : "text-black"
                }`}
              >
                Visibility. <span className="text-primary">Grounded.</span> Ready.
              </h1>
              <p
                className={`text-muted-foreground max-w-lg text-sm leading-relaxed font-medium sm:text-base`}
              >
                Your workspace is active. Monitor ingestion health, verify model readiness, and
                command your data pipeline.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3 pt-1">
              <button
                onClick={() => setIsUploadOpen(true)}
                className="bg-primary shadow-primary/15 flex items-center gap-2 rounded-xl px-6 py-3 text-xs font-black tracking-widest !text-white uppercase shadow-lg transition-all hover:scale-[1.03] hover:brightness-110 active:scale-95"
              >
                <Upload size={14} className="stroke-[3] !text-white" />
                Ingest Data
              </button>

              <Link
                href="/dashboard/query"
                prefetch={false}
                className={`flex items-center gap-2 rounded-xl border px-6 py-3 text-xs font-black tracking-widest uppercase backdrop-blur-md transition-all active:scale-95 ${
                  theme === "dark"
                    ? "border-white/10 bg-white/5 text-white hover:bg-white/10"
                    : "border-primary/20 bg-primary/5 text-primary hover:bg-primary/10"
                }`}
              >
                <Search size={14} className="stroke-[3]" />
                Explore
              </Link>
            </div>
          </div>

          <div
            className={`grid grid-cols-2 gap-px overflow-hidden rounded-2xl border ${
              theme === "dark" ? "border-white/5 bg-white/5" : "border-black/5 bg-black/5"
            } xl:w-[26rem]`}
          >
            {topStats.map((stat, idx) => {
              const Icon = stat.icon;
              return (
                <motion.div
                  key={stat.label}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.4, delay: 0.2 + idx * 0.08 }}
                  className={`p-4 sm:p-5 ${
                    theme === "dark" ? "bg-[#0b0f14]" : "bg-white"
                  } hover:bg-opacity-95 transition-all`}
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span
                      className={`text-[8px] font-bold tracking-[0.18em] uppercase ${
                        theme === "dark" ? "text-white/30" : "text-slate-900/40"
                      }`}
                    >
                      {stat.label}
                    </span>
                    <Icon size={14} className="text-primary stroke-[2.5]" />
                  </div>
                  <div
                    className={`text-xl font-black tracking-tight sm:text-2xl ${
                      theme === "dark" ? "text-white" : "text-primary"
                    }`}
                  >
                    {loading ? "..." : stat.value}
                  </div>
                  <p
                    className={`mt-0.5 text-[9px] leading-relaxed font-semibold transition-colors ${
                      theme === "dark" ? "text-white/30" : "text-slate-900/40"
                    }`}
                  >
                    {stat.detail}
                  </p>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Floating Health Status */}
        <div
          className={`absolute bottom-3 left-6 flex flex-wrap items-center gap-4 text-[8px] font-bold tracking-[0.2em] uppercase transition-colors sm:bottom-4 sm:left-8 sm:gap-6 sm:text-[9px] ${
            theme === "dark" ? "text-white/30" : "text-slate-900/40"
          }`}
        >
          <div className="flex items-center gap-1.5">
            <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
            Online
          </div>
          <div className="flex items-center gap-1.5">
            <Clock3 size={11} className="opacity-50" />
            {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </div>
          <div className="flex items-center gap-1.5">
            <History size={11} className="opacity-50" />
            {user?.email?.toUpperCase()}
          </div>
        </div>
      </motion.section>

      <section className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr_0.95fr]">
        <motion.div
          {...CARD_ENTER}
          transition={{ duration: 0.35, delay: 0.05 }}
          className="space-y-5"
        >
          <div className="theme-panel rounded-[1.45rem] p-5">
            <SectionHeader eyebrow="Needs attention" title="Today’s workspace state" chip="Live" />
            <div className="mt-3 space-y-0.5">
              {attentionItems.map((item) => {
                const Icon = item.icon;
                const tone = toneClass(item.tone);
                return (
                  <Link
                    key={item.label}
                    href={item.href}
                    prefetch={false}
                    className="group border-foreground/5 hover:bg-foreground/[0.015] flex items-center gap-3.5 rounded-lg border-b px-2 py-3.5 transition-all last:border-0 dark:border-white/5 dark:hover:bg-white/[0.015]"
                  >
                    <div
                      className={`flex h-9 w-9 items-center justify-center rounded-lg border ${tone.chip}`}
                    >
                      <Icon size={16} className="stroke-[3]" />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-foreground truncate text-sm font-semibold">
                          {item.label}
                        </p>
                        <span
                          className={`text-base font-black tracking-tight ${tone.chip
                            .split(" ")
                            .filter((c) => c.includes("text-"))
                            .join(" ")}`}
                        >
                          {loading ? "…" : item.value}
                        </span>
                      </div>
                      <p className="text-muted-foreground mt-0.5 text-xs font-medium">
                        {item.helper}
                      </p>
                    </div>
                    <ArrowRight
                      size={14}
                      className="text-muted-foreground/30 group-hover:text-primary transition group-hover:translate-x-0.5"
                    />
                  </Link>
                );
              })}
            </div>
          </div>

          <div className="theme-panel rounded-[1.45rem] p-5">
            <SectionHeader
              eyebrow="Recent documents"
              title="Latest indexed or processing files"
              chip={`${overview.recent_documents.length} items`}
            />
            <div className="mt-3 space-y-0.5">
              {loading ? (
                [1, 2, 3].map((row) => (
                  <div
                    key={row}
                    className="bg-foreground/[0.03] border-foreground/5 h-16 animate-pulse rounded-lg border-b last:border-0 dark:border-white/5 dark:bg-white/[0.02]"
                  />
                ))
              ) : overview.recent_documents.length > 0 ? (
                overview.recent_documents.map((document) => (
                  <Link
                    key={document.document_id}
                    href={`/dashboard/documents/${document.document_id}`}
                    prefetch={false}
                    className="group border-foreground/5 hover:bg-foreground/[0.015] block rounded-lg border-b px-2 py-3.5 transition-all last:border-0 dark:border-white/5 dark:hover:bg-white/[0.015]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-foreground group-hover:text-primary truncate text-sm font-semibold transition-colors">
                          {document.filename}
                        </p>
                        <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-2 text-xs font-medium">
                          <span
                            className={`font-semibold tracking-wider uppercase ${
                              document.status === "indexed"
                                ? "text-emerald-500"
                                : document.status === "failed"
                                  ? "text-rose-500"
                                  : "text-amber-500"
                            }`}
                          >
                            {formatStatusLabel(document.status)}
                          </span>
                          <span>•</span>
                          <span>{formatBytes(document.size_bytes)}</span>
                          <span>•</span>
                          <span>{formatRelativeDate(document.created_at)}</span>
                        </div>

                        {document.collection_names.length > 0 ? (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {document.collection_names.slice(0, 2).map((name) => (
                              <span
                                key={name}
                                className="theme-chip rounded-full px-2 py-0.5 text-[9px] font-semibold"
                              >
                                {name}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>

                      <div className="flex items-center gap-2">
                        {document.status !== "indexed" ? (
                          <span className="theme-chip rounded-full px-2.5 py-1 text-[10px] font-medium">
                            {document.processing_progress}%
                          </span>
                        ) : null}
                        <ArrowRight
                          size={14}
                          className="text-muted-foreground/30 group-hover:text-primary transition group-hover:translate-x-0.5"
                        />
                      </div>
                    </div>
                  </Link>
                ))
              ) : (
                <EmptyState
                  icon={FileSearch}
                  title="No documents yet"
                  body="Upload your first file to start grounded answers and indexing."
                />
              )}
            </div>
          </div>

          <div className="theme-panel rounded-[1.45rem] p-5">
            <SectionHeader
              eyebrow="Collections"
              title="Organized document sets"
              chip={`${overview.collections.length} visible`}
            />
            <div className="mt-3 space-y-0.5">
              {loading ? (
                [1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="bg-foreground/[0.03] border-foreground/5 h-14 animate-pulse rounded-lg border-b last:border-0 dark:border-white/5 dark:bg-white/[0.02]"
                  />
                ))
              ) : overview.collections.length > 0 ? (
                overview.collections.map((collection) => {
                  const cardClassName =
                    "group block px-2 py-3.5 border-b border-foreground/5 dark:border-white/5 last:border-0 hover:bg-foreground/[0.015] dark:hover:bg-white/[0.015] rounded-lg transition-all";

                  return (
                    <Link
                      key={collection.collection_id}
                      href={`/dashboard/collections/${collection.collection_id}`}
                      prefetch={false}
                      className={cardClassName}
                    >
                      <div className="flex items-start gap-3">
                        <div className="theme-accent-pill flex h-9 w-9 items-center justify-center rounded-lg">
                          <FolderKanban size={15} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-foreground group-hover:text-primary truncate text-sm font-semibold transition-colors">
                              {collection.name}
                            </p>
                            {hasAdminAccess ? (
                              <ArrowRight
                                size={14}
                                className="text-muted-foreground/30 group-hover:text-primary transition group-hover:translate-x-0.5"
                              />
                            ) : null}
                          </div>
                          <p className="text-muted-foreground mt-0.5 text-xs font-medium">
                            {collection.document_count} document
                            {collection.document_count === 1 ? "" : "s"} • updated{" "}
                            {formatRelativeDate(collection.updated_at)}
                          </p>
                        </div>
                      </div>
                    </Link>
                  );
                })
              ) : (
                <EmptyState
                  icon={FolderKanban}
                  title="No collections yet"
                  body="Create collections to keep document sets focused and reusable."
                />
              )}
            </div>
          </div>
        </motion.div>

        <motion.div
          {...CARD_ENTER}
          transition={{ duration: 0.35, delay: 0.1 }}
          className="space-y-5"
        >
          <div className="theme-panel rounded-[1.45rem] p-5">
            <SectionHeader
              eyebrow="Recent work"
              title="Activity stream"
              chip={`${overview.recent_activity.length} items`}
            />
            <div className="mt-3 space-y-0.5">
              {loading ? (
                [1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className="bg-foreground/[0.03] border-foreground/5 h-14 animate-pulse rounded-lg border-b last:border-0 dark:border-white/5 dark:bg-white/[0.02]"
                  />
                ))
              ) : overview.recent_activity.length > 0 ? (
                activityGroups.map((group) => {
                  const isGroup = group.items.length > 1;
                  const isExpanded = expandedGroups[group.id];
                  const mainEvent = group.items[0];
                  const config = getActivityConfig(mainEvent);
                  const Icon = config.icon;

                  return (
                    <div
                      key={group.id}
                      className="border-foreground/5 border-b last:border-0 dark:border-white/5"
                    >
                      <div className="group flex flex-col rounded-lg transition-all">
                        <button
                          onClick={() => isGroup && toggleGroup(group.id)}
                          disabled={!isGroup}
                          className="hover:bg-foreground/[0.015] flex w-full items-start justify-between gap-3 rounded-lg px-2 py-3.5 text-left transition-colors dark:hover:bg-white/[0.015]"
                        >
                          <div className="flex min-w-0 items-start gap-3">
                            <div
                              className={`theme-accent-pill flex h-9 w-9 items-center justify-center rounded-lg ${config.color.replace("text-", "bg-").split("-").join("-")}/10`}
                            >
                              <Icon size={15} className={`${config.color} stroke-[2.5]`} />
                            </div>
                            <div className="min-w-0">
                              <p className="text-foreground group-hover:text-primary truncate text-sm font-bold tracking-tight transition-colors">
                                {config.label}
                                {isGroup && (
                                  <span className="bg-foreground/5 text-muted-foreground ml-2 rounded-full px-2 py-0.5 text-[9px] font-bold dark:bg-white/5">
                                    {group.items.length} events
                                  </span>
                                )}
                              </p>
                              <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-1.5 text-[10px] font-medium">
                                <span className="font-semibold tracking-wider uppercase">
                                  {mainEvent.resource_type}
                                </span>
                                <span>•</span>
                                <span>{isGroup ? `Latest: ${config.detail}` : config.detail}</span>
                                <span>•</span>
                                <span>{formatRelativeDate(mainEvent.created_at)}</span>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2.5 self-center">
                            <div
                              className={`h-1.5 w-1.5 rounded-full ${
                                config.color.includes("emerald")
                                  ? "bg-emerald-500"
                                  : config.color.includes("blue")
                                    ? "bg-blue-500"
                                    : config.color.includes("amber")
                                      ? "bg-amber-500"
                                      : "bg-primary"
                              }`}
                            />
                            {isGroup && (
                              <motion.div
                                animate={{ rotate: isExpanded ? 180 : 0 }}
                                className="text-muted-foreground/30"
                              >
                                <ArrowRight size={13} className="rotate-90" />
                              </motion.div>
                            )}
                          </div>
                        </button>

                        <AnimatePresence>
                          {isGroup && isExpanded && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              className="overflow-hidden"
                            >
                              <div className="border-foreground/5 bg-foreground/[0.005] border-t px-2 py-1 pb-3 dark:border-white/5 dark:bg-white/[0.005]">
                                {group.items.slice(1).map((item) => {
                                  const subConfig = getActivityConfig(item);
                                  return (
                                    <div
                                      key={item.id}
                                      className="border-foreground/5 mt-3 ml-4.5 flex items-center justify-between border-l-2 pl-3.5 dark:border-white/5"
                                    >
                                      <div className="min-w-0">
                                        <p className="text-foreground/80 truncate text-[11px] font-bold">
                                          {subConfig.label}
                                        </p>
                                        <div className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-[10px]">
                                          <span>{subConfig.detail}</span>
                                          <span>•</span>
                                          <span>{formatRelativeDate(item.created_at)}</span>
                                        </div>
                                      </div>
                                      <div
                                        className={`h-1 w-1 rounded-full ${
                                          subConfig.color.includes("emerald")
                                            ? "bg-emerald-500/50"
                                            : subConfig.color.includes("blue")
                                              ? "bg-blue-500/50"
                                              : "bg-primary/50"
                                        }`}
                                      />
                                    </div>
                                  );
                                })}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    </div>
                  );
                })
              ) : (
                <EmptyState
                  icon={History}
                  title="No recent activity"
                  body="Uploads, queries, retries, and provider changes will appear here."
                />
              )}
            </div>
          </div>
        </motion.div>

        <motion.div
          {...CARD_ENTER}
          transition={{ duration: 0.35, delay: 0.15 }}
          className="space-y-5"
        >
          <div className="theme-panel rounded-[1.45rem] p-5">
            <SectionHeader
              eyebrow="Provider runtime"
              title="Active model routes"
              chip={`${overview.provider_runtimes.length} scopes`}
            />
            <div className="mt-3 space-y-0.5">
              {overview.provider_runtimes.map((runtime) => (
                <div
                  key={runtime.feature_scope}
                  className="group border-foreground/5 hover:bg-foreground/[0.015] rounded-lg border-b px-2 py-3.5 transition-all last:border-0 dark:border-white/5 dark:hover:bg-white/[0.015]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={`rounded-md border px-2.5 py-0.5 text-[9px] font-black tracking-[0.12em] uppercase ${
                            runtime.feature_scope === "chat"
                              ? "dark:!border-primary/40 dark:!bg-primary/15 dark:!text-primary !border-teal-300 !bg-teal-50/70 !text-teal-900"
                              : runtime.feature_scope === "embeddings"
                                ? "!border-cyan-300 !bg-cyan-50/70 !text-cyan-900 dark:!border-cyan-500/40 dark:!bg-cyan-500/15 dark:!text-cyan-300"
                                : runtime.feature_scope === "reranking"
                                  ? "!border-purple-300 !bg-purple-50/70 !text-purple-900 dark:!border-purple-500/40 dark:!bg-purple-500/15 dark:!text-purple-300"
                                  : "!border-amber-300 !bg-amber-50/70 !text-amber-900 dark:!border-amber-500/40 dark:!bg-amber-500/15 dark:!text-amber-300"
                          }`}
                        >
                          {runtime.feature_scope.replace("_", " ")}
                        </span>

                        {runtime.health_status ? (
                          <span
                            className={`rounded-md border px-2.5 py-0.5 text-[9px] font-black tracking-[0.1em] uppercase ${
                              runtime.health_status === "healthy"
                                ? "!border-emerald-300 !bg-emerald-50/70 !text-emerald-900 dark:!border-emerald-500/40 dark:!bg-emerald-500/15 dark:!text-emerald-400"
                                : "!border-amber-300 !bg-amber-50/70 !text-amber-900 dark:!border-amber-500/40 dark:!bg-amber-500/15 dark:!text-amber-400"
                            }`}
                          >
                            {runtime.health_status}
                          </span>
                        ) : null}
                      </div>
                      <p
                        className={`mt-2 text-sm font-bold ${
                          runtime.provider_type === "unconfigured"
                            ? "text-foreground/45"
                            : "text-foreground"
                        }`}
                      >
                        {runtime.provider_display_name}
                      </p>
                      <p className="text-muted-foreground mt-0.5 text-[10px] font-bold tracking-wider uppercase">
                        {runtime.model_name}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-muted-foreground/60 mt-1.5 text-[9px] font-black tracking-widest uppercase">
                        {runtime.latency_ms ? `${runtime.latency_ms} ms` : "No latency yet"}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="theme-panel rounded-[1.45rem] p-5">
            <SectionHeader
              eyebrow="Quick actions"
              title="Move the workspace forward"
              chip="Connected"
              accent
            />
            <div className="mt-4 space-y-3">
              {quickActions.map((action, idx) => {
                const Icon = action.icon;
                const card = (
                  <motion.div
                    key={action.title}
                    {...CARD_ENTER}
                    transition={{ duration: 0.28, delay: idx * 0.04 }}
                    className={
                      action.primary
                        ? "group border-primary/20 from-primary to-primary/80 text-primary-foreground rounded-xl border bg-gradient-to-br p-4 shadow-lg transition-all hover:scale-[1.015] hover:brightness-110 active:scale-95"
                        : "group border-foreground/5 bg-foreground/[0.01] hover:bg-foreground/[0.03] hover:border-primary/20 rounded-xl border p-4 transition-all duration-200 dark:border-white/5 dark:bg-white/[0.01] dark:hover:bg-white/[0.03]"
                    }
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={
                          action.primary
                            ? "flex h-10 w-10 items-center justify-center rounded-lg border border-white/20 bg-white/10 text-white"
                            : "theme-accent-pill flex h-10 w-10 items-center justify-center rounded-lg"
                        }
                      >
                        <Icon size={16} className="stroke-[2.8]" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-semibold">{action.title}</p>
                          <ArrowRight
                            size={14}
                            className={
                              action.primary
                                ? "text-white/70"
                                : "text-muted-foreground/40 group-hover:text-primary transition-all group-hover:translate-x-0.5"
                            }
                          />
                        </div>
                        <p
                          className={`mt-1 text-xs leading-5 ${action.primary ? "opacity-90" : "text-muted-foreground/80 font-medium"}`}
                        >
                          {action.body}
                        </p>
                      </div>
                    </div>
                  </motion.div>
                );

                if ("action" in action) {
                  return (
                    <button
                      key={action.title}
                      type="button"
                      onClick={action.action}
                      className="w-full text-left"
                    >
                      {card}
                    </button>
                  );
                }

                return (
                  <Link key={action.title} href={action.href} prefetch={false}>
                    {card}
                  </Link>
                );
              })}
            </div>
          </div>
        </motion.div>
      </section>

      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onSuccess={() => {
          setIsUploadOpen(false);
          fetchDashboardData();
        }}
      />
    </div>
  );
}

function SectionHeader({
  eyebrow,
  title,
  chip,
  accent = false,
}: {
  eyebrow: string;
  title: string;
  chip: string;
  accent?: boolean;
}) {
  return (
    <div className="border-glass-border flex items-center justify-between border-b pb-4">
      <div>
        <p className="text-foreground/54 text-[11px] font-semibold tracking-[0.18em] uppercase">
          {eyebrow}
        </p>
        <h2 className="text-foreground mt-2 text-xl font-semibold">{title}</h2>
      </div>
      <div
        className={`${accent ? "theme-accent-pill" : "theme-chip"} rounded-md px-3 py-1 text-[11px] font-medium`}
      >
        {chip}
      </div>
    </div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  body,
}: {
  icon: ComponentType<{ size?: number; className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <div className="theme-card rounded-[1rem] border-dashed px-5 py-8 text-center">
      <div className="theme-accent-pill mx-auto flex h-11 w-11 items-center justify-center rounded-[0.95rem]">
        <Icon size={17} />
      </div>
      <p className="text-foreground mt-3 text-sm font-semibold">{title}</p>
      <p className="text-foreground/56 mt-2 text-xs leading-6">{body}</p>
    </div>
  );
}

function toneClass(tone: "healthy" | "working" | "risk" | "neutral") {
  const map = {
    healthy:
      "!border-emerald-500/40 !bg-emerald-500/20 !text-emerald-700 dark:!border-emerald-500/25 dark:!bg-emerald-500/15 dark:!text-emerald-400",
    working:
      "!border-primary/40 !bg-primary/20 !text-primary dark:!border-primary/25 dark:!bg-primary/15 dark:!text-primary",
    risk: "!border-rose-500/40 !bg-rose-500/20 !text-rose-700 dark:!border-rose-500/25 dark:!bg-rose-500/15 dark:!text-rose-400",
    neutral:
      "!border-slate-500/40 !bg-slate-500/20 !text-slate-700 dark:!border-white/20 dark:!bg-white/10 dark:!text-slate-300",
  } as const;

  return { chip: map[tone] };
}

function formatBytes(bytes: number) {
  if (!bytes) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

function formatRelativeDate(value: string) {
  const date = new Date(value);
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatStatusLabel(status: string) {
  if (!status) return "Unknown";
  return status.replace(/_/g, " ");
}
function getActivityConfig(event: DashboardActivityItem) {
  const a = event.action.toLowerCase();
  const s = event.status?.toLowerCase() || "";

  const isSuccess = s === "success" || s === "completed" || s === "indexed";
  const isError = s === "failed" || s === "error" || s === "risk";

  if (a.includes("agent") || a.includes("autonomous") || a.includes("deepspace")) {
    return {
      icon: Sparkles,
      label: "Autonomous Action",
      color: "text-primary",
      detail: "DeepSpace Intelligence",
    };
  }

  if (a.includes("health") || a.includes("test")) {
    return {
      icon: isSuccess ? ShieldCheck : isError ? AlertTriangle : Activity,
      label: isSuccess
        ? "Infrastructure Verified"
        : isError
          ? "Probe Warning"
          : "Connectivity Probe",
      color: isSuccess ? "text-emerald-500" : isError ? "text-rose-500" : "text-blue-500",
      detail: event.resource_id ? `Target: ${event.resource_id.slice(0, 8)}` : "System Path",
    };
  }
  if (a.includes("indexed") || a.includes("processed")) {
    return {
      icon: Database,
      label: "Knowledge Indexed",
      color: "text-emerald-500",
      detail: event.resource_id ? `DocID: ${event.resource_id.slice(0, 8)}` : "Document Storage",
    };
  }
  if (a.includes("processing") || a.includes("ingest")) {
    return {
      icon: Zap,
      label: "Intelligence Pipeline",
      color: "text-amber-500",
      detail: "Stream Ingestion",
    };
  }
  if (a.includes("query")) {
    return {
      icon: Search,
      label: "Intelligence Query",
      color: "text-primary",
      detail: "Context Retrieval",
    };
  }
  if (a.includes("auth") || a.includes("login")) {
    return {
      icon: ShieldCheck,
      label: "Security Access",
      color: "text-slate-500",
      detail: "User Verified",
    };
  }
  if (a.includes("settings") || a.includes("config")) {
    return {
      icon: Settings2,
      label: "System Configuration",
      color: "text-indigo-500",
      detail: "Sync Applied",
    };
  }
  if (a.includes("collection")) {
    return {
      icon: Layers3,
      label: "Namespace Event",
      color: "text-purple-500",
      detail: "State Change",
    };
  }

  return {
    icon: History,
    label: event.action
      .split(".")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" "),
    color: "text-foreground",
    detail: "Log Event",
  };
}
