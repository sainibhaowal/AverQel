"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Brain, Search, Trash2, Clock, Globe, Info, Database, Activity } from "lucide-react";
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

export default function MemoryPanel() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
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
      const data = await memoryPromise;
      setMemories(Array.isArray(data) ? data : data.results || []);
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
                          <Activity size={10} /> Score: {Math.round(mem.relevance_score * 100)}%
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
      </div>
    </div>
  );
}
