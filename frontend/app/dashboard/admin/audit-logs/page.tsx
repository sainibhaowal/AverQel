"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldAlert,
  Activity,
  Filter,
  RefreshCcw,
  User,
  ChevronRight,
  Database,
  Lock,
  Loader2,
  XCircle,
} from "lucide-react";
import {
  Fragment,
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { fetchWithAuth } from "@/lib/api";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";

type SelectOptionValue = string | number;
type SelectOnChange<T extends SelectOptionValue> = Dispatch<SetStateAction<T>>;
type SelectIcon = React.ComponentType<{ size?: number; className?: string }>;

function CustomSelect<T extends SelectOptionValue>({
  value,
  onChange,
  options,
  icon: Icon,
  label,
}: {
  value: T;
  onChange: SelectOnChange<T>;
  options: { label: string; value: T }[];
  icon?: SelectIcon;
  label?: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedOption = options.find((o) => o.value === value) || options[0];

  return (
    <div className="relative">
      {isOpen && <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="bg-muted border-glass-border group relative z-50 flex items-center gap-2 rounded-xl border px-4 py-2 transition-colors hover:bg-white/5"
      >
        {Icon && (
          <Icon
            size={14}
            className="text-muted-foreground group-focus-within:text-primary transition-colors"
          />
        )}
        {label && (
          <span className="text-muted-foreground text-[10px] font-bold uppercase">{label}</span>
        )}
        <span className="text-foreground text-xs font-bold tracking-widest uppercase">
          {selectedOption.label}
        </span>
        <ChevronRight
          size={14}
          className={`text-muted-foreground transition-transform ${isOpen ? "rotate-90" : "rotate-0"}`}
        />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="bg-background border-glass-border absolute top-full right-0 z-50 mt-2 min-w-[160px] overflow-hidden rounded-xl border shadow-xl backdrop-blur-xl"
          >
            <div className="flex flex-col py-1">
              {options.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => {
                    onChange(opt.value);
                    setIsOpen(false);
                  }}
                  className={`flex items-center px-4 py-2.5 text-xs font-bold tracking-widest uppercase transition-colors hover:bg-white/10 ${
                    opt.value === value ? "text-primary bg-primary/10" : "text-muted-foreground"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

interface AuditLogItem {
  id: string;
  action: string;
  actor_user_id: string;
  resource_type: string;
  resource_id: string | null;
  status: string;
  trace_id: string;
  created_at: string;
  details: Record<string, string>;
}

export default function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [limit, setLimit] = useState(50);
  const [actionFilter, setActionFilter] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchLogs = useCallback(
    async (cursor: string | null = null, append = false) => {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
      setErrorMessage(null);
      try {
        const params = new URLSearchParams({ limit: limit.toString() });
        if (cursor) params.append("cursor", cursor);
        if (actionFilter) params.append("action", actionFilter);

        const res = (await fetchWithAuth(`/admin/audit-logs?${params.toString()}`)) as Response;
        if (!res.ok) {
          throw new Error(`Failed to load audit logs (${res.status})`);
        }
        const data = await res.json();
        if (append) {
          setLogs((prev) => [...prev, ...data.items]);
        } else {
          setLogs(data.items);
        }
        setNextCursor(data.page.next_cursor);
      } catch (error) {
        console.error("Audit log fetch error", error);
        setErrorMessage("Failed to load audit log history.");
        if (!append) {
          setLogs([]);
          setNextCursor(null);
        }
      } finally {
        if (append) {
          setLoadingMore(false);
        } else {
          setLoading(false);
        }
      }
    },
    [actionFilter, limit],
  );

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const getActionColor = (action: string) => {
    if (action.includes("auth")) return "text-purple-400";
    if (action.includes("admin")) return "text-red-400";
    if (action.includes("queries")) return "text-primary";
    if (action.includes("documents")) return "text-green-400";
    return "text-slate-400";
  };

  const getStatusBadgeClass = (status: string) => {
    const normalized = status.trim().toLowerCase();
    if (normalized === "success" || normalized === "completed") {
      return "bg-green-500/10 text-green-500";
    }
    if (normalized === "failed" || normalized === "error") {
      return "border-primary/30 bg-primary/5 text-primary";
    }
    return "bg-slate-500/10 text-slate-400";
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-none items-end justify-between gap-4">
        <DashboardSectionHeader
          title="Audit Logs"
          subtitle="Immutable Security Event Ledger"
          icon={ShieldAlert}
          accentClassName="bg-rose-500 text-rose-500"
          accentGlowClassName="shadow-[0_0_20px_rgba(244,63,94,0.4)]"
          backHref="/dashboard"
          backLabel="Back To Dashboard"
        />

        <div className="flex items-center gap-4">
          <CustomSelect
            value={actionFilter}
            onChange={setActionFilter}
            icon={Filter}
            options={[
              { label: "All Actions", value: "" },
              { label: "auth.login", value: "auth.login" },
              { label: "auth.signup", value: "auth.signup" },
              { label: "queries.run", value: "queries.run" },
              { label: "documents.upload", value: "documents.upload" },
              { label: "admin.read", value: "admin.audit_logs.read" },
            ]}
          />

          <CustomSelect
            value={limit}
            onChange={setLimit}
            label="Limit:"
            options={[
              { label: "25", value: 25 },
              { label: "50", value: 50 },
              { label: "100", value: 100 },
              { label: "200", value: 200 },
            ]}
          />

          <button
            onClick={() => fetchLogs()}
            className="bg-muted border-glass-border text-muted-foreground hover:text-foreground rounded-xl border p-2.5 transition-all"
          >
            <RefreshCcw size={18} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <div className="glass-card flex flex-col overflow-hidden lg:h-[calc(100dvh-15rem)] lg:min-h-0">
        <div className="relative flex-1 overflow-auto">
          <table className="w-full text-left">
            <thead className="bg-background/95 sticky top-0 z-20 shadow-sm backdrop-blur-md">
              <tr className="border-glass-border bg-muted/30 border-b">
                <th className="w-10 px-4 py-4"></th>
                <th className="text-muted-foreground w-12 px-4 py-4 text-[10px] leading-none font-bold tracking-widest uppercase">
                  No.
                </th>
                <th className="text-muted-foreground px-6 py-4 text-[10px] leading-none font-bold tracking-widest uppercase">
                  Timestamp
                </th>
                <th className="text-muted-foreground px-6 py-4 text-[10px] leading-none font-bold tracking-widest uppercase">
                  Action
                </th>
                <th className="text-muted-foreground px-6 py-4 text-[10px] leading-none font-bold tracking-widest uppercase">
                  Actor
                </th>
                <th className="text-muted-foreground px-6 py-4 text-[10px] leading-none font-bold tracking-widest uppercase">
                  Source
                </th>
                <th className="text-muted-foreground px-6 py-4 text-[10px] leading-none font-bold tracking-widest uppercase">
                  Trace
                </th>
                <th className="text-muted-foreground px-6 py-4 text-[10px] leading-none font-bold tracking-widest uppercase">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-glass-border divide-y text-[13px]">
              {logs.length > 0 ? (
                logs.map((log, index) => (
                  <Fragment key={log.id}>
                    <tr
                      onClick={() => toggleExpand(log.id)}
                      className="hover:bg-muted/50 group cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-4">
                        <ChevronRight
                          size={14}
                          className={`text-slate-600 transition-transform duration-300 ${expandedId === log.id ? "text-primary rotate-90" : ""}`}
                        />
                      </td>
                      <td className="px-4 py-4">
                        <span className="font-mono text-xs text-slate-500">{index + 1}</span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="font-mono text-slate-400">
                          {new Date(log.created_at).toLocaleString([], {
                            dateStyle: "short",
                            timeStyle: "medium",
                          })}
                        </span>
                      </td>
                      <td className="px-6 py-4 font-bold">
                        <div className="flex items-center gap-2">
                          <Activity size={14} className={getActionColor(log.action)} />
                          <span className="text-foreground">{log.action}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2 text-slate-400">
                          <User size={14} className="opacity-50" />
                          <span className="max-w-[120px] truncate font-mono">
                            {log.actor_user_id
                              ? `${log.actor_user_id.split("-")[0]}...`
                              : "System/Anon"}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="bg-muted text-muted-foreground rounded px-2 py-0.5 text-[10px] font-bold tracking-tighter uppercase">
                          {log.resource_type}
                        </span>
                      </td>
                      <td className="px-6 py-4 font-mono text-[11px] text-slate-500 opacity-50">
                        {log.trace_id.slice(0, 8)}
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`rounded-full px-2 py-1 text-[9px] font-bold tracking-wider uppercase ${getStatusBadgeClass(log.status)}`}
                        >
                          {log.status}
                        </span>
                      </td>
                    </tr>
                    <AnimatePresence>
                      {expandedId === log.id && (
                        <motion.tr
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: "auto" }}
                          exit={{ opacity: 0, height: 0 }}
                        >
                          <td
                            colSpan={8}
                            className="border-primary/10 bg-primary/[0.02] border-y px-8 py-6"
                          >
                            <div className="grid grid-cols-3 gap-8">
                              <div className="col-span-2 space-y-4">
                                <h4 className="text-primary flex items-center gap-2 text-[10px] font-bold tracking-widest uppercase">
                                  <Database size={12} /> Forensic Detail Package
                                </h4>
                                <pre className="bg-muted/50 border-glass-border text-muted-foreground overflow-x-auto rounded-xl border p-4 font-mono text-[11px]">
                                  {JSON.stringify(log.details, null, 2)}
                                </pre>
                              </div>
                              <div className="space-y-4">
                                <h4 className="flex items-center gap-2 text-[10px] font-bold tracking-widest text-slate-500 uppercase">
                                  <Lock size={12} /> Security Context
                                </h4>
                                <div className="space-y-3">
                                  <div>
                                    <p className="text-[9px] font-bold text-slate-600 uppercase">
                                      Event ID
                                    </p>
                                    <p className="truncate font-mono text-xs text-slate-400">
                                      {log.id}
                                    </p>
                                  </div>
                                  <div>
                                    <p className="text-[9px] font-bold text-slate-600 uppercase">
                                      Trace ID
                                    </p>
                                    <p className="truncate font-mono text-xs text-slate-400">
                                      {log.trace_id}
                                    </p>
                                  </div>
                                  {log.resource_id && (
                                    <div>
                                      <p className="text-[9px] font-bold text-slate-600 uppercase">
                                        Resource ID
                                      </p>
                                      <p className="truncate font-mono text-xs text-slate-400">
                                        {log.resource_id}
                                      </p>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          </td>
                        </motion.tr>
                      )}
                    </AnimatePresence>
                  </Fragment>
                ))
              ) : errorMessage ? (
                <tr>
                  <td colSpan={8} className="px-6 py-20 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <XCircle size={18} className="text-primary" />
                      <span className="text-sm font-bold tracking-widest text-red-400 uppercase">
                        Failed To Load
                      </span>
                      <p className="text-muted-foreground text-xs">{errorMessage}</p>
                      <button
                        type="button"
                        onClick={() => void fetchLogs()}
                        className="rounded-full border border-white/10 px-4 py-2 text-[10px] font-bold tracking-widest text-slate-300 uppercase transition-colors hover:text-white"
                      >
                        Retry
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr>
                  <td colSpan={8} className="px-6 py-20 text-center">
                    {loading ? (
                      <div className="flex flex-col items-center gap-3">
                        <Loader2 className="text-primary animate-spin" />
                        <span className="text-xs font-medium text-slate-500">
                          Scanning node history...
                        </span>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center gap-3 opacity-30 grayscale">
                        <Activity size={48} />
                        <span className="text-sm font-bold tracking-widest uppercase">
                          {actionFilter ? "No Matching Events" : "No Events Detected"}
                        </span>
                        <p className="text-xs text-slate-500">
                          {actionFilter
                            ? "Try clearing the action filter or syncing status."
                            : "No audit events are available for this tenant yet."}
                        </p>
                      </div>
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {nextCursor && (
          <div className="flex flex-none justify-center border-t border-white/8 px-4 py-3">
            <button
              onClick={() => fetchLogs(nextCursor, true)}
              disabled={loading || loadingMore}
              className="disabled:bg-muted disabled:text-muted-foreground bg-primary text-primary-foreground shadow-primary/25 flex items-center gap-2 rounded-xl px-8 py-3 text-sm font-bold shadow-lg transition-all hover:brightness-110"
            >
              {loadingMore ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <RefreshCcw size={16} />
              )}
              <span>Load More Records</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
