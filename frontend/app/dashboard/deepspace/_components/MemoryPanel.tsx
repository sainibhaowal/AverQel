"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Search,
  Trash2,
  Clock,
  Globe,
  Terminal,
  Info,
  Database,
  Activity,
  Sigma,
} from "lucide-react";
import { useState, useEffect } from "react";
import { apiV1 } from "@/lib/api";

interface MemoryItem {
  id: string;
  key: string;
  value: string;
  scope: "user" | "global";
  relevance_score?: number;
  created_at: string;
}

interface MemoryLifecycleSummary {
  memory_count: number;
  embedded_count: number;
  pgvector_count: number;
  embedding_coverage: number;
  duplicate_count: number;
  scope_breakdown: Record<string, number>;
  retention_breakdown: Record<string, number>;
  stale_count: number;
  stale_session_count: number;
  average_decay_score: number;
  memory_health_score: number;
  retention_risk_count: number;
  sample_queries: Array<{ query: string; matches: number; top_score: number }>;
  retention_policy: {
    session_retention_days: number;
    decay_half_life_days: number;
  };
  session_retention_days: number;
  stale_memory_ids: string[];
  stale_preview_count: number;
  attention_memories: Array<{
    id: string;
    key: string;
    value: string;
    scope: string;
    tags: string[];
    importance_score: number;
    access_count: number;
    last_accessed_at: string | null;
    metadata: Record<string, unknown>;
    embedding_provider: string | null;
    embedding_model: string | null;
    embedding_version: string | null;
    pgvector_ready: boolean | null;
    decay_score: number | null;
    created_at: string | null;
    updated_at: string | null;
    retention_state: string;
  }>;
}

export default function MemoryPanel() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [lifecycle, setLifecycle] = useState<MemoryLifecycleSummary | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchMemories();
  }, []);

  const fetchMemories = async (query = "") => {
    setIsLoading(true);
    try {
      const memoryPromise = query
        ? apiV1.get<{ results: MemoryItem[] }>(
            `/deepspace/chats/memory/search?query=${encodeURIComponent(query)}`,
          )
        : apiV1.get<MemoryItem[]>("/deepspace/chats/memory");
      const [data, lifecycleData] = await Promise.all([
        memoryPromise,
        apiV1.get<MemoryLifecycleSummary>("/deepspace/chats/memory/lifecycle"),
      ]);
      setMemories(Array.isArray(data) ? data : data.results || []);
      setLifecycle(lifecycleData);
    } catch (err) {
      console.error("Failed to fetch memories", err);
    } finally {
      setIsLoading(false);
    }
  };

  const deleteMemory = async (key: string) => {
    try {
      await apiV1.delete(`/deepspace/chats/memory/${encodeURIComponent(key)}`);
      setMemories((prev) => prev.filter((m) => m.key !== key));
    } catch (err) {
      console.error("Failed to delete memory", err);
    }
  };

  return (
    <div className="bg-background/50 flex h-full flex-col backdrop-blur-3xl">
      {/* Header */}
      <div className="border-b border-white/5 bg-white/5 p-6">
        <div className="mb-6 flex items-center gap-3">
          <div className="bg-primary/20 border-primary/30 rounded-xl border p-2.5">
            <Brain size={20} className="text-primary shadow-[0_0_15px_rgba(var(--primary),0.5)]" />
          </div>
          <div>
            <h2 className="text-foreground/90 text-lg font-black tracking-tight">
              Universal Memory
            </h2>
            <p className="text-foreground/40 text-[10px] font-bold tracking-[0.2em] uppercase">
              AverQel Persistent Knowledge
            </p>
          </div>
        </div>

        {/* Search Bar */}
        <div className="relative">
          <Search
            size={14}
            className="text-foreground/30 absolute top-1/2 left-4 -translate-y-1/2"
          />
          <input
            type="text"
            placeholder="Search across sessions..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fetchMemories(searchQuery)}
            className="text-foreground/80 focus:border-primary/50 w-full rounded-full border border-white/10 bg-white/5 py-2.5 pr-4 pl-10 text-[12px] transition-all focus:bg-white/10 focus:outline-none"
          />
        </div>

        {lifecycle ? (
          <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div className="rounded-xl border border-white/5 bg-white/[0.04] p-3">
              <div className="text-foreground/35 text-[9px] font-black tracking-[0.22em] uppercase">
                Coverage
              </div>
              <div className="mt-2 flex items-center gap-2 text-sm font-bold text-emerald-300">
                <Sigma size={13} />
                {(lifecycle.embedding_coverage * 100).toFixed(0)}%
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.04] p-3">
              <div className="text-foreground/35 text-[9px] font-black tracking-[0.22em] uppercase">
                Pgvector
              </div>
              <div className="mt-2 flex items-center gap-2 text-sm font-bold text-cyan-300">
                <Database size={13} />
                {lifecycle.pgvector_count}/{lifecycle.memory_count}
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.04] p-3">
              <div className="text-foreground/35 text-[9px] font-black tracking-[0.22em] uppercase">
                Stale
              </div>
              <div className="mt-2 flex items-center gap-2 text-sm font-bold text-amber-300">
                <Activity size={13} />
                {lifecycle.stale_count}
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.04] p-3">
              <div className="text-foreground/35 text-[9px] font-black tracking-[0.22em] uppercase">
                Health
              </div>
              <div className="mt-2 flex items-center gap-2 text-sm font-bold text-fuchsia-300">
                <Brain size={13} />
                {lifecycle.memory_health_score.toFixed(0)}/100
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.04] p-3">
              <div className="text-foreground/35 text-[9px] font-black tracking-[0.22em] uppercase">
                Session Stale
              </div>
              <div className="mt-2 flex items-center gap-2 text-sm font-bold text-orange-300">
                <Clock size={13} />
                {lifecycle.stale_session_count}
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.04] p-3">
              <div className="text-foreground/35 text-[9px] font-black tracking-[0.22em] uppercase">
                Decay
              </div>
              <div className="mt-2 flex items-center gap-2 text-sm font-bold text-fuchsia-300">
                <Clock size={13} />
                {lifecycle.average_decay_score.toFixed(2)}
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {/* Memory List */}
      <div className="custom-scrollbar flex-1 space-y-3 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex h-40 items-center justify-center">
            <div className="border-primary h-5 w-5 animate-spin rounded-full border-b-2"></div>
          </div>
        ) : memories.length === 0 ? (
          <div className="flex h-60 flex-col items-center justify-center opacity-30">
            <Database size={40} className="mb-4" />
            <p className="text-[11px] font-bold tracking-widest uppercase">Knowledge Base Empty</p>
            <p className="mt-2 text-[9px]">AverQel will learn from your interactions.</p>
          </div>
        ) : (
          <AnimatePresence mode="popLayout">
            {memories.map((mem) => (
              <motion.div
                key={mem.id}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="group hover:border-primary/30 rounded-xl border border-white/5 bg-white/5 p-4 transition-all hover:bg-white/[0.07]"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="mb-1.5 flex items-center gap-2">
                      <span className="text-primary/80 bg-primary/10 rounded px-2 py-0.5 text-[10px] font-black tracking-wider uppercase">
                        {mem.key}
                      </span>
                      {mem.scope === "global" && (
                        <span className="text-foreground/40 flex items-center gap-1 rounded-full border border-white/10 px-1.5 text-[8px] font-bold uppercase">
                          <Globe size={8} /> Global
                        </span>
                      )}
                    </div>
                    <p className="text-foreground/70 text-[12px] leading-relaxed italic">
                      &quot;{mem.value}&quot;
                    </p>
                    <div className="mt-3 flex items-center gap-4 border-t border-white/5 pt-3">
                      <div className="text-foreground/30 flex items-center gap-1.5 text-[9px] font-bold uppercase">
                        <Clock size={10} /> {new Date(mem.created_at).toLocaleDateString()}
                      </div>
                      {mem.relevance_score && (
                        <div className="flex items-center gap-1.5 text-[9px] font-bold text-emerald-400/60 uppercase">
                          <Terminal size={10} /> Score: {Math.round(mem.relevance_score * 100)}%
                        </div>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => deleteMemory(mem.key)}
                    className="text-foreground/20 rounded-lg p-2 opacity-0 transition-all group-hover:opacity-100 hover:bg-red-400/10 hover:text-red-400"
                    title="Forget Memory"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </div>

      {/* Footer / Tip */}
      <div className="border-t border-white/5 bg-white/5 p-4">
        <div className="bg-primary/5 border-primary/10 flex items-start gap-3 rounded-lg border p-3">
          <Info size={14} className="text-primary mt-0.5 shrink-0" />
          <p className="text-foreground/50 text-[10px] leading-relaxed">
            <span className="text-primary/80 font-bold">Auto-Learning:</span> AverQel automatically
            saves project patterns and preferences to this brain to serve you better in future
            sessions.
          </p>
        </div>
        {lifecycle?.retention_policy ? (
          <div className="text-foreground/40 mt-3 text-[10px] leading-relaxed">
            Retention policy: {lifecycle.retention_policy.session_retention_days} day session window
            and {lifecycle.retention_policy.decay_half_life_days} day decay half-life.
            {lifecycle.retention_risk_count > 0 ? (
              <span className="text-amber-300">
                {" "}
                {lifecycle.retention_risk_count} retention risks detected.
              </span>
            ) : null}
            {lifecycle.stale_preview_count > 0 ? (
              <span className="text-amber-300">
                {" "}
                {lifecycle.stale_preview_count} stale memories are ready for review.
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
