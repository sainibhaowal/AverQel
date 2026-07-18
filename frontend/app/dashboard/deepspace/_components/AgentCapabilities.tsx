"use client";

import { motion } from "framer-motion";
import {
  Mail,
  Calendar,
  Github,
  Slack,
  Database,
  Globe,
  Zap,
  CheckCircle2,
  Lock,
} from "lucide-react";
import { useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/api";
import RuntimeIndicatorChips, { type RuntimeIndicatorState } from "./RuntimeIndicatorChips";

interface Capability {
  id: string;
  name: string;
  slug: string;
  description: string;
  status: "active" | "inactive" | "locked";
  icon: React.ReactNode;
}

type ConnectorSummary = {
  integration?: {
    slug?: string;
  } | null;
  slug?: string;
};

export default function AgentCapabilities({
  runtimeIndicators,
}: {
  runtimeIndicators?: RuntimeIndicatorState | null;
}) {
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadCapabilities() {
      try {
        const response = (await fetchWithAuth("/integrations/connectors")) as Response;
        if (response.ok) {
          const connectors = (await response.json()) as ConnectorSummary[];
          const activeSlugs = new Set(
            connectors
              .map((c) => c.integration?.slug || c.slug)
              .filter((slug): slug is string => Boolean(slug)),
          );

          const baseCapabilities: Capability[] = [
            {
              id: "web",
              name: "Web Intelligence",
              slug: "web-search",
              description: "Live search & URL analysis",
              status: "active",
              icon: <Globe size={16} />,
            },
            {
              id: "docs",
              name: "Knowledge Base",
              slug: "ecosystem-docs",
              description: "Semantic search over documents",
              status: "active",
              icon: <Database size={16} />,
            },
            {
              id: "gmail",
              name: "Gmail Agent",
              slug: "gmail",
              description: "Read, search & draft emails",
              status: activeSlugs.has("gmail") ? "active" : "inactive",
              icon: <Mail size={16} />,
            },
            {
              id: "calendar",
              name: "Calendar Pilot",
              slug: "google-calendar",
              description: "Schedule & manage meetings",
              status: activeSlugs.has("google-calendar") ? "active" : "inactive",
              icon: <Calendar size={16} />,
            },
            {
              id: "github",
              name: "Code Inspector",
              slug: "github",
              description: "Analyze repos & files",
              status: activeSlugs.has("github") ? "active" : "inactive",
              icon: <Github size={16} />,
            },
            {
              id: "slack",
              name: "Slack Relay",
              slug: "slack",
              description: "Context from team comms",
              status: activeSlugs.has("slack") ? "active" : "inactive",
              icon: <Slack size={16} />,
            },
          ];

          setCapabilities(baseCapabilities);
        }
      } catch (err) {
        console.error("Failed to load capabilities", err);
      } finally {
        setLoading(false);
      }
    }

    loadCapabilities();
  }, []);

  if (loading) return null;

  return (
    <div className="space-y-4">
      {runtimeIndicators ? (
        <div className="rounded-2xl border border-cyan-400/14 bg-cyan-400/8 p-3">
          <div className="mb-2 flex items-center gap-2 text-[10px] font-black tracking-[0.2em] text-cyan-100/75 uppercase">
            <Zap size={11} className="text-cyan-300" />
            Runtime Posture
          </div>
          <RuntimeIndicatorChips indicators={runtimeIndicators} compact />
        </div>
      ) : null}

      <div className="flex items-center justify-between">
        <h2 className="text-foreground/40 flex items-center gap-2 text-[10px] font-black tracking-[0.2em] uppercase">
          <Zap size={12} className="text-primary" />
          Agent Skillset
        </h2>
        <span className="text-primary/60 bg-primary/5 rounded-full px-2 py-0.5 text-[10px] font-bold">
          {capabilities.filter((c) => c.status === "active").length} Active
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {capabilities.map((cap) => {
          const isActive = cap.status === "active";
          return (
            <motion.div
              key={cap.id}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="group relative"
            >
              <div
                className={`flex h-9 w-9 items-center justify-center rounded-lg border transition-all duration-300 ${
                  isActive
                    ? "border-cyan-500/30 bg-cyan-950/20 text-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.15)]"
                    : "border-white/5 bg-white/5 text-white/30 grayscale"
                }`}
              >
                {cap.icon}
              </div>

              {/* Custom Tooltip */}
              <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 z-50 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                <div className="theme-panel border-glass-border bg-surface-0/95 min-w-[170px] border p-2.5 shadow-2xl backdrop-blur-xl rounded-lg">
                  <div className="flex items-center justify-between gap-1.5 font-bold text-[11px]">
                    <span className={isActive ? "text-cyan-400" : "text-white/40"}>
                      {cap.name}
                    </span>
                    {isActive ? (
                      <CheckCircle2 size={10} className="text-emerald-500 flex-shrink-0" />
                    ) : (
                      <Lock size={10} className="text-white/30 flex-shrink-0" />
                    )}
                  </div>
                  <p className="text-foreground/50 mt-1 text-[10px] leading-relaxed">
                    {cap.description}
                  </p>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
