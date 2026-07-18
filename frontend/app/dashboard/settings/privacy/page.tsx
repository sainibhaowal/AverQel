"use client";

import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  Eye,
  EyeOff,
  FileLock2,
  Info,
  KeyRound,
  Loader2,
  ScrollText,
  ShieldCheck,
  ShieldX,
  UserRoundCheck,
  ArrowRight,
} from "lucide-react";

import { fetchWithAuth } from "@/lib/api";
import { useAuth } from "@/app/context/AuthContext";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";

interface ActivityItem {
  id: string;
  action: string;
  status: string;
  resource_type: string;
  resource_id: string | null;
  created_at: string;
  details: Record<string, string>;
}

interface AccountExport {
  generated_at: string;
  account: {
    email: string;
    roles: string[];
    status: string;
    totp_enabled: boolean;
    created_at: string;
    last_login_at: string | null;
  };
  workspace_counts: Record<string, number>;
  recent_activity: ActivityItem[];
}

const cards = [
  {
    title: "Privacy Policy",
    href: "/legal/privacy",
    icon: <ScrollText size={20} />,
    body: "What AverQel collects, what stays private, and when platform-level access may happen.",
    accent: "text-primary",
    accentBg: "bg-primary/10 border-primary/20",
  },
  {
    title: "Terms Of Service",
    href: "/legal/terms",
    icon: <Info size={20} />,
    body: "The operating rules for accounts, acceptable use, suspension, and service integrity.",
    accent: "text-primary",
    accentBg: "bg-primary/10 border-primary/20",
  },
  {
    title: "Trust And Security",
    href: "/legal/security",
    icon: <ShieldCheck size={20} />,
    body: "The security posture behind login, 2FA, session control, and privileged access.",
    accent: "text-emerald-500",
    accentBg: "bg-emerald-500/10 border-emerald-500/20",
  },
  {
    title: "Acceptable Use",
    href: "/legal/acceptable-use",
    icon: <Info size={20} />,
    body: "What is allowed in AverQel and what can lead to suspension or removal.",
    accent: "text-orange-400",
    accentBg: "bg-orange-500/10 border-orange-500/20",
  },
  {
    title: "Retention & Deletion",
    href: "/legal/data-retention",
    icon: <FileLock2 size={20} />,
    body: "How operational data and workspace content are retained and removed.",
    accent: "text-rose-400",
    accentBg: "bg-rose-500/10 border-rose-500/20",
  },
  {
    title: "Subprocessors",
    href: "/legal/subprocessors",
    icon: <Eye size={20} />,
    body: "Where AverQel discloses the external services materially supporting production.",
    accent: "text-primary",
    accentBg: "bg-primary/10 border-primary/20",
  },
];

const containerVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.15 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 22, scale: 0.97 },
  show: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring" as const, stiffness: 300, damping: 26 },
  },
};

const sectionVariants = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: {
      type: "spring" as const,
      stiffness: 260,
      damping: 26,
      delay: 0.2 + i * 0.1,
    },
  }),
};

const activityItemVariants = {
  hidden: { opacity: 0, x: -16 },
  show: (i: number) => ({
    opacity: 1,
    x: 0,
    transition: {
      type: "spring" as const,
      stiffness: 300,
      damping: 28,
      delay: i * 0.04,
    },
  }),
};

const formatDate = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "Never";

export default function PrivacySettingsPage() {
  const { logout, user } = useAuth();
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [loadingActivity, setLoadingActivity] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Delete account modal state
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const passwordInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    const loadActivity = async () => {
      setLoadingActivity(true);
      try {
        const res = (await fetchWithAuth("/auth/activity")) as Response;
        if (!res.ok) throw new Error(`Failed to load activity (${res.status})`);
        const data = (await res.json()) as { items?: ActivityItem[] };
        if (active) {
          setActivity(Array.isArray(data.items) ? data.items : []);
        }
      } catch (error) {
        console.error(error);
        if (active) toast.error("Failed to load account activity.");
      } finally {
        if (active) setLoadingActivity(false);
      }
    };
    void loadActivity();
    return () => {
      active = false;
    };
  }, []);

  // Focus password input when modal opens
  useEffect(() => {
    if (showDeleteModal) {
      setTimeout(() => passwordInputRef.current?.focus(), 120);
    } else {
      setDeletePassword("");
      setShowPassword(false);
    }
  }, [showDeleteModal]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = (await fetchWithAuth("/auth/export")) as Response;
      if (!res.ok) throw new Error(`Failed to export account data (${res.status})`);
      const data = (await res.json()) as AccountExport;
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `averqel-account-export-${user?.email ?? "user"}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success("Account export downloaded.");
    } catch (error) {
      console.error(error);
      toast.error(error instanceof Error ? error.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  const handleDelete = async () => {
    if (!deletePassword.trim()) {
      toast.error("Please enter your password.");
      return;
    }
    setDeleting(true);
    try {
      const res = (await fetchWithAuth("/auth/account", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: deletePassword }),
      })) as Response;
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.error?.message || `Delete failed (${res.status})`);
      }
      setShowDeleteModal(false);
      toast.success("Your account has been permanently deleted.");
      await logout();
      window.location.href = "/auth/login";
    } catch (error) {
      console.error(error);
      toast.error(error instanceof Error ? error.message : "Delete failed.");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="w-full space-y-8">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
      >
        <DashboardSectionHeader
          title="Trust & Privacy"
          subtitle="Data Governance And Transparency Controls"
          icon={ShieldCheck}
          accentClassName="bg-success text-success"
          accentGlowClassName="shadow-[0_0_20px_rgba(var(--success),0.4)]"
          backHref="/dashboard/settings"
          backLabel="Back To Settings"
        />
      </motion.div>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="text-muted-foreground max-w-5xl text-sm leading-7"
      >
        This area explains what AverQel needs to run the service, what remains private user
        workspace data, and gives you direct control over your own privacy actions.
      </motion.p>

      {/* Policy cards grid */}
      <motion.div
        className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        {cards.map((card) => (
          <motion.div key={card.title} variants={cardVariants} className="h-full">
            <Link
              href={card.href}
              className="settings-card group relative flex h-full min-h-[15rem] flex-col p-6 transition"
            >
              <div className="relative z-[1]">
                <div
                  className={`settings-icon-glow flex h-12 w-12 items-center justify-center rounded-2xl border ${card.accentBg} ${card.accent}`}
                >
                  {card.icon}
                </div>
                <h2 className="text-foreground mt-4 text-lg font-semibold tracking-tight">
                  {card.title}
                </h2>
                <p className="text-muted-foreground mt-2 text-sm leading-6">{card.body}</p>
                <div className="text-muted-foreground mt-auto flex items-center gap-1.5 pt-4 text-xs font-semibold opacity-0 transition-all duration-300 group-hover:translate-x-1 group-hover:opacity-100">
                  <span>Read more</span>
                  <ArrowRight size={12} />
                </div>
              </div>
            </Link>
          </motion.div>
        ))}
      </motion.div>

      {/* Three info panels */}
      <motion.div
        className="grid gap-4 xl:grid-cols-3"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        {[
          {
            icon: <UserRoundCheck className="text-primary" size={18} />,
            title: "What AverQel always needs",
            body: "Account identity, session security, login history, and service-side metadata needed to keep the app safe and operational.",
            accent: "border-primary/15",
          },
          {
            icon: <FileLock2 className="text-emerald-500" size={18} />,
            title: "What should remain private",
            body: "Documents, prompts, answers, and chat history are product content. They should not be casually accessed outside legitimate support, security, or legal needs.",
            accent: "border-emerald-500/15",
          },
          {
            icon: <Eye className="text-amber-300" size={18} />,
            title: "Owner access model",
            body: "The platform owner sees account and security metadata globally. Private content access must stay controlled, justified, and auditable.",
            accent: "border-amber-500/15",
          },
        ].map((panel, idx) => (
          <motion.div
            key={panel.title}
            custom={idx}
            variants={sectionVariants}
            initial="hidden"
            animate="show"
            className={`settings-section p-5 ${panel.accent}`}
          >
            <div className="flex items-center gap-3">
              <div className="settings-icon-glow flex h-9 w-9 items-center justify-center rounded-xl">
                {panel.icon}
              </div>
              <h3 className="text-foreground text-sm font-semibold">{panel.title}</h3>
            </div>
            <p className="text-muted-foreground mt-3 text-sm leading-6">{panel.body}</p>
          </motion.div>
        ))}
      </motion.div>

      {/* Rights and controls */}
      <motion.section
        custom={0}
        variants={sectionVariants}
        initial="hidden"
        animate="show"
        className="settings-section p-7"
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-foreground text-lg font-semibold tracking-tight">
              Your rights and controls
            </h2>
            <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
              Export your account data, review your recent security activity, and remove your own
              account if you no longer want to use AverQel.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              type="button"
              onClick={() => void handleExport()}
              disabled={exporting}
              className="border-primary/40 bg-primary/15 text-primary hover:border-primary/50 hover:bg-primary/20 inline-flex items-center gap-2 rounded-full border px-5 py-2.5 text-xs font-bold tracking-[0.18em] uppercase transition-all disabled:opacity-60"
            >
              {exporting ? "Exporting..." : "Export My Data"}
            </motion.button>

            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              type="button"
              onClick={() => setShowDeleteModal(true)}
              disabled={deleting}
              className="rounded-full border border-red-500/40 bg-red-500/15 px-5 py-2.5 text-xs font-bold tracking-[0.18em] text-red-600 uppercase transition-all hover:border-red-500/50 hover:bg-red-500/20 disabled:opacity-60"
            >
              {deleting ? "Deleting..." : "Delete My Account"}
            </motion.button>
          </div>
        </div>

        <div className="settings-divider mt-6 mb-5" />

        <div>
          <h3 className="text-foreground text-sm font-semibold tracking-[0.18em] uppercase">
            Recent account activity
          </h3>
          <div className="mt-4 max-h-[32rem] space-y-3 overflow-y-auto pr-2">
            {loadingActivity ? (
              <div className="text-muted-foreground flex items-center gap-3 text-sm">
                <Loader2 size={16} className="text-primary animate-spin" />
                Loading account activity...
              </div>
            ) : activity.length ? (
              activity.slice(0, 8).map((item, idx) => (
                <motion.div
                  key={item.id}
                  custom={idx}
                  variants={activityItemVariants}
                  initial="hidden"
                  animate="show"
                  className="settings-activity-item p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-foreground text-sm font-semibold">{item.action}</p>
                      <p className="text-muted-foreground mt-1 text-xs">
                        {item.resource_type} &middot; {formatDate(item.created_at)}
                      </p>
                    </div>
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/15 px-3 py-1 text-[10px] font-black tracking-[0.18em] text-emerald-700 uppercase">
                      <span className="settings-status-dot bg-emerald-500" />
                      {item.status}
                    </span>
                  </div>
                </motion.div>
              ))
            ) : (
              <p className="text-muted-foreground text-sm">No recent account activity yet.</p>
            )}
          </div>
        </div>
      </motion.section>

      {/* ── Delete Account Modal ── */}
      <AnimatePresence>
        {showDeleteModal && (
          <motion.div
            key="delete-modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
            style={{ backgroundColor: "rgba(0,0,0,0.72)", backdropFilter: "blur(6px)" }}
            onClick={(e) => {
              if (e.target === e.currentTarget) setShowDeleteModal(false);
            }}
          >
            <motion.div
              key="delete-modal-panel"
              initial={{ opacity: 0, scale: 0.94, y: 24 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.94, y: 24 }}
              transition={{ type: "spring", stiffness: 340, damping: 28 }}
              className="w-full max-w-md overflow-hidden rounded-[1.75rem] border border-red-500/20 bg-[#0d0d0f] shadow-[0_40px_100px_-20px_rgba(239,68,68,0.25),0_0_0_1px_rgba(239,68,68,0.08)]"
            >
              {/* Header */}
              <div className="flex items-start gap-4 border-b border-red-500/12 bg-red-500/6 px-6 py-5">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-red-500/25 bg-red-500/12 text-red-400">
                  <ShieldX size={20} />
                </div>
                <div>
                  <p className="text-base font-semibold text-red-300">Delete Account Permanently</p>
                  <p className="mt-0.5 text-xs text-red-400/70">
                    This action is irreversible and cannot be undone.
                  </p>
                </div>
              </div>

              {/* Warning body */}
              <div className="space-y-4 px-6 py-5">
                <div className="rounded-xl border border-red-500/15 bg-red-500/6 px-4 py-3 text-sm leading-6 text-red-300/80">
                  <p className="mb-1 font-semibold text-red-300">
                    The following will be permanently erased:
                  </p>
                  <ul className="list-inside list-disc space-y-0.5 text-xs text-red-400/75">
                    <li>All your documents and uploaded files</li>
                    <li>All your queries and chat history</li>
                    <li>All your comments and pinned findings</li>
                    <li>Your account and login credentials</li>
                  </ul>
                </div>

                {/* Password field */}
                <div className="space-y-2">
                  <label className="flex items-center gap-1.5 text-xs font-semibold tracking-[0.14em] text-slate-400 uppercase">
                    <KeyRound size={12} />
                    Confirm with your password
                  </label>
                  <div className="relative">
                    <input
                      ref={passwordInputRef}
                      id="delete-account-password"
                      type={showPassword ? "text" : "password"}
                      value={deletePassword}
                      onChange={(e) => setDeletePassword(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void handleDelete();
                      }}
                      placeholder="Enter your password…"
                      disabled={deleting}
                      autoComplete="current-password"
                      className="w-full rounded-xl border border-white/8 bg-white/4 px-4 py-3 pr-11 text-sm text-white placeholder-slate-500 transition outline-none focus:border-red-500/40 focus:bg-white/6 focus:ring-1 focus:ring-red-500/20 disabled:opacity-50"
                    />
                    <button
                      type="button"
                      tabIndex={-1}
                      onClick={() => setShowPassword((v) => !v)}
                      className="absolute top-1/2 right-3 -translate-y-1/2 text-slate-500 transition hover:text-slate-300"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3 border-t border-white/6 px-6 py-4">
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  type="button"
                  onClick={() => setShowDeleteModal(false)}
                  disabled={deleting}
                  className="flex-1 rounded-xl border border-white/10 bg-white/5 py-2.5 text-sm font-semibold text-slate-300 transition hover:bg-white/8 disabled:opacity-50"
                >
                  Cancel
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  type="button"
                  onClick={() => void handleDelete()}
                  disabled={deleting || !deletePassword.trim()}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-red-500/30 bg-red-500/12 py-2.5 text-sm font-semibold text-red-300 transition hover:bg-red-500/18 disabled:opacity-40"
                >
                  {deleting ? (
                    <>
                      <Loader2 size={15} className="animate-spin" /> Deleting…
                    </>
                  ) : (
                    <>
                      <ShieldX size={15} /> Delete My Account
                    </>
                  )}
                </motion.button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
