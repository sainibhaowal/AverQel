"use client";

import {
  Activity,
  Bot,
  Brain,
  ChevronRight,
  HeartPulse,
  CheckCircle2,
  AlertTriangle,
  Clock,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/api";

interface VitalsSnapshot {
  internet: string;
  llm: string;
  web_search: string;
  sources: number;
}

interface Activity {
  id: string;
  type: string;
  description: string;
  source: string;
  metadata?: Record<string, unknown> | null;
  created_at: string;
}

export default function IntelligencePulseCard() {
  const [vitals, setVitals] = useState<VitalsSnapshot | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadPulse() {
      try {
        const [vitalsRes, activityRes] = (await Promise.all([
          fetchWithAuth("/deepspace/chats/vitals"),
          fetchWithAuth("/deepspace/chats/activity?limit=3"),
        ])) as [Response, Response];

        if (vitalsRes.ok) {
          const data = await vitalsRes.json();
          setVitals(data as VitalsSnapshot);
        }
        if (activityRes.ok) {
          const data = await activityRes.json();
          setActivities(Array.isArray(data) ? data : data.items || []);
        }
      } catch (err) {
        console.error("Failed to load pulse data", err);
      } finally {
        setLoading(false);
      }
    }

    loadPulse();
    const interval = setInterval(loadPulse, 15000);
    return () => clearInterval(interval);
  }, []);

  if (loading)
    return (
      <div className="theme-panel animate-pulse rounded-[1.45rem] p-5">
        <div className="bg-foreground/10 mb-4 h-4 w-24 rounded" />
        <div className="space-y-3">
          <div className="bg-foreground/5 h-12 rounded-xl" />
          <div className="bg-foreground/5 h-12 rounded-xl" />
        </div>
      </div>
    );

  const overallHealth =
    vitals?.internet === "connected" &&
    vitals?.llm === "connected" &&
    vitals?.web_search === "available"
      ? "healthy"
      : "warning";
  const vitalCards = [
    {
      name: "Internet",
      value: vitals?.internet ?? "unknown",
      healthy: vitals?.internet === "connected",
    },
    {
      name: "LLM",
      value: vitals?.llm ?? "unknown",
      healthy: vitals?.llm === "connected",
    },
    {
      name: "Web Search",
      value: vitals?.web_search ?? "unknown",
      healthy: vitals?.web_search === "available",
    },
    {
      name: "Sources",
      value: String(vitals?.sources ?? 0),
      healthy: (vitals?.sources ?? 0) > 0,
    },
  ];

  return (
    <div className="theme-panel border-primary/10 flex flex-col rounded-[1.45rem] p-5">
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div
            className={`rounded-lg p-1.5 ${
              overallHealth === "healthy"
                ? "bg-emerald-500/10 text-emerald-500"
                : "bg-amber-500/10 text-amber-500"
            }`}
          >
            <HeartPulse size={16} />
          </div>
          <div>
            <h3 className="text-xs font-black tracking-widest uppercase">Intelligence Pulse</h3>
            <p className="text-muted-foreground text-[10px] font-bold">DeepSpace Proactive Core</p>
          </div>
        </div>
        <Link
          href="/dashboard/connectors/proactive"
          prefetch={false}
          className="text-primary hover:bg-primary/5 rounded-full p-1.5 transition"
        >
          <ChevronRight size={16} />
        </Link>
      </div>

      <div className="flex-1 space-y-4">
        {/* Vitals Summary */}
        <div className="grid grid-cols-2 gap-y-3 gap-x-4 rounded-xl bg-foreground/[0.02] dark:bg-white/[0.02] p-3">
          {vitalCards.map((vital, idx) => (
            <div
              key={vital.name}
              className={`flex flex-col justify-between ${
                idx % 2 === 0 ? "border-r border-foreground/5 dark:border-white/5 pr-2" : "pl-1"
              }`}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="text-foreground/40 text-[9px] font-black tracking-wider uppercase">
                  {vital.name}
                </span>
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    vital.healthy ? "bg-emerald-500" : "bg-amber-500"
                  }`}
                />
              </div>
              <p className="mt-1 truncate text-xs font-bold text-foreground/80">{vital.value}</p>
            </div>
          ))}
        </div>

        {/* Latest Activity */}
        <div className="space-y-3">
          <h4 className="text-foreground/30 px-1 text-[9px] font-black tracking-[0.2em] uppercase">
            Latest Autonomous Actions
          </h4>
          <div className="space-y-3 pl-1">
            {activities.length > 0 ? (
              activities.map((act) => (
                <div
                  key={act.id}
                  className="relative flex items-start gap-3 pl-4 before:absolute before:left-1.5 before:top-2 before:bottom-[-16px] before:w-[1px] before:bg-foreground/5 dark:before:bg-white/5 last:before:hidden"
                >
                  <div className="absolute left-0.5 top-1.5 h-2 w-2 rounded-full border border-primary/40 bg-primary/20" />
                  <div className="min-w-0 flex-1">
                    <p className="text-foreground/90 text-xs leading-normal font-medium">
                      {act.description}
                    </p>
                    <div className="mt-1 flex items-center gap-2 text-[10px]">
                      <span className="text-primary/75 font-bold uppercase tracking-wider">
                        {act.type}
                      </span>
                      <span className="text-muted-foreground/40">•</span>
                      <span className="text-muted-foreground/60 flex items-center gap-1 font-medium">
                        <Clock size={10} className="opacity-70" />
                        {new Date(act.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="py-4 text-center">
                <p className="text-muted-foreground text-[10px] font-medium italic">
                  Monitoring for activity...
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mt-5 border-t border-foreground/5 dark:border-white/5 pt-4">
        <Link
          href="/dashboard/connectors/proactive"
          prefetch={false}
          className="bg-primary shadow-primary/20 flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-[11px] font-black tracking-widest text-white uppercase shadow-lg transition hover:brightness-110"
        >
          <Brain size={14} />
          Open Proactive Workspace
        </Link>
      </div>
    </div>
  );
}
