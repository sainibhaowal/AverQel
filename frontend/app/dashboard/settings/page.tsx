"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  Settings as SettingsIcon,
  User,
  Cable,
  ShieldCheck,
  ArrowRight,
  MessageSquare,
  Sparkles,
} from "lucide-react";

import { useAuth } from "@/app/context/AuthContext";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { hasProviderAccess } from "@/lib/roles";

const containerVariants = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.08, delayChildren: 0.15 },
  },
};

const cardVariants = {
  hidden: { opacity: 0, y: 24, scale: 0.97 },
  show: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring" as const, stiffness: 320, damping: 28, mass: 0.8 },
  },
};

const panelVariants = {
  hidden: { opacity: 0, y: 20 },
  show: {
    opacity: 1,
    y: 0,
    transition: { type: "spring" as const, stiffness: 260, damping: 26, delay: 0.35 },
  },
};

type SettingsSection = {
  title: string;
  href: string;
  icon: React.ReactNode;
  desc: string;
  accent: string;
  accentBg: string;
  glowColor: string;
};

export default function SettingsPage() {
  const { user } = useAuth();
  const canManageProviders = hasProviderAccess(user?.roles);

  const sections: SettingsSection[] = [
    {
      title: "Profile",
      href: "/dashboard/settings/profile",
      icon: <User size={20} />,
      desc: "Update your personal details and avatar.",
      accent: "text-primary",
      accentBg: "bg-primary/10 border-primary/20",
      glowColor: "group-hover:shadow-[0_0_24px_-4px_rgba(var(--primary),0.35)]",
    },
    {
      title: "Trust & Privacy",
      href: "/dashboard/settings/privacy",
      icon: <ShieldCheck size={20} />,
      desc: "See what AverQel collects, what stays private, and what policies apply.",
      accent: "text-success",
      accentBg: "bg-success/10 border-success/20",
      glowColor: "group-hover:shadow-[0_0_24px_-4px_rgba(var(--success),0.35)]",
    },
  ];

  if (canManageProviders) {
    sections.push({
      title: "Providers",
      href: "/dashboard/settings/providers",
      icon: <Cable size={20} />,
      desc: "Configure LLM, embedding, and local runtime providers.",
      accent: "text-info",
      accentBg: "bg-info/10 border-info/20",
      glowColor: "group-hover:shadow-[0_0_24px_-4px_rgba(var(--info),0.35)]",
    });
  }

  return (
    <div className="w-full space-y-8">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
      >
        <DashboardSectionHeader
          title="Settings"
          subtitle="Personal And Workspace Preferences"
          icon={SettingsIcon}
          accentClassName="bg-slate-500 text-slate-500"
          accentGlowClassName="shadow-[0_0_20px_rgba(100,116,139,0.4)]"
        />
      </motion.div>

      <motion.div
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        {sections.map((section) => {
          const cardClassName = `settings-card group relative flex h-full min-h-[10rem] cursor-pointer flex-col gap-4 p-6 transition-all duration-300 hover:translate-y-[-4px] hover:shadow-xl`;
          const cardContent = (
            <div className="relative z-[1] flex h-full w-full flex-col">
              <div className="flex items-start justify-between">
                <div
                  className={`settings-icon-glow flex h-10 w-10 items-center justify-center rounded-xl border ${section.accentBg} ${section.accent} ${section.glowColor} transition-all`}
                >
                  {section.icon}
                </div>
                <div className="text-muted-foreground/30 group-hover:text-primary transition-colors">
                  <ArrowRight size={16} />
                </div>
              </div>
              <div className="mt-4">
                <h3 className="text-foreground mb-1 text-base font-black tracking-tight">
                  {section.title}
                </h3>
                <p className="text-muted-foreground text-xs leading-relaxed font-medium">
                  {section.desc}
                </p>
              </div>
              <div className="text-primary mt-auto pt-4 text-[10px] font-bold tracking-[0.2em] uppercase opacity-0 transition-opacity duration-300 group-hover:opacity-100">
                Configure Now
              </div>
            </div>
          );

          return (
            <motion.div key={section.title} variants={cardVariants} className="h-full">
              <Link href={section.href} className={cardClassName}>
                {cardContent}
              </Link>
            </motion.div>
          );
        })}
      </motion.div>

      <motion.div variants={panelVariants} initial="hidden" animate="show">
        <div className="settings-featured p-7">
          <div className="relative z-[1]">
            <div className="settings-divider mb-5" />
            <h2 className="text-foreground text-lg font-black tracking-tight">
              What AverQel can see
            </h2>
            <p className="text-muted-foreground mt-2.5 max-w-5xl text-sm leading-7 font-medium">
              AverQel needs account and security metadata to run the product safely. Private
              workspace content should remain purpose-bound to the service, not casually browsed.
              Open the Trust & Privacy area for the full explanation.
            </p>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link
                href="/dashboard/settings/privacy"
                className="border-primary/25 bg-primary text-primary-foreground inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm font-semibold shadow-sm transition-colors hover:bg-primary/90 focus-visible:ring-primary/40 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                <ShieldCheck size={16} strokeWidth={2} />
                Trust &amp; Privacy
                <ArrowRight size={15} strokeWidth={2} />
              </Link>
              <Link
                href="/dashboard/feedback"
                className="inline-flex h-10 items-center gap-2 rounded-md border border-border bg-background/55 px-4 text-sm font-semibold text-foreground shadow-sm transition-colors hover:border-amber-500/35 hover:bg-amber-500/8 focus-visible:ring-amber-500/30 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                <Sparkles size={16} strokeWidth={2} className="text-amber-600 dark:text-amber-400" />
                Share feedback
              </Link>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Compact icon-only support control */}
      <motion.div
        className="fixed right-6 bottom-6 z-50 sm:right-8 sm:bottom-8"
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.8, type: "spring", damping: 15 }}
      >
        <Link
          href="/dashboard/support"
          aria-label="Open support"
          title="Support"
          className="group bg-primary relative flex h-12 w-12 items-center justify-center rounded-lg text-primary-foreground shadow-lg shadow-black/10 transition-colors hover:bg-primary/90 focus-visible:ring-primary/40 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          <MessageSquare size={20} strokeWidth={2} className="transition-transform duration-200 group-hover:-rotate-6" />

          <span className="sr-only">Support</span>
          <div className="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full border-2 border-background bg-red-500" />
        </Link>
      </motion.div>
    </div>
  );
}
