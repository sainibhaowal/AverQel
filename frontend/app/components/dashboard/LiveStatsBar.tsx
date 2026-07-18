"use client";

import { useEffect, useState } from "react";
import { motion, useSpring, useTransform, type MotionValue } from "framer-motion";

interface Stats {
  documents: number;
  queries: number;
  citations: number;
  avgMs: number;
}

export default function LiveStatsBar() {
  const [stats, setStats] = useState<Stats>({
    documents: 0,
    queries: 0,
    citations: 0,
    avgMs: 0,
  });
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let es: EventSource | null = null;

    const connect = () => {
      es = new EventSource("/api/stats");
      es.onmessage = (event) => {
        try {
          const data: Stats = JSON.parse(event.data);
          setStats(data);
          setConnected(true);
        } catch {
          /* skip malformed */
        }
      };
      es.onerror = () => {
        setConnected(false);
        es?.close();
        // Auto-reconnect after 5s
        setTimeout(connect, 5000);
      };
    };

    connect();
    return () => es?.close();
  }, []);

  return (
    <section className="relative border-y border-white/5 py-8">
      {/* Subtle gradient background */}
      <div className="absolute inset-0 bg-gradient-to-r from-blue-500/5 via-transparent to-purple-500/5" />

      <div className="relative mx-auto max-w-6xl px-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          {/* Live indicator */}
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span
              className={`h-2 w-2 rounded-full ${
                connected ? "animate-pulse bg-green-400" : "bg-red-400"
              }`}
            />
            {connected ? "Live" : "Reconnecting..."}
          </div>
          {/* Stats */}
          <div className="flex flex-1 flex-wrap items-center justify-center gap-8 md:gap-16">
            <StatItem label="Documents Processed" value={stats.documents} />
            <StatItem label="Queries Answered" value={stats.queries} />
            <StatItem label="Citations Generated" value={stats.citations} />
            <StatItem label="Avg Response" value={stats.avgMs} suffix="ms" />
          </div>
          <div className="w-14" /> {/* Spacer for balance */}
        </div>
      </div>
    </section>
  );
}

function StatItem({
  label,
  value,
  suffix = "",
}: {
  label: string;
  value: number;
  suffix?: string;
}) {
  const spring = useSpring(0, { stiffness: 50, damping: 20 });

  useEffect(() => {
    spring.set(value);
  }, [value, spring]);

  return (
    <div className="text-center">
      <div className="text-2xl font-bold text-white tabular-nums md:text-3xl">
        <AnimatedNumber value={spring} />
        {suffix && <span className="ml-1 text-sm text-slate-400">{suffix}</span>}
      </div>
      <div className="mt-1 text-xs text-slate-500">{label}</div>
    </div>
  );
}

function AnimatedNumber({ value }: { value: MotionValue<number> }) {
  const display = useTransform(value, (v) => Math.round(v).toLocaleString());

  return <motion.span>{display}</motion.span>;
}
